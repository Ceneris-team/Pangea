import datetime as dt
import logging

from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.ingesta.ftp_receptor import listar_archivos_dat
from app.models.archivo_ingesta import ArchivoIngesta
from app.models.ubicacion_conexion import ConexionFTP

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
    """Job encolado por cada archivo .dat recibido vía FTP (HT-05, CA1).

    sondear_conexiones_ftp (más abajo en este mismo módulo) es quien crea
    la fila en archv_ingst con estado 'Pendiente' al detectar el archivo,
    y encola esta tarea pasando solo su id -nunca credenciales ni
    contenido, ver HT-04 / ftp_crypto.py-. Esto permite que la cola tenga
    jobs 'Pendiente' visibles en la tabla incluso antes de que un worker
    los tome (base para las métricas de CA3 / HU09).

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


@celery_app.task(name="app.tasks.ingesta.sondear_conexiones_ftp")
def sondear_conexiones_ftp() -> dict:
    """HU 05 / HT-05 CA1: corre vía Celery Beat cada minuto (ver
    celery_app.py, beat_schedule) y revisa cada cnxn_ftp activa con
    prtcl='FTP'.

    Solo sondea una conexión si ya pasó su frcnc_mnts desde ultm_snd (o si
    nunca se sondeó). ultm_snd se actualiza en cada corrida -haya o no
    archivos nuevos- para que frcnc_mnts tenga efecto real aunque Beat
    corra con una cadencia fija distinta a la de cada datalogger.

    Por cada archivo .dat nuevo (nombre no visto antes para esa conexión
    en archv_ingst) crea la fila en estado 'Pendiente' y encola
    procesar_archivo_dat - así la recepción no bloquea: esta tarea nunca
    procesa el contenido del archivo, solo detecta y encola.

    Un fallo de conexión a UN datalogger (timeout, credenciales, host
    caído) se loguea y no debe frenar el sondeo del resto -por eso no se
    usa autoretry_for aquí: reintentar toda la ronda de conexiones por un
    solo datalogger caído sería peor que perderse un ciclo de ese
    datalogger y recogerlo en el siguiente sondeo-.
    """
    db = SessionLocal()
    try:
        ahora = dt.datetime.now(dt.timezone.utc)
        conexiones = (
            db.query(ConexionFTP)
            .filter(ConexionFTP.estd == "Activa", ConexionFTP.prtcl == "FTP")
            .all()
        )

        total_encolados = 0
        for cnxn in conexiones:
            if cnxn.ultm_snd is not None:
                proximo_sondeo = cnxn.ultm_snd + dt.timedelta(minutes=cnxn.frcnc_mnts)
                if ahora < proximo_sondeo:
                    continue

            try:
                nombres = listar_archivos_dat(cnxn)
            except Exception as exc:
                logger.error(
                    "No se pudo sondear cnxn_ftp id=%s (%s): %s",
                    cnxn.id_cnxn, cnxn.hst, exc,
                )
                continue

            existentes = {
                nombre for (nombre,) in db.query(ArchivoIngesta.nmbr_archv)
                .filter(ArchivoIngesta.id_cnxn == cnxn.id_cnxn)
                .filter(ArchivoIngesta.nmbr_archv.in_(nombres))
                .all()
            }

            for nombre in nombres:
                if nombre in existentes:
                    continue
                archivo = ArchivoIngesta(id_cnxn=cnxn.id_cnxn, nmbr_archv=nombre)
                db.add(archivo)
                db.flush()  # necesitamos id_archv antes de encolar
                procesar_archivo_dat.delay(id_archv=archivo.id_archv)
                total_encolados += 1

            cnxn.ultm_snd = ahora
            db.commit()

        logger.info(
            "Sondeo FTP: %s conexiones revisadas, %s archivos nuevos encolados",
            len(conexiones), total_encolados,
        )
        return {"conexiones_revisadas": len(conexiones), "encolados": total_encolados}
    finally:
        db.close()
