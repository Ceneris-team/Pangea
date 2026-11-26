"""Regresiones DEF-15 y DEF-17 sobre HTTP y PostgreSQL reales."""

import importlib.util
from pathlib import Path

import pytest

from app.models import Dispositivo
from tests.routers.test_dispositivos import (
    client as client,
)
from tests.routers.test_dispositivos import (
    crear_conexion,
    crear_ubicacion,
    cuerpo_valido,
    preparar_dispositivo,
)
from tests.routers.test_dispositivos import (
    tecnico_editor as tecnico_editor,
)
from tests.routers.test_dispositivos import (
    tecnico_lector as tecnico_lector,
)
from tests.routers.test_entorno_operativo import autenticar
from tests.routers.test_entorno_operativo import entorno as entorno


@pytest.mark.parametrize("campo", ["marca", "estado", "busqueda"])
@pytest.mark.parametrize("control", ["\x00", "\x01", "\n", "\x7f", "\x85"])
def test_filtros_rechazan_controles_con_422(client, tecnico_lector, campo, control):
    respuesta = client.get("/dispositivos", params={campo: f"Campbell{control}"})
    assert respuesta.status_code == 422
    error = respuesta.json()["detail"][0]
    assert error["loc"] == ["query", campo]
    assert "caracteres de control" in error["msg"]
    # La sesión sigue utilizable después del dato inválido.
    assert client.get("/dispositivos", params={"marca": "Campbell"}).status_code == 200


@pytest.mark.parametrize("marca_filtro", ["Hobo", "hobo", " HOBO "])
def test_catalogo_unico_y_filtro_reune_las_cuatro_variantes_historicas(
    client, db_session, tecnico_lector, marca_filtro
):
    sede, _ = tecnico_lector
    equipos = [
        preparar_dispositivo(db_session, sede, nombre=f"Hobo-{i}", marca=marca)
        for i, marca in enumerate(["Hobo", "hobo", " Hobo", "Hobo "])
    ]
    preparar_dispositivo(db_session, sede, nombre="Otra marca", marca="Hobo Pro")
    assert client.get("/dispositivos/marcas").json()["items"] == ["Hobo", "Hobo Pro"]
    respuesta = client.get("/dispositivos", params={"marca": marca_filtro})
    assert respuesta.status_code == 200
    assert respuesta.json()["total"] == 4
    assert {fila["id_dspstv"] for fila in respuesta.json()["items"]} == {
        equipo.id_dspstv for equipo in equipos
    }
    # Sigue combinándose con el estado y conserva la coincidencia completa.
    equipos[0].estd = "Inactivo"
    db_session.flush()
    combinado = client.get("/dispositivos", params={"marca": marca_filtro, "estado": "Activo"})
    assert combinado.json()["total"] == 3


def test_crear_y_editar_guardan_marca_normalizada(entorno):
    client, db_session, empresas, recursos, cuentas, _ = entorno
    autenticar(client, cuentas["Técnico CENERIS"])
    client.headers["X-Cliente-Id"] = str(empresas[0].id_clnt)
    sede = recursos[0][1]
    ubicacion = crear_ubicacion(db_session, sede)
    conexion = crear_conexion(db_session, sede)
    respuesta = client.post(
        "/dispositivos", json=cuerpo_valido(ubicacion, conexion, mrc="  hObO  ")
    )
    assert respuesta.status_code == 201, respuesta.text
    creado = respuesta.json()["dispositivo"]
    assert creado["mrc"] == "Hobo"
    id_dispositivo = creado["id_dspstv"]
    assert db_session.get(Dispositivo, id_dispositivo).mrc == "Hobo"
    editado = client.put(f"/dispositivos/{id_dispositivo}", json={"mrc": " cAMPBELL sCIENTIFIC "})
    assert editado.status_code == 200
    db_session.expire_all()
    assert db_session.get(Dispositivo, id_dispositivo).mrc == "Campbell Scientific"
    assert client.get("/dispositivos/marcas").json()["items"] == [
        "Campbell",
        "Campbell Scientific",
    ]


@pytest.mark.parametrize("marca", ["   ", "Hobo\x00", "Hobo\n"])
def test_crear_y_editar_rechazan_marcas_invalidas(client, db_session, tecnico_editor, marca):
    sede, _ = tecnico_editor
    equipo = preparar_dispositivo(db_session, sede)
    ubicacion = crear_ubicacion(db_session, sede, "Nueva ubicación")
    conexion = crear_conexion(db_session, sede, "Nueva conexión")
    creado = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion, mrc=marca))
    editado = client.put(f"/dispositivos/{equipo.id_dspstv}", json={"mrc": marca})
    assert creado.status_code == editado.status_code == 422
    db_session.refresh(equipo)
    assert equipo.mrc == "Campbell"


def test_migracion_normaliza_datos_existentes(db_session, fabrica, monkeypatch):
    sede = fabrica.sede()
    equipos = [
        preparar_dispositivo(db_session, sede, nombre=f"Hobo-{i}", marca=marca)
        for i, marca in enumerate(["Hobo", "hobo", " Hobo", "Hobo "])
    ]
    ruta = (
        Path(__file__).parents[2]
        / "alembic/versions/a20e20261126_normalizar_marcas_dispositivos.py"
    )
    spec = importlib.util.spec_from_file_location("migracion_hu36", ruta)
    migracion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migracion)
    monkeypatch.setattr(migracion.op, "get_bind", db_session.connection)
    migracion.upgrade()
    db_session.expire_all()
    assert [equipo.mrc for equipo in equipos] == ["Hobo"] * 4
