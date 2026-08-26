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
    tipos_de_parametro,
)
from app.services.ingesta.parser import parsear_dat
from app.services.ingesta.persistencia import (
    DispositivoNoResueltoError,
    guardar_lecturas,
    resolver_dispositivo,
)
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


def normalizar_contenido_dat(contenido: str) -> str:
    """Quita el byte NUL de relleno y unifica CRLF/CR a '\\n'.

    parsear_dat() corre csv.reader sobre un io.StringIO, que no hace la
    traducción universal de saltos de línea de un archivo abierto en modo
    texto. Los .dat de campo (Campbell Scientific, entre otros) vienen con
    CRLF y a veces con NUL al final: sin esto el csv revienta con
    "new-line character seen in unquoted field".
    """
    return contenido.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")


def interpretar_y_guardar(
    db,
    contenido: str,
    formato,
    dispositivo,
    id_cnxn: int,
    id_archv: int,
    nombre_archivo: str,
):
    """Etapas PP-97..100 sobre el contenido ya obtenido de un .dat.

    Es el tramo del pipeline que NO depende de cómo llegó el archivo, y
    por eso vive acá y no dentro de la tarea Celery: la ingesta automática
    lo llama con lo que bajó por FTP, y la carga manual de la ficha del
    dispositivo (IMP-06, routers/dispositivos.py) con lo que subió el
    usuario. Duplicar estas etapas era la vía directa a que el archivo
    subido a mano se interpretara distinto que el mismo archivo entrando
    por FTP.

    No hace commit: la transacción la controla el llamador, igual que
    guardar_lecturas().
    """
    resultado_parseo = parsear_dat(normalizar_contenido_dat(contenido), formato.config)

    # mp_clmn referencia las columnas por índice, así que el mapeo se
    # arma con el header ya leído.
    mapeo = construir_mapeo(db, formato.id_mp, resultado_parseo.columnas)
    if not mapeo:
        raise ErrorDatosNoRecuperable(
            f"El formato mp_frmt id={formato.id_mp} (trama '{formato.tipo_trama}') "
            f"no tiene ninguna columna mapeada que exista en el header de "
            f"'{nombre_archivo}'; no se puede interpretar el archivo."
        )

    lecturas_estandar = estandarizar_filas(
        resultado_parseo,
        id_cnxn=id_cnxn,
        mapeo=mapeo,
    )
    resultado_validacion = validar_lecturas(
        lecturas_estandar,
        delimitador_decimal=formato.delimitador_decimal,
        tipos_parametro=tipos_de_parametro(db, formato.id_mp),
    )
    resultado_persistencia = guardar_lecturas(
        db,
        resultado_validacion.validas,
        dispositivo,
        id_archv,
    )
    return resultado_validacion, resultado_persistencia


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
            id_archv,
            archivo.id_cnxn,
            archivo.nmbr_archv,
        )

        cnxn = db.get(ConexionFTP, archivo.id_cnxn)
        if cnxn is None:
            raise ErrorDatosNoRecuperable(f"cnxn_ftp id={archivo.id_cnxn} no existe")

        try:
            dispositivo = resolver_dispositivo(db, archivo.id_cnxn)
        except DispositivoNoResueltoError as exc:
            raise ErrorDatosNoRecuperable(str(exc)) from exc

        # DEC-09 (PP-96): el formato aplicable sale de mp_frmt según el
        # DISPOSITIVO ya resuelto y el tipo de trama, que se deduce del
        # prefijo del nombre del archivo (H_ = datos periódicos,
        # E_ = estados/eventos). Antes se resolvía por sede+marca, lo que
        # hacía que dos dataloggers de la misma marca en la misma sede
        # compartieran mapeo. Se resuelve ANTES de descargar: si no hay
        # mapeo cargado, no tiene sentido bajar el archivo.
        try:
            formato = resolver_formato(db, dispositivo.id_dspstv, archivo.nmbr_archv)
        except MapeoNoEncontradoError as exc:
            raise ErrorDatosNoRecuperable(str(exc)) from exc

        contenido = descargar_archivo_dat(cnxn, archivo.nmbr_archv)

        try:
            resultado_validacion, resultado_persistencia = interpretar_y_guardar(
                db,
                contenido=contenido,
                formato=formato,
                dispositivo=dispositivo,
                id_cnxn=archivo.id_cnxn,
                id_archv=id_archv,
                nombre_archivo=archivo.nmbr_archv,
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
            id_archv,
            resultado_persistencia.guardadas,
            resultado_persistencia.omitidas_sin_valor,
            len(resultado_validacion.errores),
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

        # Los ids se juntan acá y se encolan DESPUÉS del commit: ver el
        # bloque final de esta función.
        por_encolar: list[int] = []
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
                    cnxn.id_cnxn,
                    cnxn.hst,
                    exc,
                )
                continue

            existentes = {
                nombre
                for (nombre,) in db.query(ArchivoIngesta.nmbr_archv)
                .filter(ArchivoIngesta.id_cnxn == cnxn.id_cnxn)
                .filter(ArchivoIngesta.nmbr_archv.in_(nombres))
                .all()
            }

            for nombre in nombres:
                if nombre in existentes:
                    continue
                archivo = ArchivoIngesta(id_cnxn=cnxn.id_cnxn, nmbr_archv=nombre)
                db.add(archivo)
                db.flush()  # asigna id_archv, todavía sin confirmar
                por_encolar.append(archivo.id_archv)

            cnxn.ultm_snd = ahora
            db.commit()

        # Encolar SOLO después del commit. Con .delay() dentro del bucle
        # había una carrera real: flush() asigna el id pero no confirma la
        # transacción, así que el worker -que toma el job en milisegundos-
        # consultaba una fila que todavía no era visible, logueaba
        # "archv_ingst id=N no existe, se descarta el job" y el archivo
        # quedaba 'Pendiente' PARA SIEMPRE, porque nadie lo reencola: el
        # sondeo siguiente lo ve en `existentes` y lo saltea.
        for id_archv in por_encolar:
            procesar_archivo_dat.delay(id_archv=id_archv)

        logger.info(
            "Sondeo FTP: %s conexiones revisadas, %s archivos nuevos encolados",
            len(conexiones),
            len(por_encolar),
        )
        return {"conexiones_revisadas": len(conexiones), "encolados": len(por_encolar)}
    finally:
        db.close()


