# Fique de Olho

Plataforma web do grupo G4 de Métodos de Desenvolvimento de Software (UnB 2026/2) para centralizar editais e oportunidades acadêmicas da Universidade de Brasília. A proposta é reduzir a dispersão de informações, facilitar a busca por filtros e destacar prazos importantes em uma interface leve e acessível.

## O problema e o público

Editais da UnB ficam distribuídos em páginas institucionais e documentos extensos. Estudantes precisam consultar várias fontes, interpretar cronogramas e descobrir rapidamente se uma oportunidade atende ao seu campus ou perfil.

O produto foi pensado para a comunidade discente da UnB, especialmente pessoas que acessam o serviço pelo celular, possuem pouco tempo para acompanhar publicações ou precisam de uma visão resumida antes de abrir o documento oficial.

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

### Backend com Docker

Pré-requisitos: Git, Docker Desktop e Docker Compose.

```powershell
cd Back
docker compose up --build
```

Serviços disponíveis:

- API: [http://localhost:8000](http://localhost:8000)
- Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- Healthcheck: [http://localhost:8000/health](http://localhost:8000/health)

### Backend local

```powershell
cd Back
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

O banco local padrão é configurado por `DATABASE_URL`; ajuste essa variável no arquivo `.env` quando necessário.

### Frontend

Em outro terminal:

```powershell
cd Front
npm install
npm run dev
```

Acesse [http://localhost:5173](http://localhost:5173). Para apontar para outra API, defina `VITE_API_BASE_URL` no ambiente antes de iniciar o Vite. O valor padrão é `http://localhost:8000`.

## Qualidade e comandos

Backend, na pasta `Back`:

```powershell
pytest -v
pytest tests/test_scraper.py -v
```

Frontend, na pasta `Front`:

```powershell
npm run lint
npm run build
npm run format
```

O build TypeScript funciona como uma verificação adicional do contrato consumido pela interface. A suíte atual cobre principalmente healthcheck, endpoints iniciais e parsing do scraper; cobertura percentual e pipeline CI/CD ainda devem ser formalizados.

## Documentação do projeto

- [Documentação publicada](https://unb-mds.github.io/Fique-de-Olho/)
- [Contexto e vocabulário do domínio](CONTEXT.md)
- [Requisitos, personas e backlog](docs/Requisitos/)
- [Roteiro dos slides da apresentação](docs/apresentacao/roteiro-slides.md)
- [Protótipo de alta fidelidade](https://www.figma.com/make/yqHT0b3mk0T3EkHD2aUgns/UnB-Editais-Aggregator-Site?fullscreen=1)
- [Board de planejamento](https://www.figma.com/board/Sw1R44AAXzZrW5eBolJybw/Template-MDS--c%C3%B3pia-limpa---c%C3%B3pia-?node-id=1-291)
- [Guia detalhado do backend](Back/README.md)
- [Guia detalhado do frontend](Front/README.md)

## Apresentação

- [Slides da apresentação no Canva](https://www.canva.com/design/DAHWfQx1cco/ReCF1bStwi7TDEWdPc42Ew/edit)

O roteiro específico do projeto está em [docs/apresentacao/roteiro-slides.md](docs/apresentacao/roteiro-slides.md). Depois de finalizar os slides, salve também o PDF em `docs/apresentacao/` e adicione aqui um link direto para o arquivo, por exemplo:

```md
- [Slides finais - Release 1](docs/apresentacao/slides-release-1.pdf)
```

## Organização do repositório

```text
Back/       API FastAPI, scraper, configuração, Docker e testes
Front/      aplicação React, páginas, componentes e serviços HTTP
docs/       documentação MkDocs, requisitos, estudos e ADRs
CONTEXT.md  linguagem e conceitos do domínio
```

## Próximos passos

1. Persistir editais e documentos no PostgreSQL.
2. Integrar a coleta periódica ao fluxo da API.
3. Implementar busca textual, autenticação, favoritos persistidos e notificações.
4. Adicionar pipeline CI/CD, cobertura de testes e release notes.

## Equipe

<!-- Cada integrante adiciona seu nome manualmente abaixo. -->

- Arthur Amaral da Silva 24200514
- Eduardo Henrique Coutinho Gurjão 222006679
- Felippe Ong Su 242028664
- Isac Silva Marques 242023846
- Ryan Kelvyn Fernandes de Carvalho 241025560
- Wendell Derick Mathias Santana dos Santos 241025739
