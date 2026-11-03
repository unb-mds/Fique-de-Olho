"""Add notifications for edital changes and deadlines.

Revision ID: 0002_notifications
Revises: 0001_initial_schema
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_notifications"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("editais", sa.Column("resumo", sa.Text(), nullable=True))
    op.add_column("editais", sa.Column("url_pdf", sa.String(length=500), nullable=True))
    op.add_column("editais", sa.Column("texto_extraido", sa.Text(), nullable=True))
    op.add_column("editais", sa.Column("inicio_inscricao", sa.Date(), nullable=True))
    op.add_column("editais", sa.Column("fim_inscricao", sa.Date(), nullable=True))
    op.add_column(
        "editais",
        sa.Column(
            "status_processamento",
            sa.String(length=30),
            nullable=False,
            server_default="processado",
        ),
    )
    op.add_column("editais", sa.Column("hash_conteudo", sa.String(length=64), nullable=True))
    op.create_index("ix_editais_fim_inscricao", "editais", ["fim_inscricao"])

    tipo_notificacao = postgresql.ENUM(
        "edital_atualizado",
        "prazo_encerrando",
        name="tipo_notificacao",
    )
    status_notificacao = postgresql.ENUM(
        "pendente",
        "enviada",
        "falhou",
        name="status_notificacao",
    )
    bind = op.get_bind()
    tipo_notificacao.create(bind, checkfirst=True)
    status_notificacao.create(bind, checkfirst=True)

    op.create_table(
        "notificacoes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("edital_id", sa.Integer(), nullable=False),
        sa.Column(
            "tipo",
            postgresql.ENUM(
                "edital_atualizado",
                "prazo_encerrando",
                name="tipo_notificacao",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pendente",
                "enviada",
                "falhou",
                name="status_notificacao",
                create_type=False,
            ),
            nullable=False,
            server_default="pendente",
        ),
        sa.Column("chave_evento", sa.String(length=128), nullable=False),
        sa.Column("enviada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["edital_id"], ["editais.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "usuario_id",
            "edital_id",
            "tipo",
            "chave_evento",
            name="uq_notificacao_evento",
        ),
    )
    op.create_index("ix_notificacoes_usuario_id", "notificacoes", ["usuario_id"])
    op.create_index("ix_notificacoes_edital_id", "notificacoes", ["edital_id"])


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("ix_notificacoes_edital_id", table_name="notificacoes")
    op.drop_index("ix_notificacoes_usuario_id", table_name="notificacoes")
    op.drop_table("notificacoes")
    postgresql.ENUM(name="status_notificacao").drop(bind, checkfirst=True)
    postgresql.ENUM(name="tipo_notificacao").drop(bind, checkfirst=True)
    op.drop_index("ix_editais_fim_inscricao", table_name="editais")
    op.drop_column("editais", "hash_conteudo")
    op.drop_column("editais", "status_processamento")
    op.drop_column("editais", "fim_inscricao")
    op.drop_column("editais", "inicio_inscricao")
    op.drop_column("editais", "texto_extraido")
    op.drop_column("editais", "url_pdf")
    op.drop_column("editais", "resumo")
