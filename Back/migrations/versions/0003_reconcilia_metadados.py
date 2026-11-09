"""Reconcilia o schema com os models e adiciona metadados da Issue 52.

Revision ID: 0003_reconcilia_metadados
Revises: 0002_notifications
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_reconcilia_metadados"
down_revision = "0002_notifications"
branch_labels = None
depends_on = None

STATUS_EDITAL = postgresql.ENUM(
    "ABERTO", "ENCERRADO", name="status_edital", create_type=False
)


def _catalogo(nome_tabela: str, tamanho: int) -> None:
    op.create_table(
        nome_tabela,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nome", sa.String(length=tamanho), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nome"),
    )


def _associacao(tabela: str, outra_col: str, outra_tabela: str) -> None:
    op.create_table(
        tabela,
        sa.Column("edital_id", sa.Integer(), nullable=False),
        sa.Column(outra_col, sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["edital_id"], ["editais.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint([outra_col], [f"{outra_tabela}.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("edital_id", outra_col),
    )


def upgrade() -> None:
    # 1) Catálogos e tabelas associativas
    _catalogo("tipos_editais", 100)
    _catalogo("campi", 100)
    _catalogo("cursos", 200)
    _associacao("edital_tipos", "tipo_edital_id", "tipos_editais")
    _associacao("edital_campi", "campus_id", "campi")
    _associacao("edital_cursos", "curso_id", "cursos")

    # 2) Histórico de coletas do scraper
    op.create_table(
        "coletas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fonte", sa.String(length=100), server_default="DEG", nullable=False),
        sa.Column(
            "iniciada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finalizada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="executando", nullable=False),
        sa.Column("editais_encontrados", sa.Integer(), server_default="0", nullable=False),
        sa.Column("mensagem_erro", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # 3) Ajustes em colunas existentes da tabela editais
    op.alter_column(
        "editais",
        "titulo",
        existing_type=sa.String(length=255),
        type_=sa.String(length=500),
        existing_nullable=False,
    )
    op.alter_column(
        "editais",
        "data_publicacao",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.alter_column(
        "editais",
        "status",
        existing_type=STATUS_EDITAL,
        nullable=True,
    )
    op.alter_column(
        "editais",
        "url_pagina",
        existing_type=sa.String(length=500),
        nullable=True,
    )

    # 4) Colunas de reconciliação do schema
    op.add_column("editais", sa.Column("identificador_origem", sa.String(length=200), nullable=True))
    op.add_column(
        "editais",
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )
    op.add_column(
        "editais",
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )

    op.create_unique_constraint("uq_editais_identificador_origem", "editais", ["identificador_origem"])
    op.create_unique_constraint("uq_editais_url_pdf", "editais", ["url_pdf"])

    op.create_check_constraint(
        "editais_periodo_inscricao_ck",
        "editais",
        "inicio_inscricao IS NULL OR fim_inscricao IS NULL OR inicio_inscricao <= fim_inscricao",
    )
    op.create_check_constraint(
        "editais_status_processamento_ck",
        "editais",
        "status_processamento IN ('pendente', 'processado', 'parcialmente_processado', 'erro')",
    )

    # 5) Metadados estruturados da Issue #52
    op.add_column("editais", sa.Column("orgao_emissor", sa.String(length=50), nullable=True))
    op.create_index("ix_editais_orgao_emissor", "editais", ["orgao_emissor"])
    op.add_column("editais", sa.Column("assunto", sa.Text(), nullable=True))
    op.add_column("editais", sa.Column("vagas", sa.Integer(), nullable=True))
    op.add_column("editais", sa.Column("valor_bolsa", sa.Numeric(10, 2), nullable=True))

    # 6) Busca textual full-text search
    op.execute(
        """
        ALTER TABLE editais ADD COLUMN busca_documento tsvector
        GENERATED ALWAYS AS (
            to_tsvector('portuguese',
                COALESCE(titulo, '') || ' ' || COALESCE(resumo, '') || ' ' || COALESCE(texto_extraido, ''))
        ) STORED
        """
    )
    op.execute("CREATE INDEX editais_busca_documento_gin_idx ON editais USING GIN (busca_documento)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS editais_busca_documento_gin_idx")
    op.execute("ALTER TABLE editais DROP COLUMN IF EXISTS busca_documento")

    op.drop_column("editais", "valor_bolsa")
    op.drop_column("editais", "vagas")
    op.drop_column("editais", "assunto")
    op.drop_index("ix_editais_orgao_emissor", table_name="editais")
    op.drop_column("editais", "orgao_emissor")

    op.drop_constraint("editais_status_processamento_ck", "editais", type_="check")
    op.drop_constraint("editais_periodo_inscricao_ck", "editais", type_="check")
    op.drop_constraint("uq_editais_url_pdf", "editais", type_="unique")
    op.drop_constraint("uq_editais_identificador_origem", "editais", type_="unique")

    op.drop_column("editais", "atualizado_em")
    op.drop_column("editais", "criado_em")
    op.drop_column("editais", "identificador_origem")

    op.alter_column(
        "editais",
        "url_pagina",
        existing_type=sa.String(length=500),
        nullable=False,
    )
    op.alter_column(
        "editais",
        "status",
        existing_type=STATUS_EDITAL,
        nullable=False,
    )
    op.alter_column(
        "editais",
        "data_publicacao",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "editais",
        "titulo",
        existing_type=sa.String(length=500),
        type_=sa.String(length=255),
        existing_nullable=False,
    )

    op.drop_table("coletas")
    op.drop_table("edital_cursos")
    op.drop_table("edital_campi")
    op.drop_table("edital_tipos")
    op.drop_table("cursos")
    op.drop_table("campi")
    op.drop_table("tipos_editais")
