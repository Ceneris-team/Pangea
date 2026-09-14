"""
Tickets de un solo uso para autenticar el WebSocket de HU17 (mapa en
vivo), mitigación de R-05 del RAID del proyecto (ver docstring de
_autenticar_websocket en routers/mapa_cliente.py).

POR QUÉ EXISTE: tras migrar la sesión a cookie httpOnly, el JWT ya no
vive en localStorage/sessionStorage, así que el frontend no tiene forma
de leerlo para pasarlo como query param al WebSocket (la API WebSocket
del navegador no permite headers ni cookies propias en el handshake).
Un endpoint autenticado por cookie (POST /auth/ws-ticket) emite en su
lugar un ticket opaco de vida corta y un solo uso; el WS lo cambia por
la identidad del usuario y lo destruye de inmediato.

DB DE REDIS: 6. Las anteriores ya están tomadas -1 = rate limiting,
2 = broker de Celery, 3 = result backend, 4 = pub/sub del mapa,
5 = caché de consultas (HT-10)-, así que esta sigue siendo la primera
libre.

USO ÚNICO REAL: se implementa con GETDEL (leer y borrar en una sola
operación atómica), no con un GET seguido de un DELETE. Con dos
comandos separados, dos conexiones WebSocket que llegan casi al mismo
tiempo con el mismo ticket podrían leerlo ambas antes de que cualquiera
lo borre. GETDEL en Redis es atómico: como máximo una de las dos
conexiones puede recibir el valor.
"""

import os
import secrets

import redis

TICKET_REDIS_URL = os.environ.get(
    "WS_TICKET_REDIS_URL",
    os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/2").rsplit("/", 1)[0] + "/6",
)

PREFIJO = "pangea:ws-ticket:"

# 45s: punto medio del rango 30-60s pedido. El ticket solo tiene que
# sobrevivir el tiempo entre "el frontend lo pide" y "el navegador abre
# el WebSocket con él", que en la práctica son dos llamadas consecutivas
# en el mismo efecto de React.
TTL_SEGUNDOS = int(os.environ.get("WS_TICKET_TTL_SEGUNDOS", "45"))

_cliente_local = None
_pid_del_cliente = None


def _cliente() -> redis.Redis:
    """Cliente reutilizado por proceso, mismo criterio que
    services/cache/consultas.py: evita pagar el costo de abrir/cerrar
    conexión en el camino crítico de cada login/conexión de WebSocket."""
    global _cliente_local, _pid_del_cliente
    pid_actual = os.getpid()
    if _cliente_local is None or _pid_del_cliente != pid_actual:
        _cliente_local = redis.Redis.from_url(TICKET_REDIS_URL, decode_responses=True)
        _pid_del_cliente = pid_actual
    return _cliente_local


def emitir_ticket(payload_jwt: str) -> str:
    """Genera un ticket opaco, de un solo uso, y lo asocia al JWT ya
    validado del usuario autenticado por cookie. Se guarda el JWT
    completo (no solo el user_id) para que el WS reutilice exactamente
    la misma lógica de payload (sede_id, scope, rol) que ya usa
    decode_access_token en el resto de la API, sin duplicar claims."""
    ticket = secrets.token_urlsafe(32)
    _cliente().set(f"{PREFIJO}{ticket}", payload_jwt, ex=TTL_SEGUNDOS)
    return ticket


def canjear_ticket(ticket: str) -> str | None:
    """Devuelve el JWT asociado al ticket y lo borra atómicamente. None
    si el ticket no existe (nunca existió, ya se usó, o expiró)."""
    if not ticket:
        return None
    try:
        return _cliente().getdel(f"{PREFIJO}{ticket}")
    except redis.RedisError:
        return None
