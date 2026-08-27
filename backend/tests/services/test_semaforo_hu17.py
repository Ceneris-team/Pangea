"""
HU 17 - Semáforo del mapa (umbrales TEMPORALES, ver
app/services/mapa/semaforo.py).

Estos tests fijan el COMPORTAMIENTO de la evaluación (precedencia del
nivel más grave, operadores, parámetros sin umbral, valores de texto), no
los valores concretos de los umbrales. Cuando HU 28 reemplace
_condiciones_de_parametro() por una consulta a cndcn_alrm, los tests que
usan UMBRALES_TEMPORALES habrá que reapuntarlos a datos de BD, pero los
de evaluar_semaforo() y _cumple_condicion() deberían seguir pasando tal
cual: esa es justamente la señal de que la lógica quedó bien separada de
la fuente de datos.
"""

from decimal import Decimal

from app.services.mapa.semaforo import (
    AMARILLO,
    ROJO,
    VERDE,
    _cumple_condicion,
    evaluar_parametro,
    evaluar_semaforo,
)


class TestCumpleCondicion:
    def test_operadores_soportados(self):
        assert _cumple_condicion(Decimal("5"), ">", Decimal("3")) is True
        assert _cumple_condicion(Decimal("2"), "<", Decimal("3")) is True
        assert _cumple_condicion(Decimal("3"), ">=", Decimal("3")) is True
        assert _cumple_condicion(Decimal("3"), "<=", Decimal("3")) is True
        assert _cumple_condicion(Decimal("3"), "=", Decimal("3")) is True

    def test_operador_desconocido_no_revienta(self):
        """Cuando HU 28 lea de la BD, una fila con oprdr corrupto no debe
        tumbar el mapa entero: devuelve False y sigue."""
        assert _cumple_condicion(Decimal("5"), "!!", Decimal("3")) is False


class TestEvaluarParametro:
    """Usa los parámetros REALES de la instalación (calidad de agua), con
    los nombres tal como están en prmtr: minúscula y guion bajo."""

    def test_valor_normal_es_verde(self):
        assert evaluar_parametro("temperatura", 20) == VERDE

    def test_valor_alto_es_amarillo(self):
        assert evaluar_parametro("temperatura", 30) == AMARILLO

    def test_valor_muy_alto_es_rojo(self):
        assert evaluar_parametro("temperatura", 35) == ROJO

    def test_rojo_gana_a_amarillo_cuando_cumple_ambos(self):
        """35 cumple '>32' (rojo) y '>28' (amarillo). Gana el más grave."""
        assert evaluar_parametro("temperatura", 35) == ROJO

    def test_umbral_por_debajo_tambien_dispara(self):
        """Varios parámetros definen rango por ambos lados (ej. pH)."""
        assert evaluar_parametro("ph", 5) == ROJO
        assert evaluar_parametro("ph", 6.2) == AMARILLO
        assert evaluar_parametro("ph", 7.2) == VERDE

    def test_bateria_baja_dispara_alarma(self):
        """La batería del datalogger es salud del EQUIPO, no del agua:
        por debajo de 11.5 V está por quedarse sin energía."""
        assert evaluar_parametro("bateria_v", 11.0) == ROJO
        assert evaluar_parametro("bateria_v", 12.0) == AMARILLO
        assert evaluar_parametro("bateria_v", 12.6) == VERDE

    def test_nombre_se_normaliza(self):
        """Un mapeo cargado con otra grafía ('Temperatura', 'TEMPERATURA')
        tiene que encontrar los mismos umbrales: si no, la estación
        quedaría en verde sin que nadie note por qué."""
        assert evaluar_parametro("Temperatura", 35) == ROJO
        assert evaluar_parametro("TEMPERATURA", 35) == ROJO
        assert evaluar_parametro("Oxigeno Disuelto", 3) == ROJO

    def test_parametro_sin_umbrales_es_verde(self):
        """"Sin condición de alarma definida" no es lo mismo que "en
        alarma": un parámetro desconocido no puede pintar la estación."""
        assert evaluar_parametro("parametro_inventado", 99999) == VERDE

    def test_valor_none_es_verde(self):
        assert evaluar_parametro("temperatura", None) == VERDE

    def test_valor_de_texto_es_verde(self):
        """Un evento de evnt_txt se muestra en el panel pero no
        semaforiza: no hay forma de compararlo con un umbral numérico."""
        assert evaluar_parametro("mensaje_puerta", "Puerta Abierta") == VERDE

    def test_acepta_decimal_y_str_numerico(self):
        """Los valores llegan como Decimal desde tlmtr (Numeric(14,4))."""
        assert evaluar_parametro("temperatura", Decimal("35.0000")) == ROJO
        assert evaluar_parametro("temperatura", "35") == ROJO


class TestEvaluarSemaforo:
    def test_estacion_sin_datos_es_verde(self):
        assert evaluar_semaforo({}) == VERDE

    def test_gana_el_parametro_mas_grave(self):
        """CA1: una estación con todo bien menos un parámetro en rojo se
        pinta roja - es lo que hace útil el mapa de un vistazo."""
        assert evaluar_semaforo({"temperatura": 20, "ph": 5}) == ROJO

    def test_amarillo_si_ninguno_llega_a_rojo(self):
        assert evaluar_semaforo({"temperatura": 30, "ph": 7.2}) == AMARILLO

    def test_todos_normales_es_verde(self):
        assert evaluar_semaforo({"temperatura": 20, "ph": 7.2}) == VERDE

    def test_texto_no_ensucia_el_color_de_la_estacion(self):
        assert evaluar_semaforo({"temperatura": 20, "mensaje_puerta": "Puerta Abierta"}) == VERDE
