"""
HU 17 - Semáforo del mapa con las condiciones reales de las alarmas
(HU 29, PP-74 / PP-230; ver app/services/mapa/semaforo.py).

ROJO   alguna alarma activa cumple su condición con el último valor.
AMARILLO  preaviso: sin cumplirla, a 10 % o menos del umbral, del lado en
          que se dispararía.
VERDE  el resto (incluido "sin alarma configurada" y valores de texto).

Antes de PP-74 estos tests fijaban umbrales TEMPORALES en memoria; la
lógica (precedencia del más grave, operadores, texto, sin datos) se
conserva y ahora se alimenta de condiciones (operador, umbral).
"""

from decimal import Decimal

import pytest

from app.models import Alarma, CondicionAlarma
from app.services.mapa.semaforo import (
    AMARILLO,
    ROJO,
    VERDE,
    _cumple_condicion,
    _en_preaviso,
    condiciones_por_ubicacion,
    evaluar_parametro,
    evaluar_semaforo,
)

D = Decimal


class TestCumpleCondicion:
    def test_operadores_soportados(self):
        assert _cumple_condicion(D("5"), ">", D("3")) is True
        assert _cumple_condicion(D("2"), "<", D("3")) is True
        assert _cumple_condicion(D("3"), ">=", D("3")) is True
        assert _cumple_condicion(D("3"), "<=", D("3")) is True
        assert _cumple_condicion(D("3"), "=", D("3")) is True
        assert _cumple_condicion(D("3"), ">", D("3")) is False
        assert _cumple_condicion(D("3"), "<", D("3")) is False

    def test_operador_desconocido_no_revienta(self):
        assert _cumple_condicion(D("3"), "!=", D("4")) is False


class TestPreaviso:
    @pytest.mark.parametrize(
        "valor, operador, umbral, esperado",
        [
            # ">" 32 -> margen 3.2: [28.8, 32] es preaviso; 32 ya no cumple ">".
            ("28.8", ">", "32", True),
            ("28.79", ">", "32", False),
            ("32", ">", "32", True),
            ("32.01", ">", "32", False),  # ya cumple: es rojo, no preaviso
            # ">=" 32: 32 ya cumple.
            ("31.9", ">=", "32", True),
            ("32", ">=", "32", False),
            # "<" 6.5 -> margen 0.65: [6.5, 7.15].
            ("7.15", "<", "6.5", True),
            ("7.16", "<", "6.5", False),
            ("6.5", "<", "6.5", True),
            ("6.4", "<", "6.5", False),  # ya cumple
            ("6.6", "<=", "6.5", True),
            # Umbral negativo: el margen es el 10 % del valor absoluto.
            ("-9.5", ">", "-10", False),  # ya cumple (-9.5 > -10)
            ("-10.5", ">", "-10", True),
            # Sin preaviso para "=" ni para umbral 0.
            ("3.1", "=", "3", False),
            ("-0.1", ">", "0", False),
        ],
    )
    def test_bordes(self, valor, operador, umbral, esperado):
        assert _en_preaviso(D(valor), operador, D(umbral)) is esperado


class TestEvaluarParametro:
    MAYOR_32 = [(">", D("32"))]

    def test_cumple_es_rojo(self):
        assert evaluar_parametro(self.MAYOR_32, 35) == ROJO

    def test_cerca_es_amarillo(self):
        assert evaluar_parametro(self.MAYOR_32, 30) == AMARILLO

    def test_lejos_es_verde(self):
        assert evaluar_parametro(self.MAYOR_32, 20) == VERDE

    def test_sin_condiciones_es_verde_aunque_el_valor_sea_alto(self):
        assert evaluar_parametro([], 99999) == VERDE

    def test_rojo_gana_a_amarillo_entre_varias_alarmas(self):
        """Dos alarmas sobre el mismo parámetro: una se cumple y la otra
        está en preaviso -gana la más grave-."""
        assert evaluar_parametro([(">", D("40")), (">", D("32"))], 35) == ROJO

    def test_umbral_por_debajo_tambien_dispara(self):
        menor = [("<", D("6.5"))]
        assert evaluar_parametro(menor, 5) == ROJO
        assert evaluar_parametro(menor, 6.8) == AMARILLO
        assert evaluar_parametro(menor, 8) == VERDE

    def test_valor_none_o_texto_es_verde(self):
        assert evaluar_parametro(self.MAYOR_32, None) == VERDE
        assert evaluar_parametro(self.MAYOR_32, "Puerta Abierta") == VERDE
        assert evaluar_parametro(self.MAYOR_32, True) == VERDE

    def test_acepta_decimal_y_str_numerico(self):
        assert evaluar_parametro(self.MAYOR_32, D("35.0000")) == ROJO
        assert evaluar_parametro(self.MAYOR_32, "35") == ROJO


