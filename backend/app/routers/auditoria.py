"""HT-11: consulta del historial global o de una empresa, sin endpoints de escritura."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LogAuditoria, Usuario
from app.schemas import AuditoriaListItem
from app.security.auditoria_contexto import marcar_actor
from app.security.dependencies import get_current_user
from app.security.entorno import contexto

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])


def consulta_autorizada(db, usuario):
    marcar_actor(db, usuario)
    query = db.query(LogAuditoria).outerjoin(Usuario, LogAuditoria.id_usr == Usuario.id_usr)
    if usuario.get("scope") == "global" and usuario.get("rol") == "Administrador":
        return query
    if usuario.get("scope") == "por_cliente":
        vigente = contexto(db, usuario)
        if vigente.get("rol_empresa") == "Administrador":
            return query.filter(LogAuditoria.id_clnt == vigente["cliente_id"])
    raise HTTPException(403, "Solo administradores pueden consultar la auditoria")


def serializar(query):
    return [
        AuditoriaListItem.model_validate(
            {
                **{
                    campo: getattr(registro, campo)
                    for campo in AuditoriaListItem.model_fields
                    if campo != "usuario_nombre"
                },
                "usuario_nombre": nombre,
            }
        )
        for registro, nombre in query.add_columns(Usuario.nmbr_cmplt).all()
    ]


@router.get("")
def listar_auditoria(
    empresa_id: int | None = Query(default=None, ge=1),
    proyecto_id: int | None = Query(default=None, ge=1),
    sede_id: int | None = Query(default=None, ge=1),
    usuario_id: int | None = Query(default=None, ge=1, description="Ejecutor (compatibilidad)"),
    ejecutor_id: int | None = Query(default=None, ge=1),
    usuario_afectado_id: int | None = Query(default=None, ge=1),
    accion: str | None = Query(default=None, max_length=50),
    resultado: str | None = Query(default=None, pattern="^(Exitoso|Denegado)$"),
    fecha_inicio: dt.datetime | None = Query(default=None),
    fecha_fin: dt.datetime | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: dict = Depends(get_current_user),
):
    query = consulta_autorizada(db, usuario)
    if any(fecha is not None and fecha.utcoffset() is None for fecha in (fecha_inicio, fecha_fin)):
        raise HTTPException(422, "Indica zona horaria en las fechas, por ejemplo +00:00")
    if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
        raise HTTPException(422, "La fecha inicial debe ser anterior a la final")
    if usuario_id and ejecutor_id and usuario_id != ejecutor_id:
        raise HTTPException(422, "Los filtros de ejecutor no coinciden")
    for columna, valor in (
        (LogAuditoria.id_clnt, empresa_id),
        (LogAuditoria.id_ubccn, proyecto_id),
        (LogAuditoria.id_sd, sede_id),
        (LogAuditoria.id_usr, ejecutor_id or usuario_id),
        (LogAuditoria.id_afectado, usuario_afectado_id),
        (LogAuditoria.accn, accion),
        (LogAuditoria.resultado, resultado),
    ):
        if valor is not None:
            query = query.filter(columna == valor)
    if fecha_inicio:
        query = query.filter(LogAuditoria.fch_evnt >= fecha_inicio)
    if fecha_fin:
        query = query.filter(LogAuditoria.fch_evnt <= fecha_fin)
    total = query.count()
    items = serializar(
        query.order_by(LogAuditoria.fch_evnt.desc(), LogAuditoria.id_evnt.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    )
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": items}


@router.get("/{evento_id}", response_model=AuditoriaListItem)
def obtener_evento(
    evento_id: int, db: Session = Depends(get_db), usuario: dict = Depends(get_current_user)
):
    items = serializar(consulta_autorizada(db, usuario).filter(LogAuditoria.id_evnt == evento_id))
    if not items:
        raise HTTPException(404, "Evento no encontrado")
    return items[0]
