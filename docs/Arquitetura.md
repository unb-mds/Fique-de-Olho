# Arquitetura do Fique de Olho

Este documento descreve a arquitetura implementada no repositório. As funcionalidades que aparecem nos requisitos ou nas decisões, mas ainda não estão conectadas ao fluxo da aplicação, são identificadas como planejadas ou ainda não implementadas.

## Stack de tecnologias

### Frontend

- **React 18** e **React DOM** para construir a interface web.
- **TypeScript** para tipagem estática.
- **Vite** para desenvolvimento e build.
- **React Router** para navegação entre páginas.
- **Fetch API** para comunicação HTTP com o backend.

### Backend

- **Python** como linguagem.
- **FastAPI** para a API REST e documentação OpenAPI.
- **Uvicorn** como servidor ASGI.
- **Pydantic Settings** para configuração por variáveis de ambiente.
- **SQLAlchemy** como ORM e camada de acesso ao banco.
- **psycopg2** como driver PostgreSQL.
- **httpx** e **Beautiful Soup** para requisições HTTP e parsing HTML do portal do DEG.
- **Docker** e **Docker Compose** para executar a API em ambiente containerizado.

### Banco de dados

- **PostgreSQL 16** como banco de dados relacional.
- **SQL** para definição do schema e scripts de inicialização versionados.
- **Docker Compose** para executar o banco localmente, com volume persistente.

## Componentes

### Frontend

O frontend em `Front/` usa React, TypeScript, Vite e React Router.

- `Front/src/pages/` contém as páginas inicial e de detalhes do edital.
- `Front/src/components/` reúne os elementos de interface reutilizáveis.
- `Front/src/services/` centraliza as chamadas HTTP à API e os tipos consumidos pela interface.
- `Front/src/routes/AppRoutes.tsx` define as rotas `/` e `/editais/:id`.

A página inicial busca a lista de editais e filtra a categoria no navegador. A página de detalhes busca um edital pelo identificador. Embora a API aceite filtros na listagem, o serviço atual do frontend não envia esses parâmetros.

### API e módulos de negócio

O backend em `Back/app/` usa FastAPI, Pydantic, SQLAlchemy e PostgreSQL.

- `Back/app/main.py` cria a aplicação, configura CORS, expõe o healthcheck e registra as rotas.
- `Back/app/core/` fornece configurações de ambiente e conexão/sessões de banco de dados.
- `Back/app/modules/editais/` implementa as rotas, schemas, modelos e consultas de editais.
- `Back/app/modules/scraper/` acessa o portal do DEG, interpreta a listagem e coordena a persistência dos novos registros.

O módulo de editais oferece listagem com filtros por status, categoria, campus e termo textual, além de consulta por ID. A busca textual atual compara o termo com título e resumo no PostgreSQL; não é busca semântica.

As rotas principais estão disponíveis sob `/api/v1`. O backend também registra as mesmas rotas sem esse prefixo, sem incluí-las no schema OpenAPI, para compatibilidade com chamadas existentes.

### Banco de dados

O PostgreSQL armazena os editais e seus relacionamentos com catálogos de tipos, campi e cursos. As tabelas de junção permitem relacionamentos muitos-para-muitos. O schema também define tabelas para usuários, favoritos, notificações e auditoria de coletas.

O schema é criado pelos scripts em `db/migrations/`, montados como scripts de inicialização do container do PostgreSQL. A inicialização automática do PostgreSQL executa esses scripts quando o diretório de dados do banco é criado; alterações posteriores no volume existente não são aplicadas automaticamente como migrations incrementais.

Há também um índice de busca de texto completo (`tsvector`) no banco. A listagem da API ainda não usa esse índice: seu filtro textual usa comparações `ILIKE` sobre título e resumo.

## Diagramas C4

Os espaços abaixo ficam reservados para os diagramas C4 deste projeto.

### Diagrama de Contexto (C4 — Nível 1)

![Diagrama C4 de Contexto](<assets/img/Diagrama de Contexto.drawio.png>)

### Diagrama de Contêineres (C4 — Nível 2)

![Diagrama C4 de Contexto](<assets/img/Diagrama de conteiner1.drawio.png>)

## Fluxos principais

### Consulta de editais

1. O frontend chama a API pelo serviço em `Front/src/services/editaisService.ts`.
2. A rota FastAPI valida os parâmetros e delega a consulta ao serviço do módulo de editais.
3. O serviço consulta o PostgreSQL com SQLAlchemy, aplica os filtros e serializa os registros para os schemas de resposta.
4. O frontend apresenta a listagem ou os detalhes recebidos.

### Coleta dos portais

1. Uma chamada `POST /api/v1/editais/sync` solicita a sincronização; a rota aceita um limite de itens.
2. O serviço de coleta registra uma execução em `coletas` e solicita a listagem ao portal.
3. O scraper extrai título, endereço e data de publicação do HTML. A categoria é inferida pelo título.
4. O serviço evita inserir novamente um edital cujo endereço já esteja cadastrado, persiste novos registros e atualiza o resultado da coleta.

Essa coleta é acionada sob demanda pela API; não há agendador configurado neste repositório. O scraper também possui funções para encontrar links de PDFs e classificá-los, mas o fluxo de sincronização descrito acima não baixa os documentos nem extrai texto deles. Os campos `texto_extraido` e `hash_conteudo` existem no schema, mas isso não significa que o processamento de PDF esteja implementado no fluxo atual.

## Execução e configuração

O `docker-compose.yml` inicia dois serviços:

- `db`: PostgreSQL 16, com volume persistente e scripts de inicialização do schema.
- `api`: backend FastAPI, publicado na porta 8000 e dependente do healthcheck do banco.

O frontend não faz parte desse Compose: é executado separadamente com Vite, normalmente na porta 5173. A URL da API pode ser configurada por `VITE_API_BASE_URL`; sem essa variável, o frontend usa `http://localhost:8000`. O backend carrega configurações, incluindo `DATABASE_URL`, a partir do ambiente.

O endpoint `/health` verifica a conexão com o banco e retorna estado saudável ou indisponível. A API também publica a documentação OpenAPI em `/docs` e `/redoc`.


## Referências de implementação

- `Back/README.md` — instruções e detalhes do backend.
- `Front/README.md` — instruções e detalhes do frontend.
- `db/migrations/001_initial_schema.sql` — schema inicial do banco.
- [ADR da stack do backend](adr/0001-stack-backend.md)
- [ADR da stack do frontend](adr/0002-stack-frontend.md)
- [ADR do PostgreSQL e Docker](adr/0002-postgresql-com-docker.md)