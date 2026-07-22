import datetime as dt
import logging

from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.models.archivo_ingesta import ArchivoIngesta

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
def procesar_archivo_dat(self, id_archv: int) -> dict:
    """Job encolado por cada archivo .dat recibido vía FTP/TCP (HT-05, CA1).

    El receptor FTP/TCP (aún no implementado) es quien crea la fila en
    archv_ingst con estado 'Pendiente' al detectar el archivo, y encola
    esta tarea pasando solo su id -nunca credenciales ni contenido, ver
    HT-04 / ftp_crypto.py-. Esto permite que la cola tenga jobs
    'Pendiente' visibles en la tabla incluso antes de que un worker los
    tome (base para las métricas de CA3 / HU09).

    El parseo real por marca de sensor (HU05/HU06) todavía no existe: por
    ahora esto es un stub que marca el archivo como Procesando -> Exitoso.

    Reintentos (CA2): hasta 5 intentos con backoff exponencial + jitter
    (tope 600s entre intentos) ante cualquier excepción. Al agotar los
    reintentos, Celery re-lanza la excepción original y el bloque except
    de abajo marca el archivo como 'Fallido' para reprocesamiento manual
    (HU31). Cuando el parser real exista, conviene acotar autoretry_for a
    las excepciones de conexión/parseo específicas en vez de Exception
    genérica.
    """
    db = SessionLocal()
    try:
        archivo = db.get(ArchivoIngesta, id_archv)
        if archivo is None:
            logger.error("archv_ingst id=%s no existe, se descarta el job", id_archv)
            return {"id_archv": id_archv, "estado": "no_encontrado"}

        archivo.estd = "Procesando"
        db.commit()

        logger.info(
            "Procesando archivo .dat: id_archv=%s cnxn=%s archivo=%s",
            id_archv, archivo.id_cnxn, archivo.nmbr_archv,
        )

        # TODO(HU05/HU06): descargar vía FTP/TCP (ConexionFTP + ftp_crypto)
        # y parsear el archivo según la marca del datalogger. Por ahora es
        # un stub que da por exitoso el procesamiento.

        archivo.estd = "Exitoso"
        archivo.fch_prcsd = dt.datetime.now(dt.timezone.utc)
        db.commit()
        return {"id_archv": id_archv, "estado": archivo.estd}
    except Exception as exc:
        db.rollback()
        if self.request.retries >= self.max_retries:
            archivo = db.get(ArchivoIngesta, id_archv)
            if archivo is not None:
                archivo.estd = "Fallido"
                archivo.mnsj_errr = str(exc)[:500]
                db.commit()
            logger.error(
                "archv_ingst id=%s marcado Fallido tras agotar reintentos: %s",
                id_archv, exc,
            )
        raise
    finally:
        db.close()
