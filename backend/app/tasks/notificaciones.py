import logging
from datetime import date

from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.models import Rol, Usuario
from app.security.mailer import enviar_correo

logger = logging.getLogger(__name__)

ROL_COMERCIAL = "Administrador Comercial"


@celery_app.task(
    name="app.tasks.notificaciones.enviar_correo_bienvenida",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def enviar_correo_bienvenida(correo: str, nombre_completo: str, password_temporal: str) -> dict:
    """HU04 CA2: correo de bienvenida con credenciales al crear un usuario.

    Stub hasta HT-14 (AWS SES, Sprint 4): por ahora solo loguea el envío en
    vez de conectarse a un proveedor real. El endpoint que la encola
    (POST /usuarios) y el resto del flujo de creación no deberían cambiar
    cuando se integre el proveedor real -solo el cuerpo de esta task.

    password_temporal viaja en texto plano únicamente hasta aquí (nunca se
    persiste así en BD, ver usr.cntrsn_hsh); no se debe loguear en un
    sistema con logs compartidos/productivos sin revisar antes.
    """
    logger.info(
        "[STUB envio correo] Para: %s | Asunto: Bienvenido a Pangea 4.0 | "
        "Nombre: %s | Password temporal: %s | Debe cambiarla en su primer login.",
        correo,
        nombre_completo,
        password_temporal,
    )
    return {"correo": correo, "estado": "simulado"}


def correos_comerciales(db) -> list[str]:
    """Correos de los Administradores Comerciales activos."""
    filas = (
        db.query(Usuario.crr)
        .join(Rol, Rol.id_rl == Usuario.id_rl)
        .filter(Rol.nmbr == ROL_COMERCIAL, Usuario.estd == "Activo")
        .order_by(Usuario.crr)
        .all()
    )
    return [correo for (correo,) in filas]


def aviso_vencidas(vencidas: list[dict]) -> tuple[str, str]:
    """Asunto y cuerpo del aviso de PP-321."""
    total = len(vencidas)
    asunto = (
        "Pangea: 1 suscripción vencida sin cobro"
        if total == 1
        else f"Pangea: {total} suscripciones vencidas sin cobro"
    )
    lineas = []
    for v in vencidas:
        fecha = date.fromisoformat(v["fecha_vencimiento"]).strftime("%d/%m/%Y")
        plan = v.get("plan") or "sin plan"
        lineas.append(f"- {v['empresa']} (RUC {v['ruc']}) · {plan} · venció el {fecha}")
    cuerpo = (
        "Estas suscripciones terminaron su vigencia y sus días de gracia sin un cobro "
        "registrado, así que pasaron a estado Vencida:\n\n"
        + "\n".join(lineas)
        + "\n\nLas empresas siguen recibiendo telemetría, pero quedan en modo consulta "
        "hasta que se renueve o se asigne una nueva suscripción desde Planes y suscripciones."
    )
    return asunto, cuerpo


@celery_app.task(
    name="app.tasks.notificaciones.notificar_suscripciones_vencidas",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def notificar_suscripciones_vencidas(vencidas: list[dict]) -> dict:
    """PP-321: avisa al Administrador Comercial de los contratos que la tarea
    diaria de PP-320 dejó en 'Vencida'.

    Va un solo correo con todos los destinatarios, para que un reintento no
    duplique el aviso a quienes ya lo recibieron.
    """
    if not vencidas:
        return {"enviados": 0}
    with SessionLocal() as db:
        destinatarios = correos_comerciales(db)
    if not destinatarios:
        logger.warning(
            "No hay Administradores Comerciales activos para avisar de %d vencimientos",
            len(vencidas),
        )
        return {"enviados": 0}
    asunto, cuerpo = aviso_vencidas(vencidas)
    enviar_correo(destinatarios, asunto, cuerpo)
    return {"enviados": len(destinatarios), "suscripciones": len(vencidas)}
