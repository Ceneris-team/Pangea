"""HT-08: particiones iniciales de tlmtr y colchón para el arranque del PMV

Revision ID: a7f31c4b9e02
Revises: 9efd66dfaf93
Create Date: 2026-08-05 09:12:33.104772

La migración eadc512979fc creó a mano las particiones 2026_07 .. 2026_10.
A partir del 2026-11-01 no había ninguna, así que toda lectura de ese mes
en adelante fallaba con "no partition of relation tlmtr found for row".

Esta migración extiende la cobertura 12 meses desde el mes en curso al
momento de aplicarla. El job de Celery Beat
(app.tasks.particiones.asegurar_particiones_futuras) mantiene el colchón
a partir de ahí; esta migración solo garantiza el arranque del PMV.

Es idempotente (CREATE TABLE IF NOT EXISTS vía
app.services.particiones): re-aplicarla sobre una BD que ya tenga las
particiones no falla ni duplica.
"""

import datetime as dt
from typing import Sequence, Union

from alembic import op
from app.services.particiones import (
    asegurar_particiones,
    nombre_particion,
    primer_dia_del_mes,
)

# revision identifiers, used by Alembic.
revision: str = "a7f31c4b9e02"
down_revision: Union[str, Sequence[str], None] = "9efd66dfaf93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Meses de cobertura desde el mes en curso. 12 da un año de colchón por si
# el job de Beat no llega a estar corriendo en algún entorno.
MESES_DE_COBERTURA = 12


def upgrade() -> None:
    """Upgrade schema."""
    conexion = op.get_bind()
    creadas = asegurar_particiones(conexion, dt.date.today(), MESES_DE_COBERTURA)
    print(f"HT-08: particiones creadas: {creadas or 'ninguna (ya existían)'}")


def downgrade() -> None:
    """Downgrade schema.

    Solo borra las particiones que esta migración pudo haber creado (de
    hoy en adelante), nunca las de eadc512979fc ni ninguna que ya tenga
    datos: un downgrade no debe destruir telemetría. Una partición con
    filas se conserva y se avisa por consola.
    """
    from sqlalchemy import text

    conexion = op.get_bind()
    mes = primer_dia_del_mes(dt.date.today())
    for _ in range(MESES_DE_COBERTURA):
        nombre = nombre_particion(mes)
        existe = conexion.execute(text("SELECT to_regclass(:n)"), {"n": nombre}).scalar()
        if existe is not None:
            filas = conexion.execute(text(f"SELECT count(*) FROM {nombre}")).scalar()
            if filas:
                print(f"HT-08 downgrade: {nombre} conserva {filas} filas, no se borra")
            else:
                op.execute(f"DROP TABLE IF EXISTS {nombre}")
        # avanzar al mes siguiente
        mes = (
            mes.replace(year=mes.year + 1, month=1)
            if mes.month == 12
            else mes.replace(month=mes.month + 1)
        )
