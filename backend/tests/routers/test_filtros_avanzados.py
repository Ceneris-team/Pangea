"""HU32: límites por parámetro, fuentes independientes y exportación consistente."""

import csv
import datetime as dt
import io
import json

import pytest
from openpyxl import load_workbook

from app.models import Parametro
from app.tasks import exportaciones as tareas
from tests.routers.test_entorno_operativo import autenticar
from tests.routers.test_entorno_operativo import entorno as entorno
from tests.routers.test_exportaciones import AlmacenFalso, solicitar
from tests.routers.test_exportaciones import entorno_exportacion as entorno_exportacion
from tests.routers.test_mediciones import client as client
from tests.routers.test_mediciones import (
    crear_conexion,
    crear_dispositivo,
    crear_evento_texto,
    crear_medicion,
    crear_parametro,
    crear_ubicacion,
    mapear_parametro,
)
from tests.routers.test_mediciones import escenario_basico as escenario_basico


def consultar(client, condiciones, **params):
    return client.get("/mediciones", params={"condiciones": json.dumps(condiciones), **params})


def regla(parametro, minimo=None, maximo=None, modo="dentro"):
    return {"parametro_id": parametro.id_prmtr, "minimo": minimo, "maximo": maximo, "modo": modo}


@pytest.fixture()
def series(db_session, escenario_basico):
    e = escenario_basico
    temperatura = e["parametro"]
    for valor in (-5.25, 0, 5.5, 20):
        crear_medicion(db_session, e["dispositivo"], temperatura, e["sede"], valor=valor)
    nivel = crear_parametro(db_session, "Nivel HU32", "m")
    mapear_parametro(db_session, e["dispositivo"], nivel, indice=2)
    for valor in (0.5, 1.5, 3):
        crear_medicion(db_session, e["dispositivo"], nivel, e["sede"], valor=valor)
    texto = crear_parametro(db_session, "Mensaje HU32", tipo_dato="texto")
    mapear_parametro(db_session, e["dispositivo"], texto, indice=3)
    crear_evento_texto(db_session, e["dispositivo"], texto, e["sede"])
    return e, temperatura, nivel, texto


def test_condiciones_independientes_con_unidades_distintas_y_texto_sin_condicion(client, series):
    _, temp, nivel, _ = series
    resp = consultar(client, [regla(temp, "-5.25", "5.50"), regla(nivel, "1", "2")])
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert sorted(r["vlr"] for r in items if r["id_prmtr"] == temp.id_prmtr) == [-5.25, 0, 5.5]
    assert [r["vlr"] for r in items if r["id_prmtr"] == nivel.id_prmtr] == [1.5]
    assert any(r["vlr"] == "Puerta Abierta" for r in items)
    assert {r["undd"] for r in items if r["id_prmtr"] == temp.id_prmtr} == {"°C"}


@pytest.mark.parametrize(
    "minimo,maximo,modo,esperados",
    [
        ("0", "10", "dentro", [0, 5.5, 10]),
        ("0", "10", "fuera", [-5.25, 20]),
        ("0", None, "fuera", [-5.25]),
        (None, "0", "dentro", [-5.25, 0]),
        (None, "10", "fuera", [20]),
        ("0", "0", "dentro", [0]),
        ("0", "0", "fuera", [-5.25, 5.5, 10, 20]),
    ],
)
def test_bordes_cero_y_extremos_abiertos(client, series, minimo, maximo, modo, esperados):
    _, temp, _, _ = series
    resp = consultar(client, [regla(temp, minimo, maximo, modo)], parametro_ids=temp.id_prmtr)
    assert resp.status_code == 200, resp.text
    assert sorted(r["vlr"] for r in resp.json()["items"]) == esperados


def test_pagina_todas_las_coincidencias_sin_muestrear_rango_amplio(client, series):
    _, temp, _, _ = series
    params = {
        "parametro_ids": temp.id_prmtr,
        "por_pagina": 2,
        "max_puntos": 1,
        "fecha_inicio": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=60)).isoformat(),
        "fecha_fin": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    reglas = [regla(temp, "-10", "30")]
    items = []
    while True:
        resp = consultar(client, reglas, **params)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["downsampling"] is False and data["total"] == 5
        items.extend(data["items"])
        if not data["next_cursor"]:
            break
        params["cursor"] = data["next_cursor"]
    assert len(items) == len({r["id_registro"] for r in items}) == 5


def test_filtros_intersectan_fecha_equipo_proyecto_y_parametro(client, db_session, series):
    e, temp, _, _ = series
    otra = crear_ubicacion(db_session, e["sede"], "Otro proyecto HU32")
    ajeno = crear_dispositivo(
        db_session, otra, crear_conexion(db_session, e["sede"], "Otro FTP"), "Otro equipo"
    )
    crear_medicion(db_session, ajeno, temp, e["sede"], valor=2)
    antiguo = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
    crear_medicion(db_session, e["dispositivo"], temp, e["sede"], valor=2, fecha=antiguo)
    resp = consultar(
        client,
        [regla(temp, "0", "10")],
        parametro_ids=temp.id_prmtr,
        dispositivo_ids=e["dispositivo"].id_dspstv,
        ubicacion_ids=e["ubicacion"].id_ubccn,
        fecha_inicio=(antiguo + dt.timedelta(hours=1)).isoformat(),
    )
    assert resp.status_code == 200
    assert sorted(r["vlr"] for r in resp.json()["items"]) == [0, 5.5, 10]
    assert all(r["id_dspstv"] == e["dispositivo"].id_dspstv for r in resp.json()["items"])


