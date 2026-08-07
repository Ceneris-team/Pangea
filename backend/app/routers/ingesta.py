"""
HU 09 - Monitorear cola de procesamiento

HT-05, CA3: "El sistema expone métricas en tiempo real de jobs pendientes,
en proceso y fallidos, consumibles por el módulo de monitoreo." Se cuenta
directamente sobre archv_ingst (agrupado por estd, usa idx_archvingst_estd)
en vez de consultar celery.control.inspect(): así el conteo refleja también
los jobs que un receptor FTP ya registró como 'Pendiente' pero que ningún
worker ha tomado todavía, que es justo el caso que se quiere monitorear.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ArchivoIngesta
from app.security.dependencies import get_current_user
from app.schemas import MetricasColaIngesta

router = APIRouter(prefix="/ingesta", tags=["Ingesta"])

ROLES_CON_ACCESO = {"Administrador", "Tecnico CENERIS", "Técnico CENERIS"}

ESTADOS = ("Pendiente", "Procesando", "Exitoso", "Fallido")


@router.get("/metricas", response_model=MetricasColaIngesta)
def metricas_cola_ingesta(
    db: Session = Depends(get_db),
    usuario: dict = Depends(get_current_user),
):
    if usuario.get("rol") not in ROLES_CON_ACCESO:
        raise HTTPException(status_code=403, detail="No autorizado")

    conteos = dict(
        db.query(ArchivoIngesta.estd, func.count(ArchivoIngesta.id_archv))
        .filter(ArchivoIngesta.estd.in_(ESTADOS))
        .group_by(ArchivoIngesta.estd)
        .all()
    )

    pendientes = conteos.get("Pendiente", 0)
    procesando = conteos.get("Procesando", 0)
    exitosos = conteos.get("Exitoso", 0)
    fallidos = conteos.get("Fallido", 0)

    return MetricasColaIngesta(
        pendientes=pendientes,
        procesando=procesando,
        exitosos=exitosos,
        fallidos=fallidos,
        total=pendientes + procesando + exitosos + fallidos,
    )
