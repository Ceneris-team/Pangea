"""
HU 17 CA3 - Bus de eventos de telemetría en vivo (Redis pub/sub).

CA3: "cuando llega telemetría nueva dentro del rango activo, el marcador
se actualiza automáticamente, sin recargar la página".

Por qué pub/sub y no polling: el productor del evento (el worker de
Celery que corre procesar_archivo_dat) y el consumidor (el proceso de
uvicorn que sostiene el WebSocket del navegador) son PROCESOS DISTINTOS,
y en Lightsail hasta contenedores distintos. Necesitan un canal fuera de
ambos, y Redis ya está en el stack como broker de Celery (DB 2) y como
storage de rate limiting (DB 1), así que no agrega infraestructura nueva.

Se usa una DB de Redis PROPIA (la 4 por defecto) y no la del broker: un
`FLUSHDB` de mantenimiento sobre los eventos del mapa no debe borrar la
cola de Celery, y viceversa. Pub/sub en Redis no persiste nada -si no hay
suscriptor conectado el mensaje se descarta-, que es exactamente lo que
queremos: un marcador que nadie está mirando no necesita actualizarse.

Publicador (sincrónico, dentro del worker de Celery) y suscriptor
(asincrónico, dentro del endpoint WebSocket de FastAPI) viven en el mismo
módulo para que el NOMBRE DEL CANAL y la FORMA DEL MENSAJE se definan una
sola vez. Si se separaran, un cambio en el formato tocaría dos archivos y
el bug solo aparecería en runtime.
"""

import datetime as dt
import json
import logging
import os

import redis
import redis.asyncio as redis_asyncio

logger = logging.getLogger(__name__)

# DB 4: ver el docstring del módulo. Las 1/2/3 ya están tomadas por
# rate limiting, broker de Celery y result backend respectivamente.
MAPA_EVENTOS_REDIS_URL = os.environ.get(
    "MAPA_EVENTOS_REDIS_URL",
    os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/2").rsplit("/", 1)[0] + "/4",
)

# Prefijo de canal. Un canal POR UBICACIÓN (no uno global) para que el
# filtro de permisos de HU 21 se aplique en la SUSCRIPCIÓN y no al repartir
# el mensaje: un Cliente Final nunca llega a recibir bytes de una ubicación
# que no le fue asignada, ni siquiera para descartarlos.
CANAL_PREFIJO = "pangea:mapa:ubicacion:"


def canal_de_ubicacion(id_ubccn: int) -> str:
    return f"{CANAL_PREFIJO}{id_ubccn}"


def construir_evento(
    id_ubccn: int,
    nombre_parametro: str,
    unidad: str,
    valor,
    fecha_hora: dt.datetime,
) -> dict:
    """Forma canónica del mensaje que viaja por el canal.

    Deliberadamente mínimo (CA3 solo pide actualizar el marcador): el
    parámetro, su valor, su unidad y la fecha/hora de la lectura. NO viaja
    el archivo .dat completo ni la fila entera de tlmtr - el frontend ya
    tiene el resto del contexto de la carga inicial (GET /mapa-cliente).

    Un valor numérico viaja como float y no como Decimal porque json.dumps
    no serializa Decimal; la precisión de Numeric(14,4) se conserva de
    sobra en un float de doble precisión para lo que muestra un marcador.
    Un valor de texto (evnt_txt, ej. "Puerta Abierta") viaja tal cual: el
    panel de CA2 lo muestra igual que uno numérico.
    """
    if valor is None:
        valor_serializable = None
    elif isinstance(valor, str):
        valor_serializable = valor
    else:
        valor_serializable = float(valor)

    return {
        "id_ubccn": id_ubccn,
        "parametro": nombre_parametro,
        "unidad": unidad,
        "valor": valor_serializable,
        "fch_hr": fecha_hora.isoformat() if fecha_hora is not None else None,
    }


def publicar_lectura(evento: dict) -> None:
    """Publica UN evento en el canal de su ubicación. Llamado desde el
    worker de Celery (contexto sincrónico), por eso usa el cliente `redis`
    normal y no el asíncrono.

    NUNCA lanza: se llama justo después de que la ingesta ya persistió y
    confirmó las lecturas (ver app/tasks/ingesta.py). Si Redis está caído,
    el dato YA ESTÁ GUARDADO en tlmtr y se verá al recargar el mapa; hacer
    fallar el job de ingesta -y con él marcar el archivo como Fallido y
    reintentarlo- por no poder notificar a un navegador sería invertir por
    completo la importancia de las dos cosas.
    """
    try:
        cliente = redis.Redis.from_url(MAPA_EVENTOS_REDIS_URL)
        try:
            cliente.publish(canal_de_ubicacion(evento["id_ubccn"]), json.dumps(evento))
        finally:
            cliente.close()
    except Exception as exc:
        logger.warning(
            "HU17: no se pudo publicar el evento de mapa para ubicacion=%s (%s). "
            "La lectura YA está persistida; solo se pierde la actualización en vivo.",
            evento.get("id_ubccn"),
            exc,
        )


def publicar_lecturas(eventos: list) -> None:
    """Publica varios eventos reutilizando UNA sola conexión a Redis.

    Un .dat trae típicamente decenas de lecturas; abrir y cerrar una
    conexión por cada una (como haría llamar a publicar_lectura en un
    bucle) es el tipo de detalle que no se nota en local con 3 filas y sí
    con un archivo real de un datalogger.
    """
    if not eventos:
        return
    try:
        cliente = redis.Redis.from_url(MAPA_EVENTOS_REDIS_URL)
        try:
            for evento in eventos:
                cliente.publish(canal_de_ubicacion(evento["id_ubccn"]), json.dumps(evento))
        finally:
            cliente.close()
    except Exception as exc:
        logger.warning(
            "HU17: no se pudieron publicar %s evento(s) de mapa (%s). "
            "Las lecturas YA están persistidas; solo se pierde la actualización en vivo.",
            len(eventos),
            exc,
        )


def cliente_asincrono() -> "redis_asyncio.Redis":
    """Cliente asíncrono para el lado suscriptor (endpoint WebSocket).

    Cada conexión WebSocket abre el suyo y lo cierra al desconectarse: un
    PubSub de Redis compartido entre conexiones obligaría a llevar a mano
    el conteo de cuántos clientes siguen interesados en cada canal para
    saber cuándo hacer UNSUBSCRIBE, y a repartir cada mensaje al
    subconjunto correcto de sockets. Con una conexión por WebSocket, Redis
    hace ese trabajo y desuscribirse es simplemente cerrar la conexión.
    El costo son N conexiones a Redis para N clientes de mapa abiertos,
    perfectamente asumible para la escala de este proyecto (ver R-01 del
    RAID sobre el umbral de Lightsail).
    """
    return redis_asyncio.Redis.from_url(MAPA_EVENTOS_REDIS_URL)
