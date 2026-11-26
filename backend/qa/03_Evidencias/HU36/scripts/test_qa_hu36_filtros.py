"""QA HU36 (PP-436): filtros de dispositivos por marca, ubicación y estado.

Casos que no cubre la suite de desarrollo (test_filtros_dispositivos.py).
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import uuid

import pytest

from tests.routers.test_entorno_operativo import autenticar
from tests.routers.test_entorno_operativo import entorno as entorno
from tests.routers.test_mediciones import crear_conexion, crear_dispositivo, crear_ubicacion


DEF15 = pytest.mark.xfail(
    strict=True, reason="DEF-15: byte NUL en un filtro de /dispositivos provoca error 500"
)


def _tag():
    return uuid.uuid4().hex[:6]


@pytest.fixture()
def tecnico(entorno):
    """Técnico CENERIS (scope global) con un parque propio de 6 dispositivos:
    2 ubicaciones con equipos + 1 ubicación vacía; 3 marcas; Activo/Inactivo."""
    client, db, empresas, recursos, cuentas, _ = entorno
    t = _tag()
    sede = recursos[0][1]
    ub_a = crear_ubicacion(db, sede, f"QA36 Norte {t}")
    ub_b = crear_ubicacion(db, sede, f"QA36 Sur {t}")
    ub_vacia = crear_ubicacion(db, sede, f"QA36 Vacia {t}")
    marcas = {k: f"QA36-{k}-{t}" for k in ("Campbell", "Vaisala", "Hobo")}
    especificacion = [
        ("A1", ub_a, "Campbell", "Activo"),
        ("A2", ub_a, "Campbell", "Inactivo"),
        ("A3", ub_a, "Vaisala", "Activo"),
        ("B1", ub_b, "Campbell", "Activo"),
        ("B2", ub_b, "Hobo", "Activo"),
        ("B3", ub_b, "Vaisala", "Inactivo"),
    ]
    disp = {}
    for nombre, ub, marca, estado in especificacion:
        d = crear_dispositivo(db, ub, crear_conexion(db, sede), f"QA36 {nombre} {t}", marcas[marca])
        d.estd = estado
        disp[nombre] = d
    db.flush()
    autenticar(client, cuentas["Técnico CENERIS"])
    return client, db, {"a": ub_a, "b": ub_b, "vacia": ub_vacia}, marcas, disp, t, recursos


def _ids(resp):
    assert resp.status_code == 200, resp.text
    return {i["id_dspstv"] for i in resp.json()["items"]}


def _listar(client, **params):
    params.setdefault("por_pagina", 100)
    return client.get("/dispositivos", params=params)


# CP-505 · CA-01: filtro por marca muestra solo esa marca (coincidencia exacta)
def test_cp505_filtro_por_marca(tecnico):
    client, _, _, marcas, d, _, _ = tecnico
    resp = _listar(client, marca=marcas["Campbell"])
    assert _ids(resp) == {d["A1"].id_dspstv, d["A2"].id_dspstv, d["B1"].id_dspstv}
    assert {i["mrc"] for i in resp.json()["items"]} == {marcas["Campbell"]}
    # La marca es exacta: un prefijo no trae nada (la búsqueda parcial es HU10)
    assert _ids(_listar(client, marca=marcas["Campbell"][:-1])) == set()


# CP-506 · CA-02: filtro por ubicación muestra solo los equipos de esa ubicación
def test_cp506_filtro_por_ubicacion(tecnico):
    client, _, ubs, _, d, _, _ = tecnico
    resp = _listar(client, id_ubccn=ubs["b"].id_ubccn)
    assert _ids(resp) == {d["B1"].id_dspstv, d["B2"].id_dspstv, d["B3"].id_dspstv}
    assert {i["id_ubccn"] for i in resp.json()["items"]} == {ubs["b"].id_ubccn}
    assert _ids(_listar(client, id_ubccn=ubs["vacia"].id_ubccn)) == set()


# CP-507 · CA-04: filtro por estado
@pytest.mark.parametrize("estado", ["Activo", "Inactivo"])
def test_cp507_filtro_por_estado(tecnico, estado):
    client, _, ubs, _, d, _, _ = tecnico
    propios = {x.id_dspstv for x in d.values() if x.estd == estado}
    resp = _listar(client, estado=estado)
    assert {i["estd"] for i in resp.json()["items"]} == {estado}
    visibles = _ids(resp)
    assert propios <= visibles
    assert not ({x.id_dspstv for x in d.values()} - propios) & visibles


# CP-508 · CA-04: combinación acumulativa (AND) marca + ubicación + estado
@pytest.mark.parametrize(
    "marca,ub,estado,esperados",
    [
        ("Campbell", "a", None, {"A1", "A2"}),
        ("Campbell", "a", "Activo", {"A1"}),
        ("Vaisala", "b", "Inactivo", {"B3"}),
        ("Vaisala", None, "Activo", {"A3"}),
        (None, "b", "Activo", {"B1", "B2"}),
        ("Hobo", "a", None, set()),  # combinación sin coincidencias
    ],
)
def test_cp508_filtros_acumulativos(tecnico, marca, ub, estado, esperados):
    client, _, ubs, marcas, d, _, _ = tecnico
    params = {}
    if marca:
        params["marca"] = marcas[marca]
    if ub:
        params["id_ubccn"] = ubs[ub].id_ubccn
    if estado:
        params["estado"] = estado
    resp = _listar(client, **params)
    assert _ids(resp) == {d[k].id_dspstv for k in esperados}
    assert resp.json()["total"] == len(esperados)


# CP-509 · CA-03: sin filtros (lo que envía la UI tras "Limpiar filtros")
# se restaura el listado completo, paginado desde la página 1.
def test_cp509_sin_filtros_restaura_listado(tecnico):
    client, _, _, marcas, d, _, _ = tecnico
    filtrado = _listar(client, marca=marcas["Hobo"], estado="Activo")
    assert filtrado.json()["total"] == 1
    completo = client.get("/dispositivos")
    cuerpo = completo.json()
    assert completo.status_code == 200
    assert cuerpo["pagina"] == 1 and cuerpo["por_pagina"] == 10
    todos = _ids(_listar(client))
    assert {x.id_dspstv for x in d.values()} <= todos
    assert cuerpo["total"] == len(todos)


# CP-510 · CA-05: el selector de marcas lista solo marcas de equipos registrados,
# sin duplicados, ordenadas, incluidas las de equipos inactivos.
def test_cp510_catalogo_de_marcas(tecnico):
    client, _, _, marcas, _, t, _ = tecnico
    resp = client.get("/dispositivos/marcas")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == len(set(items))
    assert items == sorted(items)
    propias = [m for m in items if m.endswith(t)]
    assert sorted(propias) == sorted(marcas.values())
    # Una marca sin equipo no existe en el catálogo
    assert f"QA36-SinEquipo-{t}" not in items


# CP-510 · CA-05 (bordes): marcas que solo difieren en mayúsculas o espacios.
# Debe haber una sola opción por marca; si se repite es DEF-17 (xfail).
def test_cp510_marcas_variantes_de_escritura(tecnico):
    client, db, ubs, _, _, t, recursos = tecnico
    base = f"QA36Var{t}"
    variantes = [base, base.lower(), f" {base}", f"{base} "]
    creados = []
    for i, m in enumerate(variantes):
        r = client.post(
            "/dispositivos",
            json={
                "nmbr": f"QA36 var {i} {t}",
                "mrc": m,
                "id_ubccn": ubs["a"].id_ubccn,
                "id_cnxn": crear_conexion(db, recursos[0][1]).id_cnxn,
            },
        )
        assert r.status_code == 201, r.text
        creados.append(r.json())
    items = [m for m in client.get("/dispositivos/marcas").json()["items"] if base.lower() in m.lower()]
    distintas_visibles = {m.strip().lower() for m in items if m.lower().strip().startswith("qa36var")}
    print(f"\nMARCAS_VARIANTES={items!r} -> visibles distintas={len(distintas_visibles)}")
    # Lo deseable: una sola opción para la misma marca escrita de 4 formas.
    if len(items) > 1:
        pytest.xfail(
            f"DEF-17: el catálogo devuelve {len(items)} opciones para una misma marca "
            "escrita con distinta capitalización/espacios"
        )


# CP-511 · CA-06: el selector de ubicaciones lista solo las que tienen
# al menos un dispositivo asociado.
def test_cp511_catalogo_de_ubicaciones(tecnico):
    client, _, ubs, _, _, t, _ = tecnico
    resp = client.get("/dispositivos/ubicaciones")
    assert resp.status_code == 200
    items = resp.json()["items"]
    ids = [u["id_ubccn"] for u in items]
    assert len(ids) == len(set(ids))
    assert ubs["a"].id_ubccn in ids and ubs["b"].id_ubccn in ids
    assert ubs["vacia"].id_ubccn not in ids
    nombres = {u["id_ubccn"]: u["nmbr"] for u in items}
    assert nombres[ubs["a"].id_ubccn] == ubs["a"].nmbr


# CP-511 · CA-06: una ubicación cuyo único equipo está Inactivo sigue
# teniendo un dispositivo asociado (registrado) y aparece.
def test_cp511_ubicacion_solo_con_inactivos(tecnico):
    client, db, ubs, marcas, _, t, recursos = tecnico
    ub = crear_ubicacion(db, recursos[0][1], f"QA36 SoloInactivo {t}")
    d = crear_dispositivo(db, ub, crear_conexion(db, recursos[0][1]), f"QA36 inact {t}", marcas["Hobo"])
    d.estd = "Inactivo"
    db.flush()
    ids = [u["id_ubccn"] for u in client.get("/dispositivos/ubicaciones").json()["items"]]
    assert ub.id_ubccn in ids


# CP-512 · CA-05/06: tras registrar un dispositivo con marca y ubicación
# nuevas, el catálogo del backend ya las incluye (la parte de UI va en E2E).
def test_cp512_catalogo_backend_refleja_alta(tecnico):
    client, db, ubs, _, _, t, recursos = tecnico
    nueva = f"QA36-Nueva-{t}"
    assert nueva not in client.get("/dispositivos/marcas").json()["items"]
    r = client.post(
        "/dispositivos",
        json={
            "nmbr": f"QA36 alta {t}",
            "mrc": nueva,
            "id_ubccn": ubs["vacia"].id_ubccn,
            "id_cnxn": crear_conexion(db, recursos[0][1]).id_cnxn,
        },
    )
    assert r.status_code == 201, r.text
    assert nueva in client.get("/dispositivos/marcas").json()["items"]
    ids = [u["id_ubccn"] for u in client.get("/dispositivos/ubicaciones").json()["items"]]
    assert ubs["vacia"].id_ubccn in ids


# CP-513 · Transversal: aislamiento. Un usuario de empresa no ve marcas,
# ubicaciones ni equipos de otra empresa, ni filtrando explícitamente por ellos.
@pytest.mark.parametrize("rol", ["Administrador", "Tecnico", "Lector"])
def test_cp513_aislamiento_catalogos_y_filtros(entorno, rol):
    client, db, empresas, recursos, cuentas, _ = entorno
    t = _tag()
    ajena_marca = f"QA36-Ajena-{t}"
    recursos[2][4].mrc = ajena_marca
    db.flush()
    autenticar(client, cuentas[rol])
    client.headers["X-Cliente-Id"] = str(empresas[0].id_clnt)
    assert ajena_marca not in client.get("/dispositivos/marcas").json()["items"]
    ubic = [u["id_ubccn"] for u in client.get("/dispositivos/ubicaciones").json()["items"]]
    assert recursos[2][0].id_ubccn not in ubic
    for params in (
        {"marca": ajena_marca},
        {"id_ubccn": recursos[2][0].id_ubccn},
        {"marca": ajena_marca, "id_ubccn": recursos[2][0].id_ubccn, "estado": "Activo"},
    ):
        resp = _listar(client, **params)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# CP-513 · Transversal: sin autenticación no hay catálogos ni listado.
@pytest.mark.parametrize("ruta", ["/dispositivos", "/dispositivos/marcas", "/dispositivos/ubicaciones"])
def test_cp513_sin_token(entorno, ruta):
    client = entorno[0]
    client.headers.clear()
    assert client.get(ruta).status_code == 401


# CP-514 · Transversal: parámetros inválidos nunca producen 500.
@pytest.mark.parametrize(
    "params",
    [
        pytest.param({"busqueda": "Campbell\x00"}, marks=DEF15),
        pytest.param({"estado": "Activo\x00"}, marks=DEF15),
        {"estado": "foo"},
        {"estado": "activo"},
        {"id_ubccn": "abc"},
        {"id_ubccn": 999999999},
        {"id_ubccn": -1},
        {"id_ubccn": 2**63},
        {"marca": ""},
        {"marca": "x" * 5000},
        {"marca": "' OR 1=1 --"},
        {"marca": "%"},
        pytest.param({"marca": "Campbell\x00"}, marks=DEF15),
        {"pagina": 0},
        {"por_pagina": 101},
    ],
)
def test_cp514_parametros_invalidos(tecnico, params):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    client.headers.update(tecnico[0].headers)
    resp = client.get("/dispositivos", params=params)
    print(f"\nCP514 {repr(params)[:60]} -> {resp.status_code} total={resp.json().get('total') if resp.headers.get('content-type','').startswith('application/json') else '-'}")
    assert resp.status_code < 500, resp.text
    if resp.status_code == 200:
        # Un valor que no existe no debe "comodinear": no trae todo el parque
        if "marca" in params and params["marca"]:
            assert resp.json()["total"] == 0
