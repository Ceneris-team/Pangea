"""
HU 28 - Crear alarma
HU 27 - Listar alarmas (lo mínimo que HU28 necesita para cerrar sus CA)

HU28 CA:
  CA1  el formulario de creación ofrece Nombre de la alarma, Parámetro a
       monitorear y Ubicación asociada
  CA2  "SIGUIENTE" lleva al paso de condiciones (HU29)
  CA3  "GUARDAR" crea la alarma con estado Activa, la agrega al listado y
       muestra "Alarma creada correctamente"
  CA4  "CANCELAR" descarta el formulario sin crear ningún registro

El alta es un flujo de DOS pasos (datos generales acá, condiciones en
HU29) pero una sola escritura: el registro recién existe cuando el
usuario pulsa GUARDAR al final del paso 2 (CA3). Por eso el POST recibe
las condiciones junto con los datos generales en vez de crear la alarma
al pasar de paso -si HU28 persistiera al pulsar SIGUIENTE, abandonar el
paso 2 dejaría alarmas a medio configurar, y CA4 dice explícitamente que
salir del alta no crea ningún registro-. HU29 define las reglas de
negocio de esas condiciones; acá solo se valida lo que ya exige el
modelo (el operador dentro del CHECK de cndcn_alrm).

Qué ve cada usuario: las ubicaciones asignadas según HU 21
(security/ubicaciones_permitidas.py), igual que HU13 y HU17. No se llama
además a verificar_sede(): HU21 es la regla de acceso a ubicaciones en
esta app, y sumarle un filtro de sede haría que una ubicación asignada
explícitamente en prms_ubccn quedara igual fuera de alcance.

Los parámetros que se pueden monitorear se restringen a los de tipo
'numerico'. Una condición de alarma es una comparación contra un umbral
(cndcn_alrm.vlr_umbrl es Numeric), y un parámetro de texto -"Puerta
Abierta", ver models/evento_texto.py- no admite ">= 3.5": ofrecerlo en el
selector sería dejar armar una alarma que no puede dispararse nunca.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Alarma,
    CondicionAlarma,
    Dispositivo,
    MapeoColumna,
    MapeoFormato,
    Parametro,
    Ubicacion,
)
from app.schemas import (
    AlarmaCreada,
    AlarmaCrear,
    AlarmaListItem,
    CondicionAlarmaItem,
    ParametroListItem,
    UbicacionParaAlarma,
)
from app.security.permisos import EDICION, LECTURA, require_permiso
from app.security.ubicaciones_permitidas import ubicaciones_permitidas

router = APIRouter(prefix="/alarmas", tags=["Alarmas"])


def _query_parametros_monitoreables(db: Session, ids_ubicaciones: list[int]):
    """Parámetros numéricos efectivamente mapeados (HU06) para algún
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


def _condiciones_por_alarma(db: Session, ids_alarmas: list[int]) -> dict[int, list]:
    """Las condiciones de varias alarmas en UNA consulta, agrupadas por
    alarma. Se resuelve así -y no con un relationship en el modelo- para
    que el listado no dispare una consulta por fila (N+1)."""
    agrupadas: dict[int, list] = {id_alrm: [] for id_alrm in ids_alarmas}
    if not ids_alarmas:
        return agrupadas
    condiciones = (
        db.query(CondicionAlarma)
        .filter(CondicionAlarma.id_alrm.in_(ids_alarmas))
        .order_by(CondicionAlarma.id_cndcn)
        .all()
    )
    for condicion in condiciones:
        agrupadas[condicion.id_alrm].append(condicion)
    return agrupadas


def _a_list_item(
    alarma: Alarma,
    parametro: Parametro,
    ubicacion: Ubicacion,
    condiciones: list,
) -> AlarmaListItem:
    return AlarmaListItem(
        id_alrm=alarma.id_alrm,
        nmbr=alarma.nmbr,
        id_prmtr=parametro.id_prmtr,
        parametro_nombre=parametro.nmbr,
        undd=parametro.undd,
        id_ubccn=ubicacion.id_ubccn,
        ubicacion_nombre=ubicacion.nmbr,
        estd=alarma.estd,
        fch_crcn=alarma.fch_crcn,
        condiciones=[CondicionAlarmaItem.model_validate(c) for c in condiciones],
    )


@router.get("/ubicaciones")
def listar_ubicaciones_para_alarma(
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Alarmas", LECTURA)),
):
    """CA1: pobla el selector "Ubicación asociada" con las ubicaciones
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
    """CA1: pobla el selector "Parámetro a monitorear".

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
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Alarmas", LECTURA)),
):
    """HU27 (mínimo): el listado al que CA3 agrega la alarma recién creada
    y al que CA4 devuelve al cancelar. Se acota a las ubicaciones
    asignadas al usuario (HU21), que es lo que aísla las alarmas de un
    cliente de las de otro."""
    ids_ubicaciones = ubicaciones_permitidas(db, usuario)
    if not ids_ubicaciones:
        return {"total": 0, "pagina": pagina, "por_pagina": por_pagina, "items": []}

    query = (
        db.query(Alarma, Parametro, Ubicacion)
        .join(Parametro, Parametro.id_prmtr == Alarma.id_prmtr)
        .join(Ubicacion, Ubicacion.id_ubccn == Alarma.id_ubccn)
        .filter(Alarma.id_ubccn.in_(ids_ubicaciones))
    )
    total = query.count()
    filas = (
        query.order_by(Alarma.fch_crcn.desc(), Alarma.id_alrm.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    condiciones = _condiciones_por_alarma(db, [a.id_alrm for a, _, _ in filas])

    return {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "items": [_a_list_item(a, p, u, condiciones[a.id_alrm]) for a, p, u in filas],
    }


@router.post("", status_code=201, response_model=AlarmaCreada)
def crear_alarma(
    body: AlarmaCrear,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Alarmas", EDICION)),
):
    """CA3: crea la alarma con estado Activa y devuelve 201 con el mensaje
    "Alarma creada correctamente" y la fila tal como la muestra el listado.

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
    for condicion in condiciones:
        db.refresh(condicion)

    return AlarmaCreada(alarma=_a_list_item(alarma, parametro, ubicacion, condiciones))
