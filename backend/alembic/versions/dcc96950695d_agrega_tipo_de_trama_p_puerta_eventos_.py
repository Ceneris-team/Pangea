"""agrega tipo de trama P (puerta/eventos de acceso) a mp_frmt

Revision ID: dcc96950695d
Revises: c3d5e7a91b44
Create Date: 2026-08-21 12:35:08.357682

Un tercer tipo de archivo real de campo, distinto de H_ (datos
periódicos) y E_ (estados/eventos del gabinete): P_*.dat trae eventos
de puerta/acceso (columnas Fecha,R,MensajeP,MensajeA). Postgres no
soporta ALTER de un CHECK existente, así que se reemplaza por uno
nuevo con el valor agregado (mismo patrón que c8d47a2b6f13, que ya
dejaba anotado "espacio a más tipos de trama si el equipo de
telemetría los define más adelante").
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'dcc96950695d'
down_revision: Union[str, Sequence[str], None] = 'c3d5e7a91b44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("mpfrmt_tptrm_check", "mp_frmt", type_="check")
    op.create_check_constraint(
        "mpfrmt_tptrm_check",
        "mp_frmt",
        "tp_trm IN ('H','E','P')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("mpfrmt_tptrm_check", "mp_frmt", type_="check")
    op.create_check_constraint(
        "mpfrmt_tptrm_check",
        "mp_frmt",
        "tp_trm IN ('H','E')",
    )
