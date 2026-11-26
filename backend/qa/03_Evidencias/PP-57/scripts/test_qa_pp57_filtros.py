"""QA PP-57 (PP-438): filtrar el listado de proyectos (ubicaciones) por nombre y estado.

Casos que no cubre la suite de desarrollo (tests/routers/test_ubicaciones.py). Usa
token real + X-Cliente-Id (mismo camino que la app) en lugar de sobrescribir la
identidad. Se copia a backend/tests/routers/ del worktree de dev 78edb10.
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Ubicacion, UsuarioCliente, UsuarioProyecto
from app.security.jwt_auth import create_access_token
from tests.routers.test_ubicaciones import crear_ubicacion_directa

URL = "/ubicaciones"


@pytest.fixture()
def e(db_session, fabrica):
    db = db_session
    empresas = [fabrica.cliente(), fabrica.cliente()]
    sedes = [fabrica.sede(empresas[0]), fabrica.sede(empresas[0]), fabrica.sede(empresas[1])]
    tecnico = fabrica.usuario(fabrica.rol("Técnico CENERIS"), scp="global")
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            client.headers["Authorization"] = "Bearer " + create_access_token(
                tecnico.id_usr, None, tecnico.scp, tecnico.rol.nmbr
            )
            client.headers["X-Cliente-Id"] = str(empresas[0].id_clnt)
            yield {"c": client, "db": db, "empresas": empresas, "sedes": sedes, "fabrica": fabrica}
    finally:
        app.dependency_overrides.clear()


def nombres(resp):
    assert resp.status_code == 200, resp.text
    return [u["nmbr"] for u in resp.json()["items"]]


def ub(e, nombre, estado="Activa", sede=0, monitoreo=True):
    u = crear_ubicacion_directa(e["db"], e["sedes"][sede], nombre, estado=estado)
    u.monitoreo_activo = monitoreo
    e["db"].flush()
    return u


# CP-529 · CA-01: sin filtros, listado autorizado del contexto, 10 por página
def test_cp529_listado_inicial_contexto(e):
    for i in range(12):
        ub(e, f"Proyecto {i:02}", "Activa" if i % 2 else "Inactiva", sede=i % 2)
    ub(e, "Proyecto otra empresa", sede=2)
    data = e["c"].get(URL).json()
    assert data["total"] == 12 and data["pagina"] == 1 and data["por_pagina"] == 10
    assert len(data["items"]) == 10
    assert "Proyecto otra empresa" not in [u["nmbr"] for u in data["items"]]
    # estado vacío («Todos los estados») equivale a sin restricción
    assert e["c"].get(URL, params={"estado": ""}).json()["total"] == 12


# CP-530 · CA-02: parcial, mayúsculas, espacios y tabuladores
@pytest.mark.parametrize("q", ["río", "RÍO", "  rÍo  ", "\trío\n", "ón RÍO SEC"])
def test_cp530_busqueda_parcial_insensible(e, q):
    ub(e, "Estación Río Seco")
    ub(e, "Laguna Azul")
    assert nombres(e["c"].get(URL, params={"busqueda": q})) == ["Estación Río Seco"]


# CP-530 · CA-02: entradas límite tratadas como texto literal
@pytest.mark.parametrize("q,esperado", [("", 3), ("   ", 3), ("\\", 1), ("_", 1), ("%", 1), ("x" * 300, 0)])
def test_cp530_busqueda_literal_y_limites(e, q, esperado):
    for n in ["Ruta C:\\datos", "Pozo_k", "Humedad 90%"]:
        ub(e, n)
    resp = e["c"].get(URL, params={"busqueda": q})
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == esperado


# CP-530 · CA-02: un carácter de control (byte NUL) no debe provocar error del servidor
# DEF-20: hoy lanza ValueError sin capturar (500 en la API real)
@pytest.mark.xfail(strict=True, raises=ValueError, reason="DEF-20: byte NUL en la búsqueda → 500")
@pytest.mark.parametrize("q", ["río\x00", "\x00"])
def test_cp530_byte_nul_no_provoca_500(e, q):
    ub(e, "Estación Río Seco")
    resp = e["c"].get(URL, params={"busqueda": q})
    assert resp.status_code in (200, 422), resp.status_code


# CP-531 · CA-03: Activo / Archivado / Todos conserva la búsqueda; archivado ≠ monitoreo detenido
def test_cp531_estado_y_todos_conserva_busqueda(e):
    ub(e, "Norte activo", "Activa", monitoreo=False)
    ub(e, "Norte archivado", "Inactiva", monitoreo=True)
    ub(e, "Sur archivado", "Inactiva")
    c = e["c"]
    assert nombres(c.get(URL, params={"estado": "Activa"})) == ["Norte activo"]
    assert nombres(c.get(URL, params={"estado": "Inactiva"})) == ["Norte archivado", "Sur archivado"]
    assert nombres(c.get(URL, params={"busqueda": "norte", "estado": ""})) == ["Norte activo", "Norte archivado"]
    item = c.get(URL, params={"estado": "Inactiva", "busqueda": "norte"}).json()["items"][0]
    assert item["estd"] == "Inactiva" and item["monitoreo_activo"] is True


# CP-532 · CA-04: combinación sobre todos los registros antes de paginar
def test_cp532_combinacion_antes_de_paginar(e):
    # Las coincidencias quedan después de la página 1 del listado sin filtro
    for i in range(15):
        ub(e, f"Alfa {i:02}")
    for i in range(13):
        ub(e, f"Zeta {i:02}", "Inactiva" if i < 11 else "Activa")
    ub(e, "Zeta ajeno", "Inactiva", sede=2)
    c = e["c"]
    p1 = c.get(URL, params={"busqueda": "ZETA", "estado": "Inactiva"}).json()
    p2 = c.get(URL, params={"busqueda": "ZETA", "estado": "Inactiva", "pagina": 2}).json()
    assert p1["total"] == p2["total"] == 11
    assert len(p1["items"]) == 10 and len(p2["items"]) == 1
    todos = p1["items"] + p2["items"]
    assert all(u["estd"] == "Inactiva" and "Zeta" in u["nmbr"] for u in todos)
    assert len({u["id_ubccn"] for u in todos}) == 11


# CP-537 · Transversal: Lector de empresa solo ve sus proyectos asignados, filtre o limpie
def test_cp537_lector_solo_asignados_y_sin_otra_empresa(e):
    db, f = e["db"], e["fabrica"]
    asignado = ub(e, "Norte asignado", "Inactiva")
    ub(e, "Norte no asignado", "Inactiva")
    ub(e, "Norte otra empresa", "Inactiva", sede=2)
    lector = f.usuario(f.rol("Usuario Empresa"), scp="por_cliente")
    miembro = UsuarioCliente(id_usr=lector.id_usr, id_clnt=e["empresas"][0].id_clnt, rol_emp="Lector", estd="Activo")
    db.add(miembro)
    db.flush()
    db.add(UsuarioProyecto(id_mmb=miembro.id_mmb, id_ubccn=asignado.id_ubccn))
    db.flush()
    c = e["c"]
    c.headers["Authorization"] = "Bearer " + create_access_token(lector.id_usr, None, lector.scp, lector.rol.nmbr)
    for params in ({"busqueda": "norte", "estado": "Inactiva"}, {"busqueda": "otra"}, {"estado": "Activa"}, {}):
        resp = c.get(URL, params=params)
        assert resp.status_code == 200, resp.text
        assert {u["nmbr"] for u in resp.json()["items"]} <= {"Norte asignado"}
    assert c.get(URL).json()["total"] == 1
    # Forzar la otra empresa por cabecera no debe abrir sus proyectos
    c.headers["X-Cliente-Id"] = str(e["empresas"][1].id_clnt)
    assert c.get(URL, params={"busqueda": "norte"}).status_code == 403


# CP-537 · Transversal: el técnico cambia de empresa y el filtro se aplica en el nuevo contexto
def test_cp537_cambio_de_empresa(e):
    ub(e, "Balance A")
    ub(e, "Balance B", sede=2)
    c = e["c"]
    assert nombres(c.get(URL, params={"busqueda": "balance"})) == ["Balance A"]
    c.headers["X-Cliente-Id"] = str(e["empresas"][1].id_clnt)
    assert nombres(c.get(URL, params={"busqueda": "balance"})) == ["Balance B"]


# CP-538 · Transversal: parámetros inválidos
@pytest.mark.parametrize(
    "params", [{"estado": "Activo"}, {"estado": "Archivado"}, {"estado": "activa"}, {"pagina": 0}, {"por_pagina": 101}]
)
def test_cp538_parametros_invalidos_422(e, params):
    assert e["c"].get(URL, params=params).status_code == 422


# CP-538 · Transversal: filtrar no modifica registros
def test_cp538_filtrar_no_modifica(e):
    us = [ub(e, f"Integridad {i}", s) for i, s in enumerate(["Activa", "Inactiva"])]
    cols = [col.name for col in Ubicacion.__table__.columns]
    for u in us:
        e["db"].refresh(u)
    antes = [tuple(getattr(u, col) for col in cols) for u in us]
    for params in ({"busqueda": "integ"}, {"estado": "Inactiva"}, {"busqueda": "x", "estado": "Activa"}, {}):
        assert e["c"].get(URL, params=params).status_code == 200
    for u in us:
        e["db"].refresh(u)
    assert [tuple(getattr(u, col) for col in cols) for u in us] == antes


# CP-539 · Detalles: orden alfabético por nombre, sin distinguir mayúsculas ni tildes
def test_cp539_orden_alfabetico(e):
    for n in ["delta", "Bravo", "Ámbar", "alfa", "Charlie", "Zona", "Ñandú", "Nube"]:
        ub(e, n)
    orden = nombres(e["c"].get(URL))
    # Mayúsculas y tildes no alteran el orden
    assert [n for n in orden if n not in ("Nube", "Ñandú")] == ["alfa", "Ámbar", "Bravo", "Charlie", "delta", "Zona"]


# CP-539 · OBS-?: la «Ñ» se ordena como «N» (cotejo en_US.utf8) y no después de la «N» del alfabeto español
@pytest.mark.xfail(strict=True, reason="OBS: cotejo en_US.utf8 ordena Ñandú antes de Nube")
def test_cp539_enie_despues_de_n(e):
    for n in ["Ñandú", "Nube", "Oro"]:
        ub(e, n)
    assert nombres(e["c"].get(URL)) == ["Nube", "Ñandú", "Oro"]
