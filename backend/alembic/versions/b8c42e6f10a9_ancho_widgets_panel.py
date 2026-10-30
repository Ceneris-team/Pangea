"""Permitir widgets de una o dos columnas en paneles personalizados."""

import sqlalchemy as sa

from alembic import op

revision = "b8c42e6f10a9"
down_revision = "e6a91b03d724"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("wdgt", sa.Column("ancho", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint("wdgt_ancho_check", "wdgt", "ancho IN (1, 2)")


def downgrade():
    op.drop_constraint("wdgt_ancho_check", "wdgt", type_="check")
    op.drop_column("wdgt", "ancho")
