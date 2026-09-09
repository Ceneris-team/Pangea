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

Módulo de permiso: "Tableros" (HT-03), el mismo que ya usan /mapa-cliente
(HU17) y /mediciones (HU13).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Panel
from app.schemas import PanelCrear, PanelCreado, PanelDetalle, PanelListItem
from app.security.permisos import EDICION, LECTURA, require_permiso

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


@router.get("/{id_pnl}", response_model=PanelDetalle)
def obtener_panel(
    id_pnl: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", LECTURA)),
):
    """HU23 CA2: abrir un panel desde el listado.

    El contenido con ubicaciones y widgets asociados llega en HU26/HU34;
    por ahora este endpoint solo confirma que el panel existe y es del
    usuario autenticado. Los paneles no se comparten entre usuarios en
    v1.0, así que el panel de otro usuario responde 404 -no 403-, igual
    que _verificar_acceso_ubicacion en HU21: no hay que confirmarle a
    quien pregunta que el recurso existe pero no es suyo.
    """
    id_usr = int(usuario["sub"])
    panel = (
        db.query(Panel).filter(Panel.id_pnl == id_pnl, Panel.id_usr == id_usr).first()
    )
    if panel is None:
        raise HTTPException(status_code=404, detail="Panel no encontrado")

    return PanelDetalle.model_validate(panel)


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
