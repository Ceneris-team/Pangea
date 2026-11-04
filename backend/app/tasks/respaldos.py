"""Tarea Celery del respaldo extendido semanal (HT-06, PP-129).

Wrapper fino sobre services/respaldos.py, igual que el resto de tasks/ sobre
sus services: la tarea solo se encarga de ser invocable por Celery Beat y de
loguear el resultado; toda la lógica (dump, cifrado, subida, retención) vive en
el service, que se puede testear sin Celery."""

import logging

from app.core.celery_app import celery_app
from app.services.respaldos import ejecutar_respaldo

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.respaldos.respaldo_semanal")
def respaldo_semanal() -> dict:
    """Corre vía Celery Beat una vez por semana (ver beat_schedule en
    app/core/celery_app.py). Genera el dump cifrado, lo sube a Object Storage
    y aplica la retención de 12 meses.

    No usa autoretry_for: si una corrida falla (bucket caído, credenciales
    mal), reintentar en el acto rara vez ayuda y Beat volverá a dispararlo la
    semana siguiente. El fallo queda logueado para que se note; un respaldo
    perdido no debe tumbar nada más del sistema."""
    resultado = ejecutar_respaldo()
    logger.info("HT-06: respaldo semanal completado: %s", resultado)
    return resultado
