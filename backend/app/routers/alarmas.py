"""
HU 27 - Listar alarmas
HU 28 - Crear alarma

HU27 CA1: al cargar el módulo "Gestión de Alarmas y Notificaciones", se
muestra una tabla con todas las alarmas configuradas por el usuario,
indicando nombre de la alarma, parámetro asociado, condición, estado y
acciones (las acciones las arma el frontend a partir de id_alrm/estd, no
viajan como dato). CA2: filtro por estado. CA3: búsqueda por nombre.

HU28 CA:
  CA1  el formulario de creación ofrece Nombre de la alarma, Parámetro a
       monitorear y Ubicación asociada
  CA2  "SIGUIENTE" lleva al paso de condiciones (HU29)
  CA3  "GUARDAR" crea la alarma con estado Activa, la agrega al listado y
       muestra "Alarma creada correctamente"
  CA4  "CANCELAR" descarta el formulario sin crear ningún registro

Detalles de la conversación:
  - Paginado de 10 registros por defecto -mismo criterio y misma forma de
    respuesta (total/pagina/por_pagina/items) que listar_dispositivos en
    routers/dispositivos.py-.
  - "Cada usuario solo puede ver y gestionar sus propias alarmas": a
    diferencia de Dispositivos/Ubicaciones, acá NO hay una vista
    "administrador ve todo" -Alarma.id_usr es el dueño, y el listado
    siempre filtra por el id_usr del token, para cualquier rol-. Por eso
    tampoco hace falta verificar_sede: el filtro por dueño ya aísla el
    recurso.
  - El caso "sin alarmas configuradas" (mensaje + botón 'Crear alarma'
    visible) es responsabilidad del frontend: el listado solo devuelve
    total=0 igual que cualquier listado vacío.

El alta (HU28) es un flujo de DOS pasos -datos generales acá, condiciones
en HU29- pero UNA sola escritura: el registro recién existe cuando el
usuario pulsa GUARDAR al final del paso 2 (CA3). Por eso el POST recibe
las condiciones junto con los datos generales en vez de crear la alarma
al pasar de paso: si HU28 persistiera al pulsar SIGUIENTE, abandonar el
paso 2 dejaría alarmas a medio configurar, y CA4 dice explícitamente que
salir del alta no crea ningún registro. HU29 define las reglas de negocio
de esas condiciones; acá solo se valida lo que ya exige el modelo (el
operador dentro del CHECK de cndcn_alrm).

Qué ubicaciones y parámetros ofrece el formulario: las asignadas al
usuario según HU 21 (security/ubicaciones_permitidas.py), igual que HU13
y HU17. Es un filtro distinto del de "mis alarmas" que usa el listado
-uno acota lo que se puede monitorear, el otro lo ya creado-.

Los parámetros que se pueden monitorear se restringen a los de tipo
'numerico'. Una condición de alarma es una comparación contra un umbral
(cndcn_alrm.vlr_umbrl es Numeric), y un parámetro de texto -"Puerta
Abierta", ver models/evento_texto.py- no admite ">= 3.5": ofrecerlo en el
selector sería dejar armar una alarma que no puede dispararse nunca.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.alarma import Alarma, CondicionAlarma
from app.models.mapeo_dispositivo import Dispositivo, MapeoColumna, MapeoFormato, Parametro
from app.models.ubicacion_conexion import Ubicacion
from app.schemas import (
    AlarmaCreada,
    AlarmaCrear,
    AlarmaListItem,
    ParametroListItem,
    UbicacionParaAlarma,
)
from app.security.permisos import EDICION, LECTURA, require_permiso
from app.security.ubicaciones_permitidas import ubicaciones_permitidas

router = APIRouter(prefix="/alarmas", tags=["Alarmas"])


def _formatear_condicion(condicion: CondicionAlarma | None, unidad: str) -> str | None:
    """'> 30 °C' a partir de oprdr/vlr_umbrl -la HU29 (configurar
    condición) es la que arma cndcn_alrm; acá solo se muestra.

    vlr_umbrl es Numeric(14,4): se formatea con 'g' para no arrastrar los
    ceros de relleno del tipo (30.0000 -> '30', 30.5000 -> '30.5')."""
    if condicion is None:
        return None
    valor = f"{float(condicion.vlr_umbrl):g}"
    return f"{condicion.oprdr} {valor} {unidad}".strip()


def _query_parametros_monitoreables(db: Session, ids_ubicaciones: list[int]):
    """HU28: parámetros numéricos efectivamente mapeados (HU06) para algún
    dispositivo de esas ubicaciones.

    Mismo recorrido que /mediciones/parametros (DEC-09: el mapeo cuelga de
    mp_frmt.id_dspstv, no al revés), con dos diferencias propias de HU28:
    se puede acotar a UNA ubicación -la que el usuario eligió en el
    formulario- y se excluyen los parámetros de tipo 'texto'.
    """
    return (
        db.query(Parametro)
        .join(MapeoColumna, MapeoColumna.id_prmtr == Parametro.id_prmtr)
        .join(MapeoFormato, MapeoFormato.id_mp == MapeoColumna.id_mp)
        .join(Dispositivo, Dispositivo.id_dspstv == MapeoFormato.id_dspstv)
        .filter(
            Dispositivo.id_ubccn.in_(ids_ubicaciones),
            Parametro.tipo_dato == "numerico",
        )
        .distinct()
    )


@router.get("/ubicaciones")
def listar_ubicaciones_para_alarma(
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Alarmas", LECTURA)),
):
    """HU28 CA1: pobla el selector "Ubicación asociada" con las ubicaciones
    asignadas al usuario (HU21)."""
    ids_ubicaciones = ubicaciones_permitidas(db, usuario)
    if not ids_ubicaciones:
        return {"items": []}

    ubicaciones = (
        db.query(Ubicacion)
        .filter(Ubicacion.id_ubccn.in_(ids_ubicaciones))
        .order_by(Ubicacion.nmbr)
        .all()
    )
    return {"items": [UbicacionParaAlarma.model_validate(u) for u in ubicaciones]}


@router.get("/parametros")
def listar_parametros_para_alarma(
    ubicacion_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Alarmas", LECTURA)),
):
    """HU28 CA1: pobla el selector "Parámetro a monitorear".

    Con `ubicacion_id` devuelve los de esa ubicación (es lo que usa el
    formulario, que encadena los dos selectores); sin él, los de todas las
    ubicaciones asignadas. Una ubicación ajena no da 403 sino lista vacía:
    el id no es un recurso que el usuario haya pedido ver, es el valor de
    un selector, y filtrarlo contra HU21 ya impide que se filtre nada.
    """
    ids_ubicaciones = ubicaciones_permitidas(db, usuario)
    if ubicacion_id is not None:
        ids_ubicaciones = [i for i in ids_ubicaciones if i == ubicacion_id]
    if not ids_ubicaciones:
        return {"items": []}

    parametros = _query_parametros_monitoreables(db, ids_ubicaciones).order_by(Parametro.nmbr).all()
    return {"items": [ParametroListItem.model_validate(p) for p in parametros]}


@router.get("")
def listar_alarmas(
    busqueda: str | None = Query(default=None, description="Nombre de la alarma, parcial"),
    estado: str | None = Query(default=None, description="Activa / Inactiva"),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=10, ge=1, le=100),  # CA: 10 por defecto
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Alarmas", LECTURA)),
):
    id_usr = int(usuario["sub"])

    query = (
        db.query(Alarma, Parametro.nmbr, Parametro.undd)
        .join(Parametro, Parametro.id_prmtr == Alarma.id_prmtr)
        .filter(Alarma.id_usr == id_usr)
    )

    if busqueda:
        query = query.filter(func.lower(Alarma.nmbr).like(f"%{busqueda.lower()}%"))
    if estado:
        query = query.filter(Alarma.estd == estado)

    total = query.count()
    filas = query.order_by(Alarma.nmbr).offset((pagina - 1) * por_pagina).limit(por_pagina).all()

    # Las condiciones de esta página, en una sola consulta (evita N+1).
    ids_alarma = [alarma.id_alrm for alarma, _nombre, _undd in filas]
    condiciones_por_alarma: dict[int, CondicionAlarma] = {}
    if ids_alarma:
        for condicion in (
            db.query(CondicionAlarma)
            .filter(CondicionAlarma.id_alrm.in_(ids_alarma))
            .order_by(CondicionAlarma.id_cndcn)
            .all()
        ):
            # Una alarma puede tener más de una condición (HU29); el
            # listado solo necesita una referencia rápida, así que se
            # queda con la primera encontrada.
            condiciones_por_alarma.setdefault(condicion.id_alrm, condicion)

    items = [
        AlarmaListItem(
            id_alrm=alarma.id_alrm,
            nmbr=alarma.nmbr,
            parametro_nombre=nombre_parametro,
            condicion=_formatear_condicion(condiciones_por_alarma.get(alarma.id_alrm), unidad),
            estd=alarma.estd,
        )
        for alarma, nombre_parametro, unidad in filas
    ]

    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": items}


@router.post("", status_code=201, response_model=AlarmaCreada)
def crear_alarma(
    body: AlarmaCrear,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Alarmas", EDICION)),
):
    """HU28 CA3: crea la alarma con estado Activa y devuelve 201 con el
    mensaje "Alarma creada correctamente" y la fila tal como la muestra el
    listado de HU27.

    CA4 no tiene endpoint: cancelar es descartar el formulario en el
    cliente, y como nada se escribió al pasar de paso (ver el módulo), no
    hay registro que deshacer.
    """
    ids_ubicaciones = ubicaciones_permitidas(db, usuario)
    if body.id_ubccn not in ids_ubicaciones:
        # 403 y no 404: el recurso existe, lo que falta es la asignación de
        # HU21. Mismo criterio que el resto de la app para un recurso
        # fuera del alcance del usuario.
        raise HTTPException(status_code=403, detail="No tienes acceso a la ubicación seleccionada")

    ubicacion = db.query(Ubicacion).filter(Ubicacion.id_ubccn == body.id_ubccn).first()
    if ubicacion is None:
        raise HTTPException(status_code=422, detail=f"La ubicación {body.id_ubccn} no existe")

    # El parámetro tiene que ser uno de los que ofrece el selector: si no,
    # se podría crear una alarma sobre un parámetro que esa ubicación no
    # mide (nunca se dispararía) o sobre uno de texto (no comparable con
    # un umbral).
    parametro = (
        _query_parametros_monitoreables(db, [body.id_ubccn])
        .filter(Parametro.id_prmtr == body.id_prmtr)
        .first()
    )
    if parametro is None:
        raise HTTPException(
            status_code=422,
            detail="El parámetro seleccionado no está disponible en esa ubicación",
        )

    alarma = Alarma(
        # El dueño de la alarma, que es por quien filtra el listado de
        # HU27 ("cada usuario solo ve y gestiona las suyas").
        id_usr=int(usuario["sub"]),
        # La sede sale de la ubicación, no del JWT: alrm.id_sd es NOT NULL
        # y tiene que ser la sede DEL RECURSO -un usuario 'global' no
        # tiene sede propia que poner acá-.
        id_sd=ubicacion.id_sd,
        nmbr=body.nmbr,
        id_prmtr=parametro.id_prmtr,
        id_ubccn=ubicacion.id_ubccn,
        # estd lo pone el server_default 'Activa' del modelo (CA3).
    )
    db.add(alarma)
    db.flush()

    condiciones = [
        CondicionAlarma(
            id_alrm=alarma.id_alrm,
            oprdr=condicion.oprdr,
            vlr_umbrl=condicion.vlr_umbrl,
        )
        for condicion in body.condiciones
    ]
    db.add_all(condiciones)

    db.commit()
    db.refresh(alarma)

    return AlarmaCreada(
        alarma=AlarmaListItem(
            id_alrm=alarma.id_alrm,
            nmbr=alarma.nmbr,
            parametro_nombre=parametro.nmbr,
            # Misma forma que el listado: la primera condición, formateada.
            condicion=_formatear_condicion(condiciones[0] if condiciones else None, parametro.undd),
            estd=alarma.estd,
        )
    )
