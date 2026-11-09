"""
HU 27 - Listar alarmas
HU 28 - Crear alarma (PP-73)

Base: módulo de la rama `fabio` (commit ca9e795, 04/09/2026), integrado a
dev para PP-73. Única regla nueva de dev: crear una alarma es
configuración operativa, así que exige la suscripción vigente de la
empresa igual que Ubicaciones, Dispositivos e Ingesta (exigir_operacion).

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

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.alarma import (
    Alarma,
    CondicionAlarma,
    DestinatarioAlarma,
    EstadoAlarma,
    IntentoNotificacion,
    NotificacionEnviada,
)
from app.models.cliente_sede import Sede
from app.models.mapeo_dispositivo import Dispositivo, MapeoColumna, MapeoFormato, Parametro
from app.models.ubicacion_conexion import Ubicacion
from app.schemas import ParametroListItem
from app.schemas_alarmas import (
    AlarmaActualizar,
    AlarmaCreada,
    AlarmaCrear,
    AlarmaListItem,
    DestinatarioCrear,
    UbicacionParaAlarma,
)
from app.security.entorno import sedes_permitidas
from app.security.permisos import EDICION, LECTURA, require_permiso
from app.security.ubicaciones_permitidas import ubicaciones_permitidas
from app.services.contratos import exigir_operacion

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
        .filter(Alarma.id_ubccn.in_(ubicaciones_permitidas(db, usuario)))
    )

    if busqueda:
        # PP-72 CA3: coincidencia parcial sin distinguir mayúsculas. autoescape
        # hace que "%" y "_" se busquen como texto y no como comodines de LIKE
        # (con like() a mano, buscar "_" devolvía todas las alarmas).
        query = query.filter(
            func.lower(Alarma.nmbr).contains(busqueda.strip().lower(), autoescape=True)
        )
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

    # Regla de dev (multiempresa): una empresa en modo consulta, sin
    # suscripción vigente, no puede dar de alta configuración operativa.
    # Es la misma comprobación que hace verificar_sede(..., EDICION), sin
    # su filtro de sede: el acceso a la ubicación ya lo decidió HU21 arriba.
    # Va después de validar el formulario para que un dato mal elegido dé
    # su 422 y no un 409.
    sede = db.get(Sede, ubicacion.id_sd)
    if sede is not None:
        exigir_operacion(db, sede.id_clnt)

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
    db.add_all(
        [
            DestinatarioAlarma(id_alrm=alarma.id_alrm, cnl="email", crr=str(correo).lower())
            for correo in body.destinatarios
        ]
    )

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


def _alarma_propia(db, usuario, id_alarma, *, editar=False):
    query = db.query(Alarma).filter(
        Alarma.id_alrm == id_alarma,
        Alarma.id_usr == int(usuario["sub"]),
        Alarma.id_ubccn.in_(ubicaciones_permitidas(db, usuario)),
    )
    if editar:
        query = query.with_for_update()
    alarma = query.first()
    if alarma is None:
        raise HTTPException(404, "Alarma no encontrada")
    if editar:
        sede = db.get(Sede, alarma.id_sd)
        exigir_operacion(db, sede.id_clnt)
    return alarma


@router.get("/notificaciones")
def historial_notificaciones(
    alarma_id: int | None = None,
    tipo: str | None = None,
    estado: str | None = None,
    destinatario: str | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Alarmas", LECTURA)),
):
    if any(f is not None and f.tzinfo is None for f in (desde, hasta)):
        raise HTTPException(422, "Las fechas deben incluir zona horaria")
    if desde and hasta and desde > hasta:
        raise HTTPException(422, "La fecha inicial no puede superar la final")
    propias = db.query(Alarma.id_alrm).filter(
        Alarma.id_usr == int(usuario["sub"]),
        Alarma.id_ubccn.in_(ubicaciones_permitidas(db, usuario)),
    )
    q = db.query(NotificacionEnviada).filter(
        NotificacionEnviada.id_usr == int(usuario["sub"]),
        or_(NotificacionEnviada.id_alrm.is_(None), NotificacionEnviada.id_alrm.in_(propias)),
    )
    sedes = sedes_permitidas(db, usuario)
    if sedes is not None:
        q = q.filter(or_(NotificacionEnviada.id_sd.is_(None), NotificacionEnviada.id_sd.in_(sedes)))
    if alarma_id is not None:
        _alarma_propia(db, usuario, alarma_id)
        q = q.filter(NotificacionEnviada.id_alrm == alarma_id)
    for campo, valor in ((NotificacionEnviada.tipo, tipo), (NotificacionEnviada.estd, estado)):
        if valor:
            q = q.filter(campo == valor)
    if destinatario:
        q = q.filter(func.lower(NotificacionEnviada.dstn) == destinatario.strip().lower())
    if desde:
        q = q.filter(NotificacionEnviada.fch_crcn >= desde)
    if hasta:
        q = q.filter(NotificacionEnviada.fch_crcn <= hasta)
    total = q.count()
    filas = (
        q.order_by(NotificacionEnviada.fch_crcn.desc(), NotificacionEnviada.id_ntfccn.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )
    intentos = {}
    if filas:
        for intento in (
            db.query(IntentoNotificacion)
            .filter(
                IntentoNotificacion.id_ntfccn.in_([n.id_ntfccn for n in filas]),
            )
            .order_by(IntentoNotificacion.id_intnt)
            .all()
        ):
            intentos.setdefault(intento.id_ntfccn, []).append(
                {
                    "numero": intento.numero,
                    "fecha": intento.fecha,
                    "resultado": intento.resultado,
                    "error": intento.error,
                    "mensaje_id": intento.mensaje_id,
                }
            )
    return {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "items": [
            {
                "id": n.id_ntfccn,
                "alarma_id": n.id_alrm,
                "tipo": n.tipo,
                "destinatario": n.dstn,
                "estado": n.estd,
                "creada": n.fch_crcn,
                "enviada": n.fch_env,
                "proximo_intento": (
                    n.prxm_intnt if n.estd in {"Pendiente", "Reintentando", "Encolado"} else None
                ),
                "reintentos": n.rntnts,
                "ultimo_error": n.ultimo_error,
                "mensaje_id": n.mensaje_id,
                "intentos": intentos.get(n.id_ntfccn, []),
            }
            for n in filas
        ],
    }


@router.get("/{id_alarma}/destinatarios")
def listar_destinatarios(
    id_alarma: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Alarmas", LECTURA)),
):
    _alarma_propia(db, usuario, id_alarma)
    filas = (
        db.query(DestinatarioAlarma)
        .filter_by(id_alrm=id_alarma, cnl="email")
        .order_by(DestinatarioAlarma.crr)
        .all()
    )
    return {"items": [{"id": d.id_dstntr, "correo": d.crr} for d in filas]}


@router.post("/{id_alarma}/destinatarios", status_code=201)
def agregar_destinatario(
    id_alarma: int,
    body: DestinatarioCrear,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Alarmas", EDICION)),
):
    _alarma_propia(db, usuario, id_alarma, editar=True)
    correo = str(body.correo).lower()
    actuales = db.query(DestinatarioAlarma).filter_by(id_alrm=id_alarma, cnl="email")
    if actuales.filter(func.lower(DestinatarioAlarma.crr) == correo).first():
        raise HTTPException(409, "Este correo ya recibe notificaciones de la alarma")
    if actuales.count() >= 100:
        raise HTTPException(422, "La alarma admite hasta 100 destinatarios")
    d = DestinatarioAlarma(id_alrm=id_alarma, cnl="email", crr=correo)
    db.add(d)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Este correo ya recibe notificaciones de la alarma") from None
    return {"id": d.id_dstntr, "correo": d.crr}


@router.delete("/{id_alarma}/destinatarios/{id_destinatario}", status_code=204)
def quitar_destinatario(
    id_alarma: int,
    id_destinatario: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Alarmas", EDICION)),
):
    _alarma_propia(db, usuario, id_alarma, editar=True)
    d = (
        db.query(DestinatarioAlarma)
        .filter_by(id_alrm=id_alarma, id_dstntr=id_destinatario, cnl="email")
        .first()
    )
    if d is None:
        raise HTTPException(404, "Destinatario no encontrado")
    db.delete(d)
    db.commit()


@router.patch("/{id_alarma}")
def actualizar_alarma(
    id_alarma: int,
    body: AlarmaActualizar,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Alarmas", EDICION)),
):
    alarma = _alarma_propia(db, usuario, id_alarma, editar=True)
    if body.estado is not None:
        alarma.estd = body.estado
    if body.condiciones is not None:
        db.query(CondicionAlarma).filter_by(id_alrm=id_alarma).delete()
        db.add_all(
            [
                CondicionAlarma(id_alrm=id_alarma, oprdr=c.oprdr, vlr_umbrl=c.vlr_umbrl)
                for c in body.condiciones
            ]
        )
    if body.estado is not None or body.condiciones is not None:
        db.query(EstadoAlarma).filter_by(id_alrm=id_alarma).update({"en_alarma": False})
    db.commit()
    return {"mensaje": "Alarma actualizada", "estado": alarma.estd}
