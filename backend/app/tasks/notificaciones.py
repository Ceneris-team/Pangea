import logging

from app.core.celery_app import celery_app

logger = logging.getLogger(__name__)


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
        correo, nombre_completo, password_temporal,
    )
    return {"correo": correo, "estado": "simulado"}
