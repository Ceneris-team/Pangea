import logging

from app.core.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.ingesta.procesar_archivo_dat",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def procesar_archivo_dat(self, id_cnxn: int, nombre_archivo: str) -> dict:
    """Job encolado por cada archivo .dat recibido vía FTP/TCP (HT-05, CA1).

    Recibe solo la referencia a la conexión y el nombre de archivo -no las
    credenciales ni el contenido- para que el payload de la cola se mantenga
    liviano y no filtre datos sensibles (ver HT-04 / ftp_crypto.py).

    El parseo real por marca de sensor (HU05/HU06) todavía no existe: por
    ahora esto es un stub que deja el enganche de la cola listo.

    Reintentos (CA2): hasta 5 intentos con backoff exponencial + jitter
    (tope 600s entre intentos) ante cualquier excepción. Cuando el parser
    real esté implementado, conviene acotar autoretry_for a las excepciones
    de conexión/parseo específicas en vez de Exception genérica, y usar
    self.request.retries para marcar el job como "fallido" en HU31 tras
    agotar los reintentos.
    """
    logger.info(
        "Procesando archivo .dat: cnxn=%s archivo=%s", id_cnxn, nombre_archivo
    )
    return {"id_cnxn": id_cnxn, "archivo": nombre_archivo, "estado": "procesado"}