@pytest.mark.parametrize(
    "cambio",
    [
        {"minimo": "abc"},
        {"minimo": "NaN"},
        {"maximo": "Infinity"},
        {"minimo": "20", "maximo": "1"},
        {"minimo": None, "maximo": None},
        {"modo": "desconocido"},
        {"parametro_id": -1},
    ],
)
def test_rechaza_configuracion_invalida(client, series, cambio):
    _, temp, _, _ = series
    assert consultar(client, [{**regla(temp, "0", "10"), **cambio}]).status_code == 422


def test_rechaza_duplicados_json_roto_y_muestreo(client, series):
    _, temp, _, _ = series
    r = regla(temp, "0")
    assert consultar(client, [r, r]).status_code == 422
    assert client.get("/mediciones", params={"condiciones": "{"}).status_code == 422
    assert consultar(client, [r], frecuencia_muestreo=15).status_code == 422
    assert consultar(client, [r], valor_min=0).status_code == 422


def test_rechaza_texto_estado_y_parametros_fuera_de_contexto(client, db_session, series):
    e, temp, _, texto = series
    assert consultar(client, [regla(texto, "0")]).status_code == 422
    estado = crear_parametro(db_session, "Estado HU32")
    estado.tipo_visualizacion = "estado"
    mapear_parametro(db_session, e["dispositivo"], estado, indice=4)
    db_session.flush()
    assert consultar(client, [regla(estado, "0")]).status_code == 422
    assert consultar(client, [regla(temp, "0")], dispositivo_ids=-1).status_code == 422
    assert consultar(client, [regla(temp, "0")], parametro_ids=texto.id_prmtr).status_code == 422
    assert consultar(client, [{**regla(temp, "0"), "parametro_id": 99999999}]).status_code == 422


def test_catalogo_refleja_fuente_y_estado_por_columna(client, db_session, series):
    e, temp, _, _ = series
    from app.models import MapeoColumna

    columna = db_session.query(MapeoColumna).filter_by(id_prmtr=temp.id_prmtr).one()
    columna.visualizacion = {"significado": "estado", "vista": "escalon", "confirmada": True}
    db_session.flush()
    items = client.get("/mediciones/parametros").json()["items"]
    dato = next(p for p in items if p["id_prmtr"] == temp.id_prmtr)
    assert dato["fuentes"] == [
        {
            "dispositivo_id": e["dispositivo"].id_dspstv,
            "ubicacion_id": e["ubicacion"].id_ubccn,
            "admite_rango": False,
        }
    ]
    assert consultar(client, [regla(temp, "0")]).status_code == 422


def test_sin_coincidencias_y_limpieza_conservando_contexto(client, series):
    e, temp, _, _ = series
    params = {"parametro_ids": temp.id_prmtr, "dispositivo_ids": e["dispositivo"].id_dspstv}
    assert consultar(client, [regla(temp, "100")], **params).json()["total"] == 0
    assert consultar(client, [], **params).json()["total"] == 5


@pytest.mark.parametrize("rol", ["Lector", "Técnico CENERIS"])
@pytest.mark.parametrize("proyecto_activo", [False, True])
def test_sesion_real_no_filtra_datos_de_otras_empresas_o_proyectos(entorno, rol, proyecto_activo):
    client, _, empresas, recursos, cuentas, parametro = entorno
    autenticar(client, cuentas[rol])
    client.headers["X-Cliente-Id"] = str(empresas[0].id_clnt)
    if proyecto_activo:
        client.headers["X-Proyecto-Id"] = str(recursos[0][0].id_ubccn)
    resp = consultar(client, [regla(parametro, "0", "100")])
    assert resp.status_code == 200, resp.text
    esperados = (
        {recursos[0][0].id_ubccn}
        if rol == "Lector" or proyecto_activo
        else {r[0].id_ubccn for r in recursos[:2]}
    )
    assert {r["id_ubccn"] for r in resp.json()["items"]} == esperados
    catalogo = client.get("/mediciones/parametros").json()["items"]
    assert {f["ubicacion_id"] for p in catalogo for f in p["fuentes"]} == esperados


@pytest.mark.parametrize("formato", ["csv", "xlsx"])
@pytest.mark.parametrize("modo", ["dentro", "fuera"])
def test_exportacion_reproduce_condiciones_de_consulta(entorno_exportacion, formato, modo):
    client, db, _, _, proyectos, equipos, body = entorno_exportacion
    parametro = db.query(Parametro).filter(Parametro.tipo_dato == "numerico").one()
    mapear_parametro(db, equipos[0], parametro)
    condiciones = [regla(parametro, "0", "1", modo)]
    consulta = consultar(
        client,
        condiciones,
        ubicacion_ids=proyectos[0].id_ubccn,
        fecha_inicio=body["fecha_inicio"],
        fecha_fin=body["fecha_fin"],
    ).json()
    exportacion = solicitar(entorno_exportacion, condiciones=condiciones, formato=formato)
    result = tareas.generar_exportacion(exportacion.id_exprtcn)
    assert result == {"estado": "Lista", "filas": consulta["total"]}
    datos = AlmacenFalso.objetos[exportacion.objeto_clave]
    if formato == "csv":
        filas = list(csv.reader(io.StringIO(datos.decode("utf-8-sig"))))[1:]
    else:
        filas = list(load_workbook(io.BytesIO(datos), read_only=True).active.values)[1:]
    valores = sorted(float(r[-2]) for r in filas if r[-1] == "numerico")
    assert valores == sorted(
        r["vlr"] for r in consulta["items"] if isinstance(r["vlr"], (float, int))
    )
