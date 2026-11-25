"""Alertas directas por SES: no requieren Redis, Celery ni conexion a la BD."""

import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from app.services import almacen_respaldos as almacen
from app.services.correo_ses import codigo_error, enviar_ses
from app.services.respaldos import ZONA, entero_configurado


def habilitado(nombre):
    return os.environ.get(nombre, "false").lower() in {"true", "1", "yes"}


def emitir_alerta(evento, mensaje):
    """Deduplica por incidente/dia. Un fallo de SES se reintenta en la siguiente revision."""
    destinos = [
        valor.strip()
        for valor in os.environ.get("BACKUP_ALERT_RECIPIENTS", "").split(",")
        if valor.strip()
    ]
    if not destinos:
        raise ValueError("Falta BACKUP_ALERT_RECIPIENTS")
    carpeta = Path(os.environ.get("BACKUP_MONITOR_STATE_DIR", ".backup-monitor"))
    carpeta.mkdir(parents=True, exist_ok=True)
    resultado = []
    for destino in destinos:
        identidad = f"{almacen.prefijo()}:{evento}:{destino}:{dt.datetime.now(ZONA).date()}"
        correlacion = hashlib.sha256(identidad.encode()).hexdigest()
        ruta = carpeta / f"{correlacion}.json"
        if ruta.exists():
            resultado.append({"destinatario": destino, "resultado": "YaAlertado"})
            continue
        message_id = enviar_ses(
            "generica",
            {
                "titulo": f"Pangea: revisar respaldos ({os.environ.get('BACKUP_ENVIRONMENT','local')})",
                "mensaje": mensaje,
            },
            destino,
            correlacion,
        )
        recibo = {
            "fecha": dt.datetime.now(dt.timezone.utc).isoformat(),
            "evento": evento,
            "destinatario": destino,
            "resultado": "Enviado",
            "message_id": message_id,
        }
        descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as salida:
            json.dump(recibo, salida)
        resultado.append(recibo)
    # Los recibos locales no deben acumularse indefinidamente.
    limite = dt.datetime.now().timestamp() - 90 * 86400
    for ruta in carpeta.glob("*.json"):
        if ruta.stat().st_mtime < limite:
            ruta.unlink()
    return resultado


def vencimiento_anterior(ahora):
    local = ahora.astimezone(ZONA)
    domingo = (local - dt.timedelta(days=(local.weekday() + 1) % 7)).replace(
        hour=2, minute=0, second=0, microsecond=0
    )
    return domingo if domingo <= local else domingo - dt.timedelta(days=7)


def comprobar_respaldo(ahora=None):
    if not habilitado("BACKUP_MONITOR_ENABLED"):
        return {"estado": "Deshabilitado"}
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    inicio = dt.datetime.fromisoformat(os.environ["BACKUP_MONITOR_START_AT"])
    if inicio.tzinfo is None:
        raise ValueError("BACKUP_MONITOR_START_AT necesita zona horaria")
    esperado = vencimiento_anterior(ahora)
    margen = dt.timedelta(hours=entero_configurado("BACKUP_EXPECTED_WINDOW_HOURS", 4))
    try:
        ultimo = almacen.leer_json(almacen.prefijo() + "control/ultimo-exito-semanal.json")
        intento = almacen.leer_json(almacen.prefijo() + "control/ultima-ejecucion.json")
    except Exception as exc:
        return {
            "estado": "Alerta",
            "alertas": emitir_alerta(
                "almacen-inaccesible",
                f"No se puede consultar el almacenamiento de respaldos. Codigo: {codigo_error(exc)}.",
            ),
        }
    if intento and intento.get("estado") == "Fallido":
        return {
            "estado": "Alerta",
            "alertas": emitir_alerta(
                "fallido-" + intento["id"],
                "Fallo el ultimo intento de respaldo. Revisar el worker y la configuracion. Codigo: "
                + intento.get("codigo_error", "desconocido"),
            ),
        }
    exito = dt.datetime.fromisoformat(ultimo["finalizado"]) if ultimo else None
    if esperado >= inicio and ahora > esperado + margen and (not exito or exito < esperado):
        return {
            "estado": "Alerta",
            "alertas": emitir_alerta(
                "ausente-" + esperado.date().isoformat(),
                "No existe un respaldo semanal exitoso dentro de la ventana de cuatro horas. Revisar Celery Beat, worker, PostgreSQL y S3.",
            ),
        }
    return {
        "estado": "Correcto",
        "ultimo_exito": ultimo["finalizado"] if ultimo else None,
        "proximo_control": (
            esperado + margen
            if ahora <= esperado + margen
            else esperado + dt.timedelta(days=7) + margen
        ).isoformat(),
    }
