# Fique de Olho - Backend (FastAPI)

Este é o backend da plataforma **Fique de Olho (UnB Editais)**, desenvolvido em Python utilizando o framework **FastAPI** e banco de dados relacional **PostgreSQL**, estruturado segundo uma **arquitetura modular orientada a domínios de negócio**.

---

## 🏗️ Arquitetura Modular

A aplicação organiza o código por **contextos e módulos de negócio** (em vez de agrupar tudo em pastas genéricas por tipo de arquivo):

```text
Back/
├── app/
│   ├── main.py                  # Ponto de entrada do FastAPI (carrega middlewares e rotas)
│   │
│   ├── core/                    # Módulo transversal / infraestrutura compartilhada
│   │   ├── config.py            # Variáveis de ambiente com Pydantic Settings
│   │   ├── database.py          # Conexão SQLAlchemy com PostgreSQL
│   │   └── security.py          # Utilitários de autenticação e tokens (futuro)
│   │
│   └── modules/                 # MÓDULOS DE NEGÓCIO INDEPENDENTES
│       ├── editais/             # Descoberta, filtros, busca e detalhamento de editais
│       ├── scraper/             # Ingestão e extração de PDFs (BeautifulSoup + pdfplumber)
│       ├── usuarios/            # Autenticação, login e perfil do estudante
│       └── favoritos/           # Acompanhamento de editais e notificações de prazo
│
├── tests/                       # Testes automatizados (pytest)
├── Dockerfile                   # Imagem do container da API
├── docker-compose.yml           # Orquestração da API e do banco PostgreSQL
└── requirements.txt             # Dependências Python do projeto
```

---

## 🚀 Como Executar

### Opção 1: Via Docker Compose (Recomendado)

O Docker Compose sobe a aplicação FastAPI e o banco de dados PostgreSQL automaticamente configurados:

```bash
# Na pasta Back/
docker compose up --build
```

A API estará disponível em:
* **Endpoints:** [http://localhost:8000](http://localhost:8000)
* **Documentação Swagger (OpenAPI):** [http://localhost:8000/docs](http://localhost:8000/docs)
* **Documentação ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
* **Healthcheck:** [http://localhost:8000/health](http://localhost:8000/health)

---

### Opção 2: Localmente com Ambiente Virtual Python

#### 1. Criar e ativar o ambiente virtual:
```powershell
# No Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### 2. Instalar as dependências:
```powershell
pip install -r requirements.txt
```

#### 3. Configurar as variáveis de ambiente:
Copie o arquivo `.env.example` para `.env`:
```powershell
Copy-Item .env.example .env
```

#### 4. Iniciar o servidor de desenvolvimento:
```powershell
uvicorn app.main:app --reload --port 8000
```

---

## 🧪 Como Rodar os Testes

Para executar a suíte de testes com o `pytest`:

```bash
pytest -v
```

---

## 📦 Como Adicionar uma Nova Feature/Módulo

Ao implementar uma nova funcionalidade (ex: `notificacoes`), siga o padrão modular:
1. Crie uma pasta dentro de `app/modules/minha_feature/`.
2. Adicione os arquivos conforme necessário:
   - `router.py`: endpoints HTTP da feature.
   - `schemas.py`: modelos Pydantic de entrada e saída.
   - `models.py`: tabelas SQLAlchemy da feature (se houver).
   - `service.py`: regras de negócio e consultas ao banco.
3. Registre o roteador em `app/main.py`:
   ```python
   from app.modules.minha_feature.router import router as minha_feature_router

   app.include_router(minha_feature_router, prefix=settings.API_V1_STR)
   ```
