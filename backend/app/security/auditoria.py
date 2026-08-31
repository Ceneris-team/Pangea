"""
HT-11 CA1: captura automática de auditoría para HU20 (editar usuario) y
HU21 (conceder permisos), sin que cada endpoint escriba el log a mano.

POR QUÉ NO ES UN MIDDLEWARE HTTP LITERAL (el documento de la HT dice
"middleware en FastAPI", y el punto 3 de la tarea pide documentar esto):
un middleware HTTP puro (`app.middleware("http")`) solo ve el `Request` de
entrada y la `Response` de salida. Para cuando puede inspeccionar la
respuesta, el `db.commit()` del endpoint YA CORRIÓ -así es como HU20/HU21
devuelven sus 200-, así que un middleware HTTP jamás podría reconstruir
`vlrs_antrrs` (CA1 lo exige): el estado "antes" ya no existe en ningún
lado accesible desde ahí, ni en la sesión (cerrada) ni en el objeto ORM
(ya mutado a los valores nuevos).

Lo que sí ve el estado "antes" es SQLAlchemy mismo, en el momento del
flush: `InstanceState.attrs.<columna>.history` guarda el valor original de
cada atributo modificado hasta que el flush lo confirma. Por eso el
mecanismo real es un LISTENER DE EVENTOS DE SQLALCHEMY
(`Session.before_flush`, registrado una sola vez a nivel de clase con
`event.listen`, igual que ya usa este proyecto en HT-10/services/cache), no
un middleware de FastAPI: se dispara automáticamente en cualquier
`db.commit()` que tenga cambios pendientes -sin que HU20/HU21 llamen nada
a mano-, y sí puede leer el valor previo porque corre ANTES de que el
flush lo sobrescriba.

Falta una pieza: el listener ve la sesión y los objetos modificados, pero
no sabe QUIÉN es el usuario ejecutor ni qué endpoint HTTP disparó el
cambio -eso vive en el JWT, ajeno al ORM-. Se le pasa con una dependencia
de FastAPI (`auditar_cambios`, usada como `Depends` en HU20/HU21) que
adjunta ese contexto a `db.info` -un dict libre por-sesión que SQLAlchemy
reserva justo para esto- ANTES de que el endpoint toque el modelo. El
listener solo actúa si encuentra esa marca: así un UPDATE de `Usuario` que
NO pasó por HU20 -el contador de intentos fallidos en /auth/login, o el
cambio de contraseña de /auth/cambiar-contrasena, ambos hacen su propio
commit sobre el mismo modelo- no genera una fila de auditoría fantasma.

Resultado: "dependencia reutilizable" + "event listener de SQLAlchemy",
tal como habilita el punto 3 de la tarea como alternativa al middleware
HTTP literal.
"""

from typing import Any

from fastapi import Depends
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LogAuditoria, PermisoUbicacion, Usuario
from app.security.dependencies import get_current_user

# Nunca debe aparecer un hash de contraseña en un registro de auditoría:
# lg_adtr no es secreta de la misma forma que usr.cntrsn_hsh -la ve
# cualquier Administrador con acceso a GET /auditoria (CA2)-, así que
# aunque el hash no es la contraseña en claro, seguiría siendo material
# sensible (permite ataques offline si se filtra) que no aporta nada al
# propósito de la auditoría, que es rastrear QUÉ cambió, no exponer
# credenciales. Se excluye por nombre de columna, no por modelo entero,
# para que sirva igual si mañana se audita otro modelo con una columna
# sensible distinta.
COLUMNAS_SENSIBLES_EXCLUIDAS = {"cntrsn_hsh"}

# Clave fija en Session.info: SQLAlchemy no tipa ese dict, así que se
# centraliza el nombre acá para que el listener y la dependencia usen
# siempre la misma clave sin repetir el string mágico en dos archivos.
_CLAVE_CONTEXTO = "auditoria_ht11"


