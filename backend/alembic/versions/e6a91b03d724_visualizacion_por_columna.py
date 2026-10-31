"""Significado y vista por columna de cada datalogger."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "e6a91b03d724"
down_revision = "d9406bc12a85"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mp_clmn", sa.Column("visualizacion", JSONB(), nullable=True))


def downgrade():
    op.drop_column("mp_clmn", "visualizacion")
