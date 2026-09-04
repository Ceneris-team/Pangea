"""
Tests unitarios de validador.py (PP-99), sin base de datos.

Cubre en particular tipos_parametro: antes de esto TODO parámetro se
validaba como número (float()), así que una columna de texto real (ej.
"MensajeP"/"MensajeA" de la trama P: "Puerta Abierta") perdía cada fila en
silencio. Ver también app/services/ingesta/mapeo.py (tipos_de_parametro)
y app/services/ingesta/persistencia.py (enruta a tlmtr o evnt_txt según
el tipo del valor ya validado).
"""

import datetime as dt

from app.services.ingesta.estandarizador import LecturaEstandar
from app.services.ingesta.validador import es_valor_numerico, validar_lecturas

AHORA = dt.datetime(2026, 8, 21, tzinfo=dt.timezone.utc)


def _lectura(parametro: str, valor_crudo, fecha_hora=None) -> LecturaEstandar:
    return LecturaEstandar(
        fecha_hora=fecha_hora or (AHORA - dt.timedelta(hours=1)),
        id_cnxn=1,
        parametro=parametro,
        valor_crudo=valor_crudo,
        numero_fila=1,
    )


def test_parametro_numerico_sin_tipos_parametro_se_comporta_como_antes():
    """Sin tipos_parametro (default), todo se valida como número -
    comportamiento previo a agregar tipo_dato, no debe cambiar."""
    resultado = validar_lecturas([_lectura("temperatura", "23.5")], ahora=AHORA)
    assert len(resultado.validas) == 1
    assert resultado.validas[0].valor == 23.5


def test_parametro_de_texto_no_se_pierde_por_no_ser_numerico():
    resultado = validar_lecturas(
        [_lectura("mensaje_puerta", "Puerta Abierta")],
        ahora=AHORA,
        tipos_parametro={"mensaje_puerta": "texto"},
    )
    assert len(resultado.errores) == 0
    assert len(resultado.validas) == 1
    assert resultado.validas[0].valor == "Puerta Abierta"
    assert isinstance(resultado.validas[0].valor, str)


def test_parametro_de_texto_recorta_espacios():
    resultado = validar_lecturas(
        [_lectura("mensaje_puerta", "  Llave No Encontrada  ")],
        ahora=AHORA,
        tipos_parametro={"mensaje_puerta": "texto"},
    )
    assert resultado.validas[0].valor == "Llave No Encontrada"


def test_parametro_de_texto_vacio_se_omite_como_los_numericos_vacios():
    resultado = validar_lecturas(
        [_lectura("mensaje_puerta", "")],
        ahora=AHORA,
        tipos_parametro={"mensaje_puerta": "texto"},
    )
    assert len(resultado.errores) == 0
    assert len(resultado.validas) == 1
    assert resultado.validas[0].valor is None


def test_una_trama_mixta_numerico_y_texto_en_la_misma_fila():
    """Caso real de la trama P: R (numérico) y MensajeP/MensajeA (texto)
    en el mismo archivo, cada columna con su propio tipo."""
    fecha = AHORA - dt.timedelta(hours=1)
    lecturas = [
        _lectura("contador_r", "875", fecha),
        _lectura("mensaje_puerta", "Puerta Abierta", fecha),
        _lectura("mensaje_alarma", "Llave No Encontrada", fecha),
    ]
    resultado = validar_lecturas(
        lecturas,
        ahora=AHORA,
        tipos_parametro={"mensaje_puerta": "texto", "mensaje_alarma": "texto"},
    )
    assert len(resultado.errores) == 0
    valores = {v.parametro: v.valor for v in resultado.validas}
    assert valores["contador_r"] == 875.0
    assert isinstance(valores["contador_r"], float)
    assert valores["mensaje_puerta"] == "Puerta Abierta"
    assert valores["mensaje_alarma"] == "Llave No Encontrada"


def test_parametro_no_listado_en_tipos_parametro_se_asume_numerico():
    """Un parámetro que no está en el mapa (ej. porque el mapeo no cargó
    tipos para él) cae al comportamiento por defecto: numérico."""
    resultado = validar_lecturas(
        [_lectura("otro_parametro", "no es numero")],
        ahora=AHORA,
        tipos_parametro={"mensaje_puerta": "texto"},
    )
    assert len(resultado.validas) == 0
    assert len(resultado.errores) == 1
    assert "no es numérico" in resultado.errores[0].motivo


class TestEsValorNumerico:
    """Usada por routers/mapeos.py (vista previa) para avisar ANTES de
    guardar si un parámetro numérico no calza con la columna real -mismo
    criterio que usa la ingesta, para que la vista previa no diga 'está
    bien' y la ingesta sí pierda la fila."""

    def test_numero_entero(self):
        assert es_valor_numerico("875") is True

    def test_numero_decimal(self):
        assert es_valor_numerico("23.5") is True

    def test_texto_no_numerico(self):
        assert es_valor_numerico("Puerta Abierta") is False

    def test_vacio_se_considera_numerico(self):
        """Vacío es válido (queda como None, "sin dato"), no un error de
        tipo -mismo criterio que _parsear_numero."""
        assert es_valor_numerico("") is True
        assert es_valor_numerico(None) is True

    def test_decimal_con_coma_segun_delimitador(self):
        assert es_valor_numerico("23,5", delimitador_decimal=",") is True
        assert es_valor_numerico("23,5", delimitador_decimal=".") is False
