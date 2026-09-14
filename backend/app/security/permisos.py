"""
HT-09: Middleware de autorización en FastAPI.

Valida, para cada endpoint del PMV, que el usuario autenticado (HT-04) tenga
permiso sobre el módulo y la acción solicitados según la matriz de HT-03
(tabla `prms_usr_sd`, Usuario-Sede-Rol-Permiso). Si el permiso es
insuficiente devuelve 403 (distinto del 401 que ya cubre HT-04 para tokens
inválidos o expirados), y registra el intento denegado tanto en el logger
`auditoria.autorizacion` como en `lg_adtr` (HT-11 CA5: "los accesos
denegados de HT-09 aparecen en el mismo histórico" que las ediciones de
HU20/HU21).

Uso en un endpoint:

    from fastapi import Depends
    from app.security.permisos import require_permiso, LECTURA, EDICION

    @router.post("/ubicaciones")
    def crear_ubicacion(usuario: dict = Depends(require_permiso("Ubicaciones", EDICION))):
        ...

Para endpoints que operan sobre un recurso de una sede concreta (p. ej.
listar/añadir dispositivos de una sede), además hay que llamar a
verificar_sede() para que un usuario con scope "por_sede" no pueda tocar
sedes ajenas aunque tenga permiso de edición en la suya:

    @router.get("/dispositivos")
    def listar_dispositivos(
        sede_id: int,
        db: Session = Depends(get_db),
        usuario: dict = Depends(require_permiso("Dispositivos", LECTURA)),
    ):
        verificar_sede(usuario, sede_id, db, modulo="Dispositivos", accion=LECTURA)
        ...

HISTORIAL: la primera versión de este archivo (adda9bb) usaba una matriz
rol -> módulo -> acciones hardcodeada en Python (MATRIZ_PERMISOS) como
implementación provisional, a falta de conectar con HT-03. Se elimina sin
dejarla como fallback: además de estar duplicada con `prms_usr_sd`, incluía
un módulo "Mediciones" que nunca fue válido según el CHECK constraint real
de HT-03 (`mdl IN ('Usuarios','Ubicaciones','Dispositivos','Ingesta',
'Tableros','Alarmas','Comercial')`), prueba de que había quedado
desalineada del modelo real. La matriz de permisos ahora vive solo en la
base de datos (tabla `prms_usr_sd`), editable sin tocar código, que es lo
que pedía HT-03 CA4 desde el principio.
"""

import logging

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LogAuditoria, PermisoUsuarioSede

from .dependencies import get_current_user

logger = logging.getLogger("auditoria.autorizacion")

LECTURA = "lectura"
EDICION = "edicion"

# Los niveles válidos en prms_usr_sd.nvl (HT-03 CHECK constraint) y qué
# acciones de aplicación habilita cada uno: "Edición" da lectura + edición,
# "Lectura" da solo lectura, "Ninguno" (o la ausencia de fila) no da nada.
_NIVELES_QUE_PERMITEN = {
    LECTURA: {"Lectura", "Edición"},
    EDICION: {"Edición"},
}


def tiene_permiso(db: Session, id_usr: int, id_sd: int | None, modulo: str, accion: str) -> bool:
    """Consulta real a prms_usr_sd (HT-03 CA2): reemplaza la matriz en
    memoria por el permiso efectivamente otorgado en la base de datos.

    id_sd es el sede_id del JWT del usuario (HT-04). Para un usuario con
    scope "por_sede" siempre viene informado, y el chequeo se restringe a
    su propia fila usuario+sede+módulo -consistente con que verificar_sede()
    ya le impide operar sobre otras sedes de todos modos-.

    Para un usuario con scope "global" puede venir en None (HT-04: "si es
    'global', sede_id puede ir en None"). CA4 de HT-09 dejó explícito con
    criterio conservador que scope=="global" solo exime del filtro de SEDE
    (eso lo resuelve verificar_sede), NO del de módulo/nivel: un usuario
    global igual necesita una fila en prms_usr_sd que le otorgue el nivel
    pedido. Como prms_usr_sd.id_sd es NOT NULL (no hay forma de expresar en
    el esquema actual de HT-03 "permiso en todas las sedes" sin una fila por
    sede), la única interpretación posible sin tocar ese esquema es: si el
    usuario tiene el nivel pedido en AL MENOS UNA de sus filas para ese
    módulo, se le concede -sea cual sea la sede de esa fila, porque
    verificar_sede ya autoriza el acceso entre sedes para scope global-.
    Ver también el punto 4 del resumen de cierre de HT-09 sobre esta
    limitación del modelo de datos.
    """
    query = db.query(PermisoUsuarioSede).filter(
        PermisoUsuarioSede.id_usr == id_usr,
        PermisoUsuarioSede.mdl == modulo,
    )
    if id_sd is not None:
        query = query.filter(PermisoUsuarioSede.id_sd == id_sd)

    niveles_otorgados = {p.nvl for p in query.all()}
    niveles_que_habilitan = _NIVELES_QUE_PERMITEN.get(accion, set())
    return bool(niveles_otorgados & niveles_que_habilitan)


