import datetime as dt
import logging
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.models import Exportacion
from app.services.exportaciones import ahora, generar_archivo, limites, revalidar_acceso
from app.services.exportaciones_storage import AlmacenExportaciones

logger = logging.getLogger(__name__)


def encolar_exportacion(id_exportacion):
    try:
        generar_exportacion.apply_async(args=[id_exportacion], retry=False)
    except Exception:
        # El registro Pendiente es una salida durable: Beat vuelve a publicar.
        logger.exception(
            "No se pudo publicar exportación id=%s; se recuperará con Beat", id_exportacion
        )


@celery_app.task(
    name="app.tasks.exportaciones.generar_exportacion", soft_time_limit=1140, time_limit=1200
)
def generar_exportacion(id_exportacion):
    db = SessionLocal()
    try:
        exportacion = (
            db.query(Exportacion)
            .filter_by(id_exprtcn=id_exportacion, estd="Pendiente")
            .with_for_update(skip_locked=True)
            .first()
        )
        if exportacion is None:
            return {"estado": "omitida"}
        exportacion.estd = "En proceso"
        exportacion.fch_inicio = ahora()
        exportacion.intentos += 1
        exportacion.error = None
        db.commit()
        revalidar_acceso(db, exportacion)
        almacen = AlmacenExportaciones(exportacion.objeto_bucket)
        exportacion.objeto_bucket = almacen.bucket
        if exportacion.objeto_clave is None:
            exportacion.objeto_clave = (
                f"exportaciones/{exportacion.id_usr}/{uuid4().hex}.{exportacion.frmt}"
            )
        exportacion.fch_exprcn = ahora() + dt.timedelta(hours=limites()["vigencia_horas"])
        db.commit()
        with tempfile.TemporaryDirectory(prefix="pangea-export-") as carpeta:
            destino = Path(carpeta) / f"telemetria.{exportacion.frmt}"
            cantidad, tamano = generar_archivo(db, exportacion, destino)
            # Libera los cursores y vuelve a consultar permisos tras la generación.
            db.commit()
            revalidar_acceso(db, exportacion)
            exportacion.objeto_version = almacen.subir(
                destino, exportacion.objeto_clave, exportacion.frmt
            )
        # Comprueba revocaciones que hayan ocurrido durante la subida.
        db.commit()
        revalidar_acceso(db, exportacion)
        exportacion.estd = "Lista"
        exportacion.filas = cantidad
        exportacion.bytes_archivo = tamano
        exportacion.fch_fin = ahora()
        exportacion.fch_exprcn = ahora() + dt.timedelta(hours=limites()["vigencia_horas"])
        db.commit()
        try:
            notificar_exportacion.apply_async(args=[id_exportacion], retry=False)
        except Exception:
            logger.exception(
                "Notificación de exportación id=%s pendiente de recuperación", id_exportacion
            )
        return {"estado": "Lista", "filas": cantidad}
    except Exception as exc:
        db.rollback()
        exportacion = db.get(Exportacion, id_exportacion)
        if exportacion:
            transitorio = isinstance(exc, (BotoCoreError, ClientError, OSError))
            exportacion.estd = (
                "Pendiente" if transitorio and exportacion.intentos < 3 else "Fallida"
            )
            exportacion.error = (
                str(exc.detail)
                if isinstance(exc, HTTPException)
                else (
                    str(exc)[:450]
                    if isinstance(exc, ValueError)
                    else "No se pudo generar el archivo. Reintenta más tarde o contacta al administrador."
                )
            )
            exportacion.fch_fin = ahora()
            db.commit()
        logger.exception("Falló generación de exportación id=%s", id_exportacion)
        return {"estado": exportacion.estd if exportacion else "Fallida"}
    finally:
        db.close()


@celery_app.task(name="app.tasks.exportaciones.notificar_exportacion")
def notificar_exportacion(id_exportacion):
    from app.security.mailer import enviar_correo_exportacion

    db = SessionLocal()
    try:
        exportacion = (
            db.query(Exportacion)
            .filter_by(id_exprtcn=id_exportacion, estd="Lista")
            .with_for_update(skip_locked=True)
            .first()
        )
        if (
            exportacion is None
            or exportacion.notificada_en
            or exportacion.fch_exprcn <= ahora()
            or exportacion.notificacion_intentos >= 5
        ):
            return {"estado": "omitida"}
        exportacion.notificacion_intentos += 1
        try:
            cuenta = revalidar_acceso(db, exportacion)
            enlace = (
                os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
                + f"/consulta-datos?exportacion={id_exportacion}"
            )
            enviar_correo_exportacion(cuenta.crr, enlace, exportacion.fch_exprcn)
        except Exception:
            exportacion.notificacion_estado = "Fallida"
            logger.exception("No se pudo notificar exportación id=%s", id_exportacion)
        else:
            exportacion.notificacion_estado = "Enviada"
            exportacion.notificada_en = ahora()
        db.commit()
        return {"estado": exportacion.notificacion_estado}
    finally:
        db.close()


@celery_app.task(name="app.tasks.exportaciones.mantener_exportaciones")
def mantener_exportaciones():
    db = SessionLocal()
    limpiadas = 0
    try:
        # Lotes acotados; SKIP LOCKED permite más de una instancia de Beat.
        vencidas = (
            db.query(Exportacion)
            .filter(
                Exportacion.objeto_clave.is_not(None),
                Exportacion.fch_exprcn <= ahora(),
                Exportacion.estd != "En proceso",
            )
            .order_by(Exportacion.id_exprtcn)
            .limit(100)
            .with_for_update(skip_locked=True)
            .all()
        )
        for exportacion in vencidas:
            try:
                AlmacenExportaciones(exportacion.objeto_bucket).eliminar(
                    exportacion.objeto_clave, exportacion.objeto_version
                )
            except Exception:
                logger.exception(
                    "No se pudo limpiar exportación id=%s; se reintentará", exportacion.id_exprtcn
                )
                continue
            exportacion.objeto_clave = None
            exportacion.objeto_version = None
            exportacion.url_dscrg = None
            exportacion.estd = "Expirada"
            limpiadas += 1
        db.commit()

        atascadas = (
            db.query(Exportacion)
            .filter(
                Exportacion.estd == "En proceso",
                Exportacion.fch_inicio < ahora() - dt.timedelta(minutes=25),
            )
            .limit(100)
            .with_for_update(skip_locked=True)
            .all()
        )
        for exportacion in atascadas:
            exportacion.estd = "Fallida"
            exportacion.error = (
                "Se agotó el tiempo de procesamiento. Reduce el rango y solicita otra exportación."
            )
            exportacion.fch_exprcn = ahora()
        db.commit()
        pendientes = (
            db.query(Exportacion.id_exprtcn)
            .filter(Exportacion.estd == "Pendiente")
            .order_by(Exportacion.id_exprtcn)
            .limit(100)
            .all()
        )
        notificaciones = (
            db.query(Exportacion.id_exprtcn)
            .filter(
                Exportacion.estd == "Lista",
                Exportacion.notificada_en.is_(None),
                Exportacion.notificacion_intentos < 5,
                Exportacion.fch_exprcn > ahora(),
            )
            .limit(100)
            .all()
        )
        for (id_,) in pendientes:
            encolar_exportacion(id_)
        for (id_,) in notificaciones:
            try:
                notificar_exportacion.apply_async(args=[id_], retry=False)
            except Exception:
                logger.exception("No se pudo publicar notificación id=%s", id_)
        return {"eliminadas": limpiadas}
    finally:
        db.close()
