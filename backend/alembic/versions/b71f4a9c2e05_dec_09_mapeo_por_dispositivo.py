"""DEC-09: el mapeo de formato cuelga del dispositivo, no de sede+marca

Revision ID: b71f4a9c2e05
Revises: c8d47a2b6f13
Create Date: 2026-08-11 11:20:00.000000

mp_frmt se identificaba por (id_sd, mrc, tp_trm). Dos dataloggers de la
misma marca en la misma sede, pero con sensores distintos conectados,
compartían el mismo mapeo: las lecturas del segundo se guardaban bajo el
parámetro equivocado sin producir ningún error visible.

Cada datalogger tiene su propia carpeta FTP exclusiva (cnxn_ftp, HU05) y
exactamente un dispositivo activo asociado (validación 409 de HU11), así
que el DISPOSITIVO es la unidad correcta a la que colgar el formato.

Cambios:
  mp_frmt: -id_sd, -mrc, +id_dspstv (FK a dspstv, NOT NULL).
           El único (id_sd, mrc, tp_trm) se reemplaza por un único PARCIAL
           (id_dspstv, tp_trm) WHERE estd='Activo': un dispositivo tiene
           como máximo un mapeo activo por tipo de trama, pero puede
           conservar versiones anteriores desactivadas.
  dspstv:  -id_mp. Un dispositivo puede tener 0, 1 o 2 mapeos (uno por
           tipo de trama), lo que no cabe en una sola FK; la relación pasa
           a vivir del lado de mp_frmt.

Migración limpia (Sprint 2 / PMV, sin datos de producción): las filas
existentes de mp_frmt no se pueden reasignar automáticamente a un
dispositivo -la relación sede+marca -> dispositivo es ambigua, que es
justamente el bug que se corrige-, así que se truncan mp_clmn y mp_frmt.
Los mapeos se vuelven a cargar desde la interfaz de HU06, ahora por
dispositivo.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b71f4a9c2e05"
down_revision: Union[str, Sequence[str], None] = "c8d47a2b6f13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # dspstv.id_mp es NOT NULL y apunta a mp_frmt, así que hay que soltar
    # esa FK antes de poder vaciar la tabla de formatos.
    op.drop_constraint("dspstv_id_mp_fkey", "dspstv", type_="foreignkey")
    op.drop_column("dspstv", "id_mp")

    # No hay forma no ambigua de repartir un mapeo de (sede, marca) entre
    # los dispositivos que lo compartían: se recargan desde la UI (HU06).
    # mp_clmn referencia mp_frmt, así que va primero.
    op.execute("TRUNCATE TABLE mp_clmn, mp_frmt RESTART IDENTITY")

    op.drop_constraint("uq_mpfrmt_sd_mrc_tptrm", "mp_frmt", type_="unique")
    op.drop_constraint("mp_frmt_id_sd_fkey", "mp_frmt", type_="foreignkey")
    op.drop_column("mp_frmt", "id_sd")
    op.drop_column("mp_frmt", "mrc")

    op.add_column("mp_frmt", sa.Column("id_dspstv", sa.Integer(), nullable=False))
    op.create_foreign_key(
        "mp_frmt_id_dspstv_fkey",
        "mp_frmt",
        "dspstv",
        ["id_dspstv"],
        ["id_dspstv"],
    )
    op.create_index("idx_mpfrmt_dspstv", "mp_frmt", ["id_dspstv"])
    # Único PARCIAL: solo entre los mapeos Activos. Permite conservar
    # versiones desactivadas del mismo dispositivo+trama.
    op.create_index(
        "uq_mpfrmt_dspstv_tptrm_activo",
        "mp_frmt",
        ["id_dspstv", "tp_trm"],
        unique=True,
        postgresql_where=sa.text("estd = 'Activo'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Simétrico al upgrade: tampoco se puede reconstruir (id_sd, mrc) a
    # partir del dispositivo sin perder la distinción que introdujo DEC-09.
    op.execute("TRUNCATE TABLE mp_clmn, mp_frmt RESTART IDENTITY")

    op.drop_index("uq_mpfrmt_dspstv_tptrm_activo", table_name="mp_frmt")
    op.drop_index("idx_mpfrmt_dspstv", table_name="mp_frmt")
    op.drop_constraint("mp_frmt_id_dspstv_fkey", "mp_frmt", type_="foreignkey")
    op.drop_column("mp_frmt", "id_dspstv")

    op.add_column("mp_frmt", sa.Column("mrc", sa.String(length=100), nullable=False))
    op.add_column("mp_frmt", sa.Column("id_sd", sa.Integer(), nullable=False))
    op.create_foreign_key("mp_frmt_id_sd_fkey", "mp_frmt", "sd", ["id_sd"], ["id_sd"])
    op.create_unique_constraint(
        "uq_mpfrmt_sd_mrc_tptrm",
        "mp_frmt",
        ["id_sd", "mrc", "tp_trm"],
    )

    op.add_column("dspstv", sa.Column("id_mp", sa.Integer(), nullable=False))
    op.create_foreign_key(
        "dspstv_id_mp_fkey",
        "dspstv",
        "mp_frmt",
        ["id_mp"],
        ["id_mp"],
    )
