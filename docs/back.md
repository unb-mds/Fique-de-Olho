# Backend

O backend do Fique de Olho é uma API REST desenvolvida com Python e FastAPI. Ele organiza os endpoints de editais, expõe documentação OpenAPI/Swagger e concentra a integração futura com coleta, processamento e persistência.

## Stack

- Python 3.12+
- FastAPI e Uvicorn
- Pydantic Settings
- SQLAlchemy e PostgreSQL
- HTTPX, BeautifulSoup e pdfplumber
- Pytest
- Docker Compose

## Estrutura principal

```text
Back/
├── app/main.py                  # Entrada da API e registro das rotas
├── app/core/                    # Configuração e banco
├── app/modules/editais/         # Endpoints de editais
├── app/modules/scraper/         # Coleta e parsing do portal DEG
└── tests/                       # Testes automatizados
```

## Endpoints atuais

- `GET /health`: verifica a saúde da API.
- `GET /api/v1/editais/`: lista os editais disponíveis.
- `GET /api/v1/editais/{id}`: consulta um edital pelo identificador.
- `/docs`: documentação interativa Swagger.
- `/redoc`: documentação ReDoc.

## Execução

```powershell
cd Back
docker compose up --build
```

Para executar localmente:

```powershell
cd Back
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Estado atual

A API utiliza dados em memória na listagem inicial. A persistência no PostgreSQL e a integração completa do scraper com os endpoints fazem parte da evolução planejada.

[Abrir o README completo do backend no GitHub](https://github.com/unb-mds/Fique-de-Olho/blob/main/Back/README.md)
