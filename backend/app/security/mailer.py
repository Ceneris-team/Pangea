"""
HU 02 - Gestionar contraseña

Envía el correo con el enlace de restablecimiento. La configuración SMTP se
lee de variables de entorno (ver .env.example); si no está configurada
(entorno local sin servidor de correo), el enlace se registra en el log en
vez de fallar, igual que el fallback de desarrollo de JWT_SECRET en
jwt_auth.py.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("pangea.mailer")

SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM", "no-reply@pangea.local")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")


def enviar_correo_exportacion(correo: str, enlace: str, expira_en) -> None:
    if not SMTP_HOST:
        raise RuntimeError("SMTP no configurado para notificar exportaciones")
    mensaje = EmailMessage()
    mensaje["Subject"] = "Tu exportación está lista - Pangea"
    mensaje["From"] = SMTP_FROM
    mensaje["To"] = correo
    mensaje.set_content(
        "Tu exportación está lista. Inicia sesión en Pangea y abre la empresa y el proyecto donde la solicitaste.\n\n"
        f"{enlace}\n\nDisponible hasta {expira_en.isoformat()}.\n"
        "El acceso a los datos se comprobará de nuevo antes de descargar."
    )
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as servidor:
        servidor.starttls()
        if SMTP_USER and SMTP_PASSWORD:
            servidor.login(SMTP_USER, SMTP_PASSWORD)
        servidor.send_message(mensaje)


def enviar_correo_recuperacion(correo: str, token: str) -> None:
    enlace = f"{FRONTEND_URL}/restablecer-contrasena?token={token}"
    asunto = "Recupera tu contraseña - Pangea"
    cuerpo = (
        "Recibimos una solicitud para restablecer tu contraseña.\n\n"
        f"Ingresa al siguiente enlace para continuar (válido por 30 minutos):\n{enlace}\n\n"
        "Si no solicitaste este cambio, puedes ignorar este correo."
    )

    if not SMTP_HOST:
        logger.info("SMTP no configurado; enlace de recuperación para %s: %s", correo, enlace)
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
