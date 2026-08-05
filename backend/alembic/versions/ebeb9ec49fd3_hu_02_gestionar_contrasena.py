"""HU 02 - gestionar contraseña: tabla tkn_rcprcn y usr.fch_cntrsn_actlzd

Revision ID: ebeb9ec49fd3
Revises: 286308e821ed
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ebeb9ec49fd3'
down_revision: Union[str, Sequence[str], None] = '286308e821ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('usr', sa.Column('fch_cntrsn_actlzd', sa.TIMESTAMP(timezone=True), nullable=True))

    op.create_table('tkn_rcprcn',
    sa.Column('id_tkn', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('id_usr', sa.Integer(), nullable=False),
    sa.Column('tkn', sa.String(length=255), nullable=False),
    sa.Column('fch_crcn', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    sa.Column('fch_exp', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('usad', sa.Boolean(), server_default='false', nullable=False),
    sa.ForeignKeyConstraint(['id_usr'], ['usr.id_usr'], ),
    sa.PrimaryKeyConstraint('id_tkn'),
    sa.UniqueConstraint('tkn')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('tkn_rcprcn')
    op.drop_column('usr', 'fch_cntrsn_actlzd')
