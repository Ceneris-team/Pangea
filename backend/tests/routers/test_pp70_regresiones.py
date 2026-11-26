"""DEF-23 a DEF-28: reglas de alta, referencias y agrupación temporal."""

import datetime as dt

import pytest

from app.models import ParametroCalculado, ResultadoCalculo, RevisionCalculo, TrabajoCalculo
from tests.routers.test_calculos_completos import calculos as calculos
from tests.routers.test_calculos_completos import crear, drenar, medir
from tests.routers.test_mediciones import crear_parametro, mapear_parametro
from tests.routers.test_parametros_calculados import entorno_calculados as entorno_calculados
from tests.routers.test_parametros_calculados import preparar_origenes


@pytest.mark.parametrize(
    "formula,unidad",
    [
        ("[Nivel de entrada] ** 2", "m^2"),
        ("[Nivel de entrada] % [Nivel de salida]", "m"),
    ],
)
def test_operadores_fuera_del_ticket_no_validan_ni_se_guardan(entorno_calculados, formula, unidad):
    e = entorno_calculados
    preparar_origenes(e)
    body = {"id_sd": e["sedes"][0].id_sd, "frml": formula, "undd": unidad}
    for ruta, datos in [("/validar-formula", body), ("", {**body, "nmbr": "No guardar"})]:
        r = e["client"].post("/parametros-calculados" + ruta, json=datos)
        assert r.status_code == 422
        assert "operaciones +, -, * y /" in r.json()["detail"]
    assert e["db"].query(ParametroCalculado).count() == 0


@pytest.mark.parametrize("estado", ["Inactivo", "Activo"])
def test_estado_inicial_no_es_un_campo_editable_del_alta(entorno_calculados, estado):
    e = entorno_calculados
    preparar_origenes(e)
    body = {
        "id_sd": e["sedes"][0].id_sd,
        "nmbr": "Alta",
        "frml": "[Nivel de entrada] * 2",
        "undd": "m",
    }
    r = e["client"].post("/parametros-calculados", json={**body, "estd": estado})
    assert r.status_code == 422
    assert e["db"].query(ParametroCalculado).count() == 0
    r = e["client"].post("/parametros-calculados", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["estd"] == "Activo"


@pytest.mark.parametrize("nombre", ["Parametro inexistente", "nivel de entrada"])
def test_referencia_no_disponible_se_identifica_en_el_mensaje(entorno_calculados, nombre):
    e = entorno_calculados
    preparar_origenes(e)
    body = {"id_sd": e["sedes"][0].id_sd, "frml": f"[{nombre}] * 2", "undd": "m"}
    for ruta, datos in [("/validar-formula", body), ("", {**body, "nmbr": "No guardar"})]:
        r = e["client"].post("/parametros-calculados" + ruta, json=datos)
        assert r.status_code == 422
        assert f"[{nombre}] no está disponible en el ámbito elegido" in r.json()["detail"]


def test_origen_homonimo_posterior_no_bloquea_y_el_catalogo_los_distingue(calculos):
    e = calculos
    crear(e, "Turbidez calc")
    p = crear_parametro(e["db"], "Turbidez calc", "m")
    mapear_parametro(e["db"], e["dispositivo"], p, indice=4)
    body = {
        "id_sd": e["sedes"][0].id_sd,
        "frml": "[Nivel de entrada] + [Nivel de salida]",
        "undd": "m",
    }
    assert e["client"].post("/parametros-calculados/validar-formula", json=body).status_code == 200
    opciones = (
        e["client"].get("/parametros-calculados/opciones-creacion").json()["sedes"][0]["origenes"]
    )
    nombres = [p["nombre"] for p in opciones]
    assert len(nombres) == len(set(nombres))
    assert {"Turbidez calc (telemetría)", "Turbidez calc (calculado)"} <= set(nombres)
    ambigua = e["client"].post(
        "/parametros-calculados/validar-formula", json={**body, "frml": "[Turbidez calc] * 2"}
    )
    assert ambigua.status_code == 422 and "ambigua" in ambigua.json()["detail"]
    for nombre in ["Turbidez calc (telemetría)", "Turbidez calc (calculado)"]:
        r = e["client"].post(
            "/parametros-calculados/validar-formula", json={**body, "frml": f"[{nombre}] * 2"}
        )
        assert r.status_code == 200, r.text


@pytest.mark.parametrize("desfase", [-30, 30])
def test_historico_agrupa_lecturas_y_cuenta_solo_cuatro_incompletos(calculos, desfase):
    e = calculos
    e["fecha"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0) - dt.timedelta(days=3)
    for i in range(12):
        fecha = e["fecha"] + dt.timedelta(hours=i)
        medir(e, e["nivel"], 10 + i, fecha)
        if i < 8:
            medir(e, e["salida"], 4, fecha + dt.timedelta(seconds=desfase))
    id_ = crear(e)
    drenar(e)
    hijo = crear(e, "Doble balance", "[Balance] * 2")
    drenar(e)
    for definicion in [id_, hijo]:
        q = (
            e["db"]
            .query(ResultadoCalculo)
            .filter_by(id_prm_clc=definicion)
            .filter(ResultadoCalculo.vigente)
        )
        assert q.count() == 12
        assert q.filter_by(estado="Calculado").count() == 8
        assert q.filter_by(estado="Incompleto").count() == 4
    trabajo = e["db"].query(TrabajoCalculo).filter_by(id_prm_clc=id_, inicio=None).one()
    assert trabajo.incidencias == 4
    detalle = e["client"].get(f"/parametros-calculados/{id_}").json()
    assert {r["estado"]: r["cantidad"] for r in detalle["resultados"]} == {
        "Calculado": 8,
        "Incompleto": 4,
    }


def test_dato_tardio_cubre_pendiente_sin_borrar_su_auditoria(calculos):
    e = calculos
    id_ = crear(e)
    hijo = crear(e, "Doble balance", "[Balance] * 2")
    medir(e, e["salida"], 4)
    drenar(e)
    anterior = e["db"].query(ResultadoCalculo).filter_by(id_prm_clc=id_).one()
    medir(e, e["nivel"], 10, e["fecha"] + dt.timedelta(seconds=30))
    drenar(e)
    e["db"].refresh(anterior)
    assert not anterior.vigente
    assert e["db"].query(RevisionCalculo).filter_by(id_resultado=anterior.id_resultado).count() >= 1
    vigentes = (
        e["db"]
        .query(ResultadoCalculo)
        .filter_by(id_prm_clc=id_)
        .filter(ResultadoCalculo.vigente)
        .all()
    )
    assert len(vigentes) == 1 and vigentes[0].vlr == 6
    q_hijo = (
        e["db"].query(ResultadoCalculo).filter_by(id_prm_clc=hijo).filter(ResultadoCalculo.vigente)
    )
    assert q_hijo.count() == 1 and q_hijo.one().vlr == 12


def test_no_agrupa_una_lectura_que_el_resultado_completo_no_utilizo(calculos):
    e = calculos
    medir(e, e["nivel"], 10)
    medir(e, e["nivel"], 20, e["fecha"] + dt.timedelta(seconds=10))
    medir(e, e["salida"], 4, e["fecha"] + dt.timedelta(seconds=30))
    id_ = crear(e)
    drenar(e)
    q = e["db"].query(ResultadoCalculo).filter_by(id_prm_clc=id_).filter(ResultadoCalculo.vigente)
    assert q.count() == 2
    assert q.filter_by(estado="Calculado").one().vlr == 16
