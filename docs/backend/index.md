# Backend — Visão Geral e Quickstart

O backend do **Fique de Olho** é uma API REST em **Python 3.12 + FastAPI** que concentra a coleta periódica dos portais da UnB, a extração de metadados de PDFs (heurística local + fallback opcional em IA), a persistência relacional em **PostgreSQL 16**, a autenticação de usuários e o disparo de alertas por e-mail.

---

## Navegue pela documentação do Backend

<div class="radar-grid" markdown>

<div class="radar-card" markdown>
<span class="radar-card__icon">🔌</span>
### Referência da API REST
Todos os endpoints de editais, autenticação (JWT e Google OAuth), favoritos, alertas, notificações e saúde, com exemplos `curl` e JSON.

[Abrir referência da API →](api.md)
</div>

<div class="radar-card" markdown>
<span class="radar-card__icon">🗄️</span>
### Banco de Dados & Migrations
Diagrama ER das 14 tabelas, enums, constraints, índices, pool do Neon e fluxo de migrações com Alembic.

[Explorar banco de dados →](banco-de-dados.md)
</div>

<div class="radar-card" markdown>
<span class="radar-card__icon">🤖</span>
### Pipeline de Coleta, PDF & IA
Os 33 portais da UnB, extração com `pdfplumber`, enriquecimento híbrido (Camada 1 + Gemini) e script de backfill.

[Entender a coleta e IA →](coleta-e-ia.md)
</div>

<div class="radar-card" markdown>
<span class="radar-card__icon">🚀</span>
### Operação, Alertas & Deploy
Notificações SendGrid, deploy no Render + Neon, testes com `pytest` e guia de troubleshooting.

[Ver guia operacional →](operacao-e-deploy.md)
</div>

</div>

---

## Arquitetura de módulos

```mermaid
flowchart LR
    Client["Frontend React / Clientes HTTP"] --> FastAPI["FastAPI (Back/app/main.py)"]
    FastAPI --> Editais["modules/editais\nListagem, filtros, cache SWR"]
    FastAPI --> Usuarios["modules/usuarios\nJWT Argon2 + Google OAuth"]
    FastAPI --> Favoritos["modules/favoritos\nLista pessoal"]
    FastAPI --> Notif["modules/notificacoes\nAlertas + SendGrid"]
    FastAPI --> Scraper["modules/scraper\n33 portais + PDF + Gemini"]

    Editais --> DB[("PostgreSQL 16\nSQLAlchemy + Alembic")]
    Usuarios --> DB
    Favoritos --> DB
    Notif --> DB
    Scraper --> DB
    Notif --> SendGrid["SendGrid API"]
    Scraper --> Portais["Portais UnB / PDFs"]
    Scraper -. "fallback opcional" .-> Gemini["Google Gemini API"]
```

### Estrutura de diretórios

```text
Back/
├── Dockerfile                        # Container Python 3.12-slim (alembic upgrade head + uvicorn)
├── requirements.txt                  # Dependências da API, scrapers e testes
├── alembic.ini                       # Configuração do Alembic
├── migrations/                       # Histórico versionado de migrations SQLAlchemy/Alembic
├── app/
│   ├── main.py                       # App FastAPI, CORS, GZip, lifespan (schedulers), /ping e /health
│   ├── core/
│   │   ├── config.py                 # Settings carregadas via Pydantic Settings (.env / ambiente)
│   │   └── database.py               # Engine, SessionLocal, Base e os 13 modelos ORM
│   └── modules/
│       ├── editais/                  # Rotas, filtros SQL, inferência de categoria e cache SWR
│       ├── usuarios/                 # Cadastro, login JWT (Argon2), Google OAuth2 e perfil
│       ├── favoritos/                # Favoritar/desfavoritar e listagem pessoal
│       ├── feedback/                 # Recebimento de sugestões/problemas (RF07) e envio por e-mail
│       ├── notificacoes/             # Alertas por edital, deduplicação, scheduler e envio SendGrid
│       └── scraper/                  # 33 scrapers, pdf.py, parser.py, summarizer.py, pipeline.py e backfill
└── tests/                            # Suíte Pytest (unitários, integração e mocks da Camada 2)
```

---

## Quickstart (rodando localmente)

=== "Docker Compose (recomendado)"

    Sobe **PostgreSQL 16 + API FastAPI + Frontend React** já conectados na mesma rede e aplica as migrations do Alembic automaticamente.

    ```powershell
    # Na raiz do repositório (G4-2026-2/)
    docker compose up --build -d
    ```

    Verifique se a API respondeu:

    ```powershell
    curl http://localhost:8000/health
    ```

    - **API:** `http://localhost:8000`
    - **Swagger interativo:** `http://localhost:8000/docs`
    - **ReDoc:** `http://localhost:8000/redoc`
    - **Frontend:** `http://localhost:5173`

    !!! tip "Recarregamento de variáveis de ambiente"
        O `uvicorn --reload` recarrega alterações em arquivos `.py`, mas **não** recarrega mudanças em `Back/.env`. Sempre que editar `Back/.env`, rode `docker compose restart api`.

