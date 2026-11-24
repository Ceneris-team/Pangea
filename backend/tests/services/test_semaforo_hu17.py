"""Semáforo sin valores ambientales prefijados: solo reglas del proyecto."""

from decimal import Decimal

import pytest

from app.services.mapa.semaforo import evaluar_parametro, evaluar_semaforo
from app.services.notificaciones import cumple_condicion


@pytest.mark.parametrize(
    "operador,valor,umbral,esperado",
    [
        (">", 5, 3, True),
        ("<", 2, 3, True),
        (">=", 3, 3, True),
        ("<=", 3, 3, True),
        ("=", 3, 3, True),
        (">", 3, 3, False),
    ],
)
def test_misma_comparacion_que_el_evaluador_de_alarmas(operador, valor, umbral, esperado):
    reglas = {"p": [(operador, Decimal(str(umbral)))]}
    assert cumple_condicion(valor, operador, umbral) is esperado
    assert evaluar_parametro("p", valor, reglas) == ("rojo" if esperado else "verde")


def test_sin_reglas_no_se_presenta_como_normal():
    assert evaluar_semaforo({"temperatura": 25}) == "sin_reglas"


def test_umbral_editado_cambia_el_resultado():
    assert evaluar_parametro("temperatura", 25, {"temperatura": [(">", 20)]}) == "rojo"
    assert evaluar_parametro("temperatura", 25, {"temperatura": [(">", 30)]}) == "verde"


def test_cualquier_condicion_cumplida_activa_el_marcador():
    reglas = {"temperatura": [("<", 5), (">", 20)], "ph": [("<", 6)]}
    assert evaluar_semaforo({"temperatura": 10, "ph": 5}, reglas) == "rojo"


@pytest.mark.parametrize("valor", [None, "texto", "NaN", "Infinity"])
def test_valor_invalido_no_se_presenta_como_normal(valor):
    assert evaluar_parametro("temperatura", valor, {"temperatura": [(">", 20)]}) == "sin_datos"
