import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LogIngesta
from app.security.entorno import ROLES_CENERIS, filtrar_proyectos, filtrar_sedes
from app.security.permisos import LECTURA, require_permiso
from app.services.ingesta.log import limite_conservacion, mensaje_seguro

router = APIRouter(prefix="/ingesta/log", tags=["Log de ingesta"])


def acceso(usuario: dict = Depends(require_permiso("Ingesta", LECTURA))):
    if usuario.get("rol") not in ROLES_CENERIS:
        raise HTTPException(
            403, "Solo Técnico CENERIS y Administrador pueden consultar el log de ingesta"
        )
    return usuario


def visibles(db, usuario):
    query = filtrar_sedes(db.query(LogIngesta), LogIngesta.id_sd, db, usuario)
    if usuario.get("proyecto_id") is not None or usuario.get("scope") == "por_cliente":
        query = filtrar_proyectos(query, LogIngesta.id_ubccn, db, usuario)
    return query.filter(LogIngesta.fecha >= limite_conservacion())


def serializar(evento):
    return {
        "id_evento": evento.id_evento,
        "id_archv": evento.id_archv,
        "archivo": evento.archivo,
        "datalogger": evento.datalogger,
        "proyecto": evento.proyecto,
        "fecha": evento.fecha,
        "recepcion": evento.recepcion,
        "inicio": evento.inicio,
        "fin": evento.fin,
        "resultado": "Procesado" if evento.resultado == "Exitoso" else evento.resultado,
        "mensaje": mensaje_seguro(evento.mensaje),
        "registros_procesados": evento.registros_procesados,
        "registros_rechazados": evento.registros_rechazados,
        "origen": evento.origen,
    }


@router.get("")
def listar(
    nombre: str = Query(default="", max_length=300),
    resultado: str | None = None,
    id_dspstv: int | None = Query(default=None, gt=0),
    id_cnxn: int | None = Query(default=None, gt=0),
    sin_identificar: bool = False,
    fecha_inicio: dt.date | None = None,
    fecha_fin: dt.date | None = None,
    zona_horaria: str = "America/Lima",
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: dict = Depends(acceso),
):
    if resultado not in (None, "Procesado", "Fallido"):
        raise HTTPException(422, "Selecciona Procesado o Fallido")
    if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
        raise HTTPException(422, "La fecha inicial no puede ser posterior a la final")
    try:
        zona = ZoneInfo(zona_horaria)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, "Zona horaria inválida") from None
    query = visibles(db, usuario)
    if nombre.strip():
        query = query.filter(LogIngesta.archivo.icontains(nombre.strip(), autoescape=True))
    if resultado:
        query = query.filter(
            LogIngesta.resultado == ("Exitoso" if resultado == "Procesado" else "Fallido")
        )
    if id_cnxn:
        query = query.filter(LogIngesta.id_cnxn == id_cnxn)
    if id_dspstv:
        query = query.filter(LogIngesta.id_dspstv == id_dspstv)
    if sin_identificar:
        query = query.filter(LogIngesta.id_dspstv.is_(None))
    if fecha_inicio:
        query = query.filter(
            LogIngesta.fecha >= dt.datetime.combine(fecha_inicio, dt.time.min, zona)
        )
    if fecha_fin:
        if fecha_fin == dt.date.max:
            raise HTTPException(422, "Fecha final fuera del rango permitido")
        fin = dt.datetime.combine(fecha_fin + dt.timedelta(days=1), dt.time.min, zona)
        query = query.filter(LogIngesta.fecha < fin)
    total = query.count()
    eventos = (
        query.order_by(LogIngesta.fecha.desc(), LogIngesta.id_evento.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )
    return {
        "items": [serializar(e) for e in eventos],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


@router.get("/dataloggers")
def dataloggers(db: Session = Depends(get_db), usuario: dict = Depends(acceso)):
    filas = (
        visibles(db, usuario)
        .with_entities(LogIngesta.id_cnxn, LogIngesta.id_dspstv, LogIngesta.datalogger)
        .distinct()
        .all()
    )
    return {
        "items": [
            {"id_cnxn": c, "id_dspstv": d, "nombre": nombre}
            for c, d, nombre in sorted(filas, key=lambda f: (f[2], f[0], f[1] or 0))
        ]
    }


@router.get("/{id_evento}")
def detalle(id_evento: int, db: Session = Depends(get_db), usuario: dict = Depends(acceso)):
    evento = visibles(db, usuario).filter(LogIngesta.id_evento == id_evento).first()
    if evento is None:
        raise HTTPException(404, "Evento no encontrado en el log autorizado de los últimos 90 días")
    historial = (
        visibles(db, usuario)
        .filter(LogIngesta.id_archv == evento.id_archv)
        .order_by(LogIngesta.fecha.desc(), LogIngesta.id_evento.desc())
        .all()
    )
    return {**serializar(evento), "historial": [serializar(e) for e in historial]}
