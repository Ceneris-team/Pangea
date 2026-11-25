"""QA HU32 (PP-435): casos de borde que no cubre la suite de desarrollo.

Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import datetime as dt
import json

import pytest

from app.models import MapeoColumna, MapeoFormato
from tests.routers.test_filtros_avanzados import consultar, regla
from tests.routers.test_filtros_avanzados import series as series
from tests.routers.test_mediciones import client as client
from tests.routers.test_mediciones import (
    crear_conexion,
    crear_dispositivo,
    crear_medicion,
    crear_parametro,
    mapear_parametro,
)
from tests.routers.test_mediciones import escenario_basico as escenario_basico


def valores(resp, parametro):
    assert resp.status_code == 200, resp.text
    return sorted(float(r["vlr"]) for r in resp.json()["items"] if r["id_prmtr"] == parametro.id_prmtr)


# CP-496 · CA-02: decimales, negativos y precisión
@pytest.mark.parametrize(
    "minimo,maximo,modo,esperados",
    [
        ("-5.25", "-5.25", "dentro", [-5.25]),  # borde negativo exacto incluido
        ("-5.2501", "-5.2499", "dentro", [-5.25]),
        ("-0", "0", "dentro", [0]),  # -0 equivale a 0
        ("0.00001", None, "dentro", [5.5, 10, 20]),  # el 0 queda fuera (escenario_basico aporta 10)
        ("+5.5", None, "dentro", [5.5, 10, 20]),
        (".5", "5.5", "dentro", [5.5]),
        ("-5.25", "20", "fuera", []),  # todos dentro -> fuera no devuelve nada
    ],
)
def test_qa_decimales_negativos_y_signos(client, series, minimo, maximo, modo, esperados):
    _, temp, _, _ = series
    resp = consultar(client, [regla(temp, minimo, maximo, modo)], parametro_ids=temp.id_prmtr)
    assert valores(resp, temp) == esperados


# CP-497 · CA-02: valores que el cliente no puede enviar pero la API recibe
@pytest.mark.parametrize("valor", ["1,5", "1 5", "", "   ", "0x10", "١٢"])
def test_qa_rechaza_formatos_no_numericos(client, series, valor):
    _, temp, _, _ = series
    resp = consultar(client, [regla(temp, valor)])
    assert resp.status_code == 422, (valor, resp.status_code, resp.text)


@pytest.mark.parametrize("valor", ["1e400", "-1e400", "9" * 60, "1" + "0" * 5000])
def test_qa_numeros_extremos_no_provocan_error_500(client, series, valor):
    _, temp, _, _ = series
    resp = consultar(client, [regla(temp, valor)], parametro_ids=temp.id_prmtr)
    assert resp.status_code in (200, 422), (resp.status_code, resp.text[:300])


def test_qa_minimo_mayor_por_precision_decimal(client, series):
    """El frontend compara con Number; el backend con Decimal. Aquí difieren."""
    _, temp, _, _ = series
    resp = consultar(client, [regla(temp, "0.30000000000000001", "0.3")])
    assert resp.status_code == 422
    assert "mínimo" in resp.text


# CP-498/499 · CA-03: dos parámetros, una condición por fuera y otra por dentro
def test_qa_fuera_y_dentro_combinados_por_parametro(client, series):
    _, temp, nivel, _ = series
    resp = consultar(client, [regla(temp, "0", "10", "fuera"), regla(nivel, None, "1.5")])
    assert valores(resp, temp) == [-5.25, 20]
    assert valores(resp, nivel) == [0.5, 1.5]
    unidades = {r["id_prmtr"]: r["undd"] for r in resp.json()["items"]}
    assert unidades[temp.id_prmtr] == "°C" and unidades[nivel.id_prmtr] == "m"


# CP-499 · R6: mismo parámetro numérico en un equipo y estado en otro
def test_qa_fuentes_mixtas_solo_admiten_rango_en_equipo_numerico(client, db_session, series):
    e, temp, _, _ = series
    otro = crear_dispositivo(
        db_session, e["ubicacion"], crear_conexion(db_session, e["sede"], "FTP mixto"), "Equipo estado"
    )
    mapear_parametro(db_session, otro, temp, indice=1)
    columna = (
        db_session.query(MapeoColumna)
        .join(MapeoFormato, MapeoFormato.id_mp == MapeoColumna.id_mp)
        .filter(MapeoFormato.id_dspstv == otro.id_dspstv, MapeoColumna.id_prmtr == temp.id_prmtr)
        .one()
    )
    columna.visualizacion = {"significado": "estado", "vista": "escalon", "confirmada": True}
    crear_medicion(db_session, otro, temp, e["sede"], valor=1)
    db_session.flush()
    # Ambos equipos: debe rechazarse (no aplica rango a un estado)
    assert consultar(client, [regla(temp, "0")]).status_code == 422
    # Solo el equipo numérico: debe aceptarse
    resp = consultar(client, [regla(temp, "0")], dispositivo_ids=e["dispositivo"].id_dspstv)
    assert valores(resp, temp) == [0, 5.5, 10, 20]


# CP-501 · CA-04: cursor con dos parámetros y texto, sin pérdidas ni duplicados
def test_qa_cursor_recorre_todas_las_coincidencias_mezcladas(client, db_session, series):
    e, temp, nivel, _ = series
    base = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=20)
    for i in range(25):
        crear_medicion(db_session, e["dispositivo"], temp, e["sede"], valor=i - 3, fecha=base + dt.timedelta(hours=i))
        crear_medicion(db_session, e["dispositivo"], nivel, e["sede"], valor=i / 10, fecha=base + dt.timedelta(hours=i))
    params = {
        "por_pagina": 7,
        "max_puntos": 2,
        "fecha_inicio": (base - dt.timedelta(days=1)).isoformat(),
        "fecha_fin": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    reglas = [regla(temp, "0", "10"), regla(nivel, "1", None, "fuera")]
    directos = consultar(client, reglas, por_pagina=500, fecha_inicio=params["fecha_inicio"], fecha_fin=params["fecha_fin"]).json()
    vistos, paginas = [], 0
    while True:
        data = consultar(client, reglas, **params).json()
        assert data["downsampling"] is False
        vistos.extend(data["items"])
        paginas += 1
        if not data["next_cursor"]:
            break
        params["cursor"] = data["next_cursor"]
    ids = [(r["id_prmtr"], r["id_registro"], r.get("origen")) for r in vistos]
    assert len(ids) == len(set(ids)) == directos["total"]
    assert paginas > 1
    for r in vistos:
        v = r["vlr"]
        if r["id_prmtr"] == temp.id_prmtr:
            assert 0 <= float(v) <= 10
        elif r["id_prmtr"] == nivel.id_prmtr:
            assert float(v) < 1


# CP-504 · seguridad: inyección en el JSON de condiciones
@pytest.mark.parametrize(
    "crudo",
    [
        '[{"parametro_id": "1 OR 1=1", "minimo": "0"}]',
        '[{"parametro_id": 1, "minimo": "0", "extra": "x"}]',
        json.dumps([{"parametro_id": 1, "minimo": "0); DROP TABLE tlmtr;--"}]),
        "[" + ",".join(['{"parametro_id": %d, "minimo": "0"}' % i for i in range(1, 102)]) + "]",
    ],
)
def test_qa_condiciones_maliciosas_responden_422(client, series, crudo):
    resp = client.get("/mediciones", params={"condiciones": crudo})
    assert resp.status_code == 422, resp.text[:300]


def test_qa_parametro_numerico_sin_condicion_conserva_lecturas(client, db_session, series):
    e, temp, nivel, _ = series
    presion = crear_parametro(db_session, "Presión QA", "kPa")
    mapear_parametro(db_session, e["dispositivo"], presion, indice=5)
    for v in (-1, 100):
        crear_medicion(db_session, e["dispositivo"], presion, e["sede"], valor=v)
    resp = consultar(client, [regla(temp, "1000")])
    assert valores(resp, temp) == []
    assert valores(resp, presion) == [-1, 100]
    assert valores(resp, nivel) == [0.5, 1.5, 3]
