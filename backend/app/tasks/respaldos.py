"""Respaldo semanal con bloqueo, reintentos y aviso independiente de la cola."""

import logging

from app.core.celery_app import celery_app
from app.services.correo_ses import codigo_error
from app.services.respaldos import RespaldoEnCurso, ejecutar_respaldo, entero_configurado
from app.services.vigilancia_respaldos import emitir_alerta, habilitado

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, name="app.tasks.respaldos.respaldo_semanal")
def respaldo_semanal(self):
    if not habilitado("BACKUP_ENABLED"):
        return {"estado": "Deshabilitado"}
    try:
        resultado = ejecutar_respaldo()
        logger.info("Respaldo completado: %s", resultado["clave"])
        return resultado
    except RespaldoEnCurso:
        return {"estado": "YaEnCurso"}
    except Exception as exc:
        # Nunca incluir cadenas de conexion o errores SQL crudos en correo/log.
        codigo = codigo_error(exc)
        logger.error("Fallo del respaldo: %s", codigo)
        try:
            emitir_alerta(
                "tarea-" + str(self.request.id),
                "El respaldo fallo. Codigo: "
                + codigo
                + ". Se realizaran hasta tres reintentos automaticos; revisar el resultado en el monitor.",
            )
        except Exception as aviso:
            logger.error("No se pudo enviar la alerta: %s", codigo_error(aviso))
        if self.request.retries < self.max_retries:
            raise self.retry(
                exc=RuntimeError(codigo),
                countdown=min(
                    entero_configurado("BACKUP_RETRY_BASE_SECONDS", 60) * 2**self.request.retries,
                    900,
                ),
            )
        raise RuntimeError("Respaldo fallido: " + codigo) from None
