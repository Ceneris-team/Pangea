"""PP-96: agrega tp_trm a mp_frmt para distinguir tramas H_ y E_

Revision ID: c8d47a2b6f13
Revises: f416e1d0ec14
Create Date: 2026-08-05 16:41:12.338901

Un mismo datalogger de una misma marca envía DOS formatos de archivo
distintos, con distinto número y significado de columnas:

  H_*.dat -> datos periódicos ("históricos", la lectura en tiempo real)
  E_*.dat -> estados y eventos que genera el equipo

mp_frmt identificaba el formato solo por (id_sd, mrc), así que no había
forma de guardar ambos sin inventar marcas falsas tipo "Campbell_H".
tp_trm cierra esa brecha y deja espacio a más tipos de trama si el equipo
de telemetría los define más adelante.

Se rellenan las filas existentes con 'H' porque el formato cargado hasta
ahora era el de datos periódicos; no hay datos de producción todavía.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d47a2b6f13"
down_revision: Union[str, Sequence[str], None] = "f416e1d0ec14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "mp_frmt",
        sa.Column("tp_trm", sa.String(length=5), nullable=False, server_default="H"),
    )
    op.create_check_constraint(
        "mpfrmt_tptrm_check",
        "mp_frmt",
        "tp_trm IN ('H','E')",
    )
    # Un solo formato activo por sede + marca + tipo de trama: es lo que
    # permite resolver sin ambigüedad qué mapeo aplica a un archivo dado.
    op.create_unique_constraint(
        "uq_mpfrmt_sd_mrc_tptrm",
        "mp_frmt",
        ["id_sd", "mrc", "tp_trm"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_mpfrmt_sd_mrc_tptrm", "mp_frmt", type_="unique")
    op.drop_constraint("mpfrmt_tptrm_check", "mp_frmt", type_="check")
    op.drop_column("mp_frmt", "tp_trm")
