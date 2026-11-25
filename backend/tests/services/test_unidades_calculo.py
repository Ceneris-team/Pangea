import pytest

from app.services.unidades_calculo import evaluar, unidad, validar_unidades


@pytest.mark.parametrize(
    "formula,valores,unidades,salida,esperado",
    [
        ("a+b", {"a": 1, "b": 50}, {"a": "m", "b": "cm"}, "m", 1.5),
        ("a/b", {"a": 1000, "b": 2}, {"a": "mg", "b": "L"}, "g/L", 0.5),
        ("(a+b)/2", {"a": 20, "b": 30}, {"a": "°C", "b": "°C"}, "°C", 25),
        ("(a+b)/2", {"a": 20, "b": 86}, {"a": "°C", "b": "°F"}, "°C", 25),
        ("a-b", {"a": 30, "b": 20}, {"a": "°C", "b": "°C"}, "°C", 10),
        ("a/b", {"a": 5, "b": 10}, {"a": "m", "b": "m"}, "%", 50),
        ("a**2", {"a": 3}, {"a": "cm"}, "cm^2", 9),
        ("a", {"a": 100}, {"a": "uS/cm"}, "S/m", 0.01),
    ],
)
def test_conversion_y_operaciones(formula, valores, unidades, salida, esperado):
    unidades = {v: unidad(u) for v, u in unidades.items()}
    validar_unidades(formula, unidades, salida)
    assert evaluar(formula, valores, unidades, salida) == pytest.approx(esperado)


@pytest.mark.parametrize(
    "formula,unidades,salida",
    [
        ("a+b", {"a": "°C", "b": "%"}, "°C"),
        ("a", {"a": "m"}, "kg"),
        ("a**b", {"a": "m", "b": "1"}, "m"),
        ("a**999999", {"a": "m"}, "m"),
    ],
)
def test_rechaza_dimensiones_y_potencias_no_validas(formula, unidades, salida):
    with pytest.raises(ValueError):
        validar_unidades(formula, {v: unidad(u) for v, u in unidades.items()}, salida)


@pytest.mark.parametrize(
    "texto", ["desconocida", "", "__import__('os')", "m**999999", "True", "m + kg"]
)
def test_rechaza_unidad_desconocida(texto):
    with pytest.raises(ValueError):
        unidad(texto)


def test_division_cero_y_resultado_no_finito():
    with pytest.raises(ValueError, match="cero"):
        evaluar("a/b", {"a": 1, "b": 0}, {"a": unidad("m"), "b": unidad("s")}, "m/s")
    with pytest.raises(ValueError):
        evaluar("a*a", {"a": 1e100}, {"a": unidad("m")}, "m^2")
