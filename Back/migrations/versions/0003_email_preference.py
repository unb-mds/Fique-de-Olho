"""Add user email notification preference.

Revision ID: 0003_email_preference
Revises: 0002_notifications
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_email_preference"
down_revision = "0002_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usuarios",
        sa.Column(
            "receber_emails",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("usuarios", "receber_emails")
