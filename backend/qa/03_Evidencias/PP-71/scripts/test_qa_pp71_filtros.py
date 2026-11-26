"""QA PP-71 (PP-437): filtrar parámetros calculados por nombre y estado.

Casos que no cubre la suite de desarrollo (tests/routers/test_parametros_calculados.py).
Se copia a backend/tests/routers/ del worktree de dev para reutilizar sus fixtures.
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import pytest

from app.models import ParametroCalculado
from tests.routers.test_parametros_calculados import definir
from tests.routers.test_parametros_calculados import entorno_calculados as entorno_calculados  # noqa: F401

URL = "/parametros-calculados"


def nombres(resp):
    assert resp.status_code == 200, resp.text
    return [p["nmbr"] for p in resp.json()["items"]]


# CP-515 · CA-01: el listado entrega nombre, unidad, descripción y estado del contexto
def test_cp515_listado_identifica_nombre_unidad_descripcion_estado(entorno_calculados):
    e = entorno_calculados
    definir(e["db"], e["sedes"][0], "Caudal neto", "Activo", "m3/s")
    item = e["client"].get(URL).json()["items"][0]
    assert {"nmbr", "undd", "dscrpcn", "estd"} <= item.keys()
    assert (item["nmbr"], item["undd"], item["estd"]) == ("Caudal neto", "m3/s", "Activo")
    assert item["dscrpcn"] == "Diferencia entre mediciones"


# CP-516 · CA-01: aislamiento entre empresas en listado, filtros y detalle
def test_cp516_aislamiento_listado_filtros_y_detalle(entorno_calculados):
    e = entorno_calculados
    propio = definir(e["db"], e["sedes"][0], "Índice QA propio")
    ajeno = definir(e["db"], e["sedes"][2], "Índice QA ajeno", "Inactivo")
    c = e["client"]
    for params in [{}, {"q": "índice qa"}, {"estado": "Inactivo"}, {"q": "ajeno", "estado": "Inactivo"}]:
        assert "Índice QA ajeno" not in nombres(c.get(URL, params=params))
    assert c.get(f"{URL}/{propio.id_prm_clc}").status_code == 200
    # Detalle de una definición de otra empresa desde el contexto de la empresa 0
    assert c.get(f"{URL}/{ajeno.id_prm_clc}").status_code == 404
    # Detalle de otra sede de la misma empresa estando en el proyecto de la sede 0
    otra_sede = definir(e["db"], e["sedes"][1], "Índice QA sede 2")
    c.headers["X-Proyecto-Id"] = str(e["proyectos"][0].id_ubccn)
    assert "Índice QA sede 2" not in nombres(c.get(URL))
    assert c.get(f"{URL}/{otra_sede.id_prm_clc}").status_code == 404


# CP-517 · CA-02: parcial, insensible a mayúsculas y recorta espacios
@pytest.mark.parametrize("q", ["presión", "PRESIÓN", "  PrEsIóN  ", "ión dif", "\tpresión\n"])
def test_cp517_busqueda_parcial_insensible(entorno_calculados, q):
    e = entorno_calculados
    definir(e["db"], e["sedes"][0], "Presión diferencial")
    definir(e["db"], e["sedes"][0], "Temperatura media")
    assert nombres(e["client"].get(URL, params={"q": q})) == ["Presión diferencial"]


# CP-518 · CA-02: entradas límite de la búsqueda
@pytest.mark.parametrize(
    "q,esperado",
    [("", 3), ("   ", 3), ("\\", 1), ("_", 1), ("%", 1), ("x" * 200, 0)],
)
def test_cp518_busqueda_literal_y_limites(entorno_calculados, q, esperado):
    e = entorno_calculados
    for n in ["Ruta C:\\datos", "Factor_k", "Humedad 90%"]:
        definir(e["db"], e["sedes"][0], n)
    resp = e["client"].get(URL, params={"q": q})
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == esperado


def test_cp518_busqueda_demasiado_larga_422(entorno_calculados):
    assert entorno_calculados["client"].get(URL, params={"q": "x" * 201}).status_code == 422


def test_cp518_byte_nul_no_provoca_500(entorno_calculados):
    resp = entorno_calculados["client"].get(URL, params={"q": "pres\x00ion"})
    assert resp.status_code in (200, 422), resp.status_code


# CP-519 · CA-03: Activo / Inactivo / Todos (sin parámetro)
def test_cp519_filtro_estado(entorno_calculados):
    e = entorno_calculados
    for n, s in [("A1", "Activo"), ("A2", "Activo"), ("I1", "Inactivo")]:
        definir(e["db"], e["sedes"][0], f"QA {n}", s)
    c = e["client"]
    assert sorted(nombres(c.get(URL, params={"estado": "Activo"}))) == ["QA A1", "QA A2"]
    assert nombres(c.get(URL, params={"estado": "Inactivo"})) == ["QA I1"]
    assert c.get(URL).json()["total"] == 3
    assert c.get(URL, params={"estado": "activo"}).status_code == 422


# CP-519 · Conv.: sin resultados calculados el estado sigue siendo el de la definición
def test_cp519_estado_no_depende_de_resultados(entorno_calculados):
    e = entorno_calculados
    definir(e["db"], e["sedes"][0], "Sin datos aún", "Activo")
    assert nombres(e["client"].get(URL, params={"estado": "Activo"})) == ["Sin datos aún"]
    assert nombres(e["client"].get(URL, params={"estado": "Inactivo"})) == []


# CP-520 · CA-04: combinación acumulativa y total del conjunto filtrado
def test_cp520_combinacion_y_total(entorno_calculados):
    e = entorno_calculados
    for i in range(25):
        definir(e["db"], e["sedes"][0], f"Caudal {i:02}", "Activo" if i < 13 else "Inactivo")
    for i in range(5):
        definir(e["db"], e["sedes"][0], f"Nivel {i}", "Inactivo")
    c = e["client"]
    data = c.get(URL, params={"q": "CAUDAL", "estado": "Inactivo"}).json()
    assert data["total"] == 12 and len(data["items"]) == 10
    assert all(p["estd"] == "Inactivo" and "Caudal" in p["nmbr"] for p in data["items"])
    p2 = c.get(URL, params={"q": "CAUDAL", "estado": "Inactivo", "pagina": 2}).json()
    assert p2["total"] == 12 and len(p2["items"]) == 2
    vacia = c.get(URL, params={"q": "caudal", "estado": "Inactivo", "pagina": 9}).json()
    assert vacia["total"] == 12 and vacia["items"] == []


# CP-526 · Conv.: cambiar de empresa vuelve a consultar en el nuevo contexto
def test_cp526_cambio_de_empresa(entorno_calculados):
    e = entorno_calculados
    definir(e["db"], e["sedes"][0], "Balance empresa A")
    definir(e["db"], e["sedes"][2], "Balance empresa B")
    c = e["client"]
    assert nombres(c.get(URL, params={"q": "balance"})) == ["Balance empresa A"]
    c.headers["X-Cliente-Id"] = str(e["empresas"][1].id_clnt)
    data = c.get(URL, params={"q": "balance"}).json()
    assert [p["nmbr"] for p in data["items"]] == ["Balance empresa B"]
    assert data["contexto"]["empresa"] == e["empresas"][1].rzn_scl


# CP-527 · Conv.: filtrar no modifica definiciones (todas las columnas)
def test_cp527_filtrar_no_modifica(entorno_calculados):
    e = entorno_calculados
    ps = [
        definir(e["db"], e["sedes"][0], f"Integridad {i}", s)
        for i, s in enumerate(["Activo", "Inactivo"])
    ]
    cols = [c.name for c in ParametroCalculado.__table__.columns]
    antes = [tuple(getattr(p, c) for c in cols) for p in ps]
    for params in [{"q": "integ"}, {"estado": "Inactivo"}, {"q": "x", "estado": "Activo"}, {}]:
        assert e["client"].get(URL, params=params).status_code == 200
    for p in ps:
        e["db"].refresh(p)
    assert [tuple(getattr(p, c) for c in cols) for p in ps] == antes
