"""El outbox de PostgreSQL es la fuente durable; Celery Beat lo drena."""

import logging

from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.models import TrabajoCalculo, Ubicacion
from app.services.motor_calculos import (
    ahora,
    invalidar_resultados,
    mantener_pendientes,
    procesar_lote,
)

logger = logging.getLogger(__name__)


def ejecutar_un_lote(db):
    trabajo = (
        db.query(TrabajoCalculo)
        .filter(TrabajoCalculo.estado.in_(["Pendiente", "En curso"]))
        .order_by(TrabajoCalculo.id_trabajo)
        .with_for_update(skip_locked=True)
        .first()
    )
    if trabajo is None:
        return False
    id_, sede, punto = trabajo.id_trabajo, trabajo.id_sd, trabajo.id_ubccn
    try:
        procesar_lote(db, trabajo)
        db.commit()
        puntos = (
            [punto]
            if punto
            else [id_ for (id_,) in db.query(Ubicacion.id_ubccn).filter_by(id_sd=sede)]
        )
        invalidar_resultados(sede, puntos)
    except Exception:
        db.rollback()
        logger.exception("No se pudo procesar el trabajo calculado %s", id_)
        trabajo = db.get(TrabajoCalculo, id_)
        trabajo.estado = "Fallido"
        trabajo.error = "No se pudo completar el lote. Reintenta el procesamiento; el avance confirmado se conserva."
        trabajo.actualizado_en = ahora()
        db.commit()
    return True


@celery_app.task(name="app.tasks.calculos.procesar_pendientes")
def procesar_pendientes():
    with SessionLocal() as db:
        for _ in range(10):
            if not ejecutar_un_lote(db):
                break
        mantener_pendientes(db)
        db.commit()