def auditar_cambios(
    usuario: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Session:
    """Dependencia reutilizable (HT-11 punto 3): se agrega a un endpoint
    con `Depends(auditar_cambios)` -además de, no en lugar de,
    `require_permiso`, que sigue siendo quien controla el 403- y arma en
    `db.info` el contexto que el listener de abajo necesita para saber
    QUIÉN ejecutó el cambio y de qué sede, antes de que el endpoint haga
    ningún `db.add`/`setattr` sobre sus modelos.

    Devuelve la misma sesión (no un valor nuevo) para que declararla como
    `Depends(auditar_cambios)` en vez de `Depends(get_db)` no obligue a
    cambiar el resto de la firma del endpoint.
    """
    db.info[_CLAVE_CONTEXTO] = {
        "id_usr": int(usuario["sub"]),
        "id_sd": usuario.get("sede_id"),
    }
    return db


def _limpiar_valor(valor: Any) -> Any:
    """JSONB no serializa objetos Python arbitrarios (Decimal, datetime,
    etc. sin un encoder). Los campos de Usuario/PermisoUbicacion que se
    auditan son todos tipos simples (str, bool, int, None), pero se
    normaliza igual por si mañana se extiende el listener a un modelo con
    columnas de otro tipo."""
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    return str(valor)


def _diff_usuario(objeto: Usuario, inspeccion) -> tuple[dict, dict]:
    """HU20: arma los diccionarios antes/después de un Usuario modificado,
    a partir del `history` de SQLAlchemy de cada columna -que solo existe
    en este momento, entre el `setattr` del endpoint y el flush real-.
    Excluye cntrsn_hsh (nunca auditable) y las columnas que no cambiaron
    -solo interesan los campos que HU20 realmente tocó-.
    """
    antes: dict = {}
    despues: dict = {}
    for atributo in inspeccion.mapper.column_attrs:
        nombre = atributo.key
        if nombre in COLUMNAS_SENSIBLES_EXCLUIDAS:
            continue
        historial = inspeccion.attrs[nombre].history
        if not historial.has_changes():
            continue
        valor_anterior = historial.deleted[0] if historial.deleted else None
        valor_nuevo = historial.added[0] if historial.added else getattr(objeto, nombre)
        antes[nombre] = _limpiar_valor(valor_anterior)
        despues[nombre] = _limpiar_valor(valor_nuevo)
    return antes, despues


def _registrar_evento(
    session: Session, contexto: dict, entidad: str, accion: str, id_afectado: int, antes, despues
) -> None:
    session.add(
        LogAuditoria(
            id_usr=contexto["id_usr"],
            id_sd=contexto["id_sd"],
            accn=accion,
            entdd=f"{entidad}:{id_afectado}",
            vlrs_antrrs=antes,
            vlrs_nvs=despues,
        )
    )


def _before_flush(session: Session, flush_context, instances) -> None:
    """HT-11 CA1: se registra una sola vez a nivel de `Session` (no por
    request) con `event.listen`, así que corre en TODO flush de TODA
    sesión del proceso -es barato comprobar la marca de `db.info` y salir
    si no está, que es el caso normal para el 99% de los requests que no
    pasan por HU20/HU21-.
    """
    contexto = session.info.get(_CLAVE_CONTEXTO)
    if contexto is None:
        return

    # HU20: ediciones de Usuario. `session.dirty` son objetos YA
    # persistidos que tienen cambios pendientes -no altas ni bajas-, que es
    # exactamente lo que hace `actualizar_usuario` (UPDATE, nunca INSERT).
    for objeto in list(session.dirty):
        if not isinstance(objeto, Usuario):
            continue
        inspeccion = inspect(objeto)
        # Objetos "dirty" que en realidad no tienen ninguna columna
        # modificada (p. ej. solo se les hizo refresh) no generan fila.
        if not inspeccion.modified:
            continue
        antes, despues = _diff_usuario(objeto, inspeccion)
        if not antes and not despues:
            continue
        _registrar_evento(
            session, contexto, "usuario", "editar_usuario", objeto.id_usr, antes, despues
        )

    # HU21: PermisoUbicacion no se actualiza fila por fila, se reemplaza el
    # conjunto completo (altas + bajas, ver actualizar_permisos_ubicaciones
    # en routers/usuarios.py). Agruparlas por usuario afectado -en vez de
    # una fila de auditoría por cada PermisoUbicacion tocada- deja un solo
    # registro por PUT, con el conjunto antes/después completo, que es lo
    # que de verdad se quiere leer en el panel de auditoría (CA1/CA2): no
    # "se borró la fila 7", sino "este usuario tenía [A, B] y pasó a
    # tener [B, C]".
    ids_usr_afectados: set[int] = set()
    altas: dict[int, set[int]] = {}
    bajas: dict[int, set[int]] = {}

    for objeto in session.new:
        if isinstance(objeto, PermisoUbicacion):
            ids_usr_afectados.add(objeto.id_usr)
            altas.setdefault(objeto.id_usr, set()).add(objeto.id_ubccn)

    for objeto in session.deleted:
        if isinstance(objeto, PermisoUbicacion):
            ids_usr_afectados.add(objeto.id_usr)
            bajas.setdefault(objeto.id_usr, set()).add(objeto.id_ubccn)

    for id_usr_afectado in ids_usr_afectados:
        antes_ids = bajas.get(id_usr_afectado, set())
        despues_ids = altas.get(id_usr_afectado, set())
        _registrar_evento(
            session,
            contexto,
            "permisos_ubicacion",
            "actualizar_permisos",
            id_usr_afectado,
            {"ubicaciones_quitadas": sorted(antes_ids)} if antes_ids else {},
            {"ubicaciones_agregadas": sorted(despues_ids)} if despues_ids else {},
        )


# Se registra UNA sola vez, a nivel de módulo, sobre la clase Session en
# general -no sobre una instancia- para que cualquier sesión que se abra
# con `SessionLocal()` (incluida la que entrega `get_db()` en cada
# request) quede cubierta sin volver a registrar el listener en cada
# request. `insert=False` (default): corre después de cualquier otro
# listener de before_flush que ya exista, aunque hoy no hay ninguno.
event.listen(Session, "before_flush", _before_flush)
