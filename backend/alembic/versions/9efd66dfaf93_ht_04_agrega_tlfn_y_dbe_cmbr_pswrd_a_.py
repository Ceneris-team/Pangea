"""HT-04: agrega tlfn y dbe_cmbr_pswrd a usr (HU04)

Revision ID: 9efd66dfaf93
Revises: d5916c328806
Create Date: 2026-07-24 17:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9efd66dfaf93'
down_revision: Union[str, Sequence[str], None] = 'd5916c328806'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('usr', sa.Column('tlfn', sa.String(length=20), nullable=True))
    # server_default 'true' cubre usuarios existentes al momento de migrar
    # (asume que deben cambiar su contraseña actual); el default de columna
    # queda igual para altas futuras vía HU04.
    op.add_column(
        'usr',
        sa.Column('dbe_cmbr_pswrd', sa.Boolean(), server_default='true', nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('usr', 'dbe_cmbr_pswrd')
    op.drop_column('usr', 'tlfn')
