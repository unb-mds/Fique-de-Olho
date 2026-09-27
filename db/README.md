# Banco de dados

O banco local do projeto usa PostgreSQL 16 executado por Docker Compose.

## Iniciar

O Compose da raiz do repositório é o ponto único de entrada para o PostgreSQL e a API. Para iniciar os dois serviços, execute na raiz:

```bash
docker compose up --build
```

Para iniciar apenas o banco (por exemplo, ao executar a API localmente), copie `.env.example` para `.env` se precisar alterar as configurações locais e execute:

```bash
docker compose up -d db
```

Verifique o estado do serviço:

```bash
docker compose ps
```

As migrations em `db/migrations/` são executadas automaticamente somente na primeira inicialização do volume do PostgreSQL. Para recriar o banco local do zero após alterar uma migration:

```bash
docker compose down -v
docker compose up -d db
```

O comando `down -v` apaga apenas os dados locais do volume Docker. Nunca o use em um ambiente que contenha dados importantes.

## Conectar ao banco

```bash
docker compose exec db psql -U fique_de_olho -d fique_de_olho
```

O banco armazena o link oficial e o texto extraído do PDF. A cópia integral do PDF não é armazenada localmente.

## Integração com o backend

O serviço `api` é construído a partir de `Back/Dockerfile` e espera o serviço `db` ficar saudável antes de iniciar. Os dois usam as mesmas credenciais e o mesmo banco, configurados por `POSTGRES_USER`, `POSTGRES_PASSWORD` e `POSTGRES_DB` no `.env` da raiz. As migrations em `db/migrations/` são montadas no PostgreSQL e executadas na primeira inicialização do volume. Assim, a API e o uso isolado do banco não criam instâncias ou volumes independentes.

O volume criado pelo Compose antigo em `Back/` não é reutilizado nem removido por esta configuração. Se ele contiver dados que devam ser preservados, exporte-os e importe-os no novo banco antes de abandonar o volume antigo.