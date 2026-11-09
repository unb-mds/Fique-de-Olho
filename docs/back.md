# Backend

O backend do Fique de Olho é uma API REST desenvolvida com Python e FastAPI. Ele organiza os endpoints de editais, expõe documentação OpenAPI/Swagger e concentra a integração com coleta, processamento e persistência.

## Stack

- Python 3.12+
- FastAPI e Uvicorn
- Pydantic Settings
- SQLAlchemy e PostgreSQL
- Alembic (gerenciamento de migrações)
- HTTPX, BeautifulSoup e pdfplumber
- Pytest
- Docker e Docker Compose
- **Render (Web Services)** para hospedagem da API em container (conforme [ADR 0004](adr/0004-plataformas-de-deploy.md))
- **Neon / Supabase** como provedor de banco de dados PostgreSQL na nuvem (conforme [ADR 0004](adr/0004-plataformas-de-deploy.md))

## Estrutura principal

```text
Back/
├── app/main.py                  # Entrada da API e registro das rotas
├── app/core/                    # Configuração e banco
├── app/modules/editais/         # Endpoints de editais
├── app/modules/scraper/         # Coleta e parsing dos portais da ADR 0004
└── tests/                       # Testes automatizados
```

## Endpoints atuais

- `GET /health`: verifica a saúde da API e conectividade com o banco.
- `GET /api/v1/editais/`: lista os editais disponíveis com suporte a filtros.
- `GET /api/v1/editais/{id}`: consulta um edital pelo identificador.
- `/docs`: documentação interativa Swagger.
- `/redoc`: documentação ReDoc.

## Execução local

Com Docker Compose (recomendado):

```powershell
docker compose up --build -d
```

Para executar o backend localmente com Python:

```powershell
cd Back
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Hospedagem e Deploy em Produção

Conforme estabelecido na [ADR 0004](adr/0004-plataformas-de-deploy.md):
- **API FastAPI:** Implantada como Web Service no **Render**, executando diretamente o `Back/Dockerfile` a partir da branch `main` com HTTPS automático.
- **Banco de Dados:** Instância gerenciada de PostgreSQL no **Neon** (com suporte a *Database Branching* e serverless) ou **Supabase**.
- **Variáveis de Ambiente:** `DATABASE_URL` e segredos configurados no painel do Render para apontar com segurança para a instância na nuvem.

[Abrir o README completo do backend no GitHub](https://github.com/unb-mds/Fique-de-Olho/blob/main/Back/README.md)
