"""HU49: prefijo de trama libre (no una letra) y origen automático en mp_frmt

Revision ID: 8362462b7138
Revises: 4dba56078c08
Create Date: 2026-09-01 00:00:00.000000

HU49 CA1-CA2: el tipo de trama deja de ser exactamente una letra A-Z. El
prefijo real de un archivo es "todo el texto antes del primer '_' del
nombre" (ver extraer_prefijo en services/ingesta/mapeo.py), que un
datalogger de campo puede nombrar con algo más largo que una letra (ej.
"ESTACION01_datos.dat"). tp_trm venía de mpfrmt_tptrm_check (ya eliminado
en c4680495205f) y de un String(5) que sigue limitando el ancho aunque el
CHECK cerrado ya no exista - esta migración amplía ese límite.

orgn_crcn es lo que permite distinguir en la UI (HU49 CA3, badge
"Auto-detectada") una trama que el pipeline creó solo porque llegó un
archivo con un prefijo nunca visto (HU49 CA1-CA2), de una que un Técnico
CENERIS configuró a mano como siempre. server_default='Manual' es lo que
garantiza que toda trama YA existente en la base se siga viendo "Manual"
tras esta migración - ninguna trama configurada hoy fue creada
automáticamente, así que ese es el valor correcto para todas ellas.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8362462b7138"
down_revision: Union[str, Sequence[str], None] = "4dba56078c08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LONGITUD_TP_TRM_ANTERIOR = 5
_LONGITUD_TP_TRM_NUEVA = 50


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "mp_frmt",
        "tp_trm",
        type_=sa.String(length=_LONGITUD_TP_TRM_NUEVA),
        existing_type=sa.String(length=_LONGITUD_TP_TRM_ANTERIOR),
        existing_nullable=False,
    )

    op.add_column(
        "mp_frmt",
        sa.Column(
            "orgn_crcn", sa.String(length=20), nullable=False, server_default="Manual"
        ),
    )
    op.create_check_constraint(
        "mpfrmt_orgncrcn_check",
        "mp_frmt",
        "orgn_crcn IN ('Manual','Automatico')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("mpfrmt_orgncrcn_check", "mp_frmt", type_="check")
    op.drop_column("mp_frmt", "orgn_crcn")

    # No trunca en silencio: si HU49 ya creó tramas con prefijo de más de
    # 5 caracteres, revertir el ancho de columna las dejaría inconsistentes
    # (algunas filas más largas que el límite nuevo). Se avisa y se aborta
    # en vez de perder datos sin que nadie lo note.
    conexion = op.get_bind()
    filas_largas = conexion.execute(
        sa.text(
            f"SELECT COUNT(*) FROM mp_frmt WHERE length(tp_trm) > {_LONGITUD_TP_TRM_ANTERIOR}"
        )
    ).scalar()
    if filas_largas:
        raise RuntimeError(
            f"No se puede revertir tp_trm a String({_LONGITUD_TP_TRM_ANTERIOR}): "
            f"hay {filas_largas} fila(s) en mp_frmt con un prefijo de más de "
            f"{_LONGITUD_TP_TRM_ANTERIOR} caracteres (creadas por HU49). "
            f"Resuélvelas manualmente antes de bajar esta migración."
        )

    op.alter_column(
        "mp_frmt",
        "tp_trm",
        type_=sa.String(length=_LONGITUD_TP_TRM_ANTERIOR),
        existing_type=sa.String(length=_LONGITUD_TP_TRM_NUEVA),
        existing_nullable=False,
    )
