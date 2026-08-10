"""
HU 10 - Listar dispositivos

CA: tabla con Nombre, Marca, Ubicación y Estado. Búsqueda por nombre o marca
(insensible a mayúsculas). Filtro por ubicación y por estado. Paginado de 10
por defecto. Mismo patrón de acceso que HU07 (routers/ubicaciones.py):
Administrador y Técnico CENERIS ven el listado completo (dentro de su sede);
Cliente Final solo ve dispositivos cuya ubicación esté en PermisoUbicacion.

Dispositivo no tiene id_sd propio (ver mapeo_dispositivo.py): el
aislamiento por sede (HT-09 CA3) se resuelve vía join con Ubicacion, mismo
criterio que mapeos.py e ingesta.py usan con su propio id_sd.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Dispositivo, Ubicacion, PermisoUbicacion
from app.security.permisos import require_permiso, LECTURA
from app.schemas import DispositivoListItem

router = APIRouter(prefix="/dispositivos", tags=["Dispositivos"])

ROLES_CON_ACCESO_TOTAL = {"Administrador", "Tecnico CENERIS", "Técnico CENERIS"}


@router.get("")
def listar_dispositivos(
    busqueda: str | None = Query(default=None, description="Nombre o marca del dispositivo, parcial"),
    id_ubccn: int | None = Query(default=None, description="Filtrar por ubicación"),
    estado: str | None = Query(default=None, description="Activo / Inactivo"),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=10, ge=1, le=100),  # CA: 10 por defecto
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Dispositivos", LECTURA)),
):
    query = db.query(Dispositivo, Ubicacion.nmbr).join(
        Ubicacion, Ubicacion.id_ubccn == Dispositivo.id_ubccn
    )

    # Aislamiento por sede (HT-09 CA3): un usuario 'por_sede' solo ve los
    # dispositivos de ubicaciones de su sede, aunque pida otra explícitamente.
    if usuario.get("scope") == "por_sede":
        query = query.filter(Ubicacion.id_sd == usuario["sede_id"])

    # CA: Administrador/Tecnico CENERIS ven todo; Cliente solo lo asignado.
    if usuario.get("rol") not in ROLES_CON_ACCESO_TOTAL:
        id_usr = int(usuario["sub"])
        query = query.join(
            PermisoUbicacion, PermisoUbicacion.id_ubccn == Dispositivo.id_ubccn
        ).filter(PermisoUbicacion.id_usr == id_usr)

    if busqueda:
        patron = f"%{busqueda.lower()}%"
        query = query.filter(
            func.lower(Dispositivo.nmbr).like(patron) | func.lower(Dispositivo.mrc).like(patron)
        )
    if id_ubccn is not None:
        query = query.filter(Dispositivo.id_ubccn == id_ubccn)
    if estado:
        query = query.filter(Dispositivo.estd == estado)

    total = query.count()
    filas = (
        query.order_by(Dispositivo.nmbr)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    items = [
        DispositivoListItem(
            id_dspstv=dispositivo.id_dspstv,
            nmbr=dispositivo.nmbr,
            mrc=dispositivo.mrc,
            ubicacion_nombre=ubicacion_nombre,
            estd=dispositivo.estd,
        )
        for dispositivo, ubicacion_nombre in filas
    ]

    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": items}