class TestEvaluarSemaforo:
    CONDICIONES = {1: [(">", D("32"))], 2: [("<", D("6.5"))]}

    def test_estacion_sin_datos_es_verde(self):
        assert evaluar_semaforo({}, self.CONDICIONES) == VERDE
        assert evaluar_semaforo({1: 50}) == VERDE  # sin condiciones

    def test_gana_el_parametro_mas_grave(self):
        assert evaluar_semaforo({1: 20, 2: 5}, self.CONDICIONES) == ROJO

    def test_amarillo_si_ninguno_llega_a_rojo(self):
        assert evaluar_semaforo({1: 31, 2: 8}, self.CONDICIONES) == AMARILLO

    def test_todos_normales_es_verde(self):
        assert evaluar_semaforo({1: 20, 2: 8}, self.CONDICIONES) == VERDE

    def test_parametro_sin_alarma_no_pinta(self):
        assert evaluar_semaforo({1: 20, 3: 99999}, self.CONDICIONES) == VERDE

    def test_texto_no_ensucia_el_color_de_la_estacion(self):
        assert evaluar_semaforo({1: 20, 4: "Puerta Abierta"}, self.CONDICIONES) == VERDE


class TestCondicionesPorUbicacion:
    """Contra la Postgres de test: solo alarmas ACTIVAS, agrupadas por
    ubicación y parámetro."""

    def test_agrupa_y_excluye_las_pausadas(self, db_session, fabrica):
        from tests.routers.test_alarmas import crear_parametro, crear_ubicacion

        sede = fabrica.sede()
        usuario = fabrica.usuario()
        u1 = crear_ubicacion(db_session, sede, "Estación semáforo 1")
        u2 = crear_ubicacion(db_session, sede, "Estación semáforo 2")
        p = crear_parametro(db_session, "Temperatura semáforo PP230", "°C")

        def alarma(ubicacion, estado, *condiciones):
            a = Alarma(
                id_usr=usuario.id_usr,
                id_sd=sede.id_sd,
                nmbr=f"A {estado} {ubicacion.id_ubccn}",
                id_prmtr=p.id_prmtr,
                id_ubccn=ubicacion.id_ubccn,
                estd=estado,
            )
            db_session.add(a)
            db_session.flush()
            for op, umbral in condiciones:
                db_session.add(CondicionAlarma(id_alrm=a.id_alrm, oprdr=op, vlr_umbrl=umbral))
            db_session.flush()

        alarma(u1, "Activa", (">", 30))
        alarma(u1, "Activa", ("<", 2))
        alarma(u1, "Inactiva", (">", 10))
        alarma(u2, "Activa", (">=", 5.5))

        resultado = condiciones_por_ubicacion(db_session, [u1.id_ubccn, u2.id_ubccn])
        assert resultado[u1.id_ubccn][p.id_prmtr] == [(">", D("30")), ("<", D("2"))]
        assert resultado[u2.id_ubccn][p.id_prmtr] == [(">=", D("5.5"))]
        assert condiciones_por_ubicacion(db_session, []) == {}

        # Y el color de la estación 1 con un valor en preaviso de > 30.
        assert evaluar_semaforo({p.id_prmtr: 28}, resultado[u1.id_ubccn]) == AMARILLO
        # La pausada (> 10) no la pinta de rojo.
        assert evaluar_semaforo({p.id_prmtr: 20}, resultado[u1.id_ubccn]) == VERDE
