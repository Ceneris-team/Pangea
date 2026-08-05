"""
HT-09: Middleware de autorización en FastAPI.

Valida, para cada endpoint del PMV, que el usuario autenticado (HT-04) tenga
permiso sobre el módulo y la acción solicitados según la matriz de HT-03. Si
el permiso es insuficiente devuelve 403 (distinto del 401 que ya cubre HT-04
para tokens inválidos o expirados), y registra el intento denegado en un log
preliminar que sirve de base para la auditoría formal de HT-11.

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
        usuario: dict = Depends(require_permiso("Dispositivos", LECTURA)),
    ):
        verificar_sede(usuario, sede_id, modulo="Dispositivos", accion=LECTURA)
        ...

NOTA: la matriz de abajo es una primera versión basada en los 4 roles
sembrados en seed_usuarios_prueba.py (HT-04). Cuando se implementen
HU08/HU10-HU13 hay que revisarla contra el diseño final de HT-03 y ajustar
módulos/roles/acciones si hace falta.
"""
import logging

from fastapi import Depends, HTTPException

from .dependencies import get_current_user

logger = logging.getLogger("auditoria.autorizacion")

LECTURA = "lectura"
EDICION = "edicion"

# rol -> módulo -> acciones permitidas
MATRIZ_PERMISOS: dict[str, dict[str, set[str]]] = {
    "Administrador": {
        "Ubicaciones": {LECTURA, EDICION},
        "Dispositivos": {LECTURA, EDICION},
        "Mediciones": {LECTURA, EDICION},
    },
    "Técnico CENERIS": {
        "Ubicaciones": {LECTURA, EDICION},
        "Dispositivos": {LECTURA, EDICION},
        "Mediciones": {LECTURA, EDICION},
    },
    "Cliente Final": {
        "Ubicaciones": {LECTURA},
        "Dispositivos": {LECTURA},
        "Mediciones": {LECTURA},
    },
    "Administrador Comercial": {
        "Ubicaciones": {LECTURA},
        "Dispositivos": {LECTURA},
        "Mediciones": {LECTURA},
    },
}


def tiene_permiso(rol: str, modulo: str, accion: str) -> bool:
    return accion in MATRIZ_PERMISOS.get(rol, {}).get(modulo, set())


def _registrar_acceso_denegado(usuario: dict, modulo: str, accion: str) -> None:
    logger.warning(
        "Acceso denegado: usuario=%s sede=%s rol=%s modulo=%s accion=%s",
        usuario.get("sub"), usuario.get("sede_id"), usuario.get("rol"), modulo, accion,
    )


def require_permiso(modulo: str, accion: str):
    """Fábrica de dependencias: exige que el usuario autenticado tenga el
    permiso indicado sobre `modulo`/`accion` según la matriz de HT-03.
    Devuelve 403, no 401 (HT-04 ya cubre token inválido/expirado)."""

    def dependencia(usuario: dict = Depends(get_current_user)) -> dict:
        if not tiene_permiso(usuario.get("rol"), modulo, accion):
            _registrar_acceso_denegado(usuario, modulo, accion)
            raise HTTPException(status_code=403, detail="No tienes permiso para realizar esta acción")
        return usuario

    return dependencia


def verificar_sede(usuario: dict, sede_id_recurso: int, modulo: str = "", accion: str = "") -> None:
    """Aísla el acceso entre sedes: un usuario con scope 'por_sede' solo
    puede operar sobre recursos de su propia sede, aunque tenga permiso de
    edición sobre el módulo. Los usuarios con scope 'global' no tienen esta
    restricción."""
    if usuario.get("scope") == "global":
        return
    if usuario.get("sede_id") != sede_id_recurso:
        _registrar_acceso_denegado(usuario, modulo or "(sede)", accion or "acceso_sede")
        raise HTTPException(status_code=403, detail="No tienes acceso a recursos de esta sede")