MINUTOS_PENDIENTE_ATASCADO = 15


@celery_app.task(name="app.tasks.ingesta.reencolar_pendientes_atascados")
def reencolar_pendientes_atascados() -> dict:
    """Red de seguridad: corre vía Celery Beat (ver celery_app.py,
    beat_schedule) y re-encola cualquier archv_ingst en 'Pendiente' cuya
    fch_dtccn tenga más de MINUTOS_PENDIENTE_ATASCADO.

    sondear_conexiones_ftp encola procesar_archivo_dat SOLO en el momento
    en que crea la fila (ver arriba); si esa fila entra a archv_ingst por
    otra vía -una carga de datos de prueba, un worker caído justo entre el
    INSERT y el .delay(), un mensaje de Celery perdido por un reinicio del
    broker- nada vuelve a encolarla jamás, y queda "En espera" para
    siempre sin que se note (caso real: 409 archivos así el 2026-08-24,
    ver RAID_LOG_PANGEA.md).

    15 minutos de margen porque un archivo recién detectado por el sondeo
    normal también pasa por 'Pendiente' un instante entre el INSERT y que
    el worker lo tome: sin margen, este job competiría por re-encolar
    archivos que ya tienen una tarea Celery en camino.
    """
    db = SessionLocal()
    try:
        limite = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=MINUTOS_PENDIENTE_ATASCADO)
        atascados = (
            db.query(ArchivoIngesta)
            .filter(ArchivoIngesta.estd == "Pendiente", ArchivoIngesta.fch_dtccn < limite)
            .order_by(ArchivoIngesta.fch_dtccn.asc())
            .all()
        )

        for archivo in atascados:
            procesar_archivo_dat.delay(id_archv=archivo.id_archv)

        if atascados:
            logger.warning(
                "reencolar_pendientes_atascados: %s archivo(s) en 'Pendiente' hace más de "
                "%s min, re-encolados (ids: %s)",
                len(atascados),
                MINUTOS_PENDIENTE_ATASCADO,
                [a.id_archv for a in atascados],
            )

        return {"reencolados": len(atascados)}
    finally:
        db.close()
