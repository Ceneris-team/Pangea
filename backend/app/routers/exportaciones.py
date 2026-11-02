import datetime as dt

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Dispositivo, Exportacion, Ubicacion, Usuario
from app.schemas_exportaciones import ExportacionCrear, ExportacionItem
from app.security.permisos import LECTURA, require_permiso
from app.security.ubicaciones_permitidas import ubicaciones_permitidas
from app.services.exportaciones import ahora, limites, obtener_propia, validar_solicitud
from app.services.exportaciones_storage import AlmacenExportaciones, bucket_configurado
from app.tasks.exportaciones import encolar_exportacion

router = APIRouter(prefix="/exportaciones", tags=["Exportaciones"])
acceso = require_permiso("Tableros", LECTURA)


@router.get("/limites")
def consultar_limites(usuario: dict = Depends(acceso)):
    return limites()


@router.get("/dispositivos")
def dispositivos_exportables(
    ubicacion_ids: list[int] | None = Query(default=None),
    pagina: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    usuario: dict = Depends(acceso),
):
    visibles = set(ubicaciones_permitidas(db, usuario))
    if ubicacion_ids:
        visibles &= set(ubicacion_ids)
    consulta = (
        db.query(Dispositivo.id_dspstv, Dispositivo.nmbr, Ubicacion.nmbr.label("proyecto_nombre"))
        .join(Ubicacion, Ubicacion.id_ubccn == Dispositivo.id_ubccn)
        .filter(Dispositivo.id_ubccn.in_(visibles))
    )
    filas = (
        consulta.order_by(Dispositivo.nmbr, Dispositivo.id_dspstv)
        .offset((pagina - 1) * 100)
        .limit(101)
        .all()
    )
    return {"items": [dict(fila._mapping) for fila in filas[:100]], "hay_mas": len(filas) > 100}


@router.post("", status_code=202)
def solicitar_exportacion(
    body: ExportacionCrear,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario: dict = Depends(acceso),
):
    filtros = validar_solicitud(db, usuario, body)
    try:
        bucket_configurado()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    cuenta = db.query(Usuario).filter_by(id_usr=int(usuario["sub"])).with_for_update().one()
    activas = (
        db.query(Exportacion)
        .filter(
            Exportacion.id_usr == cuenta.id_usr, Exportacion.estd.in_(["Pendiente", "En proceso"])
        )
        .count()
    )
    if activas >= limites()["simultaneas"]:
        raise HTTPException(
            429, "Ya tienes el máximo de exportaciones en proceso. Espera a que termine alguna."
        )
    filtros["zona_horaria"] = cuenta.zn_hrr
    exportacion = Exportacion(
        id_usr=cuenta.id_usr, frmt=body.formato, fltrs_aplcds=filtros, estd="Pendiente"
    )
    db.add(exportacion)
    db.commit()
    db.refresh(exportacion)
    background_tasks.add_task(encolar_exportacion, exportacion.id_exprtcn)
    return {
        "mensaje": "Exportación solicitada. Puedes seguir trabajando mientras se prepara.",
        "exportacion": ExportacionItem.model_validate(exportacion),
    }


@router.get("")
def listar_exportaciones(
    pagina: int = Query(1, ge=1), db: Session = Depends(get_db), usuario: dict = Depends(acceso)
):
    query = db.query(Exportacion).filter(Exportacion.id_usr == int(usuario["sub"]))
    # La lista muestra solo solicitudes del entorno actual; los accesos de descarga se revalidan.
    query = query.filter(
        Exportacion.fltrs_aplcds["cliente_id"].astext
        == (str(usuario["cliente_id"]) if usuario.get("cliente_id") else None),
        Exportacion.fltrs_aplcds["proyecto_id"].astext
        == (str(usuario["proyecto_id"]) if usuario.get("proyecto_id") else None),
    )
    items = (
        query.order_by(Exportacion.fch_slctd.desc(), Exportacion.id_exprtcn.desc())
        .offset((pagina - 1) * 20)
        .limit(20)
        .all()
    )
    return {"items": [_item(e) for e in items], "pagina": pagina}


def _item(exportacion):
    item = ExportacionItem.model_validate(exportacion)
    if exportacion.estd == "Lista" and exportacion.fch_exprcn <= ahora():
        item.estd = "Expirada"
    return item


@router.get("/{id_exportacion}", response_model=ExportacionItem)
def consultar_exportacion(
    id_exportacion: int, db: Session = Depends(get_db), usuario: dict = Depends(acceso)
):
    return _item(obtener_propia(db, id_exportacion, usuario))


@router.post("/{id_exportacion}/descarga")
def descargar_exportacion(
    id_exportacion: int, db: Session = Depends(get_db), usuario: dict = Depends(acceso)
):
    exportacion = obtener_propia(db, id_exportacion, usuario)
    if exportacion.fch_exprcn and exportacion.fch_exprcn <= ahora():
        raise HTTPException(410, "La exportación expiró. Solicita una nueva.")
    if exportacion.estd != "Lista" or not exportacion.objeto_clave:
        raise HTTPException(409, "La exportación todavía no está disponible")
    segundos = min(60, int((exportacion.fch_exprcn - ahora()).total_seconds()))
    if segundos <= 0:
        raise HTTPException(410, "La exportación expiró. Solicita una nueva.")
    try:
        url = AlmacenExportaciones(exportacion.objeto_bucket).firmar(
            exportacion.objeto_clave, segundos, exportacion.objeto_version
        )
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(
            503, "No se pudo preparar la descarga. Intenta de nuevo más tarde."
        ) from exc
    return {"url": url, "expira_en": ahora() + dt.timedelta(seconds=segundos)}
