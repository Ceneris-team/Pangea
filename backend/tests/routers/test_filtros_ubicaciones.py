"""DEF-20 / PP-57: los filtros inválidos responden 422 y conservan la sesión."""

import pytest

from tests.routers.test_entorno_operativo import autenticar
from tests.routers.test_entorno_operativo import entorno as entorno
from tests.routers.test_ubicaciones import client as client
from tests.routers.test_ubicaciones import crear_ubicacion_directa
from tests.routers.test_ubicaciones import tecnico_editor as tecnico_editor


@pytest.mark.parametrize(
    "rol", ["Técnico CENERIS", "Administrador CENERIS", "Administrador", "Tecnico", "Lector"]
)
@pytest.mark.parametrize(
    "params", [{"busqueda": "laguna\x00"}, {"busqueda": "\x00", "estado": "Inactiva"}]
)
def test_nul_devuelve_422_para_cada_rol_con_lectura(entorno, rol, params):
    client, db, empresas, recursos, cuentas, _ = entorno
    autenticar(client, cuentas[rol])
    client.headers["X-Cliente-Id"] = str(empresas[0].id_clnt)
    respuesta = client.get("/ubicaciones", params=params)
    assert respuesta.status_code == 422, respuesta.text
    error = respuesta.json()["detail"][0]
    assert error["loc"] == ["query", "busqueda"]
    assert "caracteres de control" in error["msg"]
    # El filtro válido posterior conserva el alcance de la empresa y los permisos.
    valida = client.get("/ubicaciones", params={"busqueda": recursos[0][0].nmbr})
    assert valida.status_code == 200
    assert [p["id_ubccn"] for p in valida.json()["items"]] == [recursos[0][0].id_ubccn]


@pytest.mark.parametrize("busqueda", ["laguna\x01", "\n", "\x7f", "\x85"])
def test_busqueda_rechaza_otros_controles(client, db_session, tecnico_editor, busqueda):
    proyecto = crear_ubicacion_directa(db_session, tecnico_editor, "Laguna de prueba")
    respuesta = client.get("/ubicaciones", params={"busqueda": busqueda, "estado": "Activa"})
    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["detail"][0]["loc"] == ["query", "busqueda"]
    valida = client.get("/ubicaciones", params={"busqueda": "LAGUNA", "estado": "Activa"})
    assert valida.status_code == 200
    assert [p["id_ubccn"] for p in valida.json()["items"]] == [proyecto.id_ubccn]
