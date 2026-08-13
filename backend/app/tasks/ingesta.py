import datetime as dt
import ftplib
import logging

from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.ingesta.ftp_receptor import descargar_archivo_dat, listar_archivos_dat
from app.models.archivo_ingesta import ArchivoIngesta
from app.models.ubicacion_conexion import ConexionFTP
from app.services.ingesta.estandarizador import estandarizar_filas
from app.services.ingesta.mapeo import (
    MapeoNoEncontradoError,
    construir_mapeo,
    resolver_formato,
)
from app.services.ingesta.parser import parsear_dat
from app.services.ingesta.persistencia import DispositivoNoResueltoError, guardar_lecturas, resolver_dispositivo
from app.services.ingesta.validador import validar_lecturas
from app.services.particiones import ParticionInexistenteError

logger = logging.getLogger(__name__)

# Errores transitorios: vale la pena reintentar (conexión, timeout, I/O).
# Un archivo mal formado o datos inválidos no se arreglan reintentando -
# ese tipo de error se distingue con ErrorDatosNoRecuperable más abajo.
#
# OJO: ftplib.all_errors ya es una TUPLA (Error, OSError, EOFError,
# SSLError), así que se usa tal cual y NO se anida dentro de otra tupla.
# Anidarla -(ftplib.all_errors, ...)- hace que Celery falle con
# "TypeError: catching classes that do not inherit from BaseException" al
# intentar usarla en autoretry_for, y el archivo queda colgado en
# 'Procesando' para siempre en vez de reintentarse. TimeoutError y
# OSError ya están cubiertos por all_errors (TimeoutError hereda de
# OSError).
ERRORES_TRANSITORIOS = tuple(ftplib.all_errors)


class ErrorDatosNoRecuperable(Exception):
    """El archivo se descargó y procesó, pero sus datos/configuración
    impiden completar el pipeline (ej. dispositivo no resoluble). No se
    reintenta: reintentar no cambia el resultado."""


