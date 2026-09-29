# ADR 0003: Schema inicial do banco de dados

**Status:** aceito

O backend usa PostgreSQL com SQLAlchemy para persistir o schema inicial que sustenta editais, documentos, usuários e favoritos. O modelo foi mantido na infraestrutura compartilhada em `Back/app/core/database.py` para centralizar engine, sessões e metadados enquanto o backend ainda está em estágio inicial; os módulos de negócio poderão assumir seus modelos quando a integração crescer.

## Modelo de dados

| Tabela | Campos | Regras e finalidade |
| --- | --- | --- |
| `editais` | `id`, `titulo`, `url_pagina`, `campus`, `tipo`, `data_publicacao`, `status`, `created_at` | `campus` e `tipo` são opcionais. `url_pagina` é única para evitar duplicidade na coleta incremental. A aplicação usa `aberto` ou `encerrado`; os rótulos do enum nativo do PostgreSQL são `ABERTO` e `ENCERRADO`. |
| `edital_documentos` | `id`, `edital_id`, `url_pdf`, `tipo_documento`, `created_at` | `edital_id` referencia `editais.id`. A aplicação usa `original`, `resultado_provisorio`, `resultado_final` ou `retificacao`; os rótulos do enum nativo do PostgreSQL são `ORIGINAL`, `RESULTADO_PROVISORIO`, `RESULTADO_FINAL` ou `RETIFICACAO`. Um edital pode ter vários documentos. |
| `usuarios` | `id`, `nome`, `email`, `senha_hash`, `created_at` | `email` é único. `senha_hash` guarda o hash da senha, nunca a senha em texto puro. |
| `favoritos` | `usuario_id`, `edital_id`, `created_at` | Os IDs referenciam `usuarios.id` e `editais.id`; juntos formam a chave primária, evitando favoritos duplicados para o mesmo par usuário/edital. |

As chaves primárias `id` das três entidades são inteiras. Os timestamps `created_at` usam `server_default=func.now()`. As relações ORM expõem documentos e favoritos a partir de edital e favoritos a partir de usuário. Os relacionamentos configuram exclusão em cascata na camada ORM (`delete-orphan`); exclusões via SQL direto devem ser tratadas com cuidado, pois as foreign keys não declaram `ON DELETE CASCADE`.

## Decisões

- `url_pagina` é única porque a coleta incremental identifica o edital pela página de origem e precisa evitar inserções repetidas.
- `status` e `tipo_documento` são enums para restringir gravações aos valores aceitos pelo domínio. Isso facilita consistência, mas exige uma migração ao adicionar ou renomear valores no PostgreSQL.
- `favoritos` usa chave primária composta porque a identidade do vínculo é o par usuário/edital; não há necessidade de um ID artificial para esse relacionamento.
- O driver `psycopg2` é indicado explicitamente nas URLs de conexão para corresponder à dependência instalada (`psycopg2-binary`).
- Alembic será a única fonte de mudanças no schema. O startup da API não deve criar ou atualizar tabelas; bancos vazios aplicam a migration inicial com `alembic upgrade head`, enquanto bancos existentes compatíveis com ela registram a revisão com `alembic stamp head`, sem executar DDL e preservando os dados.
- `alembic stamp` não verifica a estrutura existente; antes de adotá-la, é necessário confirmar que o schema corresponde à revisão inicial e fazer backup.
- O `downgrade` da migration inicial remove as tabelas; sua validação deve ocorrer apenas em banco descartável, nunca em produção com dados.
- A validação das migrations deve usar PostgreSQL real via Docker Compose; testes em SQLite não substituem essa verificação.

## Alterações no banco e no backend

- **Schema (`Back/app/core/database.py`):** foram definidos os modelos ORM de edital, documento, usuário e favorito, os enums de status/tipo, as chaves estrangeiras, a chave composta do favorito e a unicidade da URL do edital. Isso transforma os requisitos de busca, status, PDF e favoritos em uma estrutura relacional verificável.
- **Inicialização (`Back/app/main.py`):** o startup da API não cria nem atualiza tabelas; a revisão Alembic deve ser aplicada explicitamente antes de usar o schema.
- **Conexão (`Back/app/core/config.py`, `Back/.env.example` e `Back/docker-compose.yml`):** as URLs declaram `postgresql+psycopg2`, alinhadas ao driver instalado pelo projeto. Isso evita que o SQLAlchemy tente carregar outro driver PostgreSQL e mantém coerente a conexão local e a conexão entre containers.
- **Testes (`Back/tests/test_database_schema.py`):** os testes verificam a estrutura e relações em SQLite em memória e garantem que o startup não crie tabelas. Upgrade e downgrade são validados separadamente em PostgreSQL real via Docker Compose.

## Limites e evolução

Toda alteração futura de schema deve ser representada por uma revisão Alembic e aplicada explicitamente. A adoção de um banco anterior exige confirmar compatibilidade com a revisão inicial antes de usar `stamp`; o downgrade inicial remove as tabelas e não deve ser executado em bancos com dados a preservar. A integração de consultas e gravações ainda precisa ser conectada às rotas/serviços que forem implementando os casos de uso.

## Fluxo de inicialização e validação

Para iniciar o PostgreSQL, aplicar migrations e conferir o estado do schema, seguir a seção **Banco de Dados** do README do backend (`Back/README.md`). Os testes em `Back/tests/test_database_schema.py` validam metadados e relações em SQLite e garantem que o startup não inicialize tabelas; validar upgrade e downgrade em PostgreSQL real continua obrigatório.

