# ADR 0003: Schema inicial do banco de dados

**Status:** aceito

O backend usa PostgreSQL com SQLAlchemy para persistir o schema inicial que sustenta editais, documentos, usuários e favoritos. O modelo foi mantido na infraestrutura compartilhada em `Back/app/core/database.py` para centralizar engine, sessões e metadados enquanto o backend ainda está em estágio inicial; os módulos de negócio poderão assumir seus modelos quando a integração crescer.

## Modelo de dados

| Tabela | Campos | Regras e finalidade |
| --- | --- | --- |
| `editais` | `id`, `titulo`, `url_pagina`, `campus`, `tipo`, `data_publicacao`, `status`, `created_at` | `campus` e `tipo` são opcionais. `url_pagina` é única para evitar duplicidade na coleta incremental. `status` aceita `aberto` ou `encerrado`. |
| `edital_documentos` | `id`, `edital_id`, `url_pdf`, `tipo_documento`, `created_at` | `edital_id` referencia `editais.id`. `tipo_documento` aceita `original`, `resultado_provisorio`, `resultado_final` ou `retificacao`. Um edital pode ter vários documentos. |
| `usuarios` | `id`, `nome`, `email`, `senha_hash`, `created_at` | `email` é único. `senha_hash` guarda o hash da senha, nunca a senha em texto puro. |
| `favoritos` | `usuario_id`, `edital_id`, `created_at` | Os IDs referenciam `usuarios.id` e `editais.id`; juntos formam a chave primária, evitando favoritos duplicados para o mesmo par usuário/edital. |

As chaves primárias `id` das três entidades são inteiras. Os timestamps `created_at` usam `server_default=func.now()`. As relações ORM expõem documentos e favoritos a partir de edital e favoritos a partir de usuário. Os relacionamentos configuram exclusão em cascata na camada ORM (`delete-orphan`); exclusões via SQL direto devem ser tratadas com cuidado, pois as foreign keys não declaram `ON DELETE CASCADE`.

## Decisões

- `url_pagina` é única porque a coleta incremental identifica o edital pela página de origem e precisa evitar inserções repetidas.
- `status` e `tipo_documento` são enums para restringir gravações aos valores aceitos pelo domínio. Isso facilita consistência, mas exige uma migração ao adicionar ou renomear valores no PostgreSQL.
- `favoritos` usa chave primária composta porque a identidade do vínculo é o par usuário/edital; não há necessidade de um ID artificial para esse relacionamento.
- O driver `psycopg2` é indicado explicitamente nas URLs de conexão para corresponder à dependência instalada (`psycopg2-binary`).
- `init_db()` usa `Base.metadata.create_all()` no lifespan do FastAPI para criar tabelas ausentes no primeiro startup. A função registra erro de banco como aviso e permite que a API continue; por isso, `/health` não garante que o banco esteja conectado nem que o schema exista.

## Alterações no banco e no backend

- **Schema (`Back/app/core/database.py`):** foram definidos os modelos ORM de edital, documento, usuário e favorito, os enums de status/tipo, as chaves estrangeiras, a chave composta do favorito e a unicidade da URL do edital. Isso transforma os requisitos de busca, status, PDF e favoritos em uma estrutura relacional verificável.
- **Inicialização (`Back/app/main.py`):** o lifespan do FastAPI chama `init_db()` ao iniciar a aplicação; assim, tabelas ausentes são criadas sem exigir um comando manual separado em um banco novo.
- **Conexão (`Back/app/core/config.py`, `Back/.env.example` e `Back/docker-compose.yml`):** as URLs declaram `postgresql+psycopg2`, alinhadas ao driver instalado pelo projeto. Isso evita que o SQLAlchemy tente carregar outro driver PostgreSQL e mantém coerente a conexão local e a conexão entre containers.
- **Testes (`Back/tests/test_database_schema.py`):** os testes verificam a estrutura, criam entidades relacionadas em SQLite em memória e confirmam que o lifespan chama a inicialização. SQLite permite testar o contrato sem depender de um servidor durante a suíte; a validação real de conexão e criação no PostgreSQL continua sendo uma checagem operacional documentada no README.

## Limites e evolução

`create_all()` não altera tabelas existentes nem substitui um sistema de migrações. Até existir uma ferramenta de migração, alterações em schema já usado precisam ser planejadas e aplicadas explicitamente para não perder ou invalidar dados. O schema está definido e pode ser inicializado; a integração de consultas e gravações ainda precisa ser conectada às rotas/serviços que forem implementando os casos de uso.

## Fluxo de inicialização e validação

Para iniciar o PostgreSQL e a API, configurar ambiente e conferir as tabelas, seguir a seção **Banco de Dados** do README do backend (`Back/README.md`). Os testes focados estão em `Back/tests/test_database_schema.py`: validam metadados e relações em SQLite em memória, além de verificar que o lifespan chama a função de inicialização. Eles não substituem um teste de integração contra PostgreSQL.

