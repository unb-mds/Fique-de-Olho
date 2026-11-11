"""Merge the notification and metadata migration branches.

Revision ID: 0004_merge_notification_metadata
Revises: 0003_email_preference, 0003_reconcilia_metadados
"""

revision = "0004_merge_notification_metadata"
down_revision = ("0003_email_preference", "0003_reconcilia_metadados")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
