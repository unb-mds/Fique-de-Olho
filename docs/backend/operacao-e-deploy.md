# Operação, Notificações & Deploy

Este guia cobre o subsistema de alertas por e-mail, o deploy em produção (Render + Neon), a execução da suíte de testes e a resolução dos problemas mais comuns.

---

## Sistema de Notificações e Alertas por E-mail

O envio de e-mails é **desacoplado dos Favoritos**: o estudante precisa ativar o alerta no edital (`POST /api/v1/editais/{id}/alertas`) e manter a preferência global `receber_emails=true` (`PATCH /api/v1/auth/me/email-preferences`).

### Gatilhos e deduplicação
- **Notificação de atualização (`edital_atualizado`):** gerada quando o `upsert_edital` detecta mudança em `hash_conteudo` de um edital com alerta ativo. A `chave_evento` é o próprio `hash_conteudo`.
- **Notificação de encerramento (`prazo_encerrando`):** gerada pelo scheduler (`NOTIFICATION_SCHEDULER_INTERVAL_SECONDS=3600`) usando a data no **fuso de Brasília (UTC-3)** quando faltam exatamente **3 dias**, **1 dia** ou **0 dias** para `fim_inscricao`. A `chave_evento` combina a data de vencimento + antecedência (`YYYY-MM-DD:d3`, `:d1`, `:d0`).
- **Garantia de não duplicação:** a constraint `uq_notificacao_evento (usuario_id, edital_id, tipo, chave_evento)` garante no banco que o mesmo aviso nunca seja enviado duas vezes.
- **Envio via SendGrid:** se `SENDGRID_API_KEY` e `SENDGRID_FROM_EMAIL` não estiverem configurados, o sistema registra um aviso no startup e mantém a API totalmente funcional sem tentar disparar e-mails externos.

---

## Deploy em Produção (Render + Neon)

A infraestrutura de produção é declarada em `render.yaml` e detalhada na [ADR 0004](../adr/0004-plataformas-de-deploy.md):

| Componente | Configuração em produção |
| :--- | :--- |
| **Web Service (Render)** | `runtime: docker`, `rootDir: Back`, `dockerfilePath: Dockerfile`, `plan: free` (512 MB RAM), região `ohio`. |
| **Inicialização do container** | `alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}` |
| **Healthcheck & Keep-Alive** | `healthCheckPath: /ping` (ultraleve, sem I/O de banco; ver [Guia Keep-Alive](../Estudos/guia_keep_awake_uptimerobot_e_ping.md)). |
| **Banco PostgreSQL (Neon)** | PostgreSQL 16 serverless (`sa-east-1`), pool reciclado a cada `300s` com `pool_pre_ping=True`. |

### Checklist de variáveis obrigatórias no painel do Render
1. `DATABASE_URL` — string de conexão do Neon (com `?sslmode=require`).
2. `JWT_SECRET_KEY` — segredo forte gerado no Render (`generateValue: true`).
3. `GOOGLE_CLIENT_ID` — para habilitar login com Google.
4. `SENDGRID_API_KEY` e `SENDGRID_FROM_EMAIL` — para ativar o envio real de alertas por e-mail.
5. `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-3.5-flash-lite` e `GEMINI_FALLBACK_MODEL=gemini-flash-lite-latest` — para ativar a Camada 2 de IA.

!!! warning "Hibernação no plano Free do Render"
    Sem um monitor externo batendo em `/ping` (ex.: UptimeRobot), o container hiberna após ~15 minutos sem tráfego, reiniciando o temporizador interno do scheduler de coleta (`SCRAPER_SCHEDULER_INTERVAL_HOURS=12`). Para forçar uma atualização imediata após deploy, chame `POST /api/v1/editais/sync` pelo Swagger.

---

## Executando os testes (`pytest`)

A suíte em `Back/tests/` usa SQLite em memória (via `conftest.py`, com `GEMINI_API_KEY=""` forçado para nunca chamar a API real do Gemini em testes) e mocks HTTP para scrapers e LLM.

```powershell
# A partir da raiz do repositório (com o .venv ativo)
pytest Back/tests -m "not live"

# Rodar apenas os testes de filtros, scrapers e Camada 2 (Gemini)
pytest Back/tests/test_editais_filtros.py Back/tests/test_novos_scrapers.py Back/tests/test_summarizer.py -v
```

!!! note "Testes marcados com `@pytest.mark.live`"
    Alguns testes de scrapers fazem requisições reais aos portais da UnB e são marcados com `@pytest.mark.live`. Use `-m "not live"` em CI ou ambientes offline.

---

## Troubleshooting

??? question "Docker Compose falha com `Bind for 0.0.0.0:5432 failed` ou API não resolve o host `db`"
    Normalmente há outro PostgreSQL (ou containers do `Back/docker-compose.yml` antigo, como `back-db-1` / `back-api-1`) ocupando as portas `5432` e `8000`.

    ```powershell
    # 1. Veja quem está ocupando as portas
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

    # 2. Pare containers duplicados e recrie a stack da raiz (sem -v para preservar dados)
    docker stop back-api-1 back-db-1
    docker compose up -d --force-recreate
    ```

??? question "Logs exibem `GEMINI_API_KEY não configurada` mesmo após editar `Back/.env`"
    O `--reload` do Uvicorn monitora apenas arquivos `.py`, não o `.env`. Salve `Back/.env` (verificando se a variável está escrita exatamente como `GEMINI_API_KEY=...`) e reinicie o container:

    ```powershell
    docker compose restart api
    ```

??? question "Gemini retorna `HTTP 404` (`is no longer available to new users`) ou `HTTP 429`"
    Chaves novas do Google AI Studio não aceitam modelos aposentados (`gemini-1.5-flash` ou `gemini-2.5-flash-lite`) e o alias `gemini-flash-latest` possui cota bem mais restrita no Free Tier. Configure:

    ```env
    GEMINI_MODEL=gemini-3.5-flash-lite
    GEMINI_FALLBACK_MODEL=gemini-flash-lite-latest
    ```

    No backfill em lote, use `--sleep 2.0` para respeitar o limite de requisições por minuto (RPM).

??? question "Gemini retorna `HTTP 503 Service Unavailable` pontualmente"
    Oscilação momentânea de sobrecarga nos servidores do Google no Free Tier. O `summarizer.py` faz 1 retry automático e, se persistir, aplica fallback transparente para a Camada 1 sem quebrar a coleta.

??? question "Erro `_ssl.c: The handshake operation timed out` ao baixar PDF da UnB"
    Lentidão pontual dos servidores da UnB (ex.: `deg.unb.br`). O pipeline isola o erro por edital (`status_processamento="erro"` ou fallback com metadados do HTML) e tenta novamente no próximo ciclo de coleta.
