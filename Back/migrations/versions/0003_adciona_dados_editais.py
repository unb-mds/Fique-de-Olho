"""Adiciona órgão emissor, vagas e valor da bolsa em editais.

Revision ID: 0003_adiciona_metadados_editais
Revises: 0002_reconcilia_schema
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_adiciona_metadados_editais"
down_revision = "0002_reconcilia_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("editais", sa.Column("orgao_emissor", sa.String(length=50), nullable=True))
    op.add_column("editais", sa.Column("vagas", sa.Integer(), nullable=True))
    op.add_column("editais", sa.Column("valor_bolsa", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("editais", "valor_bolsa")
    op.drop_column("editais", "vagas")
    op.drop_column("editais", "orgao_emissor")