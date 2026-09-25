# Banco de dados

O banco local do projeto usa PostgreSQL 16 executado por Docker Compose.

## Iniciar

Copie `.env.example` para `.env` se precisar alterar as configurações locais e execute:

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