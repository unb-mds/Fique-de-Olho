"""Completa o schema para persistir tudo o que os scrapers coletam.

- editais: area, link_inscricao, numero e metadados (JSONB) + índices de filtro
- editais: identificador_origem deixa de ser UNIQUE global (vira índice composto por órgão)
- edital_documentos: titulo, url_pdf como TEXT, UNIQUE (edital_id, url_pdf), FK com CASCADE
- favoritos: FKs com ON DELETE CASCADE
- coletas: novos_editais e editais_atualizados
- editais.status_processamento: server_default alinhado com o model ('pendente')

Revision ID: 0005_scraper_persistencia
Revises: 0004_merge_notification_metadata
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_scraper_persistencia"
down_revision = "0004_merge_notification_metadata"
branch_labels = None
depends_on = None


def _recriar_fk(
    tabela: str,
    coluna: str,
    tabela_ref: str,
    ondelete: str | None,
) -> None:
    """Remove a FK existente da coluna (qualquer que seja o nome) e a recria com o ondelete dado."""
    inspetor = sa.inspect(op.get_bind())
    for fk in inspetor.get_foreign_keys(tabela):
        if fk["constrained_columns"] == [coluna] and fk["name"]:
            op.drop_constraint(fk["name"], tabela, type_="foreignkey")
    op.create_foreign_key(
        f"{tabela}_{coluna}_fkey",
        tabela,
        tabela_ref,
        [coluna],
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    # 1) editais: campos que o Front filtra/exibe e metadados variáveis por portal
    op.add_column("editais", sa.Column("area", sa.String(length=100), nullable=True))
    op.add_column("editais", sa.Column("link_inscricao", sa.Text(), nullable=True))
    op.add_column("editais", sa.Column("numero", sa.String(length=100), nullable=True))
    op.add_column("editais", sa.Column("metadados", postgresql.JSONB(), nullable=True))

    op.create_index("ix_editais_area", "editais", ["area"])
    op.create_index("ix_editais_campus", "editais", ["campus"])
    op.create_index(
        "ix_editais_metadados_gin", "editais", ["metadados"], postgresql_using="gin"
    )

    # 2) identificador_origem: UNIQUE global -> índice composto (IDs de portais podem coincidir)
    op.drop_constraint("uq_editais_identificador_origem", "editais", type_="unique")
    op.create_index(
        "ix_editais_orgao_identificador", "editais", ["orgao_emissor", "identificador_origem"]
    )

    # 3) status_processamento: o model usa 'pendente'; a migration 0002 tinha criado com 'processado'
    op.alter_column(
        "editais", "status_processamento", server_default=sa.text("'pendente'")
    )

    # 4) edital_documentos: título, URL sem limite de 500 chars e sem duplicatas por edital
    op.add_column("edital_documentos", sa.Column("titulo", sa.String(length=500), nullable=True))
    op.alter_column(
        "edital_documentos",
        "url_pdf",
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=False,
    )
    # Remove duplicatas já gravadas (mantém a linha mais antiga) antes de criar a UNIQUE
    op.execute(
        """
        DELETE FROM edital_documentos d
        USING edital_documentos outro
        WHERE d.edital_id = outro.edital_id
          AND d.url_pdf = outro.url_pdf
          AND d.id > outro.id
        """
    )
    op.create_unique_constraint(
        "uq_edital_documento_url", "edital_documentos", ["edital_id", "url_pdf"]
    )

    # 5) FKs com ON DELETE CASCADE (o ORM já fazia cascade; o banco agora também garante)
    _recriar_fk("edital_documentos", "edital_id", "editais", "CASCADE")
    _recriar_fk("favoritos", "edital_id", "editais", "CASCADE")
    _recriar_fk("favoritos", "usuario_id", "usuarios", "CASCADE")

    # 6) coletas: guarda o que o service já calculava
    op.add_column(
        "coletas",
        sa.Column("novos_editais", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "coletas",
        sa.Column("editais_atualizados", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("coletas", "editais_atualizados")
    op.drop_column("coletas", "novos_editais")

    _recriar_fk("favoritos", "usuario_id", "usuarios", None)
    _recriar_fk("favoritos", "edital_id", "editais", None)
    _recriar_fk("edital_documentos", "edital_id", "editais", None)

    op.drop_constraint("uq_edital_documento_url", "edital_documentos", type_="unique")
    op.alter_column(
        "edital_documentos",
        "url_pdf",
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=False,
        postgresql_using="left(url_pdf, 500)",
    )
    op.drop_column("edital_documentos", "titulo")

    op.alter_column(
        "editais", "status_processamento", server_default=sa.text("'processado'")
    )

    op.drop_index("ix_editais_orgao_identificador", table_name="editais")
    op.create_unique_constraint(
        "uq_editais_identificador_origem", "editais", ["identificador_origem"]
    )

    op.drop_index("ix_editais_metadados_gin", table_name="editais")
    op.drop_index("ix_editais_campus", table_name="editais")
    op.drop_index("ix_editais_area", table_name="editais")
    op.drop_column("editais", "metadados")
    op.drop_column("editais", "numero")
    op.drop_column("editais", "link_inscricao")
    op.drop_column("editais", "area")