# Fique de Olho — Editais UnB

Plataforma web do grupo **G4** de Métodos de Desenvolvimento de Software (UnB 2026/2) para centralizar, estruturar, filtrar e notificar a comunidade universitária sobre editais e oportunidades da Universidade de Brasília.

---

## O problema e a solução

Editais da UnB ficam espalhados em dezenas de páginas institucionais, PDFs extensos e links do SEI. Estudantes precisam consultar múltiplas fontes, interpretar cronogramas e conferir retificações para não perder prazos de bolsas, estágios, intercâmbios, monitorias e processos seletivos.

O **Fique de Olho** resolve isso com:
- **Coleta automatizada em 33 portais da UnB** (DEG, DPG, INT, DEX, DPI, DAC, SIGAA, Cebraspe, FINATEC, FUP, HUB, Ocean, entre outros).
- **Enriquecimento híbrido de PDFs:** extração determinística local (**Camada 1**, `pdfplumber` + regex) com fallback opcional em IA (**Camada 2**, Google Gemini `3.5-flash-lite`) para padronizar títulos, resumos, prazos de inscrição, vagas e bolsas.
- **Busca e filtros precisos:** filtros combináveis por situação (`aberto`/`fechado`), **campus** (com aliases como `FGA`/`Gama`, `FUP`/`Planaltina`, `FCE`/`Ceilândia`), **ano**, 9 categorias (`Graduação`, `Pós-graduação`, `Intercâmbio`, `Bolsa`, `Pesquisa`, `Estágio`, `Extensão`, `Evento`, `Vestibular`) e busca textual, com cache Stale-While-Revalidate.
- **Autenticação, Favoritos, Alertas e Suporte:** login com e-mail/senha (Argon2 + JWT) ou **Google OAuth2**, lista pessoal de favoritos, ativação explícita de alertas por e-mail via **SendGrid** (3d, 1d e 0d em UTC-3) e **Central de Ajuda (`?`) com formulário de feedback** encaminhado para a equipe.

---

## 🚀 Acesso Rápido e Ambientes

