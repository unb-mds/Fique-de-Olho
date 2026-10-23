# Fique de Olho

Plataforma web do grupo G4 de Métodos de Desenvolvimento de Software (UnB
2026/2) para centralizar editais e oportunidades acadêmicas da Universidade de
Brasília.

## O problema e o público

Editais da UnB ficam distribuídos em páginas institucionais e documentos
extensos. Estudantes precisam consultar várias fontes, interpretar cronogramas
e descobrir rapidamente se uma oportunidade atende ao seu campus ou perfil.

O produto foi pensado para a comunidade discente da UnB, especialmente pessoas
que acessam o serviço pelo celular, possuem pouco tempo para acompanhar
publicações ou precisam de uma visão resumida antes de abrir o documento
oficial.

## 📚 Documentação

- [Documentação publicada](https://unb-mds.github.io/Fique-de-Olho/)
- [Figma](https://www.figma.com/board/Sw1R44AAXzZrW5eBolJybw/Template-MDS--c%C3%B3pia-limpa---c%C3%B3pia-?node-id=1-291)
- [Protótipo de alta fidelidade](https://www.figma.com/make/yqHT0b3mk0T3EkHD2aUgns/UnB-Editais-Aggregator-Site?fullscreen=1)

## Pré-requisitos

Escolha uma das formas de execução:

- **Docker Compose (recomendado):** Git, Docker Desktop e Docker Compose v2.
- **Execução local:** Python 3.12 ou superior, Node.js 18 ou superior e npm.
- **Backend local com banco em Docker:** Docker Desktop e Python.

Os comandos deste README devem ser executados a partir da raiz do repositório,
a pasta que contém o arquivo `docker-compose.yml`.

## Como executar

### Opção A — Tudo com Docker Compose

Na raiz do projeto, execute:

```powershell
docker compose up --build -d
docker compose ps
```

O Compose inicia o PostgreSQL na porta `5432` e a API na porta `8000`. O banco
é criado automaticamente na primeira execução, e a API aguarda o banco ficar
saudável antes de iniciar.

Verifique se a API está funcionando:

```powershell
Invoke-RestMethod http://localhost:8000/health
```
Serviços disponíveis:

- API: [http://localhost:8000](http://localhost:8000)
- Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- Healthcheck: [http://localhost:8000/health](http://localhost:8000/health)

Para acompanhar os logs:

```powershell
docker compose logs -f api db
```

Para parar os serviços sem apagar os dados:

```powershell
docker compose down
```

Para recriar o banco do zero, apagando os dados locais:

```powershell
docker compose down -v
docker compose up --build -d
```

> O `docker-compose.yml` da raiz é o fluxo recomendado. Não é necessário
> entrar em `Back` para iniciar os serviços com Docker.

### Opção B — Backend local e banco no Docker

Na raiz do projeto, inicie somente o banco:

```powershell
docker compose up -d db
```

Em outro terminal, prepare e inicie o backend:

```powershell
cd Back
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Se o PowerShell bloquear a ativação do ambiente virtual, execute uma vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Depois, confirme que [http://localhost:8000/health](http://localhost:8000/health)
retorna `"status": "healthy"`.

### Opção C — Frontend local

Com a API em execução, abra outro terminal na raiz:

```powershell
cd Front
npm ci
npm run dev
```

Acesse [http://localhost:5173](http://localhost:5173). O frontend usa
`http://localhost:8000` como endereço padrão da API.

Para apontar para outra API, copie o arquivo de ambiente e ajuste a variável:

```powershell
Copy-Item .env.example .env
```

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

Reinicie o Vite depois de alterar o arquivo `.env`.

### Execução completa local

Para executar banco, backend e frontend em terminais separados:

1. Na raiz: `docker compose up -d db`.
2. Em um terminal: siga a **Opção B**.
3. Em outro terminal: siga a **Opção C**.

## Solução de problemas

### A porta 5432 ou 8000 já está em uso

Identifique e encerre o processo que está usando a porta ou altere a porta
publicada no `docker-compose.yml`. Se alterar a porta da API, atualize também
`Front/.env`:

```dotenv
VITE_API_BASE_URL=http://localhost:NOVA_PORTA
```

### A API está `unhealthy`

Confira o estado e os logs dos serviços:

```powershell
docker compose ps
docker compose logs db api
```

Se o volume for descartável e estiver inconsistente, recrie-o:

```powershell
docker compose down -v
docker compose up --build -d
```

### O frontend não encontra a API

Confirme que o healthcheck responde, verifique `Front/.env` e reinicie o
processo `npm run dev` depois de alterar `VITE_API_BASE_URL`.

## Arquitetura e tecnologias

```text
Front (React + TypeScript + Vite)
              │ HTTP / JSON
Back (FastAPI + Pydantic)
              │
Scraper (httpx + BeautifulSoup) ──> fontes institucionais da UnB
              │
PostgreSQL
```

- **Frontend:** React 18, TypeScript, Vite, React Router, ESLint e Prettier.
- **Backend:** Python, FastAPI, Pydantic Settings, Uvicorn, SQLAlchemy e
  PostgreSQL.
- **Coleta e parsing:** HTTPX, BeautifulSoup e pdfplumber.
- **Execução:** Docker Compose para API e banco; execução local também
  disponível.

### Como os componentes se relacionam

1. O usuário acessa a interface React pelo navegador.
2. O frontend envia requisições HTTP em JSON para a API FastAPI.
3. A API organiza as rotas por módulos de negócio, como editais e favoritos.
4. O SQLAlchemy fornece a camada de acesso ao PostgreSQL.
5. O scraper coleta listagens e documentos PDF das fontes institucionais da
   UnB, enquanto os parsers extraem os dados relevantes.
6. O Docker Compose executa a API e o PostgreSQL em serviços separados,
   permitindo que o frontend local ou outros clientes consumam a API.

As escolhas de tecnologia estão registradas nos ADRs de
[backend](docs/adr/0001-stack-backend.md) e
[frontend](docs/adr/0002-stack-frontend.md).

## Qualidade e comandos

Backend, na pasta `Back` e com o ambiente virtual ativado:

```powershell
python -m pytest -v
python -m pytest tests/test_scraper.py -v
```

Frontend, na pasta `Front`:

```powershell
npm run lint
npm run build
```

## Documentação do projeto

- [Documentação publicada](https://unb-mds.github.io/Fique-de-Olho/)
- [Contexto e vocabulário](CONTEXT.md)
- [Requisitos, personas e backlog](docs/Requisitos/)
- [Documentação do backend](Back/README.md)
- [Documentação do frontend](Front/README.md)
- [ADRs](docs/adr/)
- [Figma](https://www.figma.com/board/Sw1R44AAXzZrW5eBolJybw/Template-MDS--c%C3%B3pia-limpa---c%C3%B3pia-?node-id=1-291)
- [Protótipo de alta fidelidade](https://www.figma.com/make/yqHT0b3mk0T3EkHD2aUgns/UnB-Editais-Aggregator-Site?fullscreen=1)

## Equipe

- Arthur Amaral da Silva 24200514
- Eduardo Henrique Coutinho Gurjão 222006679
- Felippe Ong Su 242028664
- Isac Silva Marques 242023846
- Ryan Kelvyn Fernandes de Carvalho 241025560
- Wendell Derick Mathias Santana dos Santos 241025739
