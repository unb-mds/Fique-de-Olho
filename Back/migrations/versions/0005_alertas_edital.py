"""Add per-edital email notification subscriptions (alertas_edital).

Revision ID: 0005_alertas_edital
Revises: 0004_merge_notification_metadata
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_alertas_edital"
down_revision = "0004_merge_notification_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alertas_edital",
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("edital_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["edital_id"], ["editais.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("usuario_id", "edital_id"),
    )
    op.create_index("ix_alertas_edital_edital_id", "alertas_edital", ["edital_id"])


def downgrade() -> None:
    op.drop_index("ix_alertas_edital_edital_id", table_name="alertas_edital")
    op.drop_table("alertas_edital")
