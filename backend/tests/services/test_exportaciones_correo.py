import datetime as dt
from unittest.mock import patch

import pytest

from app.security import mailer


def test_exportacion_sin_smtp_no_se_marca_como_enviada(monkeypatch):
    monkeypatch.setattr(mailer, "SMTP_HOST", "")
    with pytest.raises(RuntimeError, match="SMTP"):
        mailer.enviar_correo_exportacion(
            "usuario@example.com",
            "https://app.example/consulta-datos?exportacion=1",
            dt.datetime.now(dt.timezone.utc),
        )


def test_correo_real_usa_smtp_y_enlace_a_app_sin_adjuntar_datos(monkeypatch):
    monkeypatch.setattr(mailer, "SMTP_HOST", "smtp.example.com")
    with patch.object(mailer.smtplib, "SMTP") as smtp:
        mailer.enviar_correo_exportacion(
            "usuario@example.com",
            "https://app.example/consulta-datos?exportacion=1",
            dt.datetime.now(dt.timezone.utc),
        )
        servidor = smtp.return_value.__enter__.return_value
        servidor.starttls.assert_called_once()
        mensaje = servidor.send_message.call_args.args[0]
        assert mensaje["To"] == "usuario@example.com"
        assert "https://app.example/consulta-datos?exportacion=1" in mensaje.get_content()
        assert not list(mensaje.iter_attachments())
