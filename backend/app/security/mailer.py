"""
HU 02 - Gestionar contraseña
HU 29/HU 30 - Notificación por correo al disparar una alarma

Envío de correo centralizado. La configuración SMTP se lee de variables de
entorno (ver .env.example); si no está configurada (entorno local sin
servidor de correo), el mensaje se registra en el log en vez de fallar,
igual que el fallback de desarrollo de JWT_SECRET en jwt_auth.py.
"""

import datetime as dt
import logging
import os
import smtplib
from email.message import EmailMessage
from zoneinfo import ZoneInfo

logger = logging.getLogger("pangea.mailer")

SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM", "no-reply@pangea.local")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")


def _enviar(correo: str, asunto: str, cuerpo: str) -> None:
    """Envío de bajo nivel compartido por los distintos correos de la app.

    Si SMTP_HOST no está configurado, registra el correo en el log en vez
    de fallar -entorno local sin servidor de correo-."""
    if not SMTP_HOST:
        logger.info("SMTP no configurado; correo para %s (%s):\n%s", correo, asunto, cuerpo)
        return

    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = SMTP_FROM
    mensaje["To"] = correo
    mensaje.set_content(cuerpo)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as servidor:
        servidor.starttls()
        if SMTP_USER and SMTP_PASSWORD:
            servidor.login(SMTP_USER, SMTP_PASSWORD)
        servidor.send_message(mensaje)


def enviar_correo_recuperacion(correo: str, token: str) -> None:
    enlace = f"{FRONTEND_URL}/restablecer-contrasena?token={token}"
    cuerpo = (
        "Recibimos una solicitud para restablecer tu contraseña.\n\n"
        f"Ingresa al siguiente enlace para continuar (válido por 30 minutos):\n{enlace}\n\n"
        "Si no solicitaste este cambio, puedes ignorar este correo."
    )
    _enviar(correo, "Recupera tu contraseña - Pangea", cuerpo)


def enviar_correo_alarma(
    correo: str,
    *,
    nombre_alarma: str,
    nombre_parametro: str,
    valor,
    umbral,
    unidad: str,
    nombre_ubicacion: str,
    fecha_hora: dt.datetime | None,
    zona_horaria: str | None,
) -> None:
    """HU29 CA3 / HU30 detalles de conversación: contenido del correo que
    avisa que una alarma se disparó -nombre de la alarma, parámetro, valor
    registrado, umbral configurado, ubicación y fecha/hora del disparo EN
    LA ZONA HORARIA DEL USUARIO (usr.zn_hrr)-.

    Una zona horaria inválida o ausente cae a UTC en vez de reventar: la
    notificación importa más que el detalle de a qué hora local exacta
    llega."""
    momento_local = fecha_hora
    if fecha_hora is not None:
        try:
            zona = ZoneInfo(zona_horaria) if zona_horaria else dt.timezone.utc
        except Exception:
            zona = dt.timezone.utc
        momento_local = fecha_hora.astimezone(zona)

    linea_fecha = f"Fecha y hora: {momento_local:%Y-%m-%d %H:%M:%S %Z}\n" if momento_local else ""
    cuerpo = (
        f'La alarma "{nombre_alarma}" se ha disparado.\n\n'
        f"Parámetro: {nombre_parametro}\n"
        f"Valor registrado: {valor} {unidad}\n"
        f"Umbral configurado: {umbral} {unidad}\n"
        f"Ubicación: {nombre_ubicacion}\n"
        f"{linea_fecha}"
    )
    _enviar(correo, f"Alarma disparada: {nombre_alarma}", cuerpo)
