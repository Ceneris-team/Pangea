"""HU36: los filtros y sus opciones respetan empresa y proyecto activos."""

import pytest

from tests.routers.test_entorno_operativo import autenticar
from tests.routers.test_entorno_operativo import entorno as entorno


@pytest.mark.parametrize("rol", ["Técnico CENERIS", "Administrador", "Lector"])
@pytest.mark.parametrize("proyecto_activo", [False, True])
def test_catalogos_y_filtros_con_sesion_real(entorno, rol, proyecto_activo):
    client, db, empresas, recursos, cuentas, _ = entorno
    for i, recurso in enumerate(recursos):
        recurso[4].mrc = f"Marca {i}"
    db.flush()
    autenticar(client, cuentas[rol])
    client.headers["X-Cliente-Id"] = str(empresas[0].id_clnt)
    if proyecto_activo:
        client.headers["X-Proyecto-Id"] = str(recursos[0][0].id_ubccn)
    visibles = [recursos[0]] if rol == "Lector" or proyecto_activo else recursos[:2]

    proyectos = client.get("/dispositivos/ubicaciones")
    marcas = client.get("/dispositivos/marcas")
    assert proyectos.status_code == marcas.status_code == 200
    assert {u["id_ubccn"] for u in proyectos.json()["items"]} == {r[0].id_ubccn for r in visibles}
    assert marcas.json()["items"] == [r[4].mrc for r in visibles]

    for recurso in visibles:
        filtrado = client.get(
            "/dispositivos",
            params={
                "marca": recurso[4].mrc,
                "id_ubccn": recurso[0].id_ubccn,
                "estado": "Activo",
            },
        )
        assert filtrado.status_code == 200
        assert filtrado.json()["total"] == 1
        assert filtrado.json()["items"][0]["id_dspstv"] == recurso[4].id_dspstv

    ajeno = client.get(
        "/dispositivos",
        params={
            "marca": recursos[2][4].mrc,
            "id_ubccn": recursos[2][0].id_ubccn,
        },
    )
    assert ajeno.status_code == 200
    assert ajeno.json()["total"] == 0
