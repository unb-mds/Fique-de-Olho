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
├── docker-compose.yml           # Orquestração da API e do banco PostgreSQL
└── requirements.txt             # Dependências Python do projeto
```

---

## 🚀 Como Executar

### Opção 1: Via Docker Compose (Recomendado)

O Docker Compose sobe a aplicação FastAPI e o banco de dados PostgreSQL automaticamente configurados:

```bash
# Na pasta Back/
docker compose up --build -d
docker compose exec api alembic upgrade head
```

O comando de migration cria/atualiza o schema antes de usar os endpoints que
dependem do banco. Se o volume já contém tabelas criadas pela versão anterior,
siga primeiro o procedimento **Adotar um banco existente** abaixo; não execute
`upgrade head` nesse banco.

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

#### 4. Aplicar as migrations:
```powershell
alembic upgrade head
```

#### 5. Iniciar o servidor de desenvolvimento:
```powershell
uvicorn app.main:app --reload --port 8000
```

---

## Banco de Dados

O backend usa PostgreSQL como armazenamento e SQLAlchemy como ORM. O contrato
do schema está definido em `app/core/database.py`; as entidades, relações e
decisões estão descritas no [ADR 0003](../docs/adr/0003-database-schema.md).

### O que o banco guarda

- `editais`: título, URL da página de origem, campus e tipo opcionais, data de
   publicação, status (`aberto` ou `encerrado`) e data de criação. A URL da página
   é única para impedir duplicatas na coleta incremental.
- `edital_documentos`: URLs de PDFs associadas a um edital e tipo do documento
   (`original`, `resultado_provisorio`, `resultado_final` ou `retificacao`).
- `usuarios`: nome, e-mail único, hash da senha e data de criação. A senha em
   texto puro não deve ser armazenada.
- `favoritos`: associa usuários a editais. A chave primária composta pelos IDs
   impede repetir o mesmo vínculo usuário/edital.

As chaves estrangeiras garantem que documentos e favoritos apontem para
registros existentes. Um edital pode ter vários documentos e vários favoritos;
um usuário pode ter vários favoritos. `created_at` usa o horário do servidor do
banco quando nenhum valor é informado.

### Inicializar com Docker Compose

Na pasta `Back/`, copie o exemplo de ambiente e suba os serviços:

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

O serviço `db` cria o banco `fiquedeolho_db` com usuário e senha do `.env` (os
valores do exemplo são apenas para desenvolvimento). A porta publicada no host
é `5433` no exemplo; a API dentro do Docker conecta ao endereço `db:5432`. Se as
portas do host estiverem ocupadas, altere `POSTGRES_PORT` ou `API_PORT` no
`.env`.

O startup da API não altera o schema. Em um banco vazio, aplique a revisão inicial:

```bash
docker compose exec api alembic upgrade head
```

Confira a revisão aplicada e as tabelas:

```bash
docker compose exec api alembic current
docker compose exec db psql -U fiquedeolho -d fiquedeolho_db -c '\dt'
```

Se tiver alterado usuário ou banco, use os valores configurados no `.env`. Para
verificar mensagens de inicialização:

```bash
docker compose logs -f db api
```

### Executar a API localmente contra o Compose

Com o serviço `db` ativo, configure `Back/.env` com a porta publicada no host:

```dotenv
DATABASE_URL=postgresql+psycopg2://fiquedeolho:fiquedeolho@localhost:5433/fiquedeolho_db
```

Depois, ative o ambiente virtual, aplique as migrations e execute:

```bash
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Adotar um banco existente

Para um banco criado pela versão anterior do backend, faça um backup e confirme
que tabelas, colunas, índices, constraints e enums correspondem à revisão inicial
`0001_initial_schema`. `stamp` não compara nem altera o schema: apenas registra
que a revisão já está aplicada. Só após essa conferência, execute:

```bash
docker compose exec api alembic stamp head
docker compose exec api alembic current
```

Para execução local, use `alembic stamp head` com `DATABASE_URL` apontando para
o banco verificado. Se o schema não corresponder à revisão inicial, não use
`stamp`; avalie uma migration de adoção antes de prosseguir.

### Reverter uma migration

O downgrade da revisão inicial remove todas as tabelas do schema. Teste-o somente
em um banco descartável, nunca em produção nem em um volume com dados que devam
ser preservados:

```bash
docker compose exec api alembic downgrade base
```

Para alterações futuras, crie revisões com `alembic revision --autogenerate -m
"descricao"`, revise o arquivo gerado e aplique com `alembic upgrade head`.

### O que a camada de banco entrega ao backend

Os modelos ORM descrevem os registros e seus relacionamentos. `SessionLocal`
cria sessões SQLAlchemy e `get_db()` fornece uma sessão com fechamento ao fim
do uso. No estado atual, essa dependência ainda não está conectada às rotas ou
serviços para consultar e persistir dados; essa integração de negócio é uma
etapa posterior.

## 🧪 Como Rodar os Testes

Para executar a suíte de testes com o `pytest`:

```bash
pytest -v
```

Para validar especificamente o schema e os modelos:

```bash
pytest tests/test_database_schema.py -v
```

Esse teste verifica tabelas, colunas, chave primária composta e relações em
SQLite em memória. O teste de startup confirma que a API não cria tabelas
automaticamente. SQLite não valida as migrations PostgreSQL; aplique `upgrade`
e `downgrade` em um banco descartável via Compose para verificar os tipos enum e
o schema real.

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

#### 1. Rodar os testes automatizados

Na pasta `Back/`, com o ambiente virtual ativado:

```powershell
pytest tests/test_scraper.py -v
```

Se o ambiente virtual não estiver ativado, execute pelo caminho direto do Python no Windows:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_scraper.py -v
```

Esses testes não dependem da internet. Eles simulam o HTML do portal para 2026 e 2025 e verificam também se uma falha de rede retorna uma lista vazia sem interromper a execução.

#### 2. Consultar o portal real

Para executar o scraper contra as páginas reais do DEG:

```powershell
python -c "from app.modules.scraper.deg import fetch_editais; atual = fetch_editais(); anterior = fetch_editais(2025); print(f'2026: {len(atual)} editais'); print(atual[0] if atual else 'nenhum'); print(f'2025: {len(anterior)} editais'); print(anterior[0] if anterior else 'nenhum')"
```

O resultado deve mostrar a quantidade encontrada e o primeiro edital de cada ano. A função `fetch_editais()` retorna `[]` quando ocorre uma falha de comunicação com o portal.

> **Nota:** nesta etapa o scraper ainda é uma função de coleta independente. A integração com o endpoint de listagem da API e a persistência no PostgreSQL serão feitas nas próximas etapas do backend.

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
