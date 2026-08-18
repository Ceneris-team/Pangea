"""
HU 07 - Listar ubicaciones

CA: tabla con Nombre, Descripción, Latitud, Longitud, Estado y Acciones.
Búsqueda por nombre (insensible a mayúsculas). Filtro por estado. Paginado
de 10 por defecto. Administrador y Técnico CENERIS ven el listado
completo; Cliente solo ve las ubicaciones que le fueron asignadas
(prms_ubccn, lógica definida en HU 21 - Sprint 3, pero el filtro ya
tiene que existir aquí).

HU 08 - Agregar ubicación

CA1 formulario con Nombre, Descripción (opcional), Latitud, Longitud y el
polígono dibujado sobre el mapa. CA2 guardar con estado "Activa" y
nombre único. CA3/CA4 (redirección al listado y cancelar) son de
frontend. Solo Administrador y Técnico CENERIS registran ubicaciones:
se exige Edición sobre el módulo "Ubicaciones" (HT-09), mismo mecanismo
que el GET de arriba usa con LECTURA.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Dispositivo, MapeoColumna, MapeoFormato, Parametro, Sede, Ubicacion, PermisoUbicacion,
)
from app.security.permisos import require_permiso, verificar_sede, LECTURA, EDICION
from app.schemas import (
    ParametroListItem, UbicacionCrear, UbicacionCreada, UbicacionDetalle, UbicacionListItem,
)

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
        query.order_by(Ubicacion.nmbr).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    )

    items = [UbicacionListItem.model_validate(u) for u in ubicaciones]

    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": items}


def _verificar_acceso_ubicacion(db: Session, usuario: dict, ubicacion: Ubicacion) -> None:
    """Mismo criterio de listar_ubicaciones: Administrador/Técnico ven
    cualquier ubicación (dentro de su sede, ver verificar_sede);
    Cliente Final solo la suya, vía PermisoUbicacion (HU 21)."""
    verificar_sede(usuario, ubicacion.id_sd, modulo="Ubicaciones", accion=LECTURA)
    if usuario.get("rol") not in ROLES_CON_ACCESO_TOTAL:
        id_usr = int(usuario["sub"])
        tiene_permiso = (
            db.query(PermisoUbicacion)
            .filter(
                PermisoUbicacion.id_ubccn == ubicacion.id_ubccn,
                PermisoUbicacion.id_usr == id_usr,
            )
            .first()
        )
        if tiene_permiso is None:
            raise HTTPException(status_code=404, detail="Ubicación no encontrada")


@router.get("/{id_ubccn}", response_model=UbicacionDetalle)
def obtener_ubicacion(
    id_ubccn: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ubicaciones", LECTURA)),
):
    """Ficha de una ubicación: mismos datos del listado (HU07) más el
    polígono, para un mapa de detalle."""
    ubicacion = db.query(Ubicacion).filter(Ubicacion.id_ubccn == id_ubccn).first()
    if ubicacion is None:
        raise HTTPException(status_code=404, detail="Ubicación no encontrada")

    _verificar_acceso_ubicacion(db, usuario, ubicacion)

    return UbicacionDetalle.model_validate(ubicacion)


@router.get("/{id_ubccn}/parametros", response_model=dict)
def parametros_en_uso(
    id_ubccn: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ubicaciones", LECTURA)),
):
    """Qué parámetros se están midiendo hoy en esta ubicación, derivado de
    los mapeos de formato de sus dispositivos (mismo criterio que HU13,
    GET /mediciones/parametros, pero para UNA ubicación puntual en vez del
    conjunto asignado al usuario). No es una lista editable a mano: si un
    parámetro no aparece acá es porque ningún dispositivo de esta
    ubicación tiene una columna mapeada a él todavía (ver HU06)."""
    ubicacion = db.query(Ubicacion).filter(Ubicacion.id_ubccn == id_ubccn).first()
    if ubicacion is None:
        raise HTTPException(status_code=404, detail="Ubicación no encontrada")

    _verificar_acceso_ubicacion(db, usuario, ubicacion)

    parametros = (
        db.query(Parametro)
        .join(MapeoColumna, MapeoColumna.id_prmtr == Parametro.id_prmtr)
        .join(MapeoFormato, MapeoFormato.id_mp == MapeoColumna.id_mp)
        .join(Dispositivo, Dispositivo.id_dspstv == MapeoFormato.id_dspstv)
        .filter(Dispositivo.id_ubccn == id_ubccn)
        .distinct()
        .order_by(Parametro.nmbr)
        .all()
    )
    items = [ParametroListItem.model_validate(p) for p in parametros]
    return {"items": items}


def _resolver_sede(usuario: dict, id_sd_body: int | None) -> int:
    """Mismo criterio que HU05/HU06 (routers/mapeos.py): un usuario con
    scope 'por_sede' siempre registra en su propia sede; uno 'global'
    debe indicar a qué sede pertenece la ubicación."""
    if usuario.get("scope") == "por_sede":
        return usuario["sede_id"]
    if id_sd_body is None:
        raise HTTPException(
            status_code=422,
            detail="Debe indicar id_sd: su usuario no está limitado a una sede única",
        )
    return id_sd_body


@router.post("", status_code=201)
def crear_ubicacion(
    body: UbicacionCrear,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ubicaciones", EDICION)),
):
    """HU08 CA2: registra la ubicación con estado 'Activa' y devuelve 201
    con "Ubicación registrada correctamente", siguiendo el patrón de
    respuesta de HU04/HU06 ({"mensaje": ..., <recurso>: ...}).

    El nombre se valida único POR SEDE, no global: es lo que implementa
    el modelo real (UniqueConstraint uq_ubccn_sd_nombre). Ver el resumen
    de cierre de la HU sobre esta diferencia con el texto del CA.
    """
    id_sd = _resolver_sede(usuario, body.id_sd)

    # Un id_sd inexistente reventaría como IntegrityError de FK en el
    # commit, y ahí se confundiría con el 409 de nombre duplicado.
    if db.query(Sede).filter(Sede.id_sd == id_sd).first() is None:
        raise HTTPException(status_code=422, detail=f"La sede {id_sd} no existe")

    # Un usuario 'por_sede' ya opera sobre su sede por _resolver_sede; esto
    # cubre al 'global' que manda un id_sd ajeno y a cualquier cambio futuro
    # que deje pasar id_sd desde el body.
    verificar_sede(usuario, id_sd, modulo="Ubicaciones", accion=EDICION)

    # CA: nombre único dentro de la sede. Se chequea antes del insert para
    # devolver el 409 con el mensaje de negocio; el UNIQUE de la BD sigue
    # siendo la garantía real ante dos altas simultáneas (ver except).
    duplicada = (
        db.query(Ubicacion)
        .filter(Ubicacion.id_sd == id_sd, func.lower(Ubicacion.nmbr) == body.nmbr.lower())
        .first()
    )
    if duplicada is not None:
        raise HTTPException(
            status_code=409, detail="Ya existe una ubicación con ese nombre en esta sede"
        )

    ubicacion = Ubicacion(
        id_sd=id_sd,
        nmbr=body.nmbr,
        dscrpcn=(body.dscrpcn.strip() or None) if body.dscrpcn else None,
        lttd=body.lttd,
        lngtd=body.lngtd,
        plgn_gjsn=body.plgn_gjsn,
        # estd lo pone el server_default 'Activa' del modelo (CA2).
    )
    db.add(ubicacion)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Ya existe una ubicación con ese nombre en esta sede"
        )
    db.refresh(ubicacion)

    return {
        "mensaje": "Ubicación registrada correctamente",
        "ubicacion": UbicacionCreada.model_validate(ubicacion),
    }