@celery_app.task(
    name="app.tasks.ingesta.procesar_archivo_dat",
    bind=True,
    autoretry_for=ERRORES_TRANSITORIOS,
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

    Pipeline PP-96..100 (HU06): resuelve el formato -> descarga -> parsea
    -> estandariza -> valida -> persiste en tlmtr. El formato y el mapeo
    columna->parámetro salen de mp_frmt/mp_clmn/prmtr según el DISPOSITIVO
    (DEC-09) y el tipo de trama (prefijo H_/E_ del nombre del archivo);
    ver app.services.ingesta.mapeo.

    Reintentos (CA2): hasta 5 intentos con backoff exponencial + jitter
    (tope 600s entre intentos), pero solo ante errores transitorios
    (conexión FTP, timeout, I/O) - ver ERRORES_TRANSITORIOS. Un error de
    datos (ErrorDatosNoRecuperable, ej. dispositivo no resoluble) marca el
    archivo como 'Fallido' de inmediato sin reintentar, porque reintentar
    no lo arregla; queda para reprocesamiento manual (HU31) una vez
    corregida la causa (ej. configuración de dispositivo).
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

        cnxn = db.get(ConexionFTP, archivo.id_cnxn)
        if cnxn is None:
            raise ErrorDatosNoRecuperable(f"cnxn_ftp id={archivo.id_cnxn} no existe")

        try:
            dispositivo = resolver_dispositivo(db, archivo.id_cnxn)
        except DispositivoNoResueltoError as exc:
            raise ErrorDatosNoRecuperable(str(exc)) from exc

<<<<<<< HEAD
        # El formato aplicable sale de mp_frmt según el dispositivo (ya
        # resuelto arriba) y el tipo de trama, que se deduce del prefijo
        # del nombre del archivo (H_ = datos periódicos, E_ = eventos). Se
        # resuelve ANTES de descargar: si no hay mapeo cargado, no tiene
        # sentido bajar el archivo.
        try:
            formato = resolver_formato(
                db, dispositivo.id_dspstv, archivo.nmbr_archv,
            )
=======
        # DEC-09 (PP-96): el formato aplicable sale de mp_frmt según el
        # DISPOSITIVO ya resuelto y el tipo de trama, que se deduce del
        # prefijo del nombre del archivo (H_ = datos periódicos,
        # E_ = estados/eventos). Antes se resolvía por sede+marca, lo que
        # hacía que dos dataloggers de la misma marca en la misma sede
        # compartieran mapeo. Se resuelve ANTES de descargar: si no hay
        # mapeo cargado, no tiene sentido bajar el archivo.
        try:
            formato = resolver_formato(db, dispositivo.id_dspstv, archivo.nmbr_archv)
>>>>>>> 9cc2710c1fbe0adfb3cde23c8f9f64de00d99853
        except MapeoNoEncontradoError as exc:
            raise ErrorDatosNoRecuperable(str(exc)) from exc

        contenido = descargar_archivo_dat(cnxn, archivo.nmbr_archv)
        resultado_parseo = parsear_dat(contenido, formato.config)

        # mp_clmn referencia las columnas por índice, así que el mapeo se
        # arma con el header ya leído.
        mapeo = construir_mapeo(db, formato.id_mp, resultado_parseo.columnas)
        if not mapeo:
            raise ErrorDatosNoRecuperable(
                f"El formato mp_frmt id={formato.id_mp} (trama '{formato.tipo_trama}') "
                f"no tiene ninguna columna mapeada que exista en el header de "
                f"'{archivo.nmbr_archv}'; no se puede interpretar el archivo."
            )

        lecturas_estandar = estandarizar_filas(
            resultado_parseo, id_cnxn=archivo.id_cnxn, mapeo=mapeo,
        )

        resultado_validacion = validar_lecturas(lecturas_estandar)

        try:
            resultado_persistencia = guardar_lecturas(
                db, resultado_validacion.validas, dispositivo, id_archv,
            )
        except ParticionInexistenteError as exc:
            # HT-08 CA4: falta la partición de tlmtr para esas fechas.
            # Reintentar no la crea (eso lo hace el job de Beat), así que
            # se trata como error de datos: Fallido con causa clara y
            # reprocesable por HU31 una vez exista la partición.
            raise ErrorDatosNoRecuperable(str(exc)) from exc

        archivo.estd = "Exitoso"
        archivo.fch_prcsd = dt.datetime.now(dt.timezone.utc)
        archivo.rgstrs_prcsds = resultado_persistencia.guardadas
        if resultado_validacion.errores:
            resumen_errores = "; ".join(
                f"fila {e.numero_fila}: {e.motivo}" for e in resultado_validacion.errores[:5]
            )
            archivo.mnsj_errr = resumen_errores[:500]
        db.commit()

        logger.info(
            "archv_ingst id=%s procesado: %s guardadas, %s sin valor, %s con error de validación",
            id_archv, resultado_persistencia.guardadas,
            resultado_persistencia.omitidas_sin_valor, len(resultado_validacion.errores),
        )
        return {
            "id_archv": id_archv,
            "estado": archivo.estd,
            "guardadas": resultado_persistencia.guardadas,
            "errores_validacion": len(resultado_validacion.errores),
        }
    except ErrorDatosNoRecuperable as exc:
        db.rollback()
        archivo = db.get(ArchivoIngesta, id_archv)
        if archivo is not None:
            archivo.estd = "Fallido"
            archivo.mnsj_errr = str(exc)[:500]
            db.commit()
        logger.error("archv_ingst id=%s marcado Fallido (error no recuperable): %s", id_archv, exc)
        return {"id_archv": id_archv, "estado": "Fallido"}
    except Exception as exc:
        db.rollback()
        # Se marca Fallido cuando ya no va a haber otro intento, sea porque
        # se agotaron los reintentos o porque el error no es de los
        # transitorios (autoretry_for) y por tanto Celery no lo reintenta.
        # Sin esta segunda condición, un error inesperado -por ejemplo un
        # IntegrityError de Postgres- dejaba el archivo colgado en
        # 'Procesando' indefinidamente: ni se reintentaba, ni aparecía como
        # fallido en las métricas de HU09, ni se podía reprocesar (HU31).
        es_transitorio = isinstance(exc, ERRORES_TRANSITORIOS)
        if not es_transitorio or self.request.retries >= self.max_retries:
            archivo = db.get(ArchivoIngesta, id_archv)
            if archivo is not None:
                archivo.estd = "Fallido"
                archivo.mnsj_errr = str(exc)[:500]
                db.commit()
            logger.error(
                "archv_ingst id=%s marcado Fallido (%s): %s",
                id_archv,
                "reintentos agotados" if es_transitorio else "error no reintentable",
                exc,
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
