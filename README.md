# Fique de Olho

Plataforma web do grupo G4 de Métodos de Desenvolvimento de Software (UnB 2026/2) para centralizar editais e oportunidades acadêmicas da Universidade de Brasília. A proposta é reduzir a dispersão de informações, facilitar a busca por filtros e destacar prazos importantes em uma interface leve e acessível.

## O problema e o público

Editais da UnB ficam distribuídos em páginas institucionais e documentos extensos. Estudantes precisam consultar várias fontes, interpretar cronogramas e descobrir rapidamente se uma oportunidade atende ao seu campus ou perfil.

O produto foi pensado para a comunidade discente da UnB, especialmente pessoas que acessam o serviço pelo celular, possuem pouco tempo para acompanhar publicações ou precisam de uma visão resumida antes de abrir o documento oficial.

## 📚 Documentação

- [Pages](https://unb-mds.github.io/Fique-de-Olho/)
- [Figma](https://www.figma.com/board/Sw1R44AAXzZrW5eBolJybw/Template-MDS--c%C3%B3pia-limpa---c%C3%B3pia-?node-id=1-291)
- [protótipo de alta fidelidade](https://www.figma.com/make/yqHT0b3mk0T3EkHD2aUgns/UnB-Editais-Aggregator-Site?fullscreen=1)

## ⚙️ Pré-requisitos

Para executar o projeto, instale:

- Git
- Docker com Docker Compose v2 (Docker Desktop no Windows/macOS ou Docker Engine no Linux)
- Node.js 18 ou superior e npm

## 🚀 Executando o projeto

### 1. Obter o código

Se ainda não clonou o repositório:

```bash
git clone https://github.com/unb-mds/Fique-de-Olho.git
cd Fique-de-Olho
```

Se o repositório já estiver clonado, entre na pasta dele e siga para a próxima etapa.

## O que existe hoje

- Frontend React com listagem de editais, destaques, filtros por categoria, favoritos visuais e página de detalhe.
- API FastAPI com documentação OpenAPI, healthcheck e endpoints de listagem e consulta por identificador.
- Scraper do portal do DEG para listagens de editais e documentos PDF, com tratamento de falha de rede.
- Testes automatizados do healthcheck, endpoints e scraper, usando respostas HTML simuladas.
- Documentação de domínio, requisitos, personas, backlog, arquitetura e decisões técnicas em `docs/`.

> Estado atual: a API ainda utiliza dados em memória para a listagem. A persistência no PostgreSQL, autenticação, notificações e integração completa do scraper com os endpoints são próximos passos, não funcionalidades concluídas.

## Arquitetura e tecnologias

```text
Front (React + TypeScript + Vite)
			  │ HTTP / JSON
Back (FastAPI + Pydantic)
			  │
Scraper (httpx + BeautifulSoup) ──> fontes institucionais da UnB
			  │
PostgreSQL (infraestrutura preparada para persistência)
```

- **Frontend:** React 18, TypeScript, Vite, React Router, ESLint e Prettier.
- **Backend:** Python, FastAPI, Pydantic Settings, Uvicorn, SQLAlchemy e PostgreSQL.
- **Coleta e parsing:** HTTPX, BeautifulSoup e pdfplumber.
- **Execução:** Docker Compose para API e banco; execução local também disponível.

As escolhas estão registradas nos ADRs de [backend](docs/adr/0001-stack-backend.md) e [frontend](docs/adr/0002-stack-frontend.md).

## Como executar

### Backend com Docker / Bancos

Pré-requisitos: Git, Docker Desktop e Docker Compose.

```bash
cd Back
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose ps
```

O Compose inicia o PostgreSQL e aguarda o banco ficar saudável antes de iniciar a API. A migration `alembic upgrade head` cria ou atualiza as tabelas no banco. Execute-a após iniciar os serviços e sempre que uma nova migration for adicionada.

O PostgreSQL fica disponível na porta `5433` do computador e a API na porta `8000`. Para alterar essas portas, configure `POSTGRES_PORT` e `API_PORT` no arquivo `Back/.env` (pode ser criado a partir de `Back/.env.example`) antes de iniciar os serviços. Se mudar `API_PORT`, configure também `VITE_API_BASE_URL` em `Front/.env` (veja `Front/.env.example`) com a mesma porta e reinicie o Vite.

Confira os serviços e a API:
docker compose up --build
```
Serviços disponíveis:

- API: [http://localhost:8000](http://localhost:8000)
- Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- Healthcheck: [http://localhost:8000/health](http://localhost:8000/health)

Para ver os logs dos serviços, ainda na pasta `Back`, use `docker compose logs -f api db`.
```

### Backend local

```powershell
cd Back
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

O banco local padrão é configurado por `DATABASE_URL`; ajuste essa variável no arquivo `.env` quando necessário.

### 3. Iniciar o frontend

Abra outro terminal na raiz do repositório e execute:

```bash
cd Front
npm install
npm run dev
```

Abra o endereço exibido pelo Vite, normalmente [http://localhost:5173](http://localhost:5173). Por padrão, o frontend já se conecta à API em `http://localhost:8000`; não é necessário criar um arquivo `.env` para a configuração padrão.

### Parar os serviços

No terminal da pasta `Back`, execute:

```bash
docker compose down
```

Esse comando mantém o volume do PostgreSQL e os dados persistidos. **Não use `docker compose down -v`**, a menos que queira apagar permanentemente o banco local.

### Estado atual da integração

O PostgreSQL e as migrations inicializam o schema da aplicação, mas a rota `GET /api/v1/editais/` ainda retorna dados de demonstração definidos no código, sem consultar o banco. A integração entre os modelos e os endpoints ainda não foi implementada.

Para detalhes sobre migrations, execução local do backend e testes, consulte o [README do backend](Back/README.md).

## Documentação do projeto

- [Documentação publicada](https://unb-mds.github.io/Fique-de-Olho/)
- [Contexto e vocabulário do domínio](CONTEXT.md)
- [Requisitos, personas e backlog](docs/Requisitos/)
- [Roteiro dos slides da apresentação](docs/apresentacao/roteiro-slides.md)
- [Protótipo de alta fidelidade](https://www.figma.com/make/yqHT0b3mk0T3EkHD2aUgns/UnB-Editais-Aggregator-Site?fullscreen=1)
- [Board de planejamento](https://www.figma.com/board/Sw1R44AAXzZrW5eBolJybw/Template-MDS--c%C3%B3pia-limpa---c%C3%B3pia-?node-id=1-291)
- [Guia detalhado do backend](Back/README.md)
- [Guia detalhado do frontend](Front/README.md)

```

## Organização do repositório

```text
Back/       API FastAPI, scraper, configuração, Docker e testes
Front/      aplicação React, páginas, componentes e serviços HTTP
docs/       documentação MkDocs, requisitos, estudos e ADRs
CONTEXT.md  linguagem e conceitos do domínio
```
## Equipe

<!-- Cada integrante adiciona seu nome manualmente abaixo. -->

- Arthur Amaral da Silva 24200514
- Eduardo Henrique Coutinho Gurjão 222006679
- Felippe Ong Su 242028664
- Isac Silva Marques 242023846
- Ryan Kelvyn Fernandes de Carvalho 241025560
- Wendell Derick Mathias Santana dos Santos 241025739
