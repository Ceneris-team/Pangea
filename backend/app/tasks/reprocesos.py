"""Outbox de HU31: entrega recuperable y ejecución exclusiva por archivo."""

import datetime as dt
import logging

from botocore.exceptions import ClientError
from sqlalchemy import and_, or_
from sqlalchemy.exc import OperationalError

from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.models import ArchivoIngesta, IntentoProcesamiento
from app.security.auditoria import limpiar_contexto_auditoria, marcar_contexto_auditoria
from app.services.cache.invalidacion import invalidar_por_lectura
from app.services.ingesta.mapeo import MapeoNoEncontradoError, resolver_formato
from app.services.ingesta.originales import dispositivo_del_archivo, leer_original
from app.services.ingesta.persistencia import DispositivoNoResueltoError
from app.services.ingesta.reprocesos import MAX_REINTENTOS, ahora, finalizar, solicitar
from app.services.particiones import ParticionInexistenteError

logger = logging.getLogger(__name__)
MINUTOS_ABANDONO = 15


def _es_transitorio(exc):
    from app.tasks.ingesta import ERRORES_TRANSITORIOS

    if isinstance(exc, OperationalError):
        codigo = getattr(exc.orig, "pgcode", "") or ""
        return (
            exc.connection_invalidated
            or codigo.startswith("08")
            or codigo in {"40001", "40P01", "53300", "57P01"}
        )
    if isinstance(exc, ClientError):
        respuesta = exc.response
        return respuesta.get("ResponseMetadata", {}).get(
            "HTTPStatusCode", 0
        ) >= 500 or respuesta.get("Error", {}).get("Code") in {
            "SlowDown",
            "Throttling",
            "RequestTimeout",
            "429",
        }
    return isinstance(exc, ERRORES_TRANSITORIOS)


def _reservar(db, id_archv):
    return (
        db.query(ArchivoIngesta)
        .filter_by(id_archv=id_archv)
        .populate_existing()
        .with_for_update(skip_locked=True)
        .first()
    )


def _fallar(db, archivo, intento, mensaje, *, transitorio=False):
    finalizar(intento, "Fallido", mensaje)
    archivo.mnsj_errr = mensaje[:500]
    archivo.estd = "Fallido"
    archivo.fch_prcsd = ahora()
    if transitorio and intento.reintentos < MAX_REINTENTOS:
        # Liberar el índice único antes de insertar el próximo intento.
        db.flush()
        solicitar(
            db,
            archivo,
            intento.id_usr,
            anterior=intento,
            demora=min(600, 2 ** (intento.reintentos + 1)),
        )


