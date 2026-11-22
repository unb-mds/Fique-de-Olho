"""Add feedbacks table for user suggestions and issue reports (RF07).

Revision ID: 0006_feedbacks
Revises: 0005_alertas_edital
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_feedbacks"
down_revision = "0005_alertas_edital"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedbacks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tipo", sa.String(length=30), server_default="sugestao", nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("pagina", sa.String(length=255), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("feedbacks")
