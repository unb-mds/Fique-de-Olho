# [![Fique de Olho logo][]][site] Banco de dados

[![CI][CI badge]][CI workflow]
[![PostgreSQL 16][PostgreSQL badge]][PostgreSQL]
[![SQLAlchemy 2][SQLAlchemy badge]][SQLAlchemy]
[![Alembic][Alembic badge]][Alembic]
[![Neon][Neon badge]][Neon]

O banco de dados do **Fique de Olho** guarda os editais da UnB coletados em 33 portais, os usuários, os favoritos, os alertas por e-mail e o histórico de cada coleta. É um PostgreSQL 16, rodando em Docker no seu computador e no [Neon][] em produção, com o schema versionado exclusivamente pelo [Alembic][].

## Documentação

* [Início rápido](#início-rápido)
* [Modelo de dados](#modelo-de-dados)
* [Catálogo das 14 tabelas](#catálogo-das-14-tabelas)
* [Migrations com Alembic](#migrations-com-alembic)
* [Ambientes](#ambientes)
* [Operação do dia a dia](#operação-do-dia-a-dia)
* [Solução de problemas](#solução-de-problemas)
* [Referência completa do backend](../docs/backend/banco-de-dados.md)
* [ADR 0003 — Schema inicial do banco de dados](../docs/adr/0003-database-schema.md)
* [ADR 0006 — Evolução do schema, alertas e notificações](../docs/adr/0006-evolucao-schema-catalogos-alertas-notificacoes.md)

## Início rápido

Você precisa de Git, Docker e Docker Compose v2. Na **raiz do repositório**:

```bash
docker compose up -d db        # sobe só o PostgreSQL
docker compose ps              # confere se está "healthy"
```

Para subir tudo (banco, API e frontend), use `docker compose up --build -d`. Nesse caso a API aplica as migrations sozinha antes de iniciar (`alembic upgrade head`).

Se você subiu só o banco e vai rodar a API fora do Docker, aplique o schema à mão:

```bash
cd Back
source .venv/bin/activate
alembic upgrade head
```

Para conectar ao banco:

```bash
docker compose exec db psql -U fique_de_olho -d fique_de_olho
```

| Parâmetro | Valor padrão de desenvolvimento |
| :--- | :--- |
| Host / porta | `localhost` / `5432` (muda com `POSTGRES_PORT`) |
| Banco | `fique_de_olho` |
| Usuário | `fique_de_olho` |
| Senha | `fique_de_olho_dev` |
| `DATABASE_URL` | `postgresql+psycopg2://fique_de_olho:fique_de_olho_dev@localhost:5432/fique_de_olho` |

> Essas credenciais existem **somente para desenvolvimento local**. Em produção, a `DATABASE_URL` vem das variáveis de ambiente do Render e nunca é commitada.

Se a porta `5432` já estiver em uso na sua máquina, crie um arquivo `.env` na raiz com `POSTGRES_PORT=55432` e suba de novo.

## Sobre o banco

Nós queremos um banco simples de operar, seguro contra dados duplicados e fácil de evoluir em equipe.

### Uma única fonte da verdade para o schema

Todas as tabelas, colunas, índices, constraints e enums nascem de revisões do Alembic em [`Back/migrations/versions/`](../Back/migrations/versions). Os modelos SQLAlchemy ficam em [`Back/app/core/database.py`](../Back/app/core/database.py). O startup da API **nunca** chama `Base.metadata.create_all()`, então nenhuma mudança de schema acontece sem uma migration revisada.

### Seguro contra duplicidade

A coleta pode rodar várias vezes sem criar editais repetidos. A tabela `editais` tem unicidade em `url_pagina` (chave de idempotência da coleta), `url_pdf` e `identificador_origem`. Já a tabela `notificacoes` tem a constraint `uq_notificacao_evento` sobre `(usuario_id, edital_id, tipo, chave_evento)`, que impede o mesmo e-mail de ser enviado duas vezes.

### Dados com regras de integridade

O banco valida o que a aplicação promete. A constraint `editais_periodo_inscricao_ck` garante que a data de início da inscrição não seja posterior ao fim, e `editais_status_processamento_ck` restringe o estado de processamento a `pendente`, `processado`, `parcialmente_processado` ou `erro`.

### Pronto para o Neon Serverless

O Neon suspende o banco após 5 minutos sem uso. Por isso o engine SQLAlchemy usa `pool_pre_ping=True` (testa a conexão antes de usá-la) e `pool_recycle=300` (recicla conexões antes da janela de suspensão).

### Observável

Cada execução do scraper por portal vira uma linha em `coletas`, com início, fim, situação e quantidade de editais encontrados. É dessa tabela que sai o selo **"Atualizado em"** da página inicial: a API devolve o `MAX(finalizada_em)` das coletas com status `concluida` em `GET /api/v1/editais/ultima-atualizacao`.

## Modelo de dados

```mermaid
erDiagram
    EDITAIS ||--o{ EDITAL_DOCUMENTOS : "possui"
    EDITAIS ||--o{ FAVORITOS : "salvo em"
    EDITAIS ||--o{ ALERTAS_EDITAL : "monitorado por"
    EDITAIS ||--o{ NOTIFICACOES : "origina"
    EDITAIS ||--o{ EDITAL_TIPOS : "classificado"
    EDITAIS ||--o{ EDITAL_CAMPI : "ofertado em"
    EDITAIS ||--o{ EDITAL_CURSOS : "direcionado a"

    TIPOS_EDITAIS ||--o{ EDITAL_TIPOS : "tipo"
    CAMPI ||--o{ EDITAL_CAMPI : "campus"
    CURSOS ||--o{ EDITAL_CURSOS : "curso"

    USUARIOS ||--o{ FAVORITOS : "favorita"
    USUARIOS ||--o{ ALERTAS_EDITAL : "ativa alerta"
    USUARIOS ||--o{ NOTIFICACOES : "recebe"

    EDITAIS {
        int id PK
        varchar titulo
        varchar url_pagina UK
        varchar url_pdf UK
        varchar identificador_origem UK
        varchar orgao_emissor
        text resumo
        text texto_extraido
        date inicio_inscricao
        date fim_inscricao
        int vagas
        numeric valor_bolsa
        status_edital status
        varchar status_processamento
    }

    USUARIOS {
        int id PK
        varchar email UK
        varchar senha_hash
        boolean receber_emails
    }

    COLETAS {
        int id PK
        varchar fonte
        timestamptz finalizada_em
        varchar status
        int editais_encontrados
    }

    FEEDBACKS {
        int id PK
        varchar tipo
        text mensagem
    }
```

As tabelas `coletas` e `feedbacks` não têm relacionamento com as demais: uma registra a execução do scraper e a outra guarda os envios da Central de Ajuda.

## Catálogo das 14 tabelas

### Núcleo de editais

| Tabela | Chave primária | Finalidade |
| :--- | :--- | :--- |
| `editais` | `id` | Entidade central. Guarda título, links, órgão emissor, resumo, texto extraído do PDF, período de inscrição, vagas, valor da bolsa, situação e hash do conteúdo. Índices em `url_pagina`, `fim_inscricao` e `orgao_emissor`. |
| `edital_documentos` | `id` | Anexos oficiais de um edital: original, retificação e resultados. Índice em `edital_id`. |

O banco guarda o link oficial e o texto extraído do PDF. **A cópia do PDF não é armazenada.**

### Catálogos controlados

| Tabela | Chave primária | Finalidade |
| :--- | :--- | :--- |
| `tipos_editais` | `id` | Categorias de edital, com `nome` único. |
| `campi` | `id` | Campi da UnB, com `nome` único. |
| `cursos` | `id` | Cursos, com `nome` único. |
| `edital_tipos` | `(edital_id, tipo_edital_id)` | Liga editais a tipos (muitos para muitos). |
| `edital_campi` | `(edital_id, campus_id)` | Liga editais a campi (muitos para muitos). |
| `edital_cursos` | `(edital_id, curso_id)` | Liga editais a cursos (muitos para muitos). |

Nas tabelas associativas, apagar um edital apaga as ligações (`ON DELETE CASCADE`), mas um valor de catálogo em uso não pode ser removido (`ON DELETE RESTRICT`).

### Usuários, favoritos, alertas e notificações

| Tabela | Chave primária | Finalidade |
| :--- | :--- | :--- |
| `usuarios` | `id` | Conta do usuário. `email` único, `senha_hash` em Argon2 e `receber_emails` (padrão `true`) para optar por não receber e-mails. |
| `favoritos` | `(usuario_id, edital_id)` | Lista pessoal de editais. Favoritar **não** dispara e-mail. |
| `alertas_edital` | `(usuario_id, edital_id)` | Ativação explícita de alertas por e-mail para um edital. |
| `notificacoes` | `id` | Fila e histórico de e-mails, com proteção contra envio duplicado. |

### Coleta e suporte

| Tabela | Chave primária | Finalidade |
| :--- | :--- | :--- |
| `coletas` | `id` | Uma linha por execução do scraper em um portal (`fonte`), com `iniciada_em`, `finalizada_em`, `status`, `editais_encontrados` e `mensagem_erro`. |
| `feedbacks` | `id` | Sugestões, relatos de problema e elogios enviados pela Central de Ajuda. |

O `status` de uma coleta assume um destes valores: `executando`, `concluida` ou `falhou`.

### Enums nativos do PostgreSQL

| Enum | Valores | Usado em |
| :--- | :--- | :--- |
| `status_edital` | `aberto`, `encerrado` | `editais.status` |
| `tipo_documento` | `original`, `retificacao`, `resultado_provisorio`, `resultado_final` | `edital_documentos.tipo_documento` |
| `tipo_notificacao` | `edital_atualizado`, `prazo_encerrando` | `notificacoes.tipo` |
| `status_notificacao` | `pendente`, `enviada`, `falhou` | `notificacoes.status` |

## Migrations com Alembic

O histórico atual, em ordem:

| Revisão | O que faz |
| :--- | :--- |
| `0001_initial_schema` | Tabelas iniciais (`editais`, `edital_documentos`, `usuarios`, `favoritos`) e enums básicos. |
| `0002_notifications` | Tabela `notificacoes` e seus enums. |
| `0003_email_preference` | Coluna `usuarios.receber_emails`. |
| `0003_reconcilia_metadados` | Metadados dos editais, catálogos e tabela `coletas`. |
| `0004_merge_notification_metadata` | Junta as duas linhas de revisão `0003`. |
| `0005_alertas_edital` | Tabela `alertas_edital`, separando alertas de favoritos. |
| `0006_feedbacks` | Tabela `feedbacks`. |

Comandos do dia a dia, dentro de `Back/` com o ambiente virtual ativo:

```bash
alembic current                                    # revisão aplicada no banco
alembic heads                                      # deve listar uma única head
alembic upgrade head                               # aplica as migrations pendentes
alembic revision --autogenerate -m "descricao"     # gera uma nova migration
```

Com o projeto no Docker, troque `alembic ...` por `docker compose exec api alembic ...`.

### Regras para alterar o schema

1. Altere o modelo em `Back/app/core/database.py`.
2. Gere a migration com `alembic revision --autogenerate` e **leia o arquivo gerado** antes de aceitar.
3. Aplique em um PostgreSQL real com `alembic upgrade head`. Os testes unitários usam SQLite em memória e **não validam** enums nativos nem `CheckConstraint`.
4. Rode `alembic heads` e confirme que existe uma única head.
5. Nunca rode `alembic downgrade` em produção. Use só em banco local descartável.
6. Abra a PR com o modelo e a migration juntos.

## Ambientes

| Ambiente | Banco | Como o schema é criado |
| :--- | :--- | :--- |
| **Local (Docker Compose)** | `postgres:16-alpine`, volume `postgres_data` | A API roda `alembic upgrade head` ao iniciar |
| **Testes unitários** | SQLite em memória (`sqlite://`) | `Base.metadata.create_all` dentro de cada teste |
| **CI (GitHub Actions)** | Serviço `postgres:16-alpine` | `alembic upgrade head` e depois os seeds de `db/migrations/` |
| **Coleta periódica (GitHub Actions)** | Banco de produção | `alembic upgrade head` antes de cada ciclo |
| **Produção** | Neon Serverless, AWS São Paulo (`sa-east-1`) | `DATABASE_URL` definida no Render |

## Estrutura de pastas

```text
db/
├── README.md                          # este arquivo
└── migrations/
    ├── 001_initial_schema.sql         # legado: não é executado por nenhum ambiente
    ├── 002_seed_catalogos.sql         # seed de catálogos (usado pelo CI)
    └── 003_seed_editais.sql           # editais de demonstração (usado pelo CI)

Back/
├── app/core/database.py               # modelos SQLAlchemy e conexão
├── alembic.ini                        # configuração do Alembic
└── migrations/                        # revisões do Alembic (fonte da verdade do schema)
    ├── env.py
    └── versions/
```

> A pasta `db/migrations/` **não** define o schema. Ela guarda scripts SQL de apoio. O Compose não a monta no PostgreSQL, porque isso criaria as tabelas antes do Alembic e geraria conflito.

## Operação do dia a dia

### Ver o estado do banco

```bash
docker compose exec db psql -U fique_de_olho -d fique_de_olho
```

```sql
\dt                                               -- lista as 14 tabelas
SELECT * FROM alembic_version;                    -- revisão aplicada
SELECT status, COUNT(*) FROM editais GROUP BY status;
SELECT fonte, status, editais_encontrados, finalizada_em
  FROM coletas ORDER BY id DESC LIMIT 10;         -- últimas coletas
SELECT MAX(finalizada_em) FROM coletas
  WHERE status = 'concluida';                     -- o que o selo "Atualizado em" mostra
```

### Popular com editais reais

Com o banco vazio, o site não tem o que mostrar. Dispare uma coleta pela API:

```bash
curl -X POST "http://localhost:8000/api/v1/editais/sync?orgao=DEG&max_itens=5"
```

Sem o parâmetro `orgao`, a coleta percorre todos os portais. Mais detalhes em [Pipeline de coleta, PDF e IA](../docs/backend/coleta-e-ia.md).

### Backup e restauração

```bash
# backup
docker compose exec -T db pg_dump -U fique_de_olho -d fique_de_olho -Fc > backup.dump

# restauração (substitui os dados atuais)
docker compose exec -T db pg_restore -U fique_de_olho -d fique_de_olho --clean --if-exists < backup.dump
```

### Recriar o banco local do zero

```bash
docker compose down -v      # apaga o volume com os dados locais
docker compose up -d        # a API recria o schema com as migrations
```

> O `-v` **apaga todos os dados** do volume. Use apenas no seu ambiente local e nunca em um banco que tenha dados importantes.

## Solução de problemas

**`port is already allocated` ou `address already in use` na porta 5432 (ou 5433).**
Outro PostgreSQL ou um contêiner antigo está usando a porta. Veja quem é com `sudo ss -tlnp | grep 5432` e `docker ps -a`. Para evitar o conflito, crie um `.env` na raiz com `POSTGRES_PORT=55432`. A API continua falando com o banco pela rede interna do Docker, então nada mais muda.

**Contêiner ou volume de uma stack antiga.**
Uma configuração anterior usava o banco `fiquedeolho_db`, o usuário `fiquedeolho` e a porta `5433`. Se ela ainda existir na sua máquina, pare com `docker compose down` (sem `-v`) na pasta onde ela foi criada. Se houver dados a preservar, exporte com `pg_dump` antes de remover o volume.

**`Multiple head revisions are present`.**
Duas migrations partiram da mesma revisão. Rode `alembic heads` para ver quais são e crie uma revisão de merge com `alembic merge -m "merge" <head1> <head2>`. O histórico já passou por isso uma vez (`0004_merge_notification_metadata`).

**`relation "..." does not exist` ao iniciar a API fora do Docker.**
As migrations não foram aplicadas. Rode `alembic upgrade head` em `Back/`.

**`password authentication failed`.**
O volume foi criado com outras credenciais. Confira `POSTGRES_USER`, `POSTGRES_PASSWORD` e `POSTGRES_DB` no `.env` da raiz. Se mudou as credenciais depois de criar o volume, é preciso recriá-lo (`docker compose down -v`).

**O selo "Atualizado em" não aparece.**
Ele depende de pelo menos uma coleta registrada ou de editais com `atualizado_em`. Confira `GET /api/v1/editais/ultima-atualizacao`. Se retornar `{"ultima_atualizacao": null}`, o banco está vazio: veja [Popular com editais reais](#popular-com-editais-reais).

## Contribuindo

O Fique de Olho é um projeto de código aberto da disciplina de Métodos de Desenvolvimento de Software (UnB, 2026/2), e contribuições são bem-vindas. Antes de mexer no banco, leia as [regras para alterar o schema](#regras-para-alterar-o-schema) e a [referência completa do backend](../docs/backend/banco-de-dados.md). Para o guia geral do projeto, veja o [README principal](../README.md).

[Fique de Olho logo]: ../docs/assets/img/logo.svg
[site]: https://fique-de-olho.vercel.app
[CI badge]: https://img.shields.io/github/actions/workflow/status/unb-mds/G4-2026-2/pipeline.yml?branch=main&label=CI&logo=github&style=flat-square
[CI workflow]: https://github.com/unb-mds/G4-2026-2/actions/workflows/pipeline.yml
[PostgreSQL badge]: https://img.shields.io/badge/PostgreSQL-16-07143D?style=flat-square&logo=postgresql&logoColor=B9FC01
[PostgreSQL]: https://www.postgresql.org/
[SQLAlchemy badge]: https://img.shields.io/badge/SQLAlchemy-2.0-07143D?style=flat-square&logo=python&logoColor=B9FC01
[SQLAlchemy]: https://www.sqlalchemy.org/
[Alembic badge]: https://img.shields.io/badge/Alembic-migrations-0131CD?style=flat-square
[Alembic]: https://alembic.sqlalchemy.org/
[Neon badge]: https://img.shields.io/badge/Neon-Serverless-0131CD?style=flat-square&logo=neon&logoColor=white
[Neon]: https://neon.tech/