import pytest
from pydantic import ValidationError

from app.services.visualizacion import ConfigVisualizacion, resumir_serie, sugerir_visualizacion


@pytest.mark.parametrize(
    "nombre,unidad,valores,esperado",
    [
        ("COUNT", "", [1, 2, 3], "desconocido"),
        ("x", "", [0, 1], "desconocido"),
        ("RECORD", "", [100, 101, 105], "secuencia"),
        ("contador_tramas", "", [], "secuencia"),
        ("ContadorPuerta", "", [], "contador"),
        ("estado_puerta", "", [0, 1], "estado"),
        ("estado_puerta", "", [0, 5], "desconocido"),
        ("temperatura", "°C", [1, 2, 3], "continuo"),
        ("sensor_1", "kPa", [], "continuo"),
    ],
)
def test_sugerencias_no_inventan_eventos(nombre, unidad, valores, esperado):
    config = sugerir_visualizacion(nombre, unidad, valores)
    assert config["significado"] == esperado
    assert not config["confirmada"]


def config(tipo, **kwargs):
    return ConfigVisualizacion(significado=tipo, vista="kpi", **kwargs)


def test_secuencia_cuenta_tramas_no_saltos_y_deduplica():
    resumen = resumir_serie([(1, 100), (2, 101), (2, 101), (3, 105)], None, config("secuencia"))
    assert resumen["valor"] == 3
    assert resumen["saltos_secuencia"] == 3
    assert resumen["duplicados"] == 1
    assert not resumen["parcial"]


def test_secuencia_con_disminucion_sin_regla_marca_saltos_parciales():
    resumen = resumir_serie([(1, 100), (2, 1), (3, 3)], None, config("secuencia"))
    assert resumen["valor"] == 3
    assert resumen["reinicios"] == 1
    assert resumen["parcial"]
    assert resumen["saltos_secuencia"] == 1


def test_contador_usa_referencia_anterior_y_no_la_cuenta_como_lectura():
    r = resumir_serie([(1, 101), (2, 105)], (0, 100), config("contador"))
    assert r["valor"] == 5
    assert r["lecturas"] == 2
    assert not r["parcial"]


@pytest.mark.parametrize(
    "politica,modulo,total,parcial",
    [
        ("desconocido", None, 2, True),
        ("cero", None, 5, False),
        ("modulo", 100, 7, False),
    ],
)
def test_reinicios_explicitos(politica, modulo, total, parcial):
    r = resumir_serie(
        [(1, 3), (2, 5)], (0, 98), config("contador", reinicio=politica, modulo=modulo)
    )
    assert r["valor"] == total
    assert r["parcial"] == parcial
    assert r["reinicios"] == 1


def test_sin_referencia_y_una_lectura_no_inventa_cero():
    r = resumir_serie([(1, 100)], None, config("contador"))
    assert r["valor"] is None
    assert r["parcial"]


def test_estado_cuenta_activaciones_con_referencia():
    r = resumir_serie([(1, 1), (2, 1), (3, 0), (4, 1)], (0, 0), config("estado"))
    assert r["valor"] == 2


def test_vistas_y_modulo_invalidos():
    with pytest.raises(ValidationError):
        ConfigVisualizacion(significado="continuo", vista="barras")
    with pytest.raises(ValidationError):
        config("contador", reinicio="modulo")


def test_sin_datos_y_ultima_medicion():
    assert resumir_serie([], None, config("secuencia"))["valor"] is None
    assert resumir_serie([(1, 50), (2, 10)], None, config("continuo"))["valor"] == 10