def _registrar_acceso_denegado(db: Session, usuario: dict, modulo: str, accion: str) -> None:
    """HT-11 CA5: además del logger de siempre, persiste el intento
    denegado en `lg_adtr` con el mismo esquema que HU20/HU21 -id_usr =
    quien intentó, id_sd = su sede (según su JWT, no la del recurso:
    verificar_sede ya lo bloquea antes de saber si el recurso era de otra
    sede), accn/entdd = módulo y acción pedidos-. `vlrs_antrrs`/`vlrs_nvs`
    quedan en NULL: un 403 no cambia ningún dato, no hay "antes" ni
    "después" que registrar.

    La escritura del log NUNCA debe tumbar el 403 que ya se decidió
    devolver -perder una fila de auditoría es preferible a que una falla
    de infraestructura (BD caída, lg_adtr bloqueada) le devuelva un 500 a
    un usuario que en rigor solo tenía que recibir un "no tienes permiso"-.
    Por eso el rollback y la excepción se contienen acá: quien llama seguía
    de largo hacia el HTTPException(403) pase lo que pase con esto. Se deja
    un rollback() explícito para no arrastrar la sesión rota hacia el resto
    del request si algo más la reutiliza después (no debería ocurrir, ya
    que este es el último paso antes del 403, pero es gratis y evita un
    "InvalidRequestError: session is in 'inactive' state" en cascada).
    """
    logger.warning(
        "Acceso denegado: usuario=%s sede=%s rol=%s modulo=%s accion=%s",
        usuario.get("sub"),
        usuario.get("sede_id"),
        usuario.get("rol"),
        modulo,
        accion,
    )
    try:
        sub = usuario.get("sub")
        db.add(
            LogAuditoria(
                id_usr=int(sub),
                id_sd=usuario.get("sede_id"),
                accn=f"acceso_denegado:{accion}",
                entdd=modulo,
                vlrs_antrrs=None,
                vlrs_nvs=None,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("No se pudo persistir el acceso denegado en lg_adtr (HT-11 CA5)")


def require_permiso(modulo: str, accion: str):
    """Fábrica de dependencias: exige que el usuario autenticado tenga el
    permiso indicado sobre `modulo`/`accion` según prms_usr_sd (HT-03).
    Devuelve 403, no 401 (HT-04 ya cubre token inválido/expirado)."""

    def dependencia(
        usuario: dict = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        id_usr = int(usuario["sub"])
        id_sd = usuario.get("sede_id")
        if not tiene_permiso(db, id_usr, id_sd, modulo, accion):
            _registrar_acceso_denegado(db, usuario, modulo, accion)
            raise HTTPException(
                status_code=403, detail="No tienes permiso para realizar esta acción"
            )
        return usuario

    return dependencia


def require_alguno_permiso(*modulos_acciones: tuple[str, str]):
    """Como require_permiso, pero basta con tener UNO de los permisos de la
    lista. Existe para los endpoints auxiliares que varios módulos
    comparten: GET /sedes puebla el selector de sede tanto del formulario
    de mapeos (HU06, módulo Ingesta) como del de ubicaciones (HU08, módulo
    Ubicaciones), y exigir Ingesta a quien solo administra Ubicaciones
    sería un 403 que no responde a ninguna regla de negocio.

    Se mantiene aparte de require_permiso en vez de generalizarlo: los
    endpoints de un solo módulo son la mayoría y su forma actual -un
    módulo, una acción- deja más claro qué permiso exigen.
    """

    def dependencia(
        usuario: dict = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> dict:
        id_usr = int(usuario["sub"])
        id_sd = usuario.get("sede_id")
        for modulo, accion in modulos_acciones:
            if tiene_permiso(db, id_usr, id_sd, modulo, accion):
                return usuario
        modulos = "/".join(modulo for modulo, _ in modulos_acciones)
        _registrar_acceso_denegado(db, usuario, modulos, "|".join(a for _, a in modulos_acciones))
        raise HTTPException(status_code=403, detail="No tienes permiso para realizar esta acción")

    return dependencia


def verificar_sede(
    usuario: dict, sede_id_recurso: int, db: Session, modulo: str = "", accion: str = ""
) -> None:
    """Aísla el acceso entre sedes: un usuario con scope 'por_sede' solo
    puede operar sobre recursos de su propia sede, aunque tenga permiso de
    edición sobre el módulo. Los usuarios con scope 'global' no tienen esta
    restricción de sede (pero sí siguen pasando por tiene_permiso() para el
    chequeo de módulo/nivel, ver el docstring de esa función).

    `db` (HT-11 CA5) es obligatorio y no el último parámetro con default:
    todo caller de este proyecto ya tiene una sesión a mano -es la misma
    que usó para cargar el recurso cuya sede está verificando-, así que no
    hay motivo para que un llamado nuevo pueda "olvidarse" de pasarla y
    dejar ese acceso denegado fuera del histórico de auditoría."""
    if usuario.get("scope") == "global":
        return
    if usuario.get("sede_id") != sede_id_recurso:
        _registrar_acceso_denegado(db, usuario, modulo or "(sede)", accion or "acceso_sede")
        raise HTTPException(status_code=403, detail="No tienes acceso a recursos de esta sede")
