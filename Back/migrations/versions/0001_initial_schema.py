"""Create the initial Fique de Olho schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    status_edital = postgresql.ENUM("ABERTO", "ENCERRADO", name="status_edital")
    tipo_documento = postgresql.ENUM(
        "ORIGINAL",
        "RESULTADO_PROVISORIO",
        "RESULTADO_FINAL",
        "RETIFICACAO",
        name="tipo_documento",
    )
    status_edital.create(bind, checkfirst=True)
    tipo_documento.create(bind, checkfirst=True)

    op.create_table(
        "editais",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("url_pagina", sa.String(length=500), nullable=False),
        sa.Column("campus", sa.String(length=255), nullable=True),
        sa.Column("tipo", sa.String(length=100), nullable=True),
        sa.Column("data_publicacao", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "ABERTO", "ENCERRADO", name="status_edital", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_editais_id", "editais", ["id"], unique=False)
    op.create_index("ix_editais_url_pagina", "editais", ["url_pagina"], unique=True)

    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("senha_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usuarios_id", "usuarios", ["id"], unique=False)
    op.create_index("ix_usuarios_email", "usuarios", ["email"], unique=True)

    op.create_table(
        "edital_documentos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edital_id", sa.Integer(), nullable=False),
        sa.Column("url_pdf", sa.String(length=500), nullable=False),
        sa.Column(
            "tipo_documento",
            postgresql.ENUM(
                "ORIGINAL",
                "RESULTADO_PROVISORIO",
                "RESULTADO_FINAL",
                "RETIFICACAO",
                name="tipo_documento",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["edital_id"], ["editais.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_edital_documentos_id", "edital_documentos", ["id"], unique=False)
    op.create_index(
        "ix_edital_documentos_edital_id", "edital_documentos", ["edital_id"], unique=False
    )

    op.create_table(
        "favoritos",
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("edital_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["edital_id"], ["editais.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("usuario_id", "edital_id"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("favoritos")
    op.drop_index("ix_edital_documentos_edital_id", table_name="edital_documentos")
    op.drop_index("ix_edital_documentos_id", table_name="edital_documentos")
    op.drop_table("edital_documentos")
    op.drop_index("ix_usuarios_email", table_name="usuarios")
    op.drop_index("ix_usuarios_id", table_name="usuarios")
    op.drop_table("usuarios")
    op.drop_index("ix_editais_url_pagina", table_name="editais")
    op.drop_index("ix_editais_id", table_name="editais")
    op.drop_table("editais")
    postgresql.ENUM(name="tipo_documento").drop(bind, checkfirst=True)
    postgresql.ENUM(name="status_edital").drop(bind, checkfirst=True)