"""agrega descripcion a mp_frmt

Revision ID: 6ccd31c550dd
Revises: c4680495205f
Create Date: 2026-08-21 16:20:00.000000

Con tp_trm como letra libre (c4680495205f), una letra que no es H/E/P ya
no se explica sola en la UI -nadie sabe qué es "X" sin abrir el mapeo y
mirar las columnas-. Se agrega una descripción corta y opcional, mismo
patrón que prmtr.dscrpcn.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6ccd31c550dd'
down_revision: Union[str, Sequence[str], None] = 'c4680495205f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("mp_frmt", sa.Column("dscrpcn", sa.String(length=200), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("mp_frmt", "dscrpcn")
