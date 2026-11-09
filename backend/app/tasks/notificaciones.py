"""HT-14: despacho recuperable desde PostgreSQL y envío asíncrono por SES."""

import logging
import os
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_

from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.models.alarma import IntentoNotificacion, NotificacionEnviada
from app.services.correo_ses import (
    cifrar_password_temporal,
    codigo_error,
    enviar_ses,
    error_transitorio,
)

logger = logging.getLogger(__name__)
MAX_REINTENTOS = int(os.environ.get("SES_MAX_RETRIES", "5"))
BASE_BACKOFF = int(os.environ.get("SES_RETRY_BASE_SECONDS", "10"))
MAX_BACKOFF = int(os.environ.get("SES_RETRY_MAX_SECONDS", "600"))
if MAX_REINTENTOS < 0 or BASE_BACKOFF < 1 or MAX_BACKOFF < BASE_BACKOFF:
    raise ValueError("Política de reintentos SES inválida")
RESERVA_SEGUNDOS = 300


def ahora():
    return datetime.now(timezone.utc)


def backoff(reintento):
    limite = min(MAX_BACKOFF, BASE_BACKOFF * 2 ** (reintento - 1))
    return random.uniform(limite / 2, limite)


@celery_app.task(name="app.tasks.notificaciones.despachar_pendientes", ignore_result=True)
def despachar_pendientes():
    """Repara mensajes perdidos entre commit y broker mediante reservas finitas."""
    momento = ahora()
    with SessionLocal() as db:
        filas = (
            db.query(NotificacionEnviada)
            .filter(
                NotificacionEnviada.cnl == "email",
                NotificacionEnviada.estd.in_(["Pendiente", "Reintentando", "Encolado"]),
                NotificacionEnviada.prxm_intnt <= momento,
                or_(
                    NotificacionEnviada.bloqueo_hasta.is_(None),
                    NotificacionEnviada.bloqueo_hasta <= momento,
                ),
            )
            .order_by(NotificacionEnviada.id_ntfccn)
            .limit(100)
            .with_for_update(skip_locked=True)
            .all()
        )
        ids = [n.id_ntfccn for n in filas]
        for n in filas:
            n.estd = "Encolado"
            n.bloqueo_hasta = momento + timedelta(seconds=RESERVA_SEGUNDOS)
        db.commit()
    for id_notificacion in ids:
        try:
            enviar_notificacion.apply_async(args=[id_notificacion], retry=False)
        except Exception:
            logger.warning(
                "Broker no disponible; notificación %s permanece recuperable", id_notificacion
            )
            with SessionLocal() as db:
                n = (
                    db.query(NotificacionEnviada)
                    .filter_by(id_ntfccn=id_notificacion)
                    .with_for_update()
                    .one()
                )
                if n.estd == "Encolado":
                    n.estd, n.bloqueo_hasta = "Pendiente", None
                    db.commit()
    return {"reservadas": len(ids)}


@celery_app.task(
    bind=True,
    name="app.tasks.notificaciones.enviar_notificacion",
    max_retries=MAX_REINTENTOS,
    acks_late=True,
    reject_on_worker_lost=True,
    ignore_result=True,
)
def enviar_notificacion(self, id_notificacion):
    espera = None
    with SessionLocal() as db:
        # Bloqueo durante SES: impide envíos simultáneos del mismo aviso;
        # no bloquea filas de telemetría ni de configuración de alarmas.
        n = (
            db.query(NotificacionEnviada)
            .filter_by(id_ntfccn=id_notificacion)
            .with_for_update(skip_locked=True)
            .one_or_none()
        )
        if n is None or n.estd in {"Enviado", "Fallido"} or n.prxm_intnt > ahora():
            return {"estado": "omitido"}
        if n.cnl != "email":
            return {"estado": "canal_no_soportado"}
        numero = (
            db.query(func.coalesce(func.max(IntentoNotificacion.numero), 0))
            .filter_by(id_ntfccn=n.id_ntfccn)
            .scalar()
            + 1
        )
        try:
            mensaje_id = enviar_ses(n.plantilla, n.contexto, n.dstn, n.id_ntfccn)
        except Exception as exc:
            error = codigo_error(exc)
            n.ultimo_error = error
            db.add(
                IntentoNotificacion(
                    id_ntfccn=n.id_ntfccn, numero=numero, resultado="Fallido", error=error
                )
            )
            if error_transitorio(exc) and n.rntnts < MAX_REINTENTOS:
                n.rntnts += 1
                espera = backoff(n.rntnts)
                n.estd = "Reintentando"
                n.prxm_intnt = ahora() + timedelta(seconds=espera)
                n.bloqueo_hasta = None
            else:
                n.estd, n.bloqueo_hasta = "Fallido", None
            logger.warning("Notificación %s: %s (%s)", n.id_ntfccn, n.estd, error)
        else:
            n.estd, n.mensaje_id, n.fch_env = "Enviado", mensaje_id, ahora()
            n.ultimo_error, n.bloqueo_hasta = None, None
            if n.plantilla == "bienvenida":
                n.contexto = {"nombre": n.contexto.get("nombre", "")}
            db.add(
                IntentoNotificacion(
                    id_ntfccn=n.id_ntfccn, numero=numero, resultado="Enviado", mensaje_id=mensaje_id
                )
            )
        estado = n.estd
        db.commit()
    if espera is not None:
        # El presupuesto persiste en BD incluso si Beat recupera la tarea
        # con un identificador nuevo. El fallo de publicación no pierde el aviso.
        raise self.retry(countdown=espera, max_retries=None)
    return {"estado": estado}


@celery_app.task(
    name="app.tasks.notificaciones.enviar_correo_bienvenida",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
    ignore_result=True,
)
def enviar_correo_bienvenida(correo, nombre_completo, password_temporal):
    """HU04: conserva el envío de credenciales, cifradas hasta el envío SES."""
    from app.models.rol_usuario import Usuario
    from app.services.notificaciones import crear_notificacion

    with SessionLocal() as db:
        usuario = db.query(Usuario).filter_by(crr=correo.lower()).one()
        crear_notificacion(
            db,
            destinatario=correo,
            tipo="bienvenida",
            plantilla="bienvenida",
            contexto={
                "nombre": nombre_completo,
                "password_cifrada": cifrar_password_temporal(password_temporal),
            },
            id_usr=usuario.id_usr,
            clave=f"bienvenida:{usuario.id_usr}",
        )
        db.commit()
    return {"estado": "Pendiente"}
