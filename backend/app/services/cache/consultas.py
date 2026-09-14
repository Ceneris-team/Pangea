"""
HT-10 - Caché de consultas de gráficos y mapas en Redis.

Cachea la RESPUESTA YA SERIALIZADA de los tres endpoints de lectura que
alimentan las vistas pesadas del Cliente Final y del Administrador:

    GET /mediciones        (HU12/HU13/HU15 - gráficos)
    GET /mapa-cliente      (HU17 - carga inicial del mapa, NO el WebSocket)
    GET /ubicaciones/mapa  (HU22 - mapa de administración)

El WebSocket /mapa-cliente/ws queda deliberadamente fuera: ya empuja cada
lectura en vivo por Redis pub/sub (ver services/mapa/eventos.py) y no
tiene nada que cachear -un mensaje que se publica una sola vez a los
suscriptores conectados-.

DB DE REDIS
-----------
Se usa la DB 5. Las anteriores ya están tomadas y no deben compartirse:
1 = rate limiting (main.py), 2 = broker de Celery, 3 = result backend
(core/celery_app.py), 4 = pub/sub del mapa (services/mapa/eventos.py).
Una DB propia permite un FLUSHDB de la caché -operación legítima de
mantenimiento, ver invalidar_todo()- sin borrar la cola de Celery.

AISLAMIENTO MULTI-SEDE (CA4) - lo más importante de este módulo
---------------------------------------------------------------
La clave NUNCA se arma solo con los parámetros de la query. Se arma con
el AMBITO DE VISIBILIDAD EFECTIVO del usuario que pide, porque dos
usuarios distintos con la MISMA query string ven conjuntos de datos
distintos: la respuesta depende de prms_ubccn (HU21) y del sede_id del
JWT (HT-04), no solo de la URL.

Cachear por query string sería el bug clásico de este proyecto: el
Cliente Final de la sede A recibiría los datos de la sede B por haber
pedido la misma URL un segundo después. Por eso ambito_de_usuario()
incluye, además del sede_id, el conjunto ORDENADO de ubicaciones
permitidas, que es el filtro que efectivamente aplica cada endpoint.

Ese detalle no es cosmético: un usuario con scope "global" trae
sede_id=None en el JWT (ver security/permisos.py, docstring de
tiene_permiso), así que una clave basada solo en sede_id metería a TODOS
los usuarios globales -y a cualquier otro con sede_id nulo- en el mismo
cubo. El conjunto de ubicaciones desambigua ese caso.

DEGRADACION
-----------
Ninguna función de este módulo lanza hacia el llamador. Si Redis está
caído, leer devuelve None (miss) y escribir no hace nada: el endpoint
consulta Postgres y responde igual, más lento. Una caché caída no puede
tumbar una vista de lectura. Mismo criterio que publicar_lectura() en
services/mapa/eventos.py.
"""

import datetime as dt
import hashlib
import json
import logging
import os

import redis

logger = logging.getLogger(__name__)

# DB 5: ver el docstring del módulo. Se deriva de CELERY_BROKER_URL igual
# que MAPA_EVENTOS_REDIS_URL, para que apuntar el stack a otro host de
# Redis siga funcionando con una sola variable de entorno en despliegue.
CACHE_REDIS_URL = os.environ.get(
    "CACHE_REDIS_URL",
    os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/2").rsplit("/", 1)[0] + "/5",
)

# Prefijo de TODAS las claves de esta caché. Permite razonar sobre el
# keyspace (y hacer un SCAN acotado) aunque alguien decida más adelante
# compartir la DB con otra cosa.
PREFIJO = "pangea:cache:"