=== "Python local (venv)"

    Requer Python 3.12+ e uma instância PostgreSQL acessível em `DATABASE_URL` (local ou Neon).

    ```powershell
    cd Back
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt

    # Copie o arquivo de exemplo e ajuste DATABASE_URL e segredos
    Copy-Item .env.example .env

    # Aplique as migrations antes de iniciar a API
    alembic upgrade head

    # Inicie o servidor de desenvolvimento
    uvicorn app.main:app --reload --port 8000
    ```

---

## Variáveis de ambiente

Todas as configurações são lidas em `Back/app/core/config.py` (arquivo `Back/.env` ou variáveis injetadas no Render/Docker). Consulte o template em `Back/.env.example`.

| Variável | Padrão | Obrigatória | Finalidade |
| :--- | :--- | :---: | :--- |
| `DATABASE_URL` | `postgresql+psycopg2://fique_de_olho:...@localhost:5432/fique_de_olho` | Sim | Conexão PostgreSQL (converte `postgres://` e `postgresql://` automaticamente para `postgresql+psycopg2://`). |
| `JWT_SECRET_KEY` | valor inseguro de dev | **Sim em prod** | Chave HMAC-SHA256 para assinar tokens JWT. |
| `JWT_ALGORITHM` | `HS256` | Não | Algoritmo de assinatura do JWT. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24h) | Não | Validade do token Bearer de acesso. |
| `GOOGLE_CLIENT_ID` | `""` | Se usar OAuth | Client ID do Google Identity Services para validar ID Tokens em `/api/v1/auth/google`. |
| `SENDGRID_API_KEY` | `""` | Se enviar e-mail | Chave da API SendGrid. Sem ela, notificações ficam registradas sem envio real. |
| `SENDGRID_FROM_EMAIL` | `""` | Se enviar e-mail | Endereço remetente verificado no SendGrid. |
| `FEEDBACK_TO_EMAIL` | `fiquedeolho1011@gmail.com` | Não | E-mail de destino dos relatos enviados em `POST /api/v1/feedback`. |
| `NOTIFICATION_SCHEDULER_ENABLED` | `true` | Não | Liga/desliga o agendador em segundo plano de alertas por e-mail. |
| `NOTIFICATION_SCHEDULER_INTERVAL_SECONDS` | `3600` | Não | Intervalo (s) do ciclo de notificações (atraso inicial de 30s após boot). |
| `SCRAPER_SCHEDULER_ENABLED` | `true` | Não | Liga/desliga a coleta periódica automática de todos os portais. |
| `SCRAPER_SCHEDULER_INTERVAL_HOURS` | `12` | Não | Intervalo (h) entre ciclos automáticos de coleta. |
| `SCRAPER_SCHEDULER_RUN_ON_STARTUP` | `false` | Não | Se `true`, dispara um ciclo de coleta logo ao subir a API. |
| `SCRAPER_SCHEDULER_FETCH_DOCS` | `true` | Não | Busca documentos anexos (PDFs/SEI) durante a coleta agendada. |
| `SCRAPER_SCHEDULER_PDF_ENRICHMENT` | `true` | Não | Habilita extração de PDF e fallback LLM durante a coleta agendada. |
| `EDITAIS_CACHE_TTL_SECONDS` | `900` (15 min) | Não | TTL do cache em memória Stale-While-Revalidate das listagens e `/stats`. |
| `GEMINI_API_KEY` | `""` | Não | Chave do Google AI Studio para ativar a Camada 2 (LLM). Opcional. |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Não | Modelo primário da Camada 2. |
| `GEMINI_FALLBACK_MODEL` | `gemini-flash-lite-latest` | Não | Modelo de fallback acionado automaticamente se o primário retornar HTTP `404`. |
| `GEMINI_TIMEOUT_SECONDS` | `15.0` | Não | Timeout HTTP (s) de cada requisição ao Gemini. |
| `GEMINI_RETRY_DELAY_SECONDS` | `2.0` | Não | Atraso base (s) antes de 1 retry automático em `429`, `502`, `503` ou `504`. |

---

## Decisões arquiteturais relacionadas

- [ADR 0001 — Stack do Backend](../adr/0001-stack-backend.md)
- [ADR 0002 — PostgreSQL com Docker](../adr/0002-postgresql-com-docker.md)
- [ADR 0003 — Schema inicial do banco de dados](../adr/0003-database-schema.md)
- [ADR 0004 — Plataformas de Hospedagem e Deploy](../adr/0004-plataformas-de-deploy.md)
- [ADR 0005 — Pipeline Híbrido de Enriquecimento (Camada 1 + Gemini)](../adr/0005-enriquecimento-hibrido-camada1-gemini.md)
- [ADR 0006 — Evolução do Schema: Catálogos M:N, Alertas e Notificações Idempotentes](../adr/0006-evolucao-schema-catalogos-alertas-notificacoes.md)
