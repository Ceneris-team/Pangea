"""
HU 17 - Ver datos en mapa (rol Cliente Final)

CA1: vista "MAPA" con marcadores en las coordenadas de las ubicaciones
     ASIGNADAS al Cliente Final (filtro de HU 21, prms_ubccn).
CA2: clic en un marcador -> panel con nombre de la estación, último valor
     de cada parámetro y fecha/hora de la última lectura.
CA3: cuando llega telemetría nueva, el marcador se actualiza
     automáticamente, sin recargar la página (WebSocket + Redis pub/sub).
CA4: botón "Ver gráfico" -> vista de gráficos (HU 15) con la ubicación
     preseleccionada. Puro frontend (navegación).

Esta vista es DISTINTA de HU 22 (GET /ubicaciones/mapa, vista de
Administrador): aquella muestra TODAS las ubicaciones con sus polígonos y
el conteo de dispositivos para gestión; esta muestra solo lo asignado al
Cliente Final, sin polígonos, con la telemetría en vivo. Por eso es un
router propio y no un parámetro más del endpoint de HU 22 -que queda
intacto-.

Módulo de permiso: "Tableros", igual que /mediciones (HU 13). "Mediciones"
no es un módulo válido en el CHECK de prms_usr_sd; el Cliente Final ya
tiene Lectura sobre "Tableros" en el seed.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.security.jwt_auth import TokenExpirado, TokenInvalido, decode_access_token
from app.security.permisos import LECTURA, require_permiso, tiene_permiso
from app.security.ubicaciones_permitidas import ubicaciones_permitidas
from app.services.mapa.eventos import canal_de_ubicacion, cliente_asincrono
from app.services.mapa.semaforo import evaluar_semaforo
from app.services.mapa.ultimos_valores import (
    ubicaciones_con_coordenadas,
    ultimos_valores_por_ubicacion,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mapa-cliente", tags=["Mapa Cliente Final"])

# CA3 / mitigación del riesgo de Lightsail: cada cuántos segundos el
# servidor manda un ping por el WebSocket si no hubo eventos.
#
# El balanceador HTTP de Lightsail Container Service no expone un timeout
# de conexión configurable, y no está documentado cuánto tolera una
# conexión inactiva (verificado en la Fase 0 de HU 17: no hay forma de
# confirmarlo desde el repo). 25 segundos es deliberadamente conservador:
# queda por debajo del timeout de 30s más habitual en proxies HTTP, así
# que la conexión nunca llega a verse "inactiva" desde afuera. El cliente
# además reconecta solo con backoff, así que si aun así se corta, se
# recupera sin intervención (ver useMapaEnVivo.ts).
SEGUNDOS_ENTRE_PINGS = 25


@router.get("")
def mapa_del_cliente(
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", LECTURA)),
):
    """CA1 + CA2: carga inicial del mapa.

    Devuelve las ubicaciones que el usuario puede ver, con sus
    coordenadas, el último valor de cada parámetro y el color del semáforo
    ya calculado en el servidor.

    El color se calcula acá y no en el frontend a propósito: cuando HU 28
    exista, los umbrales serán configurables por usuario y vivirán en la
    BD; que el navegador nunca haya sabido calcularlos significa que ese
    cambio no toca el frontend. Ver app/services/mapa/semaforo.py.

    Es un endpoint REST normal, separado del WebSocket, porque el mapa
    tiene que poder pintarse ANTES de que llegue ningún evento en vivo
    (y aunque el WebSocket falle por completo).
    """
    ids_permitidas = ubicaciones_permitidas(db, usuario)
    ubicaciones = ubicaciones_con_coordenadas(db, ids_permitidas)
    ultimos = ultimos_valores_por_ubicacion(db, ids_permitidas)

    items = []
    for ubicacion in ubicaciones:
        por_parametro = ultimos.get(ubicacion.id_ubccn, {})

        parametros = [
            {
                "parametro": dato["parametro"],
                "unidad": dato["unidad"],
                # float() y no Decimal: Decimal no es serializable a JSON.
                # Un evento de texto (evnt_txt) llega como str y se deja tal cual.
                "valor": float(dato["valor"])
                if not isinstance(dato["valor"], str)
                else dato["valor"],
                "fch_hr": dato["fch_hr"].isoformat() if dato["fch_hr"] else None,
            }
            for dato in sorted(por_parametro.values(), key=lambda d: d["parametro"])
        ]

        # CA2: "la fecha/hora de la última lectura" de la estación, que es
        # la más reciente entre todos sus parámetros.
        fechas = [dato["fch_hr"] for dato in por_parametro.values() if dato["fch_hr"]]
        ultima_lectura = max(fechas).isoformat() if fechas else None

        items.append(
            {
                "id_ubccn": ubicacion.id_ubccn,
                "nmbr": ubicacion.nmbr,
                "dscrpcn": ubicacion.dscrpcn,
                "lttd": float(ubicacion.lttd),
                "lngtd": float(ubicacion.lngtd),
                "estd": ubicacion.estd,
                "semaforo": evaluar_semaforo(
                    {nombre: dato["valor"] for nombre, dato in por_parametro.items()}
                ),
                "ultima_lectura": ultima_lectura,
                "parametros": parametros,
            }
        )

    return {"items": items}


def _autenticar_websocket(token: str | None) -> dict | None:
    """Valida el JWT que llega por query param y devuelve su payload.

    POR QUÉ QUERY PARAM Y NO HEADER: la API WebSocket del navegador
    (`new WebSocket(url)`) no permite agregar headers propios, así que el
    "Authorization: Bearer ..." que usa el resto de la API (ver
    security/dependencies.get_current_user) no es una opción acá. Pasar el
    token por query string es el patrón habitual para autenticar
    WebSockets desde un navegador.

    #########################################################################
    ##  DEUDA DE SEGURIDAD - RELACIONADA CON R-05 DEL RAID_LOG_PANGEA.md   ##
    ##                                                                     ##
    ##  Un token en la URL es más expuesto que uno en un header: queda en  ##
    ##  los logs de acceso del servidor y del balanceador, y en el         ##
    ##  historial de cualquier proxy intermedio. Sobre TLS no viaja en     ##
    ##  claro por la red, pero SÍ queda escrito en disco del lado del      ##
    ##  servidor.                                                          ##
    ##                                                                     ##
    ##  Esto NO está resuelto, está ASUMIDO conscientemente para HU 17.    ##
    ##  Mitigación recomendada cuando se retome R-05: emitir un ticket de  ##
    ##  un solo uso y vida corta (30-60s) por HTTP autenticado, y que el   ##
    ##  WebSocket presente ESE ticket en la URL en vez del JWT de sesión   ##
    ##  de 8 horas (ver EXPIRATION_MINUTES en security/jwt_auth.py).       ##
    ##                                                                     ##
    ##  Anotado para revisión de seguridad, no resuelto silenciosamente.   ##
    #########################################################################
    """
    if not token:
        return None
    try:
        return decode_access_token(token)
    except (TokenExpirado, TokenInvalido):
        return None


@router.websocket("/ws")
async def websocket_telemetria(websocket: WebSocket, token: str | None = None):
    """CA3: canal en vivo. El frontend lo abre al entrar a la vista de mapa.

    Al conectar, el backend resuelve QUÉ ubicaciones puede ver este
    usuario (mismo filtro de HU 21 que usa la carga inicial) y se suscribe
    SOLO a los canales Redis de esas ubicaciones. El filtro de permisos
    queda así en la suscripción: un Cliente Final nunca recibe bytes de
    una ubicación ajena, ni siquiera para descartarlos.

    Códigos de cierre (RFC 6455): 1008 = policy violation, para token
    ausente/inválido y para falta de permiso sobre el módulo.
    """
    usuario = _autenticar_websocket(token)
    if usuario is None:
        # accept() + close() y no un simple close(): sin aceptar primero,
        # el navegador solo ve un error de handshake genérico y no puede
        # distinguir "token vencido" de "servidor caído" -y por tanto no
        # sabe si tiene sentido reintentar o hay que volver al login-.
        await websocket.accept()
        await websocket.close(code=1008, reason="Token ausente o invalido")
        return

    # El JWT se valida sin tocar la BD, pero el permiso de módulo y las
    # ubicaciones asignadas sí requieren consulta. Sesión propia y de vida
    # corta: get_db() es una dependencia HTTP y no aplica acá, y mantener
    # una sesión abierta durante toda la vida del WebSocket -que puede
    # durar horas- retendría una conexión del pool de Postgres sin usarla.
    db = SessionLocal()
    try:
        if not tiene_permiso(db, int(usuario["sub"]), usuario.get("sede_id"), "Tableros", LECTURA):
            await websocket.accept()
            await websocket.close(code=1008, reason="Sin permiso sobre Tableros")
            return
        ids_permitidas = ubicaciones_permitidas(db, usuario)
    finally:
        db.close()

    await websocket.accept()

    if not ids_permitidas:
        # Sin ubicaciones asignadas no hay nada a qué suscribirse. Se deja
        # la conexión abierta igual (con pings) en vez de cerrarla: cerrar
        # dispararía el backoff de reconexión del cliente en un bucle
        # infinito por una situación que es normal, no un error.
        logger.info("HU17 WS: usuario=%s sin ubicaciones asignadas", usuario.get("sub"))

    redis_cliente = cliente_asincrono()
    pubsub = redis_cliente.pubsub()
    try:
        if ids_permitidas:
            await pubsub.subscribe(*[canal_de_ubicacion(i) for i in ids_permitidas])

        logger.info(
            "HU17 WS conectado: usuario=%s ubicaciones=%s",
            usuario.get("sub"),
            len(ids_permitidas),
        )

        while True:
            if ids_permitidas:
                mensaje = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=SEGUNDOS_ENTRE_PINGS,
                )
            else:
                # Sin ubicaciones asignadas no hay ningún canal suscrito, y
                # llamar a get_message() sobre un PubSub sin canales lanza
                # RuntimeError ("pubsub connection not set: did you forget
                # to call subscribe()?"), que cerraba la conexión con un
                # 1006 en cuanto el usuario no tenía nada asignado -el
                # caso real que apareció en producción, donde el Cliente
                # Final todavía no tiene filas en prms_ubccn-.
                #
                # Se espera el mismo intervalo y se cae al ping de abajo:
                # la conexión queda viva y lista para cuando el
                # administrador le asigne una ubicación (el cliente
                # reconecta al recargar y ahí sí se suscribe).
                await asyncio.sleep(SEGUNDOS_ENTRE_PINGS)
                mensaje = None

            if mensaje is None:
                # Sin eventos en la ventana: se manda un ping de
                # keep-alive. Es lo que evita que el balanceador vea la
                # conexión como inactiva (ver SEGUNDOS_ENTRE_PINGS), y de
                # paso detecta un socket ya muerto -si el cliente se fue
                # sin cerrar limpiamente, este send falla y salimos del
                # bucle en vez de quedarnos colgados para siempre-.
                await websocket.send_text(json.dumps({"tipo": "ping"}))
                continue

            datos = mensaje.get("data")
            if isinstance(datos, bytes):
                datos = datos.decode("utf-8")

            try:
                evento = json.loads(datos)
            except (TypeError, ValueError):
                logger.warning("HU17 WS: mensaje no-JSON en el canal, se descarta: %r", datos)
                continue

            await websocket.send_text(json.dumps({"tipo": "lectura", "evento": evento}))

    except WebSocketDisconnect:
        logger.info("HU17 WS desconectado: usuario=%s", usuario.get("sub"))
    except asyncio.CancelledError:
        # Apagado del servidor: no es un error, no se loguea como tal.
        raise
    except Exception as exc:
        logger.warning("HU17 WS cerrado por error: usuario=%s (%s)", usuario.get("sub"), exc)
    finally:
        # close() del pubsub y del cliente: sin esto, cada reconexión del
        # navegador dejaría una conexión colgada contra Redis.
        try:
            await pubsub.aclose()
        except Exception:
            pass
        try:
            await redis_cliente.aclose()
        except Exception:
            pass
