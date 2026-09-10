"""
HU 23 - Listar paneles

CA1: listado con nombre, fecha de creación y las acciones disponibles,
     de TODOS los paneles del usuario autenticado.
CA2: abrir un panel desde el listado es navegación de frontend (el
     contenido con ubicaciones/widgets llega en HU26/HU34).
CA3: búsqueda por nombre o fragmento, insensible a mayúsculas.

Los paneles NO son compartidos entre usuarios en v1.0 (ver "Detalles de
la conversación" de la HU): el filtro es siempre por id_usr (dueño), sin
excepción de rol -a diferencia de Ubicaciones/Dispositivos, acá no hay
un "Administrador ve todo"-. Orden por fecha de creación descendente por
defecto, tal como pide la HU.

HU 24 - Crear panel

CA1/CA4 son de frontend (mostrar/cerrar el formulario). CA2: único campo
del formulario es el nombre; se crea el panel vacío -sin ubicaciones ni
widgets, eso es HU26/HU34- y se devuelve con el mensaje "Panel creado
correctamente". CA3 (el panel recién creado, con "Añadir ubicaciones"
visible pero sin funcionalidad real) lo resuelve el frontend navegando a
GET /paneles/{id_pnl}, que ya existe desde HU23.

El nombre es único POR USUARIO (uq_pnl_usr_nombre), no por sede -a
diferencia de Ubicaciones-: es el propio dueño quien organiza su
colección de tableros, y dos usuarios de la misma sede pueden llamar
"Resumen" a paneles distintos sin chocar.

Crear un panel es exclusivo del rol Cliente Final (HU24: "YO COMO
Cliente Final..."), reforzado con un chequeo de ROL explícito además
del de permiso de módulo -ver ROL_CREADOR_DE_PANELES en crear_panel-:
que otro rol tenga Edición sobre "Tableros" no lo habilita a crear
paneles, son cosas independientes.

HU 25 - Editar / eliminar panel

CA1 (formulario de edición con el nombre precargado) es de frontend: el
propio GET /paneles/{id_pnl} de HU23 ya trae ese dato. CA2: PUT edita el
nombre, mismo chequeo de unicidad por usuario que HU24 pero excluyendo
el propio panel. CA3 (diálogo de confirmación) es de frontend. CA4:
DELETE borra el panel de forma PERMANENTE, junto con sus
PanelUbicacion/Widget asociados -que no tienen ON DELETE CASCADE en el
esquema real, así que se borran a mano en el orden correcto antes que
el Panel, ver eliminar_panel-. Los datos de telemetría no se tocan.

Mismo control de acceso que HU24 en ambos endpoints: rol Cliente Final
+ dueño del panel (_obtener_panel_propio, reusado también por el GET de
HU23).

Módulo de permiso: "Tableros" (HT-03), el mismo que ya usan /mapa-cliente
(HU17) y /mediciones (HU13).

HU 26 - Añadir ubicaciones al panel

CA1: GET /{id_pnl}/ubicaciones-disponibles -las asignadas al usuario según
HU21 que todavía no están en ESTE panel (filtra pnl_ubccn). CA2: POST
/{id_pnl}/ubicaciones asocia las seleccionadas ("Ubicaciones añadidas
correctamente"); una misma ubicación no puede añadirse dos veces al mismo
panel -uq_pnlubccn_pnl_ubccn ya lo garantiza, acá se traduce el
IntegrityError en un 422 legible-. CA3: GET /{id_pnl} (HU23) ahora
devuelve cada ubicación con el último valor de cada parámetro -reusa
services/mapa/ultimos_valores.py, la misma pieza que ya usa /mapa-cliente
para lo mismo-. CA4: DELETE /{id_pnl}/ubicaciones/{id_ubccn} retira la
ubicación ("Ubicación retirada del panel"); no borra telemetría ni la
ubicación misma, solo la fila de pnl_ubccn.

Mismo control de acceso que HU24/HU25: rol Cliente Final (ROL_CREADOR_DE_
PANELES) + dueño del panel (_obtener_panel_propio) para las dos
operaciones de escritura. El GET de disponibles no lleva el chequeo de
rol -ver el mismo criterio en obtener_panel, que tampoco lo lleva-: es
lectura sobre un panel que ya tiene que ser tuyo para llegar a esta rama.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Panel, PanelUbicacion, Ubicacion, Widget
from app.schemas import (
    PanelActualizado,
    PanelActualizar,
    PanelCreado,
    PanelCrear,
    PanelDetalle,
    PanelListItem,
    UbicacionEnPanel,
    UbicacionesAnadidas,
    UbicacionesAnadir,
    UbicacionParaPanel,
    UbicacionRetirada,
)
from app.security.permisos import EDICION, LECTURA, require_permiso
from app.security.ubicaciones_permitidas import ubicaciones_permitidas
from app.services.mapa.ultimos_valores import ultimos_valores_por_ubicacion

router = APIRouter(prefix="/paneles", tags=["Paneles"])

MSG_NOMBRE_DUPLICADO = "Ya tienes un panel con ese nombre"

# HU24: "YO COMO Cliente Final..." -crear paneles es exclusivo de este rol,
# sin importar el permiso de módulo que tenga otro rol sobre "Tableros".
# Administrador/Técnico CENERIS pueden tener Edición sobre "Tableros" por
# otros motivos (ver seed_usuarios_prueba.py) sin que eso los habilite a
# crear paneles: son cosas independientes, por eso el chequeo de rol va
# ADEMÁS del de permiso de módulo, no en su lugar.
ROL_CREADOR_DE_PANELES = "Cliente Final"


@router.get("")
def listar_paneles(
    busqueda: str | None = Query(default=None, description="Nombre del panel, parcial"),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", LECTURA)),
):
    id_usr = int(usuario["sub"])
    query = db.query(Panel).filter(Panel.id_usr == id_usr)

    if busqueda:
        patron = f"%{busqueda.lower()}%"
        query = query.filter(func.lower(Panel.nmbr).like(patron))

    paneles = query.order_by(Panel.fch_crcn.desc()).all()
    items = [PanelListItem.model_validate(p) for p in paneles]

    return {"items": items}


def _obtener_panel_propio(db: Session, id_pnl: int, id_usr: int) -> Panel:
    """El patrón "no es mío" para un Panel: siempre 404, nunca 403.

    Los paneles no se comparten entre usuarios en v1.0 (HU23), así que
    el panel de otro usuario responde igual que uno inexistente -no hay
    que confirmarle a quien pregunta que el recurso existe pero no es
    suyo-, mismo criterio que _verificar_acceso_ubicacion en HU21.

    Compartido por GET/{id_pnl} (HU23 CA2), PUT/{id_pnl} (HU25 CA2) y
    DELETE/{id_pnl} (HU25 CA4): las tres operan sobre "el panel de este
    usuario con este id", así que resuelven el mismo filtro una sola vez
    acá en vez de repetir el .query(...).filter(...) en cada endpoint.
    """
    panel = db.query(Panel).filter(Panel.id_pnl == id_pnl, Panel.id_usr == id_usr).first()
    if panel is None:
        raise HTTPException(status_code=404, detail="Panel no encontrado")
    return panel


def _detalle_panel(db: Session, panel: Panel) -> PanelDetalle:
    """HU26 CA3: el panel con sus ubicaciones ya añadidas, cada una con
    el último valor de cada parámetro (mismo resumen que /mapa-cliente,
    ver services/mapa/ultimos_valores.py)."""
    ubicaciones = (
        db.query(Ubicacion)
        .join(PanelUbicacion, PanelUbicacion.id_ubccn == Ubicacion.id_ubccn)
        .filter(PanelUbicacion.id_pnl == panel.id_pnl)
        .order_by(Ubicacion.nmbr)
        .all()
    )
    ultimos = ultimos_valores_por_ubicacion(db, [u.id_ubccn for u in ubicaciones])

    items = [
        UbicacionEnPanel(
            id_ubccn=ubicacion.id_ubccn,
            nmbr=ubicacion.nmbr,
            parametros=[
                {
                    "parametro": dato["parametro"],
                    "unidad": dato["unidad"],
                    # float() y no Decimal: Decimal no es serializable a
                    # JSON. Un evento de texto (evnt_txt) llega como str
                    # y se deja tal cual -mismo criterio que mapa_cliente.
                    "valor": (
                        float(dato["valor"])
                        if not isinstance(dato["valor"], str)
                        else dato["valor"]
                    ),
                    "fch_hr": dato["fch_hr"].isoformat() if dato["fch_hr"] else None,
                }
                for dato in sorted(
                    ultimos.get(ubicacion.id_ubccn, {}).values(), key=lambda d: d["parametro"]
                )
            ],
        )
        for ubicacion in ubicaciones
    ]
    return PanelDetalle(
        id_pnl=panel.id_pnl, nmbr=panel.nmbr, fch_crcn=panel.fch_crcn, ubicaciones=items
    )


@router.get("/{id_pnl}", response_model=PanelDetalle)
def obtener_panel(
    id_pnl: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", LECTURA)),
):
    """HU23 CA2: abrir un panel desde el listado. HU26 CA3: ahora incluye
    las ubicaciones ya añadidas con su telemetría más reciente -antes de
    HU26 este endpoint solo confirmaba que el panel existía."""
    id_usr = int(usuario["sub"])
    panel = _obtener_panel_propio(db, id_pnl, id_usr)

    return _detalle_panel(db, panel)


@router.get("/{id_pnl}/ubicaciones-disponibles")
def listar_ubicaciones_disponibles(
    id_pnl: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", LECTURA)),
):
    """HU26 CA1: el listado para 'Añadir ubicaciones' -las asignadas al
    usuario (HU21) que todavía no están en ESTE panel."""
    id_usr = int(usuario["sub"])
    panel = _obtener_panel_propio(db, id_pnl, id_usr)

    ids_permitidas = ubicaciones_permitidas(db, usuario)
    if not ids_permitidas:
        return {"items": []}

    ids_ya_en_panel = {
        id_ubccn
        for (id_ubccn,) in db.query(PanelUbicacion.id_ubccn).filter(
            PanelUbicacion.id_pnl == panel.id_pnl
        )
    }
    ids_disponibles = [i for i in ids_permitidas if i not in ids_ya_en_panel]
    if not ids_disponibles:
        return {"items": []}

    ubicaciones = (
        db.query(Ubicacion)
        .filter(Ubicacion.id_ubccn.in_(ids_disponibles))
        .order_by(Ubicacion.nmbr)
        .all()
    )
    return {"items": [UbicacionParaPanel.model_validate(u) for u in ubicaciones]}


@router.post("/{id_pnl}/ubicaciones", response_model=UbicacionesAnadidas)
def anadir_ubicaciones(
    id_pnl: int,
    body: UbicacionesAnadir,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", EDICION)),
):
    """HU26 CA2: 'AGREGAR AL PANEL' -> asocia las ubicaciones
    seleccionadas y devuelve "Ubicaciones añadidas correctamente".

    Mismo control de acceso que crear_panel/actualizar_panel: rol
    Cliente Final + dueño del panel."""
    if usuario.get("rol") != ROL_CREADOR_DE_PANELES:
        raise HTTPException(
            status_code=403, detail=f"Solo {ROL_CREADOR_DE_PANELES} puede editar paneles"
        )

    id_usr = int(usuario["sub"])
    panel = _obtener_panel_propio(db, id_pnl, id_usr)

    ids_permitidas = set(ubicaciones_permitidas(db, usuario))
    ids_ajenas = [i for i in body.ids_ubccn if i not in ids_permitidas]
    if ids_ajenas:
        raise HTTPException(
            status_code=403,
            detail=f"No tienes acceso a la(s) ubicación(es) {sorted(ids_ajenas)}",
        )

    for id_ubccn in body.ids_ubccn:
        db.add(PanelUbicacion(id_pnl=panel.id_pnl, id_ubccn=id_ubccn))

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # "Una misma ubicación no puede añadirse dos veces al mismo
        # panel" -uq_pnlubccn_pnl_ubccn- traducido a un 422 legible en
        # vez del IntegrityError crudo de Postgres.
        raise HTTPException(
            status_code=422,
            detail="Una o más ubicaciones seleccionadas ya están en este panel",
        ) from exc

    return UbicacionesAnadidas(panel=_detalle_panel(db, panel))


@router.delete("/{id_pnl}/ubicaciones/{id_ubccn}", response_model=UbicacionRetirada)
def quitar_ubicacion(
    id_pnl: int,
    id_ubccn: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", EDICION)),
):
    """HU26 CA4: 'Quitar' -> retira la ubicación del panel (no borra
    telemetría ni la ubicación misma, solo la fila de pnl_ubccn)."""
    if usuario.get("rol") != ROL_CREADOR_DE_PANELES:
        raise HTTPException(
            status_code=403, detail=f"Solo {ROL_CREADOR_DE_PANELES} puede editar paneles"
        )

    id_usr = int(usuario["sub"])
    panel = _obtener_panel_propio(db, id_pnl, id_usr)

    fila = (
        db.query(PanelUbicacion)
        .filter(PanelUbicacion.id_pnl == panel.id_pnl, PanelUbicacion.id_ubccn == id_ubccn)
        .first()
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="Esa ubicación no está en el panel")

    db.delete(fila)
    db.commit()

    return UbicacionRetirada(panel=_detalle_panel(db, panel))


def _resolver_sede_panel(usuario: dict) -> int:
    """id_sd del panel: sale del sede_id real del JWT (Fase 1 de HT-04
    resuelto esto vía prms_usr_sd para scope 'por_sede', que es el caso
    del actor de la HU, Cliente Final).

    RED DE SEGURIDAD, no la barrera principal: con el chequeo de rol en
    crear_panel (ROL_CREADOR_DE_PANELES), esta función solo se llama ya
    para un usuario "Cliente Final", y ese rol es siempre scope
    'por_sede' en el seed real -así que sede_id nunca debería venir en
    None acá en la práctica-. Se deja el chequeo igual, sin quitarlo, por
    si algún día existe un Cliente Final con scope 'global' (el esquema
    no lo impide) o el rol se reasigna sin pasar por el seed: en ese
    caso hay que rechazar con 422 en vez de adivinar una sede, porque el
    formulario de HU24 CA1 solo pide el nombre -no hay selector de sede-.
    """
    id_sd = usuario.get("sede_id")
    if id_sd is None:
        raise HTTPException(
            status_code=422,
            detail="Su usuario no está limitado a una sede única; no puede crear paneles todavía",
        )
    return id_sd


@router.post("", status_code=201)
def crear_panel(
    body: PanelCrear,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", EDICION)),
):
    """HU24 CA2: crea el panel vacío y devuelve 201 con "Panel creado
    correctamente", mismo patrón de respuesta que crear_ubicacion
    ({"mensaje": ..., <recurso>: ...}).

    Exige EDICIÓN sobre "Tableros" -mismo criterio que toda escritura en
    el proyecto, ver crear_ubicacion/crear_dispositivo- MÁS un chequeo
    de ROL explícito: HU24 es "YO COMO Cliente Final...", así que crear
    un panel es exclusivo de ese rol sin importar el permiso de módulo
    que tenga otro rol sobre "Tableros" (dos cosas independientes, ver
    ROL_CREADOR_DE_PANELES). El chequeo de rol va ANTES de resolver la
    sede: un Administrador/Técnico CENERIS/Administrador Comercial (todos
    scope 'global' en el seed) se corta acá, por rol, y nunca llega al
    422 de _resolver_sede_panel.

    El nombre se valida único POR USUARIO (uq_pnl_usr_nombre), no por
    sede: ver el docstring del módulo. Se chequea antes del insert para
    el mensaje de negocio; el UNIQUE real de la BD (ver except) sigue
    siendo la garantía ante dos altas simultáneas del mismo usuario.
    """
    if usuario.get("rol") != ROL_CREADOR_DE_PANELES:
        raise HTTPException(
            status_code=403, detail=f"Solo {ROL_CREADOR_DE_PANELES} puede crear paneles"
        )

    id_usr = int(usuario["sub"])
    id_sd = _resolver_sede_panel(usuario)

    duplicado = (
        db.query(Panel)
        .filter(Panel.id_usr == id_usr, func.lower(Panel.nmbr) == body.nmbr.lower())
        .first()
    )
    if duplicado is not None:
        raise HTTPException(status_code=409, detail=MSG_NOMBRE_DUPLICADO)

    panel = Panel(id_usr=id_usr, id_sd=id_sd, nmbr=body.nmbr)
    db.add(panel)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=MSG_NOMBRE_DUPLICADO)
    db.refresh(panel)

    return {
        "mensaje": "Panel creado correctamente",
        "panel": PanelCreado.model_validate(panel),
    }


@router.put("/{id_pnl}")
def actualizar_panel(
    id_pnl: int,
    body: PanelActualizar,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", EDICION)),
):
    """HU25 CA1/CA2: edita el nombre de un panel existente y devuelve 200
    con "Panel actualizado correctamente", mismo patrón de respuesta que
    crear_panel/actualizar_ubicacion ({"mensaje": ..., <recurso>: ...}).

    Mismo control de acceso que crear_panel: rol Cliente Final (HU25
    "reusa" la regla de HU24, no es un permiso nuevo) + el panel tiene
    que ser del usuario autenticado (_obtener_panel_propio, 404 si no).
    El chequeo de rol va primero, antes de siquiera buscar el panel: un
    Administrador no debería enterarse ni de si el id existe.

    El nombre se valida único POR USUARIO, EXCLUYENDO el propio panel
    -guardar sin cambiar el nombre, o cambiarlo por otro texto, no puede
    chocar consigo mismo-, mismo criterio que actualizar_ubicacion.
    """
    if usuario.get("rol") != ROL_CREADOR_DE_PANELES:
        raise HTTPException(
            status_code=403, detail=f"Solo {ROL_CREADOR_DE_PANELES} puede editar paneles"
        )

    id_usr = int(usuario["sub"])
    panel = _obtener_panel_propio(db, id_pnl, id_usr)

    duplicado = (
        db.query(Panel)
        .filter(
            Panel.id_usr == id_usr,
            func.lower(Panel.nmbr) == body.nmbr.lower(),
            Panel.id_pnl != id_pnl,
        )
        .first()
    )
    if duplicado is not None:
        raise HTTPException(status_code=409, detail=MSG_NOMBRE_DUPLICADO)

    panel.nmbr = body.nmbr

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=MSG_NOMBRE_DUPLICADO)
    db.refresh(panel)

    return {
        "mensaje": "Panel actualizado correctamente",
        "panel": PanelActualizado.model_validate(panel),
    }


@router.delete("/{id_pnl}")
def eliminar_panel(
    id_pnl: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", EDICION)),
):
    """HU25 CA3/CA4: elimina PERMANENTEMENTE un panel y todo su
    contenido. El mensaje de confirmación (CA3) y el diálogo en sí son
    de frontend; este endpoint es el "CONFIRMAR" de CA4.

    Mismo control de acceso que actualizar_panel: rol Cliente Final +
    dueño del panel (_obtener_panel_propio, 404 si no es suyo).

    BORRADO EN CASCADA EXPLÍCITO: las FK de pnl_ubccn.id_pnl y
    wdgt.id_pnl NO tienen ON DELETE CASCADE a nivel de base de datos
    (verificado contra el esquema real, no asumido -ver
    information_schema.referential_constraints, delete_rule=NO ACTION
    en ambas-), así que un DELETE del Panel con hijos todavía
    referenciándolo reventaría con IntegrityError. Por eso PanelUbicacion
    y Widget se borran acá antes que el Panel, en ese orden (Widget
    también depende de id_ubccn/id_prmtr, pero no de PanelUbicacion, así
    que el orden entre esos dos no importa entre sí -solo que ambos
    vayan antes que Panel).

    Los datos de TELEMETRÍA no se tocan (HU25, "Detalles de la
    conversación"): esto borra únicamente la configuración de
    visualización (qué ubicaciones/widgets arma ESTE panel), nunca las
    filas de tlmtr que esos widgets simplemente consultaban.
    """
    if usuario.get("rol") != ROL_CREADOR_DE_PANELES:
        raise HTTPException(
            status_code=403, detail=f"Solo {ROL_CREADOR_DE_PANELES} puede eliminar paneles"
        )

    id_usr = int(usuario["sub"])
    panel = _obtener_panel_propio(db, id_pnl, id_usr)

    db.query(Widget).filter(Widget.id_pnl == id_pnl).delete()
    db.query(PanelUbicacion).filter(PanelUbicacion.id_pnl == id_pnl).delete()
    db.delete(panel)
    db.commit()

    return {"mensaje": "Panel eliminado correctamente"}
