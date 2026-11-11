"""Identidad transaccional compartida por HTTP, ORM y procesos automáticos."""

from uuid import uuid4

from fastapi import Depends
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from starlette.requests import HTTPConnection

from app.database import get_db

CLAVE_CONTEXTO = "auditoria_ht11"


def aplicar_contexto(connection, contexto):
    connection.execute(
        text(
            "SELECT set_config('pangea.actor', :actor, true), "
            "set_config('pangea.origen', :origen, true), "
            "set_config('pangea.solicitud', :solicitud, true), "
            "set_config('pangea.operacion', :operacion, true)"
        ),
        {
            "actor": str(contexto.get("id_usr") or ""),
            "origen": contexto.get("origen", "Proceso"),
            "solicitud": contexto.get("solicitud", ""),
            "operacion": contexto.get("operacion", ""),
        },
    )


def marcar_actor(db, usuario, *, origen=None):
    contexto = db.info.setdefault(CLAVE_CONTEXTO, {})
    contexto.update(id_usr=int(usuario["sub"]), id_sd=usuario.get("sede_id"))
    contexto.update(cliente_id=usuario.get("cliente_id"), proyecto_id=usuario.get("proyecto_id"))
    if origen:
        contexto["origen"] = origen
    aplicar_contexto(db.connection(), contexto)


@event.listens_for(Session, "after_begin")
def _contexto_transaccion(session, transaction, connection):
    aplicar_contexto(connection, session.info.get(CLAVE_CONTEXTO, {"origen": "SQL"}))


def preparar_peticion(request: HTTPConnection, db: Session = Depends(get_db)):
    """No exige autenticación a login/health; la identidad la valida get_current_user."""
    if request.scope["type"] != "http" or request.url.path in {"/", "/health"}:
        yield
        return
    contexto = {
        "origen": "API",
        "solicitud": str(uuid4()),
        "operacion": f"{request.scope['method']} {request.scope['route'].path}",
    }
    db.info[CLAVE_CONTEXTO] = contexto
    db.info.pop("auditoria_denegacion", None)
    request.state.auditoria_db = db
    request.state.auditoria_contexto = contexto
    aplicar_contexto(db.connection(), contexto)
    try:
        yield
    finally:
        db.info.pop(CLAVE_CONTEXTO, None)
        db.info.pop("auditoria_denegacion", None)
