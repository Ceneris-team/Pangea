"""HU50: tabla mp_clmn_pendiente para columnas sin match automático

Revision ID: 6cf46ba44eab
Revises: 8362462b7138
Create Date: 2026-09-01 00:05:00.000000

HU50 CA3/CA6: cuando el auto-mapeo de columnas (construir_mapeo,
services/ingesta/mapeo.py) no encuentra un prmtr.nmbr que coincida
(normalizado) con el nombre de una columna del header, esa columna queda
"pendiente de asignar" hasta que un Técnico/Administrador la resuelva a
mano desde la pestaña Datos de la ficha del dispositivo.

Se modela como tabla SEPARADA de mp_clmn, no como un id_prmtr nullable
ahí. mp_clmn la consultan en caliente, en cada archivo procesado,
construir_mapeo() y tipos_de_parametro() -ambas con INNER JOIN contra
prmtr sin ningún chequeo de nulidad-; introducir NULL en esa tabla sería
una superficie de riesgo evitable para el requisito de cero regresión de
HU49/HU50 sobre dispositivos ya configurados. Es el mismo criterio que ya
usa este proyecto para separar evnt_txt de tlmtr (ver el docstring de
Parametro en app/models/mapeo_dispositivo.py): un estado que no es "un
mapeo válido" no vive en la tabla que sí lo es.

estd tiene 3 valores, no un booleano:
  'Pendiente' - nunca evaluada por un humano (recién detectada).
  'Resuelta'  - el Técnico asignó un parámetro (CA5); se creó la fila
                real correspondiente en mp_clmn.
  'Ignorada'  - el Técnico decidió explícitamente que esa columna del
                header nunca va a tener parámetro (ej. un checksum del
                datalogger) - sin este tercer estado, esa columna
                quedaría "Pendiente" para siempre y generaría ruido
                perpetuo en la notificación de HU50 CA4.

El UNIQUE(id_mp, indc_clmn) es la pieza mecánica de HU50 CA6: una vez que
existe una fila para esa columna (sea cual sea su estado), el auto-mapeo
nunca vuelve a evaluarla - ni siquiera si después se da de alta en prmtr
un parámetro que ahora sí matchearía por nombre. Evita que un cambio de
texto accidental en el datalogger, o un alta tardía del parámetro, reabra
algo que un Técnico ya resolvió o descartó a mano.

Sin FK a archv_ingst a propósito: el problema (columna sin match) está
identificado por dispositivo+trama+índice+nombre, no por el archivo
puntual que lo reveló por primera vez. Si el archivo de origen se purga
de la cola más adelante, esta fila sigue siendo válida.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6cf46ba44eab"
down_revision: Union[str, Sequence[str], None] = "8362462b7138"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "mp_clmn_pendiente",
        sa.Column("id_mp_cl_pnd", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_mp", sa.Integer(), nullable=False),
        sa.Column("indc_clmn", sa.Integer(), nullable=False),
        sa.Column("nmbr_clmn_orgn", sa.String(length=200), nullable=False),
        sa.Column(
            "estd", sa.String(length=20), nullable=False, server_default="Pendiente"
        ),
        sa.Column(
            "fch_dtccn",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("fch_resolucion", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id_usr_resolvio", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["id_mp"], ["mp_frmt.id_mp"]),
        sa.ForeignKeyConstraint(["id_usr_resolvio"], ["usr.id_usr"]),
        sa.PrimaryKeyConstraint("id_mp_cl_pnd"),
        sa.CheckConstraint(
            "estd IN ('Pendiente','Resuelta','Ignorada')", name="mpclmnpnd_estd_check"
        ),
        sa.UniqueConstraint("id_mp", "indc_clmn", name="uq_mpclmnpnd_mp_indccolmn"),
    )
    op.create_index(
        "idx_mpclmnpnd_mp_estd", "mp_clmn_pendiente", ["id_mp", "estd"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_mpclmnpnd_mp_estd", table_name="mp_clmn_pendiente")
    op.drop_table("mp_clmn_pendiente")
