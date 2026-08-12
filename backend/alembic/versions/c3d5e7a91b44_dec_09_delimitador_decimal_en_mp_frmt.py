"""DEC-09: delimitador decimal configurable por mapeo

Revision ID: c3d5e7a91b44
Revises: b71f4a9c2e05
Create Date: 2026-08-12 14:10:00.000000

La pestaña FORMATO de la ficha del dispositivo expone "Delimitador
decimal" junto al delimitador de columna. Hasta ahora el motor asumía
punto: validador._parsear_numero() hacía float(valor) directo, así que un
datalogger configurado en locale europeo ("23,5") producía "valor no es
numérico" en cada fila y el archivo entero se registraba como error de
validación sin causa evidente.

Se guarda por mapeo y no global porque conviven dataloggers de distinta
procedencia en la misma sede, que es justamente la premisa de DEC-09.

El default '.' preserva el comportamiento actual de los mapeos ya
cargados: la columna es NOT NULL con server_default, así que las filas
existentes quedan explícitamente en punto, sin cambio de conducta.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d5e7a91b44'
down_revision: Union[str, Sequence[str], None] = 'b71f4a9c2e05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'mp_frmt',
        sa.Column(
            'dlmtdr_dcml', sa.String(length=1), nullable=False, server_default='.',
        ),
    )
    # Solo punto o coma: son los dos separadores decimales que produce un
    # datalogger real, y el motor traduce la coma a punto antes de float().
    op.create_check_constraint(
        'mpfrmt_dlmtdrdcml_check', 'mp_frmt', "dlmtdr_dcml IN ('.', ',')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('mpfrmt_dlmtdrdcml_check', 'mp_frmt', type_='check')
    op.drop_column('mp_frmt', 'dlmtdr_dcml')