| Serviço | Plataforma | Link | Descrição |
| :--- | :---: | :--- | :--- |
| **Aplicação Web (Frontend)** | Vercel | [fique-de-olho.vercel.app](https://fique-de-olho.vercel.app) | Interface React 18 + TypeScript + Vite |
| **API REST & Swagger** | Render | [fique-de-olho-api.onrender.com/docs](https://fique-de-olho-api.onrender.com/docs) | Documentação interativa OpenAPI (FastAPI) |
| **Healthcheck da API** | Render | [fique-de-olho-api.onrender.com/health](https://fique-de-olho-api.onrender.com/health) | Status da API, banco PostgreSQL e SendGrid |
| **Keep-Alive** | Render | [fique-de-olho-api.onrender.com/ping](https://fique-de-olho-api.onrender.com/ping) | Sonda leve (sem I/O de banco) |
| **Banco de Dados** | Neon | AWS São Paulo (`sa-east-1`) | PostgreSQL 16 Serverless (14 tabelas via Alembic) |
| **Documentação Técnica** | GitHub Pages | [unb-mds.github.io/G4-2026-2/](https://unb-mds.github.io/G4-2026-2/) | Portal MkDocs Material |

---

## 📚 Documentação Técnica

### Backend, API e Banco de Dados
- [Visão Geral & Quickstart do Backend](docs/backend/index.md)
- [Referência da API REST (19 endpoints, auth, filtros, feedback e exemplos)](docs/backend/api.md)
- [Banco de Dados & Migrations (diagrama ER, 14 tabelas e Alembic)](docs/backend/banco-de-dados.md)
- [Pipeline de Coleta, PDF & IA (33 portais, Camada 1 + Gemini e backfill)](docs/backend/coleta-e-ia.md)
- [Operação, Notificações & Deploy (SendGrid, Render/Neon, testes e troubleshooting)](docs/backend/operacao-e-deploy.md)

### Arquitetura, Domínio e Produto
- [Glossário de Domínio (`CONTEXT.md`)](CONTEXT.md)
- [Arquitetura do Sistema](docs/Arquitetura.md)
- [Frontend](docs/front.md)
- [Decisões Arquiteturais (ADRs 0001–0006)](docs/adr/)
- [Requisitos, Personas e Backlog](docs/Requisitos/)
- [Board de Planejamento (Figma)](https://www.figma.com/board/Sw1R44AAXzZrW5eBolJybw/Template-MDS--c%C3%B3pia-limpa---c%C3%B3pia-?node-id=1-291) · [Protótipo de Alta Fidelidade](https://www.figma.com/make/yqHT0b3mk0T3EkHD2aUgns/UnB-Editais-Aggregator-Site?fullscreen=1)

---

## ⚡ Como executar localmente

### Pré-requisitos
- **Docker Compose (recomendado):** Git, Docker Desktop e Docker Compose v2.
- **Execução local sem container:** Python 3.12+, Node.js 18+ e PostgreSQL 16.

### Opção A — Stack completa com Docker Compose (recomendado)

A partir da **raiz do repositório**, o `docker-compose.yml` sobe os 3 serviços (**Frontend**, **API** e **PostgreSQL**) e executa `alembic upgrade head` automaticamente:

```powershell
docker compose up --build -d
docker compose ps
```

Serviços locais:
- **Frontend:** [http://localhost:5173](http://localhost:5173)
- **API:** [http://localhost:8000](http://localhost:8000) · **Swagger:** [http://localhost:8000/docs](http://localhost:8000/docs) · **Health:** [http://localhost:8000/health](http://localhost:8000/health)
- **PostgreSQL:** `localhost:5432`

Comandos úteis:

```powershell
# Ver logs da API e do banco
docker compose logs -f api db

# Reiniciar a API após alterar Back/.env (ex.: GEMINI_API_KEY ou SENDGRID_API_KEY)
docker compose restart api

# Parar preservando os dados do banco local
docker compose down
```

### Opção B — Backend e Frontend fora do Docker (banco no Docker)

1. Suba apenas o PostgreSQL na raiz:
   ```powershell
   docker compose up -d db
   ```
2. Em um terminal, inicie o **Backend**:
   ```powershell
   cd Back
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   alembic upgrade head
   uvicorn app.main:app --reload --port 8000
   ```
3. Em outro terminal, inicie o **Frontend**:
   ```powershell
   cd Front
   npm ci
   npm run dev
   ```

> **Variáveis opcionais no `Back/.env`:** para testar a Camada 2 de IA localmente sem custo (Free Tier do Google AI Studio), defina `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-3.5-flash-lite` e `GEMINI_FALLBACK_MODEL=gemini-flash-lite-latest`.

### Visualizar a documentação (MkDocs) localmente

```powershell
# Usa a porta 8001 para não conflitar com a API FastAPI na porta 8000
mkdocs serve -a 127.0.0.1:8001
```

---

## 🏗️ Arquitetura resumida

```text
Front (React 18 + TypeScript + Vite) ──────────────► Vercel
                  │ HTTP / JSON (Bearer JWT)
Back (FastAPI + SQLAlchemy + Alembic) ─────────────► Render (Docker)
   ├── modules/editais      (filtros SQL + cache SWR)
   ├── modules/usuarios     (Argon2 + JWT + Google OAuth2)
   ├── modules/favoritos    (lista pessoal)
   ├── modules/feedback     (RF07 -> tabela feedbacks + e-mail SendGrid)
   ├── modules/notificacoes (alertas_edital + SendGrid)
   └── modules/scraper      (33 portais + pdfplumber + Gemini 3.5 Flash-Lite)
                  │
PostgreSQL 16 (14 tabelas) ────────────────────────► Neon Serverless
```

Decisões registradas em:
- [ADR 0001 — Stack do Backend](docs/adr/0001-stack-backend.md)
- [ADR 0002 — Stack do Frontend](docs/adr/0002-stack-frontend.md)
- [ADR 0003 — Schema inicial do banco de dados](docs/adr/0003-database-schema.md)
- [ADR 0004 — Plataformas de Hospedagem e Deploy](docs/adr/0004-plataformas-de-deploy.md)
- [ADR 0005 — Pipeline Híbrido (Camada 1 + Gemini)](docs/adr/0005-enriquecimento-hibrido-camada1-gemini.md)
- [ADR 0006 — Evolução do Schema, Alertas e Notificações](docs/adr/0006-evolucao-schema-catalogos-alertas-notificacoes.md)

---

## 🧪 Qualidade e testes

```powershell
# Backend (unitários + integração sem chamadas externas)
pytest Back/tests -m "not live"

# Backfill local de títulos, resumos e datas (dry-run)
docker exec fique-de-olho-api python -m app.modules.scraper.backfill_titles_summaries --limit 5 --sleep 2.0

# Frontend
cd Front
npm run lint
npm run build
```

Para problemas comuns (portas `5432`/`8000` ocupadas, `.env` no Docker, `404`/`429`/`503` do Gemini), consulte o [Guia de Troubleshooting](docs/backend/operacao-e-deploy.md#troubleshooting).

---

## 👥 Equipe

- Arthur Amaral da Silva — `24200514`
- Eduardo Henrique Coutinho Gurjão — `222006679`
- Felippe Ong Su — `242028664`
- Isac Silva Marques — `242023846`
- Ryan Kelvyn Fernandes de Carvalho — `241025560`
- Wendell Derick Mathias Santana dos Santos — `241025739`