# TTL corto para datos que cambian seguido (HT-10 punto 2). 45s es el
# punto medio del rango 30-60s que pide la HT: absorbe la ráfaga de
# recargas de una vista que el usuario está manipulando (cambiar de
# parámetro, mover el rango) sin que un dato pueda quedar visiblemente
# viejo -la ingesta automática produce archivos cada ~15 min, ver
# frcnc_mnts, así que 45s es muy inferior a la cadencia real del dato-.
#
# El TTL es además la RED DE SEGURIDAD de la invalidación: si un evento
# de invalidación se pierde (Redis reiniciado, worker caído entre el
# commit y la llamada), la entrada caduca sola en menos de un minuto en
# vez de quedar servida indefinidamente.
TTL_CORTO = int(os.environ.get("CACHE_TTL_CORTO", "45"))

# HT-10 punto 2 pide un TTL largo (24h) para AGREGADOS HISTORICOS
# PRECALCULADOS. A la fecha de esta HT el proyecto NO tiene ninguno: no
# hay tabla de rollup ni vista materializada de telemetría (se verificó
# sobre app/models/ y alembic/versions/; además HT-08 dejó explícito que
# no se pueden usar extensiones de Postgres en Lightsail Managed
# Database, así que tampoco hay agregados continuos de TimescaleDB).
#
# No se inventa el agregado para poder aplicarle el TTL: el caso NO
# APLICA todavía. Cuando exista ese precálculo, esta es la constante que
# le corresponde y el único cambio es pasarla como ttl al guardar.
TTL_LARGO = int(os.environ.get("CACHE_TTL_LARGO", str(24 * 60 * 60)))


# Cliente reutilizado por proceso, con su pool de conexiones.
#
# POR QUE NO UNA CONEXION NUEVA POR OPERACION: se midió. Abrir y cerrar
# la conexión en cada get cuesta ~16,5 ms de media en local, contra
# ~0,35 ms reutilizando el pool: unas 47 veces más, y MUCHO más de lo que
# tarda la consulta a Postgres que la caché pretende evitar (una consulta
# de 7 días sobre el dataset de medición tarda ~1,7 ms). Con conexión por
# operación la caché era más lenta que no tener caché, que es justo lo
# contrario de esta HT. Ver app/scripts/medir_cache_ht10.py.
#
# publicar_lectura() en services/mapa/eventos.py sí abre una conexión por
# llamada, pero ahí el contexto es otro: se publica un puñado de veces
# por archivo .dat dentro de un job de Celery que ya tardó segundos en
# FTP, no en el camino crítico de cada petición HTTP.
_cliente_local = None
_pid_del_cliente = None


