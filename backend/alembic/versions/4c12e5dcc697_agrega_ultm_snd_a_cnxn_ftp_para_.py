"""agrega ultm_snd a cnxn_ftp para respetar frcnc_mnts en el sondeo (HT-05)

Revision ID: 4c12e5dcc697
Revises: eadc512979fc
Create Date: 2026-07-24 10:51:47.401925

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4c12e5dcc697'
down_revision: Union[str, Sequence[str], None] = 'eadc512979fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('cnxn_ftp', sa.Column('ultm_snd', sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('cnxn_ftp', 'ultm_snd')
