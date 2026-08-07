"""
HT-08: job programado que mantiene el colchón de particiones de tlmtr.

Postgres no crea particiones solo. Si llega una lectura cuya fch_hr no cae
en ninguna partición existente, el INSERT falla (ver
app.services.particiones y el manejo en app.services.ingesta.persistencia).
Este job corre a diario vía Celery Beat y garantiza que siempre haya
particiones creadas con antelación, para que ese caso no ocurra en
operación normal.
"""
import datetime as dt
import logging

from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.services.particiones import (
    asegurar_particiones,
    mes_siguiente,
    nombre_particion,
    particiones_existentes,
)

logger = logging.getLogger(__name__)

# Cuántos meses por delante se mantienen creados. Con 3, la partición del
# mes siguiente existe siempre con semanas de anticipación -HT-08 pide al
# menos una semana- y aún quedan dos meses más de colchón si el job deja
# de correr (worker caído, Beat apagado, despliegue largo).
MESES_DE_COLCHON = 3


@celery_app.task(name="app.tasks.particiones.asegurar_particiones_futuras")
def asegurar_particiones_futuras() -> dict:
    """Crea las particiones de tlmtr que falten para los próximos meses.

    Corre a diario (ver beat_schedule en app/core/celery_app.py). Correrlo
    a diario y no mensualmente es deliberado: si el job falla un día -o el
    worker está caído justo el día que tocaba-, al día siguiente se
    recupera solo. Un job mensual que falle deja un hueco que nadie nota
    hasta que la ingesta empieza a rechazar lecturas.

    Es idempotente (CREATE TABLE IF NOT EXISTS): las corridas en las que
    no falta nada no emiten DDL y devuelven creadas=[].

    Además de crear hacia adelante, verifica que no haya huecos en el
    rango que debería estar cubierto y los repara: así un fallo puntual no
    deja un agujero permanente en medio del calendario.
    """
    db = SessionLocal()
    try:
        hoy = dt.date.today()

        # Desde el mes en curso hacia adelante: cubre el hueco del mes
        # actual si por alguna razón faltara, no solo los futuros.
        creadas = asegurar_particiones(db.connection(), hoy, MESES_DE_COLCHON + 1)
        db.commit()

        # Tras el commit hay que pedir la conexión de nuevo: la anterior
        # quedó cerrada al cerrarse la transacción.
        existentes = particiones_existentes(db.connection())
        mes_siguiente_nombre = nombre_particion(mes_siguiente(hoy))

        if creadas:
            logger.info("HT-08: particiones creadas: %s", creadas)
        else:
            logger.debug("HT-08: sin particiones que crear, colchón completo")

        return {
            "creadas": creadas,
            "particion_mes_siguiente": mes_siguiente_nombre,
            "mes_siguiente_listo": mes_siguiente_nombre in existentes,
            "total_particiones": len(existentes),
        }
    except Exception:
        db.rollback()
        logger.exception("HT-08: fallo al asegurar particiones de tlmtr")
        raise
    finally:
        db.close()
