# Referência da API REST

A API do **Fique de Olho** expõe endpoints REST sob o prefixo canônico `/api/v1` e gera documentação OpenAPI automaticamente.

| Ambiente | Base URL | Swagger UI |
| :--- | :--- | :--- |
| **Produção (Render)** | `https://fique-de-olho-api.onrender.com` | `/docs` |
| **Desenvolvimento (Local)** | `http://localhost:8000` | `/docs` |

!!! note "Compatibilidade de rotas legadas"
    As rotas do módulo de editais (`/api/v1/editais/...`) também respondem sem o prefixo (`/editais/...`) para compatibilidade com chamadas legadas, mas apenas o prefixo `/api/v1` aparece no schema OpenAPI.

---

## Autenticação

Rotas autenticadas exigem o cabeçalho HTTP:

```http
Authorization: Bearer <access_token>
```

- **Senhas:** armazenadas com hash **Argon2** (`pwdlib[argon2]`), nunca em texto puro.
- **Tokens:** assinados com **JWT HS256**, validade padrão de **24 horas** (`ACCESS_TOKEN_EXPIRE_MINUTES=1440`), contendo apenas `sub` (ID do usuário) e `email`.
- **Google OAuth2:** o cliente envia o `credential` (ID Token emitido pelo Google Identity Services) para `POST /api/v1/auth/google`; o backend valida o token com `google-auth` e devolve um Bearer/JWT próprio da API.

---

## Mapa completo de endpoints

### Infraestrutura, Saúde e Feedback

| Método | Rota | Auth | Descrição |
| :---: | :--- | :---: | :--- |
| `GET` | `/` | Não | Redireciona para `/docs`. |
| `GET` / `HEAD` | `/ping` | Não | Sonda ultraleve de keep-alive (sem acesso ao banco). |
| `GET` | `/health` | Não | Verifica conectividade com PostgreSQL (`SELECT 1`) e status do SendGrid. |
| `POST` | `/api/v1/feedback` | Não | Registra feedback do usuário (`sugestao`, `problema`, `elogio`) no banco e encaminha e-mail para `FEEDBACK_TO_EMAIL` (`fiquedeolho1011@gmail.com`). |

### Editais e Coleta

| Método | Rota | Auth | Descrição |
| :---: | :--- | :---: | :--- |
| `GET` | `/api/v1/editais/` | Não | Lista editais com filtros combináveis e paginação (`skip`/`limit`). |
| `GET` | `/api/v1/editais/stats` | Não | Totais agregados (`total`, `abertos`, `encerrados`). |
| `GET` | `/api/v1/editais/{id}` | Não | Detalhes completos de um edital (inclui `texto_extraido`, `hash_conteudo` e documentos). |
| `POST` | `/api/v1/editais/sync` | Não | Dispara coleta sob demanda de um órgão (`orgao`) ou de todos os portais registrados. |

### Autenticação, Perfil e Histórico de Notificações

| Método | Rota | Auth | Descrição |
| :---: | :--- | :---: | :--- |
| `POST` | `/api/v1/auth/register` | Não | Cria uma nova conta (`201 Created` ou `409 Conflict` se e-mail já existir). |
| `POST` | `/api/v1/auth/login` | Não | Autentica com e-mail e senha e retorna `access_token` + `usuario`. |
| `POST` | `/api/v1/auth/google` | Não | Autentica ou cadastra usuário via Google ID Token. |
| `GET` | `/api/v1/auth/me` | **Bearer** | Retorna o perfil do usuário autenticado. |
| `PATCH` | `/api/v1/auth/me/email-preferences` | **Bearer** | Liga ou desliga o recebimento global de e-mails (`receber_emails`). |
| `GET` | `/api/v1/auth/me/notifications` | **Bearer** | Lista até 50 notificações mais recentes do usuário autenticado. |

### Favoritos e Alertas de Edital

| Método | Rota | Auth | Descrição |
| :---: | :--- | :---: | :--- |
| `GET` | `/api/v1/editais/favoritos` | **Bearer** | Lista os editais salvos na lista pessoal de favoritos. |
| `POST` | `/api/v1/editais/{id}/favoritar` | **Bearer** | Adiciona edital aos favoritos (operação idempotente). |
| `DELETE` | `/api/v1/editais/{id}/favoritar` | **Bearer** | Remove edital dos favoritos. |
| `GET` | `/api/v1/editais/alertas` | **Bearer** | Lista IDs dos editais com alertas por e-mail ativos + flag `email_configurado`. |
| `POST` | `/api/v1/editais/{id}/alertas` | **Bearer** | Ativa alertas por e-mail para o edital e agenda verificação/confirmação em background. |
| `DELETE` | `/api/v1/editais/{id}/alertas` | **Bearer** | Desativa alertas do edital e descarta notificações pendentes dele. |

