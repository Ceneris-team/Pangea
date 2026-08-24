"""agrega tipo_dato a parametros y tabla evnt_txt para eventos de texto

Revision ID: 4dba56078c08
Revises: 6ccd31c550dd
Create Date: 2026-08-21 17:10:00.000000

La trama P real de campo trae columnas de texto (MensajeP/MensajeA: "Puerta
Abierta", "Llave No Encontrada"), no solo numéricas. Hasta ahora TODO
parámetro se validaba como número (validador._parsear_numero exige
float()), así que mapear una columna de texto perdía cada fila en
silencio. tlmtr.vlr es Numeric(14,4) NOT NULL y está particionada con
datos reales -no se puede simplemente volverla texto/nullable sin una
migración grande sobre una tabla en producción-, así que los eventos de
texto van a una tabla nueva y separada (evnt_txt), sin particionar (bajo
volumen esperado frente a la telemetría numérica).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4dba56078c08'
down_revision: Union[str, Sequence[str], None] = '6ccd31c550dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "prmtr",
        sa.Column("tipo_dato", sa.String(length=10), nullable=False, server_default="numerico"),
    )
    op.create_check_constraint(
        "prmtr_tipodato_check",
        "prmtr",
        "tipo_dato IN ('numerico','texto')",
    )

    op.create_table(
        "evnt_txt",
        sa.Column("id_evnt", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("fch_hr", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("id_dspstv", sa.Integer(), nullable=False),
        sa.Column("id_prmtr", sa.Integer(), nullable=False),
        sa.Column("id_sd", sa.Integer(), nullable=False),
        sa.Column("vlr", sa.String(length=500), nullable=False),
        sa.Column("id_archv", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["id_dspstv"], ["dspstv.id_dspstv"]),
        sa.ForeignKeyConstraint(["id_prmtr"], ["prmtr.id_prmtr"]),
        sa.ForeignKeyConstraint(["id_sd"], ["sd.id_sd"]),
        sa.ForeignKeyConstraint(["id_archv"], ["archv_ingst.id_archv"]),
        sa.PrimaryKeyConstraint("id_evnt"),
    )
    op.create_index(
        "idx_evnttxt_dspstv_prmtr", "evnt_txt", ["id_dspstv", "id_prmtr", "fch_hr"]
    )
    op.create_index("idx_evnttxt_fchhr", "evnt_txt", ["fch_hr"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_evnttxt_fchhr", table_name="evnt_txt")
    op.drop_index("idx_evnttxt_dspstv_prmtr", table_name="evnt_txt")
    op.drop_table("evnt_txt")

    op.drop_constraint("prmtr_tipodato_check", "prmtr", type_="check")
    op.drop_column("prmtr", "tipo_dato")
