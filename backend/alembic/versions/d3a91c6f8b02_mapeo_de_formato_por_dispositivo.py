"""Mapeo de formato por dispositivo, no por marca

Revision ID: d3a91c6f8b02
Revises: c8d47a2b6f13
Create Date: 2026-08-11 19:10:00.000000

mp_frmt identificaba el formato por (sede, marca, tipo de trama), compartido
por TODOS los dispositivos de esa marca. Eso no puede representar el caso
real: dos dispositivos de la misma marca en campo pueden traer sus columnas
en distinto orden porque un técnico los armó distinto. Se corrige atando el
mapeo directamente al dispositivo (id_dspstv), que además ya se resuelve
ANTES de buscar el formato en app/tasks/ingesta.py, así que no hace falta
volver a pasar por sede/marca.

Como contraparte, dspstv.id_mp (el dispositivo apuntando a su mapeo) deja de
tener sentido: ahora es mp_frmt el que apunta al dispositivo, y un
dispositivo puede no tener mapeo todavía (se crea primero el dispositivo,
el mapeo se configura después desde su ficha).

No hay datos de producción todavía (decisión de producto): se limpian
mp_clmn/mp_frmt en vez de migrar filas existentes a un dispositivo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd3a91c6f8b02'
down_revision: Union[str, Sequence[str], None] = 'c8d47a2b6f13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Sin datos de producción: se limpia en vez de migrar fila a fila.
    op.execute("DELETE FROM mp_clmn")
    op.execute("DELETE FROM mp_frmt")

    # dspstv.id_mp: el dispositivo ya no apunta a un mapeo (ver docstring).
    op.drop_constraint("dspstv_id_mp_fkey", "dspstv", type_="foreignkey")
    op.drop_column("dspstv", "id_mp")

    # mp_frmt: sede+marca -> dispositivo.
    op.drop_constraint("uq_mpfrmt_sd_mrc_tptrm", "mp_frmt", type_="unique")
    op.drop_constraint("mp_frmt_id_sd_fkey", "mp_frmt", type_="foreignkey")
    op.drop_column("mp_frmt", "id_sd")
    op.drop_column("mp_frmt", "mrc")
    op.add_column("mp_frmt", sa.Column("id_dspstv", sa.Integer(), nullable=False))
    op.create_foreign_key(
        "mp_frmt_id_dspstv_fkey", "mp_frmt", "dspstv", ["id_dspstv"], ["id_dspstv"],
    )
    op.create_unique_constraint(
        "uq_mpfrmt_dspstv_tptrm", "mp_frmt", ["id_dspstv", "tp_trm"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM mp_clmn")
    op.execute("DELETE FROM mp_frmt")

    op.drop_constraint("uq_mpfrmt_dspstv_tptrm", "mp_frmt", type_="unique")
    op.drop_constraint("mp_frmt_id_dspstv_fkey", "mp_frmt", type_="foreignkey")
    op.drop_column("mp_frmt", "id_dspstv")
    op.add_column("mp_frmt", sa.Column("mrc", sa.String(length=100), nullable=False))
    op.add_column("mp_frmt", sa.Column("id_sd", sa.Integer(), nullable=False))
    op.create_foreign_key("mp_frmt_id_sd_fkey", "mp_frmt", "sd", ["id_sd"], ["id_sd"])
    op.create_unique_constraint(
        "uq_mpfrmt_sd_mrc_tptrm", "mp_frmt", ["id_sd", "mrc", "tp_trm"],
    )

    op.add_column("dspstv", sa.Column("id_mp", sa.Integer(), nullable=True))
    op.create_foreign_key("dspstv_id_mp_fkey", "dspstv", "mp_frmt", ["id_mp"], ["id_mp"])