---

## Contratos detalhados e exemplos

### `GET /api/v1/editais/`

Retorna a listagem paginada ordenada por `data_publicacao DESC NULLS LAST`. A resposta inclui cabeçalho HTTP `Cache-Control: public, max-age=60, stale-while-revalidate=300` e utiliza cache em memória Stale-While-Revalidate (`EDITAIS_CACHE_TTL_SECONDS`, padrão 15 min) invalidado a cada `POST /sync` ou ciclo do scheduler.

| Query param | Tipo | Padrão | Regra |
| :--- | :--- | :---: | :--- |
| `q` ou `busca` | `string` | `null` | Busca case-insensitive (`ILIKE`) em `titulo`, `resumo`, `assunto` e `orgao_emissor`. |
| `ano` | `int` | `null` | Filtra pelo ano de `data_publicacao` (ex.: `2026`). |
| `status` | `aberto` \| `fechado` | `null` | Filtra pela situação calculada do edital (veja [regras de situação](#regras-de-filtragem-e-situacao)). |
| `categoria` | `string` | `null` | Uma das 9 categorias suportadas: `Pós-graduação`, `Graduação`, `Intercâmbio`, `Evento`, `Bolsa`, `Pesquisa`, `Estágio`, `Extensão`, `Vestibular`. |
| `campus` | `string` | `null` | Busca em `campus` e na relação M:N `campi`. |
| `skip` | `int` (>= 0) | `0` | Offset de paginação. |
| `limit` | `int` (1–100) | `24` | Quantidade máxima de itens retornados. |

=== "curl"

    ```bash
    curl "http://localhost:8000/api/v1/editais/?status=aberto&categoria=Gradua%C3%A7%C3%A3o&limit=5"
    ```

=== "Resposta 200 OK"

    ```json
    [
      {
        "id": 1539,
        "titulo": "Edital DEG/UnB Nº 76/2026 – Seleção de Pesquisadores...",
        "status": "aberto",
        "resumo": "O presente Edital tem por objeto selecionar pesquisadores...",
        "descricao": "O presente Edital tem por objeto selecionar pesquisadores...",
        "campus": "Darcy Ribeiro",
        "unidade": "Darcy Ribeiro",
        "categoria": "Graduação",
        "tipo": "Graduação",
        "orgao_emissor": "DEG",
        "orgaoEmissor": "DEG",
        "assunto": null,
        "url_pagina": "https://deg.unb.br/edital-deg-unb-no-76-2026-...",
        "url_pdf": "https://deg.unb.br/wp-content/uploads/edital_deg_unb_76_2026.pdf",
        "urlDocumento": "https://deg.unb.br/wp-content/uploads/edital_deg_unb_76_2026.pdf",
        "data_publicacao": "2026-11-19",
        "dataPublicacao": "2026-11-19T00:00:00+00:00",
        "inicio_inscricao": "2026-11-19",
        "fim_inscricao": "2026-11-30",
        "prazoFinal": "2026-11-30",
        "status_processamento": "processado",
        "vagas": null,
        "valor_bolsa": 8000.0,
        "valor": "R$ 8.000,00",
        "campi": [],
        "tipos": [],
        "documentos": [
          {
            "id": 4719,
            "url_pdf": "https://deg.unb.br/wp-content/uploads/edital_deg_unb_76_2026.pdf",
            "tipo_documento": "original"
          }
        ]
      }
    ]
    ```

!!! info "Performance da listagem"
    Na listagem (`GET /api/v1/editais/`), a coluna pesada `texto_extraido` é adiada via `defer(Edital.texto_extraido)` e os relacionamentos (`documentos`, `campi`, `tipos`) são carregados em lote (`lazy="selectin"`) para evitar consultas N+1. O texto completo do PDF só é enviado em `GET /api/v1/editais/{id}`.

---

### Regras de filtragem e situação

#### Situação (`aberto` vs `fechado`)
A mesma regra unificada (`_condicao_edital_aberto` / `_edital_esta_aberto` em `Back/app/modules/editais/service.py`) governa a listagem, o campo `status` serializado e o endpoint `/stats`:

- **Encerrado (`fechado`):**
  1. Possui documento vinculado do tipo `resultado_final` (inclui *Resultado Final*, *Resultado Definitivo* e *Homologação*); **ou**
  2. Possui `fim_inscricao < hoje`; **ou**
  3. Não possui `fim_inscricao` e tem `status = encerrado`, título indicando encerramento (`resultado final`, `resultado definitivo`, `edital encerrado`, etc.) ou `data_publicacao` com mais de **90 dias** (`SEM_PRAZO_MAX_DIAS_ABERTO = 90`).
- **Aberto (`aberto`):** todos os demais casos (`fim_inscricao >= hoje` sem resultado final, ou sem prazo e publicado nos últimos 90 dias).

#### Separação de categorias críticas
- **`Graduação`:** inclui termos de graduação (`graduação`, `licenciatura`, `bacharelado`, `monitoria`) e o órgão `DEG`, **excluindo explicitamente** qualquer registro que corresponda a Pós-graduação (`pós-graduação`, `mestrado`, `doutorado`, `stricto sensu`, `lato sensu`, `pós-doutorado`, `ppg`, `DPG` e órgãos `PPG*`).
- **`Intercâmbio`:** inclui `intercâmbio`, `mobilidade`, `exchange`, `internacionalização`, `study of the u.s.` e editais do órgão `INT` (exceto editais de estágio da própria INT).

---

### `GET /api/v1/editais/stats` e `GET /health`

=== "GET /api/v1/editais/stats"

    ```json
    {
      "total": 403,
      "abertos": 55,
      "encerrados": 348
    }
    ```

=== "GET /health"

    Retorna `200 OK` quando o banco responde `SELECT 1`, ou `503 Service Unavailable` caso contrário.

    ```json
    {
      "status": "healthy",
      "service": "Fique de Olho API",
      "version": "0.1.0",
      "database": "connected",
      "email_configured": true
    }
    ```

---

### `POST /api/v1/editais/sync`

Dispara a coleta síncrona em um portal específico ou em todos os 33 portais registrados, invalidando o cache ao concluir.

| Query param | Tipo | Padrão | Descrição |
| :--- | :--- | :---: | :--- |
| `orgao` | `string` | `null` | Sigla do órgão em `SCRAPERS_REGISTRY` (ex.: `DEG`, `INT`, `SIGAA`). Se omitido, sincroniza todos. |
| `max_itens` | `int` (1–500) | `30` | Limite máximo de editais processados por portal. |

```bash
curl -X POST "http://localhost:8000/api/v1/editais/sync?orgao=INT&max_itens=10"
```

---

### Autenticação, Favoritos e Alertas

=== "Cadastro e Login"

    ```bash
    # 1. Cadastrar (senha mínima de 8 caracteres)
    curl -X POST http://localhost:8000/api/v1/auth/register \
      -H "Content-Type: application/json" \
      -d '{"nome":"Maria Silva","email":"maria@aluno.unb.br","senha":"senha-segura-123"}'

    # 2. Login para obter o Bearer/JWT
    curl -X POST http://localhost:8000/api/v1/auth/login \
      -H "Content-Type: application/json" \
      -d '{"email":"maria@aluno.unb.br","senha":"senha-segura-123"}'
    ```

=== "Favoritar e Ativar Alerta"

    ```bash
    # Salvar na lista pessoal de favoritos (não dispara e-mails)
    curl -X POST http://localhost:8000/api/v1/editais/1539/favoritar \
      -H "Authorization: Bearer <TOKEN>"

    # Ativar alertas por e-mail para atualizações e prazos (3d, 1d e 0d)
    curl -X POST http://localhost:8000/api/v1/editais/1539/alertas \
      -H "Authorization: Bearer <TOKEN>"

    # Consultar histórico de notificações do usuário
    curl http://localhost:8000/api/v1/auth/me/notifications \
      -H "Authorization: Bearer <TOKEN>"
    ```

---

## Códigos HTTP mais comuns

| Status | Quando ocorre |
| :---: | :--- |
| `200 OK` | Consulta, login, sync ou toggle de favorito/alerta concluído. |
| `201 Created` | Usuário cadastrado com sucesso em `POST /api/v1/auth/register`. |
| `400 Bad Request` | Sigla de órgão inexistente em `POST /api/v1/editais/sync`. |
| `401 Unauthorized` | Credenciais inválidas, token JWT ausente/expirado ou ID Token Google inválido. |
| `404 Not Found` | Edital inexistente ou ID não numérico. |
| `409 Conflict` | Tentativa de cadastrar um e-mail já existente. |
| `422 Unprocessable Entity` | Payload ou query param fora da validação Pydantic (ex.: senha < 8 chars, `limit > 100`). |
| `503 Service Unavailable` | Banco de dados indisponível no `/health`. |