@celery_app.task(
    name="app.tasks.reprocesos.procesar_reproceso", acks_late=True, reject_on_worker_lost=True
)
def procesar_reproceso(id_archv: int, id_intnt: int):
    from app.tasks.ingesta import (
        ErrorDatosNoRecuperable,
        _publicar_eventos_mapa,
        interpretar_y_guardar,
    )

    db = SessionLocal()
    confirmado = False
    try:
        archivo = _reservar(db, id_archv)
        if archivo is None:
            return {"estado": "ocupado_o_inexistente"}
        intento = db.get(IntentoProcesamiento, id_intnt)
        if intento is None or intento.id_archv != id_archv or intento.rsltd != "Pendiente":
            return {"estado": "descartado"}
        if archivo.estd != "Pendiente":
            finalizar(intento, "Fallido", "El archivo ya no está disponible para este reproceso")
            db.commit()
            return {"estado": "descartado"}
        intento.rsltd = "Procesando"
        intento.fch_inicio = ahora()
        intento.proximo_envio = None
        archivo.estd = "Procesando"
        db.commit()

        # El bloqueo se mantiene durante TODO el procesamiento y su commit.
        # El recuperador usa SKIP LOCKED: nunca rescata una ejecución en curso.
        archivo = _reservar(db, id_archv)
        if archivo is None:
            return {"estado": "ocupado"}
        intento = db.get(IntentoProcesamiento, id_intnt, populate_existing=True)
        if intento.rsltd != "Procesando" or archivo.estd != "Procesando":
            return {"estado": "descartado"}

        try:
            dispositivo = dispositivo_del_archivo(db, archivo)
            original = leer_original(archivo)
            if original is None:
                raise ErrorDatosNoRecuperable(
                    "No existe una copia original conservada. Requiere revisión técnica; "
                    "el archivo actual del FTP no sustituye al original."
                )
            contenido = original.decode("utf-8-sig")
            marcar_contexto_auditoria(db, intento.id_usr)
            try:
                formato = resolver_formato(
                    db,
                    dispositivo.id_dspstv,
                    archivo.nmbr_archv,
                    permitir_creacion_automatica=False,
                )
                validacion, resultado = interpretar_y_guardar(
                    db,
                    contenido,
                    formato,
                    dispositivo,
                    archivo.id_cnxn,
                    archivo.id_archv,
                    archivo.nmbr_archv,
                )
            finally:
                limpiar_contexto_auditoria(db)
        except (
            DispositivoNoResueltoError,
            MapeoNoEncontradoError,
            UnicodeDecodeError,
            ValueError,
            ParticionInexistenteError,
        ) as exc:
            raise ErrorDatosNoRecuperable(str(exc)) from exc

        archivo.estd = "Exitoso"
        archivo.fch_prcsd = ahora()
        archivo.rgstrs_prcsds = resultado.guardadas
        archivo.mnsj_errr = (
            "; ".join(
                f"fila {error.numero_fila}: {error.motivo}" for error in validacion.errores[:5]
            )[:500]
            or None
        )
        finalizar(intento, "Exitoso", archivo.mnsj_errr, resultado.guardadas)
        if resultado.guardadas and (
            dispositivo.ultima_recepcion is None or archivo.fch_dtccn > dispositivo.ultima_recepcion
        ):
            dispositivo.ultima_recepcion = archivo.fch_dtccn
            dispositivo.sin_datos_desde = None
            dispositivo.aviso_sin_datos = None
        db.commit()
        confirmado = True
        if resultado.guardadas:
            invalidar_por_lectura(id_sd=resultado.id_sd, id_ubccn=resultado.id_ubccn)
            _publicar_eventos_mapa(db, resultado)
        return {"estado": "Exitoso", "guardadas": resultado.guardadas}
    except Exception as exc:
        db.rollback()
        if confirmado:
            # Un fallo de difusión posterior al commit no revierte datos confirmados.
            logger.exception("No se pudo difundir el resultado del reproceso %s", id_intnt)
            return {"estado": "Exitoso"}
        archivo = _reservar(db, id_archv)
        intento = db.get(IntentoProcesamiento, id_intnt, populate_existing=True)
        if archivo is not None and intento is not None and intento.rsltd == "Procesando":
            _fallar(db, archivo, intento, str(exc), transitorio=_es_transitorio(exc))
            db.commit()
        logger.warning("Reproceso %s no completado: %s", id_intnt, exc)
        return {"estado": archivo.estd if archivo else "ocupado"}
    finally:
        db.close()


@celery_app.task(name="app.tasks.reprocesos.despachar_pendientes")
def despachar_pendientes():
    db = SessionLocal()
    entregas = []
    try:
        limite = ahora() - dt.timedelta(minutes=MINUTOS_ABANDONO)
        filas = (
            db.query(ArchivoIngesta, IntentoProcesamiento)
            .join(IntentoProcesamiento, IntentoProcesamiento.id_archv == ArchivoIngesta.id_archv)
            .filter(
                or_(
                    and_(
                        IntentoProcesamiento.rsltd == "Pendiente",
                        IntentoProcesamiento.proximo_envio <= ahora(),
                    ),
                    and_(
                        IntentoProcesamiento.rsltd == "Procesando",
                        IntentoProcesamiento.fch_inicio < limite,
                    ),
                )
            )
            .order_by(
                IntentoProcesamiento.proximo_envio.asc().nullsfirst(), IntentoProcesamiento.id_intnt
            )
            .with_for_update(of=ArchivoIngesta, skip_locked=True)
            .limit(100)
            .all()
        )
        for archivo, intento in filas:
            if intento.rsltd == "Procesando":
                _fallar(
                    db,
                    archivo,
                    intento,
                    "Ejecución interrumpida; se recuperó la solicitud conservada",
                    transitorio=True,
                )
                continue
            if archivo.estd != "Pendiente":
                finalizar(intento, "Fallido", "El estado del archivo cambió antes del despacho")
                continue
            # Reservar antes de publicar. Si se pierde el mensaje, vuelve a ser elegible.
            intento.proximo_envio = ahora() + dt.timedelta(seconds=60)
            entregas.append((archivo.id_archv, intento.id_intnt))
        db.commit()
        publicados = 0
        for archivo_id, intento_id in entregas:
            try:
                procesar_reproceso.apply_async(
                    kwargs={"id_archv": archivo_id, "id_intnt": intento_id},
                    task_id=f"reproceso-{intento_id}",
                    retry=False,
                )
                publicados += 1
            except Exception:
                logger.exception("Solicitud %s conservada; broker no disponible", intento_id)
        return {"publicados": publicados, "pendientes_recuperables": len(entregas) - publicados}
    finally:
        db.close()
