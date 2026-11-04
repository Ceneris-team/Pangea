"""HT-11: contexto de actor y compatibilidad de eventos automaticos de HU49.

Los cambios de usuarios, membresias y permisos se capturan en PostgreSQL.
El listener conserva solamente la auditoria de tramas automaticas de ingesta.
"""

from fastapi import Depends
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LogAuditoria, MapeoFormato
from app.security.auditoria_contexto import CLAVE_CONTEXTO, aplicar_contexto, marcar_actor
from app.security.dependencies import get_current_user

_CLAVE_CONTEXTO = CLAVE_CONTEXTO
_CLAVE_TRAMAS_PENDIENTES = "auditoria_ht11_tramas_automaticas_pendientes"


def auditar_cambios(
    usuario: dict = Depends(get_current_user), db: Session = Depends(get_db)
) -> Session:
    marcar_actor(db, usuario)
    return db


def marcar_contexto_auditoria(db: Session, id_usr: int, id_sd: int | None = None) -> None:
    marcar_actor(db, {"sub": str(id_usr), "sede_id": id_sd}, origen="Proceso")


def limpiar_contexto_auditoria(db: Session) -> None:
    db.info.pop(_CLAVE_CONTEXTO, None)
    aplicar_contexto(db.connection(), {"origen": "SQL"})


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
            origen=contexto.get("origen", "Proceso"),
            ejecutor=f"proceso:{contexto['id_usr']}",
        )
    )


def _before_flush(session: Session, flush_context, instances) -> None:
    contexto = session.info.get(_CLAVE_CONTEXTO)
    if contexto is None:
        return
    aplicar_contexto(session.connection(), contexto)
    # HU49 CA5: alta automática de mp_frmt (trama nueva auto-detectada,
    # ver services/ingesta/mapeo.py). NO se registra acá (a diferencia de
    # HU20/HU21): mp_frmt.id_mp es autoincrement y todavía no existe en
    # este punto de before_flush -el INSERT real no corrió- así que
    # entdd=f"mapeo_formato:{objeto.id_mp}" quedaría con id_mp=None.
    # PermisoUbicacion no tiene este problema porque sus FKs (id_usr,
    # id_ubccn) ya vienen seteadas por quien lo crea, no son su propia PK
    # autogenerada. Se captura la lista de candidatos en session.info
    # (por-SESIÓN, no un global de módulo: dos sesiones distintas no
    # deben poder pisarse esta lista) y se registra el evento recién en
    # _after_flush, más abajo, que corre DESPUÉS del INSERT real, cuando
    # el PK ya está poblado -son las MISMAS instancias Python, así que
    # SQLAlchemy les completó el id_mp in-place-.
    for objeto in session.new:
        if isinstance(objeto, MapeoFormato) and objeto.orgn_crcn == "Automatico":
            session.info.setdefault(_CLAVE_TRAMAS_PENDIENTES, []).append((objeto, contexto))


def _after_flush(session: Session, flush_context) -> None:
    """HU49 CA5: completa el registro de auditoría de las tramas
    automáticas detectadas en _before_flush, ahora que el INSERT real ya
    corrió y mp_frmt.id_mp tiene un valor real."""
    pendientes = session.info.pop(_CLAVE_TRAMAS_PENDIENTES, None)
    if not pendientes:
        return
    for objeto, contexto in pendientes:
        _registrar_evento(
            session,
            contexto,
            "mapeo_formato",
            "crear_trama_automatica",
            objeto.id_mp,
            {},
            {
                "id_dspstv": objeto.id_dspstv,
                "tp_trm": objeto.tp_trm,
                "orgn_crcn": objeto.orgn_crcn,
            },
        )
    # Sin flush() manual acá: llamar a Session.flush() dentro de un
    # handler de after_flush revienta con "Session is already flushing"
    # -este evento corre DENTRO del flush en curso-. No hace falta:
    # SQLAlchemy vuelve a recorrer session.new antes de cerrar ese mismo
    # flush, así que el LogAuditoria recién agregado por _registrar_evento
    # se inserta igual, en la misma transacción (mismo mecanismo que ya
    # usa el bloque de HU21 más arriba, que agrega objetos nuevos desde
    # dentro de before_flush sin flush explícito).


event.listen(Session, "before_flush", _before_flush)
event.listen(Session, "after_flush", _after_flush)
