"""
HU 07 - Listar ubicaciones

CA: tabla con Nombre, Descripción, Latitud, Longitud, Estado y Acciones.
Búsqueda por nombre (insensible a mayúsculas). Filtro por estado. Paginado
de 10 por defecto. Administrador y Técnico CENERIS ven el listado
completo; Cliente solo ve las ubicaciones que le fueron asignadas
(prms_ubccn, lógica definida en HU 21 - Sprint 3, pero el filtro ya
tiene que existir aquí).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Ubicacion, PermisoUbicacion
from app.security.permisos import require_permiso, LECTURA
from app.schemas import UbicacionListItem

router = APIRouter(prefix="/ubicaciones", tags=["Ubicaciones"])

ROLES_CON_ACCESO_TOTAL = {"Administrador", "Tecnico CENERIS", "Técnico CENERIS"}


@router.get("")
def listar_ubicaciones(
    busqueda: str | None = Query(default=None, description="Nombre de la ubicación, parcial"),
    estado: str | None = Query(default=None, description="Activa / Inactiva"),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=10, ge=1, le=100),  # CA: 10 por defecto
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ubicaciones", LECTURA)),
):
    query = db.query(Ubicacion)

    # CA: Administrador/Tecnico CENERIS ven todo; Cliente solo lo asignado (HU 21)
    if usuario.get("rol") not in ROLES_CON_ACCESO_TOTAL:
        id_usr = int(usuario["sub"])
        query = query.join(
            PermisoUbicacion, PermisoUbicacion.id_ubccn == Ubicacion.id_ubccn
        ).filter(PermisoUbicacion.id_usr == id_usr)

    if busqueda:
        patron = f"%{busqueda.lower()}%"
        query = query.filter(func.lower(Ubicacion.nmbr).like(patron))
    if estado:
        query = query.filter(Ubicacion.estd == estado)

    total = query.count()
    ubicaciones = (
        query.order_by(Ubicacion.nmbr)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    items = [UbicacionListItem.model_validate(u) for u in ubicaciones]

    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": items}