def _cliente():
    """Cliente de Redis del proceso actual, creado la primera vez.

    Se guarda junto al PID que lo creó y se descarta si el PID cambió.
    Eso es lo que lo hace seguro ante el fork: el worker de Celery usa el
    pool prefork y uvicorn puede levantar varios workers, y un socket
    heredado del padre lo compartirían varios hijos a la vez -con
    respuestas cruzadas entre procesos-. Al detectar el cambio de PID
    cada hijo se crea el suyo.
    """
    global _cliente_local, _pid_del_cliente
    pid = os.getpid()
    if _cliente_local is None or _pid_del_cliente != pid:
        _cliente_local = redis.Redis.from_url(
            CACHE_REDIS_URL,
            decode_responses=True,
            # Una caché caída no puede colgar una petición: si Redis no
            # responde rápido, sale por timeout y el endpoint consulta
            # Postgres como si fuera un miss (ver obtener()).
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _pid_del_cliente = pid
    return _cliente_local


def ambito_de_usuario(usuario: dict, ids_ubicaciones_permitidas) -> str:
    """Identidad de VISIBILIDAD del solicitante, para el prefijo de clave.

    Es la pieza que cumple CA4. Combina:

    - sede_id del JWT: separa explícitamente las sedes, que es el eje
      multi-sede del proyecto (sd -> ubccn -> dspstv -> tlmtr).
    - el conjunto ordenado de ubicaciones permitidas (HU21): separa a dos
      Clientes Finales de la MISMA sede con asignaciones distintas, y
      desambigua a los usuarios con sede_id=None (scope global).

    Se ordena antes de serializar porque ubicaciones_permitidas() no
    garantiza orden (sale de un SELECT sin ORDER BY): sin ordenar, el
    mismo usuario podría generar dos claves distintas para los mismos
    datos y la caché nunca acertaría.

    El conjunto se resume con un hash corto en vez de meterlo entero en
    la clave: un Administrador con 300 ubicaciones produciría una clave
    de varios KB, y Redis la guardaría entera en cada entrada.
    """
    ids = sorted(int(i) for i in ids_ubicaciones_permitidas)
    huella = hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()[:16]
    sede = usuario.get("sede_id")
    return f"sd{sede if sede is not None else 'NA'}:ub{huella}"


def _normalizar(valor):
    """Serializa un parámetro de query a algo estable y comparable.

    Las listas se ORDENAN: ?parametro_ids=3&parametro_ids=1 y
    ?parametro_ids=1&parametro_ids=3 piden exactamente los mismos datos y
    tienen que compartir entrada de caché. Las fechas se normalizan a
    ISO-8601 para que un datetime y su representación textual no generen
    dos claves distintas.
    """
    if valor is None:
        return None
    if isinstance(valor, (list, tuple, set)):
        return sorted(str(_normalizar(v)) for v in valor)
    if isinstance(valor, (dt.datetime, dt.date)):
        return valor.isoformat()
    return valor


def clave(recurso: str, ambito: str, **parametros) -> str:
    """Clave compuesta: recurso + ámbito de visibilidad + parámetros.

    Formato: pangea:cache:<recurso>:<ambito>:<hash de parámetros>

    El ámbito va ANTES del hash y con la parte de sede sin hashear para
    que la clave siga siendo legible al inspeccionar Redis a mano (KEYS
    pangea:cache:mediciones:sd7:* muestra lo cacheado de la sede 7), que
    es justo lo que uno necesita cuando sospecha de una fuga entre sedes.

    Los parámetros van hasheados porque el rango de fechas y las listas de
    ids producen claves largas y de longitud variable.
    """
    normalizados = {k: _normalizar(v) for k, v in sorted(parametros.items())}
    huella = hashlib.sha256(
        json.dumps(normalizados, separators=(",", ":"), sort_keys=True, default=str).encode()
    ).hexdigest()[:24]
    return f"{PREFIJO}{recurso}:{ambito}:{huella}"


def obtener(clave_cache: str):
    """Lee una entrada. Devuelve None si no está, si expiró o si Redis
    falla (los tres casos son un MISS desde el punto de vista del
    endpoint, que simplemente consulta Postgres)."""
    try:
        # Sin close(): el cliente es compartido por el proceso y su pool
        # gestiona las conexiones. Cerrarlo acá devolvería el coste de
        # reconectar en cada operación, que es justo lo que se evitó.
        crudo = _cliente().get(clave_cache)
    except Exception as exc:
        logger.warning("HT-10: no se pudo leer la cache (%s). Se consulta la BD.", exc)
        return None

    if crudo is None:
        return None
    try:
        return json.loads(crudo)
    except (TypeError, ValueError):
        # Entrada corrupta o de un formato de respuesta anterior: se trata
        # como miss. No se borra a mano; el TTL la retira sola.
        logger.warning("HT-10: entrada de cache ilegible en %s, se ignora.", clave_cache)
        return None


def guardar(clave_cache: str, valor, ttl: int = TTL_CORTO, indices: list | None = None) -> None:
    """Guarda una respuesta con TTL.

    `indices` son los conjuntos de invalidación a los que pertenece esta
    entrada (ver indice_de_sede / indice_de_ubicacion): normalmente las
    sedes y/o ubicaciones cuyos datos aparecen en la respuesta. Sirven
    para que una lectura nueva pueda borrar SOLO lo afectado (CA2 / punto
    3 de la HT) en vez de vaciar la caché entera.
    """
    try:
        contenido = json.dumps(valor, default=str)
    except (TypeError, ValueError) as exc:
        # Una respuesta no serializable es un bug del llamador, no un
        # fallo de infraestructura, pero tampoco justifica romper una
        # petición que ya tiene los datos listos para devolver.
        logger.warning("HT-10: respuesta no serializable, no se cachea (%s).", exc)
        return

    try:
        pipe = _cliente().pipeline()
        # set(..., ex=) y no setex(): redis-py deprecó setex desde
        # 2.6.12 y emite un DeprecationWarning en cada escritura.
        pipe.set(clave_cache, contenido, ex=ttl)
        for indice in indices or []:
            # El índice vive más que la entrada: si caducara antes,
            # quedaría una entrada viva que ningún evento de invalidación
            # sabría encontrar. El margen es holgado a propósito -un
            # índice de sobra solo cuesta unos bytes-.
            pipe.sadd(indice, clave_cache)
            pipe.expire(indice, ttl * 10)
        pipe.execute()
    except Exception as exc:
        logger.warning("HT-10: no se pudo escribir en la cache (%s). Se sigue sin cachear.", exc)


def indice_de_sede(id_sd: int) -> str:
    """Conjunto con las claves cacheadas que contienen datos de esta sede."""
    return f"{PREFIJO}indice:sede:{int(id_sd)}"


def indice_de_ubicacion(id_ubccn: int) -> str:
    """Conjunto con las claves cacheadas que contienen datos de esta ubicación."""
    return f"{PREFIJO}indice:ubicacion:{int(id_ubccn)}"


def invalidar(indices: list) -> int:
    """Borra las entradas registradas en esos índices. Devuelve cuántas.

    Es la invalidación DIRIGIDA que pide el punto 3 de la HT: una lectura
    nueva de la sede 7 no puede tirar la caché de la sede 3. El SMEMBERS
    da exactamente las claves que tocaron esa sede/ubicación, así que no
    hace falta un SCAN sobre el keyspace (que sería O(N) sobre TODA la DB
    y, con un pipeline de ingesta que corre cada minuto, un problema de
    rendimiento en sí mismo).

    No lanza: se llama DESPUES de que la lectura ya está comiteada. Si
    Redis está caído, el dato ya está en Postgres y la entrada obsoleta
    caduca sola por TTL en menos de un minuto (ver TTL_CORTO).
    """
    if not indices:
        return 0
    try:
        cliente = _cliente()
        claves = set()
        for indice in indices:
            claves.update(cliente.smembers(indice))
        pipe = cliente.pipeline()
        if claves:
            pipe.delete(*claves)
        # El índice se borra junto con sus claves: sus miembros ya no
        # existen y dejarlo solo acumularía basura hasta su expire.
        pipe.delete(*indices)
        pipe.execute()
        return len(claves)
    except Exception as exc:
        logger.warning(
            "HT-10: no se pudo invalidar la cache (%s). Las entradas afectadas caducan "
            "solas por TTL en <=%ss.",
            exc,
            TTL_CORTO,
        )
        return 0


def invalidar_sede(id_sd: int | None = None, id_ubccn: int | None = None) -> int:
    """Atajo para el caso normal: llegó una lectura nueva para esta sede
    y/o esta ubicación. Ver services/cache/invalidacion.py, que es el
    punto por el que entran los dos caminos de escritura."""
    indices = []
    if id_sd is not None:
        indices.append(indice_de_sede(id_sd))
    if id_ubccn is not None:
        indices.append(indice_de_ubicacion(id_ubccn))
    return invalidar(indices)


def invalidar_todo() -> int:
    """Vacía la caché entera. Solo para mantenimiento y para los tests.

    NO se usa en el camino de escritura de telemetría: el punto 3 de la HT
    pide explícitamente invalidación filtrada por sede/dispositivo.
    """
    try:
        cliente = _cliente()
        claves = list(cliente.scan_iter(match=f"{PREFIJO}*", count=500))
        if claves:
            cliente.delete(*claves)
        return len(claves)
    except Exception as exc:
        logger.warning("HT-10: no se pudo vaciar la cache (%s).", exc)
        return 0
