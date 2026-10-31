"""
HU 23 - Listar paneles

CA1: listado con nombre, fecha de creación y las acciones disponibles,
     de TODOS los paneles del usuario autenticado.
CA2: abrir un panel desde el listado muestra ubicaciones y widgets.
CA3: búsqueda por nombre o fragmento, insensible a mayúsculas.

Los paneles son privados al crearse. El propietario puede compartirlos con
su empresa; los lectores solo ven ubicaciones y widgets dentro de su alcance.
El listado se ordena por fecha de creación descendente.

HU 24 - Crear panel

CA1/CA4 son de frontend (mostrar/cerrar el formulario). CA2: único campo
del formulario es el nombre; se crea el panel vacío -sin ubicaciones ni
widgets- y se devuelve con el mensaje "Panel creado correctamente".
CA3: el frontend abre el nuevo panel y permite añadir ubicaciones (HU26).

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
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    ArchivoIngesta,
    Dispositivo,
    Panel,
    PanelUbicacion,
    Parametro,
    Sede,
    Ubicacion,
    Widget,
)
from app.schemas import (
    PanelActualizado,
    PanelActualizar,
    PanelCreado,
    PanelCrear,
    PanelDetalle,
    PanelListItem,
    PanelUbicacionAgregar,
    PanelUbicacionesAgregar,
    PanelVisibilidad,
    WidgetGuardar,
    WidgetsReordenar,
)
from app.security.entorno import filtrar_sedes, sedes_permitidas
from app.security.permisos import EDICION, LECTURA, require_permiso, verificar_sede
from app.security.ubicaciones_permitidas import ubicaciones_permitidas
from app.services.contratos import condiciones_de, ultimo_contrato
from app.services.limites_plan import fecha_comercial
from app.services.mapa.semaforo import evaluar_semaforo
from app.services.mapa.ultimos_valores import ultimos_valores_por_ubicacion


def verificar_tableros_contratados(
    db: Session = Depends(get_db), usuario: dict = Depends(require_permiso("Tableros", LECTURA))
):
    cliente_id = usuario.get("cliente_id")
    if cliente_id is None and usuario.get("sede_id"):
        sede = db.get(Sede, usuario["sede_id"])
        cliente_id = sede.id_clnt if sede else None
    contrato = ultimo_contrato(db, cliente_id, fecha_comercial()) if cliente_id else None
    if contrato and "tableros" not in condiciones_de(db, contrato)["funcionalidades"]:
        raise HTTPException(403, "Los tableros no están incluidos en la suscripción contratada")


router = APIRouter(
    prefix="/paneles", tags=["Paneles"], dependencies=[Depends(verificar_tableros_contratados)]
)

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
    alcance = Panel.id_usr == id_usr
    proyecto_activo = usuario.get("proyecto_id")
    if proyecto_activo is not None:
        paneles_del_proyecto = db.query(PanelUbicacion.id_pnl).filter(
            PanelUbicacion.id_ubccn == proyecto_activo
        )
        sede_activa = db.query(Ubicacion.id_sd).filter(Ubicacion.id_ubccn == proyecto_activo)
        paneles_con_ubicaciones = db.query(PanelUbicacion.id_pnl)
        legado_vacio = (
            Panel.id_ubccn_origen.is_(None)
            & Panel.id_sd.in_(sede_activa)
            & ~Panel.id_pnl.in_(paneles_con_ubicaciones)
        )
        alcance = and_(
            alcance,
            or_(
                Panel.id_ubccn_origen == proyecto_activo,
                Panel.id_pnl.in_(paneles_del_proyecto),
                legado_vacio,
            ),
        )
    if usuario.get("scope") != "global":
        visibles = ubicaciones_permitidas(db, usuario)
        compartidos_visibles = db.query(PanelUbicacion.id_pnl).filter(
            PanelUbicacion.id_ubccn.in_(visibles)
        )
        compartidos = (Panel.vsbldd == "Empresa") & Panel.id_pnl.in_(compartidos_visibles)
        if proyecto_activo is not None:
            compartidos = compartidos & Panel.id_pnl.in_(paneles_del_proyecto)
        alcance = or_(alcance, compartidos)
    query = db.query(Panel).filter(alcance)
    if usuario.get("scope") == "por_cliente":
        query = query.join(Sede, Sede.id_sd == Panel.id_sd).filter(
            Sede.id_clnt == usuario["cliente_id"]
        )
    else:
        query = filtrar_sedes(query, Panel.id_sd, db, usuario)

    if busqueda:
        patron = f"%{busqueda.lower()}%"
        query = query.filter(func.lower(Panel.nmbr).like(patron))

    paneles = query.order_by(Panel.fch_crcn.desc()).all()
    visibles = set(ubicaciones_permitidas(db, usuario))
    proyectos_por_panel: dict[int, list[dict]] = {p.id_pnl: [] for p in paneles}
    if paneles and visibles:
        asociaciones = (
            db.query(PanelUbicacion.id_pnl, Ubicacion.id_ubccn, Ubicacion.nmbr)
            .join(Ubicacion, Ubicacion.id_ubccn == PanelUbicacion.id_ubccn)
            .filter(
                PanelUbicacion.id_pnl.in_(proyectos_por_panel), Ubicacion.id_ubccn.in_(visibles)
            )
            .all()
        )
        for id_pnl, id_ubccn, nmbr in asociaciones:
            proyectos_por_panel[id_pnl].append({"id_ubccn": id_ubccn, "nmbr": nmbr})
        origenes = (
            db.query(Panel.id_pnl, Ubicacion.id_ubccn, Ubicacion.nmbr)
            .join(Ubicacion, Ubicacion.id_ubccn == Panel.id_ubccn_origen)
            .filter(Panel.id_pnl.in_(proyectos_por_panel), Ubicacion.id_ubccn.in_(visibles))
            .all()
        )
        for id_pnl, id_ubccn, nmbr in origenes:
            if not any(item["id_ubccn"] == id_ubccn for item in proyectos_por_panel[id_pnl]):
                proyectos_por_panel[id_pnl].append({"id_ubccn": id_ubccn, "nmbr": nmbr})
    items = [
        PanelListItem.model_validate(
            {
                **PanelListItem.model_validate(p).model_dump(),
                "es_propietario": p.id_usr == id_usr,
                "proyectos": sorted(proyectos_por_panel[p.id_pnl], key=lambda item: item["nmbr"]),
            }
        )
        for p in paneles
    ]

    activo = db.get(Ubicacion, proyecto_activo) if proyecto_activo is not None else None
    return {
        "items": items,
        "proyecto_activo": {"id_ubccn": activo.id_ubccn, "nmbr": activo.nmbr} if activo else None,
    }


def _obtener_panel_propio(db: Session, id_pnl: int, id_usr: int) -> Panel:
    """Resuelve las acciones del propietario; un panel ajeno devuelve 404."""
    panel = db.query(Panel).filter(Panel.id_pnl == id_pnl, Panel.id_usr == id_usr).first()
    if panel is None:
        raise HTTPException(status_code=404, detail="Panel no encontrado")
    return panel


def _panel_en_proyecto_activo(db: Session, panel: Panel, usuario: dict) -> None:
    proyecto_id = usuario.get("proyecto_id")
    if proyecto_id is None or panel.id_ubccn_origen == proyecto_id:
        return
    if panel.id_ubccn_origen is None:
        proyecto = db.get(Ubicacion, proyecto_id)
        tiene_asociaciones = (
            db.query(PanelUbicacion.id_pnl).filter(PanelUbicacion.id_pnl == panel.id_pnl).first()
        )
        if proyecto is not None and proyecto.id_sd == panel.id_sd and tiene_asociaciones is None:
            return
    asociado = (
        db.query(PanelUbicacion.id_pnl)
        .filter(PanelUbicacion.id_pnl == panel.id_pnl, PanelUbicacion.id_ubccn == proyecto_id)
        .first()
    )
    if asociado is None:
        raise HTTPException(404, "Panel no encontrado en el proyecto activo")


def _verificar_ambito_panel(db: Session, panel: Panel, usuario: dict) -> None:
    if usuario.get("scope") == "por_cliente":
        sede = db.get(Sede, panel.id_sd)
        if sede is None or sede.id_clnt != usuario.get("cliente_id"):
            raise HTTPException(404, "Panel no encontrado")
    else:
        verificar_sede(usuario, panel.id_sd, db, modulo="Tableros", accion=LECTURA)


def _panel_para_lectura(db: Session, id_pnl: int, usuario: dict) -> Panel:
    panel = db.get(Panel, id_pnl)
    if panel is None:
        raise HTTPException(404, "Panel no encontrado")
    if panel.id_usr == int(usuario["sub"]):
        _verificar_ambito_panel(db, panel, usuario)
        _panel_en_proyecto_activo(db, panel, usuario)
        return panel
    if usuario.get("scope") == "global" or panel.vsbldd != "Empresa":
        raise HTTPException(404, "Panel no encontrado")
    _verificar_ambito_panel(db, panel, usuario)
    visibles = ubicaciones_permitidas(db, usuario)
    if (
        not db.query(PanelUbicacion.id_pnl)
        .filter(PanelUbicacion.id_pnl == id_pnl, PanelUbicacion.id_ubccn.in_(visibles))
        .first()
    ):
        raise HTTPException(404, "Panel no encontrado")
    return panel


@router.get("/{id_pnl}", response_model=PanelDetalle)
def obtener_panel(
    id_pnl: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", LECTURA)),
):
    """HU23 CA2: abrir un panel desde el listado.

    Los datos básicos del panel se complementan con /contenido, que entrega
    las ubicaciones (HU26) y los widgets (HU34) accesibles al usuario.
    """
    panel = _panel_para_lectura(db, id_pnl, usuario)
    return PanelDetalle.model_validate(panel).model_copy(
        update={"es_propietario": panel.id_usr == int(usuario["sub"])}
    )


def _panel_accesible(db: Session, id_pnl: int, usuario: dict) -> Panel:
    panel = _obtener_panel_propio(db, id_pnl, int(usuario["sub"]))
    _verificar_ambito_panel(db, panel, usuario)
    _panel_en_proyecto_activo(db, panel, usuario)
    return panel


def _exigir_gestion_panel(usuario: dict) -> None:
    if usuario.get("scope") != "por_cliente" and usuario.get("rol") != ROL_CREADOR_DE_PANELES:
        raise HTTPException(403, f"Solo {ROL_CREADOR_DE_PANELES} puede gestionar paneles")


@router.put("/{id_pnl}/visibilidad")
def cambiar_visibilidad_panel(
    id_pnl: int,
    body: PanelVisibilidad,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", EDICION)),
):
    _exigir_gestion_panel(usuario)
    panel = _panel_accesible(db, id_pnl, usuario)
    panel.vsbldd = body.vsbldd
    db.commit()
    return {
        "mensaje": (
            "Panel compartido con la empresa" if body.vsbldd == "Empresa" else "Panel privado"
        ),
        "vsbldd": body.vsbldd,
    }


@router.post("/{id_pnl}/duplicar", status_code=201)
def duplicar_panel(
    id_pnl: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", EDICION)),
):
    _exigir_gestion_panel(usuario)
    original = _panel_accesible(db, id_pnl, usuario)
    id_usr = int(usuario["sub"])
    base = f"Copia de {original.nmbr}"[:100].rstrip()
    nombre = base
    numero = 2
    while db.query(Panel.id_pnl).filter(Panel.id_usr == id_usr, Panel.nmbr == nombre).first():
        sufijo = f" {numero}"
        nombre = f"{base[:100 - len(sufijo)].rstrip()}{sufijo}"
        numero += 1
    copia = Panel(
        id_usr=id_usr,
        id_sd=original.id_sd,
        id_ubccn_origen=usuario.get("proyecto_id") or original.id_ubccn_origen,
        nmbr=nombre,
        vsbldd="Privado",
    )
    db.add(copia)
    db.flush()
    visibles = set(ubicaciones_permitidas(db, usuario))
    ubicaciones = db.query(PanelUbicacion.id_ubccn).filter(PanelUbicacion.id_pnl == id_pnl).all()
    ids_copiados = {fila[0] for fila in ubicaciones if fila[0] in visibles}
    db.add_all(PanelUbicacion(id_pnl=copia.id_pnl, id_ubccn=id_ubccn) for id_ubccn in ids_copiados)
    widgets = (
        db.query(Widget)
        .filter(Widget.id_pnl == id_pnl, Widget.id_ubccn.in_(ids_copiados))
        .order_by(Widget.pscn, Widget.id_wdgt)
        .all()
    )
    db.add_all(
        Widget(
            id_pnl=copia.id_pnl,
            tp=w.tp,
            id_prmtr=w.id_prmtr,
            id_ubccn=w.id_ubccn,
            pscn=w.pscn,
            ancho=w.ancho,
        )
        for w in widgets
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un panel con ese nombre")
    return {"mensaje": "Panel duplicado correctamente", "panel": PanelCreado.model_validate(copia)}


def _ubicacion_visible(db: Session, usuario: dict, id_ubccn: int) -> Ubicacion:
    ubicacion = db.get(Ubicacion, id_ubccn)
    if ubicacion is None or id_ubccn not in ubicaciones_permitidas(db, usuario):
        raise HTTPException(404, "Ubicación no disponible")
    return ubicacion


def _widget_propio(db: Session, id_pnl: int, id_wdgt: int) -> Widget:
    widget = db.query(Widget).filter(Widget.id_pnl == id_pnl, Widget.id_wdgt == id_wdgt).first()
    if widget is None:
        raise HTTPException(404, "Widget no encontrado")
    return widget


def _widget_item(widget: Widget, parametro: Parametro) -> dict:
    return {
        "id_wdgt": widget.id_wdgt,
        "tp": widget.tp,
        "id_prmtr": widget.id_prmtr,
        "id_ubccn": widget.id_ubccn,
        "pscn": widget.pscn,
        "ancho": widget.ancho,
        "parametro_nombre": parametro.nmbr,
        "undd": parametro.undd,
    }


@router.get("/{id_pnl}/contenido")
def obtener_contenido_panel(
    id_pnl: int,
    dispositivo_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", LECTURA)),
):
    _panel_para_lectura(db, id_pnl, usuario)
    visibles = set(ubicaciones_permitidas(db, usuario))
    ubicaciones = (
        db.query(Ubicacion)
        .join(PanelUbicacion, PanelUbicacion.id_ubccn == Ubicacion.id_ubccn)
        .filter(PanelUbicacion.id_pnl == id_pnl, Ubicacion.id_ubccn.in_(visibles))
        .order_by(Ubicacion.nmbr, Ubicacion.id_ubccn)
        .all()
    )
    if (
        dispositivo_id is not None
        and not db.query(Dispositivo.id_dspstv)
        .filter(
            Dispositivo.id_dspstv == dispositivo_id,
            Dispositivo.id_ubccn.in_([u.id_ubccn for u in ubicaciones]),
        )
        .first()
    ):
        raise HTTPException(404, "Dispositivo no disponible en el panel")
    widgets = (
        db.query(Widget, Parametro)
        .join(Parametro, Parametro.id_prmtr == Widget.id_prmtr)
        .filter(Widget.id_pnl == id_pnl, Widget.id_ubccn.in_(visibles))
        .order_by(Widget.pscn, Widget.id_wdgt)
        .all()
    )
    ultimos = ultimos_valores_por_ubicacion(db, [u.id_ubccn for u in ubicaciones], dispositivo_id)
    dispositivos = (
        db.query(Dispositivo)
        .filter(Dispositivo.id_ubccn.in_([u.id_ubccn for u in ubicaciones]))
        .order_by(Dispositivo.nmbr, Dispositivo.id_dspstv)
        .all()
    )
    conexiones = {d.id_cnxn for d in dispositivos}
    archivos = (
        (
            db.query(ArchivoIngesta)
            .filter(ArchivoIngesta.id_cnxn.in_(conexiones))
            .distinct(ArchivoIngesta.id_cnxn)
            .order_by(
                ArchivoIngesta.id_cnxn,
                ArchivoIngesta.fch_dtccn.desc(),
                ArchivoIngesta.id_archv.desc(),
            )
            .all()
        )
        if conexiones
        else []
    )
    ultimo_archivo = {a.id_cnxn: a for a in archivos}
    return {
        "proyecto_activo": (
            {
                "id_ubccn": usuario["proyecto_id"],
                "nmbr": db.get(Ubicacion, usuario["proyecto_id"]).nmbr,
            }
            if usuario.get("proyecto_id") is not None
            else None
        ),
        "ubicaciones": [
            {
                "id_ubccn": u.id_ubccn,
                "nmbr": u.nmbr,
                "dscrpcn": u.dscrpcn,
                "lttd": float(u.lttd),
                "lngtd": float(u.lngtd),
                "estd": u.estd,
                "semaforo": (
                    evaluar_semaforo(
                        {
                            nombre: dato["valor"]
                            for nombre, dato in ultimos.get(u.id_ubccn, {}).items()
                        }
                    )
                    if ultimos.get(u.id_ubccn)
                    else "sin_datos"
                ),
                "ultima_lectura": (
                    max(
                        (
                            dato["fch_hr"]
                            for dato in ultimos.get(u.id_ubccn, {}).values()
                            if dato["fch_hr"]
                        ),
                        default=None,
                    ).isoformat()
                    if ultimos.get(u.id_ubccn)
                    else None
                ),
                "ultimos_valores": [
                    {
                        "id_prmtr": dato["id_prmtr"],
                        "id_dspstv": dato["id_dspstv"],
                        "parametro": dato["parametro"],
                        "unidad": dato["unidad"],
                        "dispositivo_nombre": dato["dispositivo_nombre"],
                        "valor": (
                            dato["valor"]
                            if isinstance(dato["valor"], str)
                            else float(dato["valor"])
                        ),
                        "fch_hr": dato["fch_hr"].isoformat() if dato["fch_hr"] else None,
                    }
                    for dato in sorted(
                        ultimos.get(u.id_ubccn, {}).values(), key=lambda d: d["parametro"]
                    )
                ],
            }
            for u in ubicaciones
        ],
        "dispositivos": [
            {
                "id_dspstv": d.id_dspstv,
                "id_ubccn": d.id_ubccn,
                "nmbr": d.nmbr,
                "estd": d.estd,
                "ultima_ingesta": (
                    {
                        "estado": ultimo_archivo[d.id_cnxn].estd,
                        "fecha": ultimo_archivo[d.id_cnxn].fch_dtccn.isoformat(),
                    }
                    if d.id_cnxn in ultimo_archivo
                    else None
                ),
            }
            for d in dispositivos
        ],
        "widgets": [_widget_item(w, p) for w, p in widgets],
    }


@router.get("/{id_pnl}/ubicaciones/disponibles")
def ubicaciones_disponibles_panel(
    id_pnl: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", LECTURA)),
):
    _panel_accesible(db, id_pnl, usuario)
    ubicaciones = (
        db.query(Ubicacion)
        .filter(Ubicacion.id_ubccn.in_(ubicaciones_permitidas(db, usuario)))
        .order_by(Ubicacion.nmbr, Ubicacion.id_ubccn)
        .all()
    )
    return {"items": [{"id_ubccn": u.id_ubccn, "nmbr": u.nmbr} for u in ubicaciones]}


@router.post("/{id_pnl}/ubicaciones", status_code=201)
def agregar_ubicacion_panel(
    id_pnl: int,
    body: PanelUbicacionAgregar,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", EDICION)),
):
    _exigir_gestion_panel(usuario)
    _panel_accesible(db, id_pnl, usuario)
    ubicacion = _ubicacion_visible(db, usuario, body.id_ubccn)
    existente = (
        db.query(PanelUbicacion)
        .filter(PanelUbicacion.id_pnl == id_pnl, PanelUbicacion.id_ubccn == body.id_ubccn)
        .first()
    )
    if existente:
        raise HTTPException(409, "La ubicación ya está añadida al panel")
    panel = db.get(Panel, id_pnl)
    if panel.id_ubccn_origen is None:
        panel.id_ubccn_origen = body.id_ubccn
    db.add(PanelUbicacion(id_pnl=id_pnl, id_ubccn=body.id_ubccn))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "La ubicación ya está añadida al panel")
    return {
        "mensaje": "Ubicación añadida correctamente",
        "ubicacion": {"id_ubccn": ubicacion.id_ubccn, "nmbr": ubicacion.nmbr},
    }


@router.post("/{id_pnl}/ubicaciones/lote", status_code=201)
def agregar_ubicaciones_panel(
    id_pnl: int,
    body: PanelUbicacionesAgregar,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", EDICION)),
):
    _exigir_gestion_panel(usuario)
    _panel_accesible(db, id_pnl, usuario)
    ids = body.ids
    if any(id_ubccn <= 0 for id_ubccn in ids) or len(ids) != len(set(ids)):
        raise HTTPException(422, "Selecciona ubicaciones válidas sin repetir")
    if not set(ids).issubset(ubicaciones_permitidas(db, usuario)):
        raise HTTPException(404, "Ubicación no disponible")
    ubicaciones = db.query(Ubicacion).filter(Ubicacion.id_ubccn.in_(ids)).all()
    if len(ubicaciones) != len(ids):
        raise HTTPException(404, "Ubicación no disponible")
    existente = (
        db.query(PanelUbicacion)
        .filter(PanelUbicacion.id_pnl == id_pnl, PanelUbicacion.id_ubccn.in_(ids))
        .first()
    )
    if existente:
        raise HTTPException(409, "Una ubicación ya está añadida al panel")
    panel = db.get(Panel, id_pnl)
    if panel.id_ubccn_origen is None and ids:
        panel.id_ubccn_origen = usuario.get("proyecto_id") or ids[0]
    db.add_all(PanelUbicacion(id_pnl=id_pnl, id_ubccn=id_ubccn) for id_ubccn in ids)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Una ubicación ya está añadida al panel")
    por_id = {u.id_ubccn: u for u in ubicaciones}
    return {
        "mensaje": "Ubicaciones añadidas correctamente",
        "ubicaciones": [{"id_ubccn": id_ubccn, "nmbr": por_id[id_ubccn].nmbr} for id_ubccn in ids],
    }


@router.delete("/{id_pnl}/ubicaciones/{id_ubccn}")
def quitar_ubicacion_panel(
    id_pnl: int,
    id_ubccn: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", EDICION)),
):
    _exigir_gestion_panel(usuario)
    _panel_accesible(db, id_pnl, usuario)
    asociacion = (
        db.query(PanelUbicacion)
        .filter(PanelUbicacion.id_pnl == id_pnl, PanelUbicacion.id_ubccn == id_ubccn)
        .first()
    )
    if asociacion is None:
        raise HTTPException(404, "Ubicación no encontrada en el panel")
    db.query(Widget).filter(Widget.id_pnl == id_pnl, Widget.id_ubccn == id_ubccn).delete()
    db.delete(asociacion)
    db.commit()
    return {"mensaje": "Ubicación retirada del panel"}


def _validar_widget(db: Session, id_pnl: int, body: WidgetGuardar, usuario: dict) -> None:
    _ubicacion_visible(db, usuario, body.id_ubccn)
    asociacion = (
        db.query(PanelUbicacion)
        .filter(PanelUbicacion.id_pnl == id_pnl, PanelUbicacion.id_ubccn == body.id_ubccn)
        .first()
    )
    if asociacion is None:
        raise HTTPException(422, "Añade la ubicación al panel antes de crear el widget")
    parametro = db.get(Parametro, body.id_prmtr)
    if parametro is None or parametro.tipo_dato != "numerico":
        raise HTTPException(422, "El widget necesita un parámetro numérico disponible")


@router.post("/{id_pnl}/widgets", status_code=201)
def crear_widget_panel(
    id_pnl: int,
    body: WidgetGuardar,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", EDICION)),
):
    _exigir_gestion_panel(usuario)
    _panel_accesible(db, id_pnl, usuario)
    _validar_widget(db, id_pnl, body, usuario)
    siguiente = db.query(func.max(Widget.pscn)).filter(Widget.id_pnl == id_pnl).scalar()
    widget = Widget(
        id_pnl=id_pnl,
        tp=body.tp,
        id_prmtr=body.id_prmtr,
        id_ubccn=body.id_ubccn,
        ancho=body.ancho,
        pscn=(siguiente if siguiente is not None else -1) + 1,
    )
    db.add(widget)
    db.commit()
    db.refresh(widget)
    return {
        "mensaje": "Widget creado correctamente",
        "widget": _widget_item(widget, db.get(Parametro, body.id_prmtr)),
    }


@router.put("/{id_pnl}/widgets/orden")
def reordenar_widgets_panel(
    id_pnl: int,
    body: WidgetsReordenar,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", EDICION)),
):
    _exigir_gestion_panel(usuario)
    _panel_accesible(db, id_pnl, usuario)
    widgets = db.query(Widget).filter(Widget.id_pnl == id_pnl).with_for_update().all()
    if len(body.ids) != len(widgets) or set(body.ids) != {w.id_wdgt for w in widgets}:
        raise HTTPException(422, "El orden debe incluir todos los widgets del panel una sola vez")
    posiciones = {id_wdgt: posicion for posicion, id_wdgt in enumerate(body.ids)}
    for widget in widgets:
        widget.pscn = posiciones[widget.id_wdgt]
    db.commit()
    return {"mensaje": "Orden de widgets guardado correctamente"}


@router.put("/{id_pnl}/widgets/{id_wdgt}")
def actualizar_widget_panel(
    id_pnl: int,
    id_wdgt: int,
    body: WidgetGuardar,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", EDICION)),
):
    _exigir_gestion_panel(usuario)
    _panel_accesible(db, id_pnl, usuario)
    widget = _widget_propio(db, id_pnl, id_wdgt)
    _validar_widget(db, id_pnl, body, usuario)
    widget.tp, widget.id_prmtr, widget.id_ubccn, widget.ancho = (
        body.tp,
        body.id_prmtr,
        body.id_ubccn,
        body.ancho,
    )
    db.commit()
    return {
        "mensaje": "Widget actualizado correctamente",
        "widget": _widget_item(widget, db.get(Parametro, body.id_prmtr)),
    }


@router.delete("/{id_pnl}/widgets/{id_wdgt}")
def eliminar_widget_panel(
    id_pnl: int,
    id_wdgt: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", EDICION)),
):
    _exigir_gestion_panel(usuario)
    _panel_accesible(db, id_pnl, usuario)
    widget = _widget_propio(db, id_pnl, id_wdgt)
    db.delete(widget)
    db.commit()
    return {"mensaje": "Widget eliminado correctamente"}


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
    if usuario.get("scope") != "por_cliente" and usuario.get("rol") != ROL_CREADOR_DE_PANELES:
        raise HTTPException(
            status_code=403, detail=f"Solo {ROL_CREADOR_DE_PANELES} puede crear paneles"
        )

    id_usr = int(usuario["sub"])
    id_sd = (
        _resolver_sede_panel(usuario)
        if usuario.get("scope") != "por_cliente"
        else next(iter(sedes_permitidas(db, usuario) or []), None)
    )
    if id_sd is None:
        raise HTTPException(422, "Crea una sede en el proyecto antes de crear un tablero")

    duplicado = (
        db.query(Panel)
        .filter(Panel.id_usr == id_usr, func.lower(Panel.nmbr) == body.nmbr.lower())
        .first()
    )
    if duplicado is not None:
        raise HTTPException(status_code=409, detail=MSG_NOMBRE_DUPLICADO)

    panel = Panel(
        id_usr=id_usr, id_sd=id_sd, id_ubccn_origen=usuario.get("proyecto_id"), nmbr=body.nmbr
    )
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
    if usuario.get("scope") != "por_cliente" and usuario.get("rol") != ROL_CREADOR_DE_PANELES:
        raise HTTPException(
            status_code=403, detail=f"Solo {ROL_CREADOR_DE_PANELES} puede editar paneles"
        )

    id_usr = int(usuario["sub"])
    panel = _obtener_panel_propio(db, id_pnl, id_usr)
    verificar_sede(usuario, panel.id_sd, db, modulo="Tableros", accion=LECTURA)

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
    if usuario.get("scope") != "por_cliente" and usuario.get("rol") != ROL_CREADOR_DE_PANELES:
        raise HTTPException(
            status_code=403, detail=f"Solo {ROL_CREADOR_DE_PANELES} puede eliminar paneles"
        )

    id_usr = int(usuario["sub"])
    panel = _obtener_panel_propio(db, id_pnl, id_usr)
    verificar_sede(usuario, panel.id_sd, db, modulo="Tableros", accion=LECTURA)

    db.query(Widget).filter(Widget.id_pnl == id_pnl).delete()
    db.query(PanelUbicacion).filter(PanelUbicacion.id_pnl == id_pnl).delete()
    db.delete(panel)
    db.commit()

    return {"mensaje": "Panel eliminado correctamente"}
