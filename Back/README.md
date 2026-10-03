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
│       ├── scraper/             # Coleta de listagens e extração de PDFs
│       ├── usuarios/            # Autenticação, login e perfil do estudante
│       └── favoritos/           # Acompanhamento de editais e notificações de prazo
│
├── tests/                       # Testes automatizados (pytest)
├── Dockerfile                   # Imagem do container da API
├── ../docker-compose.yml        # Orquestração da API e do banco PostgreSQL
└── requirements.txt             # Dependências Python do projeto
```

---

## 🚀 Como Executar

### Opção 1: Via Docker Compose (Recomendado)

O Docker Compose sobe a aplicação FastAPI e o banco de dados PostgreSQL automaticamente configurados:

```bash
# Na raiz do repositório
docker compose up --build
```

A API estará disponível em:
* **Endpoints:** [http://localhost:8000](http://localhost:8000)
* **Documentação Swagger (OpenAPI):** [http://localhost:8000/docs](http://localhost:8000/docs)
* **Documentação ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
* **Healthcheck:** [http://localhost:8000/health](http://localhost:8000/health) *(Valida conexão em tempo real com o PostgreSQL)*
* **Listagem de Editais:** [http://localhost:8000/api/v1/editais/](http://localhost:8000/api/v1/editais/) *(Filtros: `?status=aberto&categoria=Monitoria&campus=Darcy+Ribeiro&busca=termo`)*
* **Detalhe de Edital:** `GET /api/v1/editais/{id}` ou `GET /editais/{id}`
* **Sincronização com DEG:** `POST /api/v1/editais/sync?max_itens=20` *(Dispara raspagem e persistência no PostgreSQL)*

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

#### 3. Configurar as variáveis de ambiente (opcional):
O backend usa por padrão o PostgreSQL local do projeto. Para personalizar as configurações, copie `.env.example` para `.env`:
```powershell
Copy-Item .env.example .env
```

Antes de iniciar a API localmente, suba o banco a partir da raiz do repositório:

```bash
docker compose up -d db
```

#### 4. Iniciar o servidor de desenvolvimento:
```powershell
uvicorn app.main:app --reload --port 8000
```

---

## 🧪 Como Rodar os Testes

A suíte de testes automatizados cobre a conectividade com o banco de dados PostgreSQL, a filtragem e serialização de editais e a raspagem/parsing de documentos do DEG.

### Opção 1: Via Docker (Recomendado)
Com os containers em execução a partir da raiz do repositório:

```bash
docker exec -it fique-de-olho-api pytest -v
```

### Opção 2: Localmente com Ambiente Virtual
Na pasta `Back/`, com o ambiente virtual ativado:

```powershell
pytest -v
```

---

### Testando o scraper do portal DEG

O scraper de nível 1 está em `app/modules/scraper/deg.py`. Ele acessa as páginas de editais do portal do DEG, usando `httpx` para a requisição e `BeautifulSoup` para extrair:

- `titulo`: título completo do edital;
- `link`: endereço da página individual do edital;
- `data_publicacao`: data exibida na listagem.

Ele aceita a página atual ou uma página de ano anterior:

```text
https://deg.unb.br/editais/
https://deg.unb.br/editais-2025/
https://deg.unb.br/editais-2024/
```

#### 1. Rodar os testes automatizados do scraper

Na pasta `Back/`, com o ambiente virtual ativado:

```powershell
pytest tests/test_scraper.py -v
```

Se o ambiente virtual não estiver ativado, execute pelo caminho direto do Python no Windows:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_scraper.py -v
```

Esses testes não dependem da internet. Eles simulam o HTML do portal para 2026 e 2025 e verificam também se uma falha de rede retorna uma lista vazia sem interromper a execução.

#### 2. Consultar o portal real e persistência no banco

Para executar o scraper contra as páginas reais do DEG:

```powershell
python -c "from app.modules.scraper.deg import fetch_editais; atual = fetch_editais(); anterior = fetch_editais(2025); print(f'2026: {len(atual)} editais'); print(atual[0] if atual else 'nenhum'); print(f'2025: {len(anterior)} editais'); print(anterior[0] if anterior else 'nenhum')"
```

O resultado deve mostrar a quantidade encontrada e o primeiro edital de cada ano. A função `fetch_editais()` retorna `[]` quando ocorre uma falha de comunicação com o portal.

> **Persistência no PostgreSQL:** O scraper está integrado ao banco de dados pelo serviço `app.modules.scraper.service.sync_deg_editais()`. A cada sincronização, um registro de auditoria é salvo na tabela `coletas` e os novos editais são persistidos na tabela `editais` vinculados aos seus respectivos campi e tipos. Você também pode disparar a coleta via API com `POST /api/v1/editais/sync`.


### Scraper nível 2: documentos PDF

O scraper de nível 2 recebe o link de uma página individual de edital e extrai os PDFs disponíveis no conteúdo principal. Cada documento retorna:

- `titulo`: texto exibido no link;
- `link`: endereço do arquivo PDF;
- `tipo`: classificação por heurística.

As classificações reconhecidas são `resultado_final`, `resultado_provisorio`, `retificacao` e `homologacao`. Quando nenhuma palavra-chave é encontrada no título ou no nome do arquivo, o documento é classificado como `original`.

Para testar contra uma página real:

```powershell
python -c "from app.modules.scraper.deg import fetch_documentos; url = 'https://deg.unb.br/edital-deg-n-58-2026-premio-anual-de-inovacao-no-ensino-de-graduacao-da-universidade-de-brasilia/'; documentos = fetch_documentos(url); print(f'{len(documentos)} documentos'); [print(documento) for documento in documentos]"
```

Os testes automatizados do nível 2 estão em `tests/test_scraper.py` e não dependem da internet.

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
