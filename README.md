# Fique de Olho - UnB Editais

Grupo G4 - Métodos de Desenvolvimento de Software 2026/2

## 🎯 Objetivo

O projeto facilita o acesso aos editais da Universidade de Brasília, centralizando,
filtrando e notificando as publicações para que estudantes não percam prazos de
bolsas, monitorias, PIBIC e transferências.

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

### 2. Iniciar o banco de dados e a API

Em um terminal, na raiz do repositório, execute:

```bash
cd Back
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose ps
```

O Compose inicia o PostgreSQL e aguarda o banco ficar saudável antes de iniciar a API. A migration `alembic upgrade head` cria ou atualiza as tabelas no banco. Execute-a após iniciar os serviços e sempre que uma nova migration for adicionada.

O PostgreSQL fica disponível na porta `5433` do computador e a API na porta `8000`. Para alterar essas portas, configure `POSTGRES_PORT` e `API_PORT` no arquivo `Back/.env` (pode ser criado a partir de `Back/.env.example`) antes de iniciar os serviços. Se mudar `API_PORT`, configure também `VITE_API_BASE_URL` em `Front/.env` (veja `Front/.env.example`) com a mesma porta e reinicie o Vite.

Confira os serviços e a API:

- Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- Healthcheck: [http://localhost:8000/health](http://localhost:8000/health)

Para ver os logs dos serviços, ainda na pasta `Back`, use `docker compose logs -f api db`.

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

## 👥 Autores

<!-- Cada integrante adiciona seu nome manualmente abaixo -->

- 
-
-
-
