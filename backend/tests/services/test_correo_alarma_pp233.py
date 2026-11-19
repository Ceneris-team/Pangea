"""
HU 30 - Configurar notificaciones (PP-75). PP-233: componer el contenido
del correo de disparo de alarma (CA3).

El aviso dice qué alarma, dónde, qué valor y contra qué condición, en
palabras ("mayor que 30 °C") y sin los ceros de relleno de Numeric(14,4),
con la fecha en la zona horaria del dueño de la alarma (usr.zn_hrr). Las
plantillas siguen aceptando el contexto anterior a PP-233 (avisos que ya
estaban en cola).
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models import NotificacionEnviada
from app.services.correo_ses import renderizar
from app.services.notificaciones import (
    fecha_en_zona,
    formatear_numero,
    simbolo_condicion,
    texto_condicion,
    zona_valida,
)
from tests.services import test_notificaciones_ses as ses

caso = ses.caso
aislar_destinatario_pruebas = ses.aislar_destinatario_pruebas


def cond(oprdr, umbral):
    return SimpleNamespace(oprdr=oprdr, vlr_umbrl=Decimal(str(umbral)))


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (Decimal("35.0000"), "35"),
        (Decimal("7.0010"), "7.001"),
        (Decimal("-0.5000"), "-0.5"),
        (Decimal("0.0000"), "0"),
        (Decimal("-0"), "0"),
        (Decimal("1E+1"), "10"),
        (Decimal("9999999999.9999"), "9999999999.9999"),
        (12.5, "12.5"),
        ("texto", "texto"),
    ],
)
def test_formatear_numero(valor, esperado):
    assert formatear_numero(valor) == esperado


def test_condicion_en_palabras_y_en_simbolo():
    assert texto_condicion([cond(">", "30.0000")], "°C") == "mayor que 30 °C"
    assert texto_condicion([cond("<=", "6.5")], "") == "menor o igual que 6.5"
    assert simbolo_condicion([cond(">=", "12.2500")], "V") == ">= 12.25 V"
    # Alarmas anteriores a PP-74 con dos condiciones.
    assert (
        texto_condicion([cond(">", 30), cond("<", 5)], "°C") == "mayor que 30 °C o menor que 5 °C"
    )


def test_zona_horaria_invalida_cae_a_lima():
    assert zona_valida("America/Lima") == "America/Lima"
    assert zona_valida("Europe/Madrid") == "Europe/Madrid"
    assert zona_valida("Marte/Olympus") == "America/Lima"
    assert zona_valida(None) == "America/Lima"


def test_fecha_en_la_zona_del_usuario():
    fecha = datetime(2026, 11, 19, 20, 40, 12, tzinfo=timezone.utc)
    assert fecha_en_zona(fecha, "America/Lima") == "19/11/2026 15:40:12"
    assert fecha_en_zona(fecha, "Europe/Madrid") == "19/11/2026 21:40:12"


CONTEXTO_NUEVO = {
    "alarma": "Temperatura alta",
    "ubicacion": "Planta Norte",
    "dispositivo": "CR1000",
    "parametro": "Temperatura",
    "unidad": "°C",
    "valor": "35",
    "fecha": "2026-11-19T20:40:12+00:00",
    "fecha_local": "19/11/2026 15:40:12",
    "zona_horaria": "America/Lima",
    "condicion": "> 30 °C",
    "condicion_texto": "mayor que 30 °C",
}


def test_correo_con_el_contenido_completo():
    asunto, texto, html = renderizar("alarma_activada", CONTEXTO_NUEVO)
    assert asunto == "Alarma activada: Temperatura alta · Planta Norte"
    for fragmento in (
        "Temperatura registró 35 °C y la alarma se activa cuando es mayor que 30 °C.",
        "Ubicación: Planta Norte",
        "Dispositivo: CR1000",
        "Valor medido: 35 °C",
        "Condición: mayor que 30 °C (> 30 °C)",
        "Fecha de lectura: 19/11/2026 15:40:12 (America/Lima)",
        "Configurar notificaciones",
    ):
        assert fragmento in texto, fragmento
    assert "mayor que 30 °C" in html and "19/11/2026 15:40:12 (America/Lima)" in html
    assert "30.0000" not in texto + html


def test_contexto_anterior_a_pp233_sigue_renderizando():
    """Un aviso que quedó en cola con el contexto viejo no debe romper."""
    viejo = {
        k: v
        for k, v in CONTEXTO_NUEVO.items()
        if k not in ("fecha_local", "zona_horaria", "condicion_texto")
    }
    viejo["condicion"] = "> 30.0000"
    asunto, texto, _ = renderizar("alarma_activada", viejo)
    assert asunto.startswith("Alarma activada: Temperatura alta")
    assert "Fecha de lectura: 2026-11-19T20:40:12+00:00 (UTC)" in texto
    assert "Condición: > 30.0000" in texto


def test_nombres_con_html_o_saltos_no_rompen_el_correo():
    peligroso = {**CONTEXTO_NUEVO, "alarma": "<script>alert(1)</script>\nX", "ubicacion": "A\r\nB"}
    asunto, _, html = renderizar("alarma_activada", peligroso)
    assert "\n" not in asunto and "\r" not in asunto
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_el_aviso_real_lleva_la_zona_horaria_del_dueno(db_session, caso):
    """De punta a punta: evaluar una lectura y renderizar el aviso creado."""
    caso["usuario"].zn_hrr = "Europe/Madrid"
    db_session.flush()
    fecha = datetime(2026, 11, 19, 20, 40, 12, tzinfo=timezone.utc)
    caso["fecha"] = fecha
    ses.evaluar(db_session, caso, [Decimal("35.5000")])
    aviso = db_session.query(NotificacionEnviada).filter_by(tipo="alarma_activada").first()
    ctx = aviso.contexto
    assert ctx["valor"] == "35.5"
    assert ctx["condicion"] == "> 30 °C" and ctx["condicion_texto"] == "mayor que 30 °C"
    assert ctx["zona_horaria"] == "Europe/Madrid"
    assert ctx["fecha_local"] == "19/11/2026 21:40:12"
    _, texto, _ = renderizar("alarma_activada", ctx)
    assert "registró 35.5 °C y la alarma se activa cuando es mayor que 30 °C" in texto
    assert "19/11/2026 21:40:12 (Europe/Madrid)" in texto
