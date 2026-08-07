"""
HU 13 - Seleccionar parámetros y ubicaciones

CA: el Cliente Final filtra la vista de telemetría por uno o más
parámetros y/o ubicaciones (selección múltiple). Sin filtros, se muestran
todos los datos disponibles para la cuenta. Los parámetros y ubicaciones
ofrecidos dependen de lo asignado al usuario (prms_ubccn, HU 21) y del
catálogo de parámetros mapeados (mp_clmn/prmtr, HU 06).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Dispositivo,
    MapeoColumna,
    Parametro,
    PermisoUbicacion,
    Telemetria,
    Ubicacion,
)
from app.schemas import MedicionListItem, ParametroListItem
from app.security.permisos import LECTURA, require_permiso

router = APIRouter(prefix="/mediciones", tags=["Mediciones"])

ROLES_CON_ACCESO_TOTAL = {"Administrador", "Tecnico CENERIS", "Técnico CENERIS"}


def _ubicaciones_permitidas(db: Session, usuario: dict):
    """CA: el Cliente Final solo ve parámetros/ubicaciones que le asignó
    el Administrador (HU 21). Administrador/Técnico ven todo."""
    query = db.query(Ubicacion.id_ubccn)
    if usuario.get("rol") not in ROLES_CON_ACCESO_TOTAL:
        id_usr = int(usuario["sub"])
        query = query.join(
            PermisoUbicacion, PermisoUbicacion.id_ubccn == Ubicacion.id_ubccn
        ).filter(PermisoUbicacion.id_usr == id_usr)
    return [row[0] for row in query.all()]


@router.get("/parametros")
def listar_parametros_disponibles(
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Mediciones", LECTURA)),
):
    """CA1: lista los parámetros disponibles asociados a las ubicaciones
    asignadas al usuario. Un parámetro solo aparece si está mapeado (HU 06)
    para algún dispositivo de esas ubicaciones."""
    ids_ubicaciones = _ubicaciones_permitidas(db, usuario)
    if not ids_ubicaciones:
        return {"items": []}

    parametros = (
        db.query(Parametro)
        .join(MapeoColumna, MapeoColumna.id_prmtr == Parametro.id_prmtr)
        .join(Dispositivo, Dispositivo.id_mp == MapeoColumna.id_mp)
        .filter(Dispositivo.id_ubccn.in_(ids_ubicaciones))
        .distinct()
        .order_by(Parametro.nmbr)
        .all()
    )
    items = [ParametroListItem.model_validate(p) for p in parametros]
    return {"items": items}


@router.get("")
def listar_mediciones(
    parametro_ids: list[int] | None = Query(default=None),
    ubicacion_ids: list[int] | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Mediciones", LECTURA)),
):
    """CA2-CA4: aplica los filtros de parámetros y/o ubicaciones sobre la
    vista de datos. Si no se selecciona ninguno, se muestran todos los
    datos disponibles para la cuenta (dentro de las ubicaciones permitidas)."""
    ids_ubicaciones_permitidas = set(_ubicaciones_permitidas(db, usuario))

    query = (
        db.query(Telemetria, Ubicacion, Parametro)
        .join(Dispositivo, Dispositivo.id_dspstv == Telemetria.id_dspstv)
        .join(Ubicacion, Ubicacion.id_ubccn == Dispositivo.id_ubccn)
        .join(Parametro, Parametro.id_prmtr == Telemetria.id_prmtr)
        .filter(Ubicacion.id_ubccn.in_(ids_ubicaciones_permitidas))
    )

    if ubicacion_ids:
        ids_solicitadas = set(ubicacion_ids) & ids_ubicaciones_permitidas
        query = query.filter(Ubicacion.id_ubccn.in_(ids_solicitadas))
    if parametro_ids:
        query = query.filter(Parametro.id_prmtr.in_(parametro_ids))

    total = query.count()
    filas = (
        query.order_by(Telemetria.fch_hr.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    items = [
        MedicionListItem(
            id_lctr=t.id_lctr,
            fch_hr=t.fch_hr,
            id_ubccn=u.id_ubccn,
            ubicacion_nombre=u.nmbr,
            id_prmtr=p.id_prmtr,
            parametro_nombre=p.nmbr,
            undd=p.undd,
            vlr=float(t.vlr),
        )
        for t, u, p in filas
    ]

    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": items}
