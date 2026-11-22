---
status: accepted
---

# ADR 0006 — Evolução do Schema: Catálogos M:N, Alertas Desacoplados de Favoritos e Notificações Idempotentes

A [ADR 0003](0003-database-schema.md) definiu o schema inicial de 4 tabelas (`editais`, `edital_documentos`, `usuarios`, `favoritos`). Com a expansão para 33 portais, filtros combinados e envio real de e-mails via SendGrid, evoluímos o schema (via revisões Alembic `0002` a `0005`) para **13 tabelas**, separando explicitamente **`alertas_edital`** de **`favoritos`**, introduzindo catálogos controlados M:N (`tipos_editais`, `campi`, `cursos`), registrando histórico de `coletas` e garantindo entrega idempotente de `notificacoes` com `UniqueConstraint (usuario_id, edital_id, tipo, chave_evento)`.

## Opções consideradas

- **Disparar e-mails automaticamente para todo item em `favoritos`:** mais simples no schema, mas gera spam para estudantes que querem apenas salvar editais para consulta sem receber e-mails de cada alteração.
- **Deduplicar notificações apenas em memória ou no scheduler:** falha após reinicializações/hibernação do container no Render Free, causando e-mails duplicados.
- **Manter apenas colunas texto (`campus`, `tipo`) em `editais` sem tabelas de catálogo:** impede evolução futura para filtros normalizados multi-valor por curso e campus.

## Consequências

- O glossário de domínio (`CONTEXT.md`) e a API distinguem claramente **Favorito** (`/favoritar`) de **Alerta de Edital** (`/alertas`), respeitando também o opt-out global `usuarios.receber_emails`.
- O scheduler de notificações pode rodar a cada hora (ou reiniciar com cold starts do Render) com garantia de banco de que cada atualização (`hash_conteudo`) ou marco de prazo (`3d`, `1d`, `0d` em UTC-3) gera no máximo um registro por usuário/edital.
- A [ADR 0003](0003-database-schema.md) permanece como registro histórico das decisões fundacionais (enums PostgreSQL, unicidade de `url_pagina` e governança exclusiva via Alembic), complementada por esta decisão.
