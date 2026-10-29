"""Sesiones reales: operación, consulta y aislamiento entre dos empresas."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (
    ArchivoIngesta,
    LimitePlan,
    PlanSuscripcion,
    Suscripcion,
    UsuarioCliente,
    UsuarioProyecto,
)
from app.security.jwt_auth import create_access_token
from app.services.limites_plan import fecha_comercial
from tests.routers.test_mediciones import (
    crear_conexion,
    crear_dispositivo,
    crear_medicion,
    crear_parametro,
    crear_ubicacion,
    mapear_parametro,
)


@pytest.fixture()
def entorno(db_session, fabrica):
    db = db_session
    empresas = [fabrica.cliente(), fabrica.cliente()]
    plan = PlanSuscripcion(
        nmbr=f"Plan entorno {empresas[0].id_clnt}", prc_mnsl=100, funcionalidades=["tableros"]
    )
    db.add(plan)
    db.flush()
    db.add(LimitePlan(id_pln=plan.id_pln, mx_sds=0, mx_ubccns=10, mx_dspstvs=10, mx_usrs=10))
    for empresa in empresas:
        db.add(
            Suscripcion(
                id_clnt=empresa.id_clnt,
                id_pln=plan.id_pln,
                fch_inc=fecha_comercial(),
                fch_vncmnt=fecha_comercial() + timedelta(days=30),
                estd="Activa",
            )
        )
    db.flush()
    recursos = []
    parametro = crear_parametro(db, f"Nivel multiempresa {empresas[0].id_clnt}")
    for i, empresa in enumerate([empresas[0], empresas[0], empresas[1]]):
        sede = fabrica.sede(empresa)
        ubicacion = crear_ubicacion(db, sede, f"Estacion {i}")
        conexion = crear_conexion(db, sede)
        dispositivo = crear_dispositivo(db, ubicacion, conexion, f"Datalogger {i}")
        mapeo = mapear_parametro(db, dispositivo, parametro)
        crear_medicion(db, dispositivo, parametro, sede, valor=10 + i)
        archivo = ArchivoIngesta(
            id_cnxn=conexion.id_cnxn, nmbr_archv=f"H_demo_{i}.dat", estd="Fallido"
        )
        db.add(archivo)
        db.flush()
        recursos.append((ubicacion, sede, ubicacion, conexion, dispositivo, mapeo, archivo))
    cuentas = {}
    for nombre in ("Administrador", "Tecnico", "Lector"):
        usuario = fabrica.usuario(fabrica.rol("Usuario Empresa"), scp="por_cliente")
        miembro = UsuarioCliente(id_usr=usuario.id_usr, id_clnt=empresas[0].id_clnt, rol_emp=nombre)
        db.add(miembro)
        db.flush()
        if nombre == "Lector":
            db.add(UsuarioProyecto(id_mmb=miembro.id_mmb, id_ubccn=recursos[0][0].id_ubccn))
        cuentas[nombre] = (usuario, miembro)
    for nombre in ("Administrador CENERIS", "Técnico CENERIS"):
        usuario = fabrica.usuario(
            fabrica.rol("Administrador" if nombre == "Administrador CENERIS" else nombre),
            scp="global",
        )
        cuentas[nombre] = (usuario, None)
    db.flush()
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            yield client, db, empresas, recursos, cuentas, parametro
    finally:
        app.dependency_overrides.clear()


def autenticar(client, cuenta):
    usuario = cuenta[0]
    client.headers.clear()
    client.headers["Authorization"] = "Bearer " + create_access_token(
        usuario.id_usr, None, usuario.scp, usuario.rol.nmbr
    )


@pytest.mark.parametrize("rol", ["Administrador", "Tecnico"])
def test_empresa_opera_recursos_propios_y_rechaza_ajenos(entorno, rol):
    client, db, empresas, recursos, cuentas, parametro = entorno
    autenticar(client, cuentas[rol])
    propios = recursos[:2]
    ajeno = recursos[2]
    assert {x["id_dspstv"] for x in client.get("/dispositivos").json()["items"]} == {
        r[4].id_dspstv for r in propios
    }
    for _, _, ubicacion, conexion, dispositivo, mapeo, _ in propios:
        assert (
            client.put(
                f"/dispositivos/{dispositivo.id_dspstv}", json={"nmbr": "Editado"}
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"/conexiones-ftp/{conexion.id_cnxn}", json={"nmbr": "FTP editado"}
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"/ubicaciones/{ubicacion.id_ubccn}", json={"dscrpcn": "Editada"}
            ).status_code
            == 200
        )
        assert client.get(f"/mapeos/{mapeo.id_mp}").status_code == 200
    for url in (
        f"/dispositivos/{ajeno[4].id_dspstv}",
        f"/conexiones-ftp/{ajeno[3].id_cnxn}",
        f"/ubicaciones/{ajeno[2].id_ubccn}",
        f"/mapeos/{ajeno[5].id_mp}",
        f"/ingesta/cola/{ajeno[6].id_archv}",
    ):
        assert client.get(url).status_code in {403, 404}, url
    assert (
        client.put(
            f"/dispositivos/{propios[0][4].id_dspstv}", json={"id_cnxn": ajeno[3].id_cnxn}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/conexiones-ftp",
            json={
                "id_sd": ajeno[1].id_sd,
                "nmbr": "Intrusion",
                "hst": "localhost",
                "prt": 21,
                "usr_ftp": "demo",
                "contrasena_ftp": "demo",
                "rt_rmt": "/datos",
                "frcnc_mnts": 1,
            },
        ).status_code
        == 403
    )
    assert client.get("/ingesta/metricas").json()["total"] == 2
    assert client.get("/usuarios").status_code == 403
    assert (
        client.put(f"/parametros/{parametro.id_prmtr}", json={"nmbr": "Global"}).status_code == 403
    )
    # Un header alterado no puede cambiar la frontera de la empresa.
    client.headers["X-Cliente-Id"] = str(empresas[1].id_clnt)
    assert client.get("/dispositivos").status_code == 403


def test_lector_consulta_datos_y_mapas_sin_poder_operar(entorno):
    client, _, _, recursos, cuentas, parametro = entorno
    autenticar(client, cuentas["Lector"])
    ubicacion, dispositivo = recursos[0][2], recursos[0][4]
    assert [x["id_ubccn"] for x in client.get("/ubicaciones").json()["items"]] == [
        ubicacion.id_ubccn
    ]
    assert [x["id_ubccn"] for x in client.get("/ubicaciones/mapa").json()] == [ubicacion.id_ubccn]
    assert [x["id_ubccn"] for x in client.get("/mapa-cliente").json()["items"]] == [
        ubicacion.id_ubccn
    ]
    respuesta = client.get("/mediciones")
    assert respuesta.status_code == 200, respuesta.text
    assert {x["id_dspstv"] for x in respuesta.json()["items"]} == {dispositivo.id_dspstv}
    assert (
        client.put(f"/dispositivos/{dispositivo.id_dspstv}", json={"nmbr": "Prohibido"}).status_code
        == 403
    )
    assert client.get("/conexiones-ftp").status_code == 403
    assert client.get("/ingesta/cola").status_code == 403
    tablero = client.post("/paneles", json={"nmbr": "Mi tablero"})
    assert tablero.status_code == 201, tablero.text
    panel_id = tablero.json()["panel"]["id_pnl"]
    disponibles = client.get(f"/paneles/{panel_id}/ubicaciones/disponibles")
    assert [u["id_ubccn"] for u in disponibles.json()["items"]] == [ubicacion.id_ubccn]
    assert (
        client.post(
            f"/paneles/{panel_id}/ubicaciones/lote", json={"ids": [ubicacion.id_ubccn]}
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/paneles/{panel_id}/ubicaciones/lote", json={"ids": [recursos[2][0].id_ubccn]}
        ).status_code
        == 404
    )
    valores = client.get(f"/paneles/{panel_id}/contenido").json()["ubicaciones"][0][
        "ultimos_valores"
    ]
    assert valores[0]["parametro"] == parametro.nmbr
    assert valores[0]["id_prmtr"] == parametro.id_prmtr
    assert valores[0]["dispositivo_nombre"] == dispositivo.nmbr
    assert valores[0]["valor"] == 10
    diagnostico = client.get(f"/paneles/{panel_id}/contenido").json()["dispositivos"][0]
    assert diagnostico["id_dspstv"] == dispositivo.id_dspstv
    assert diagnostico["ultima_ingesta"]["estado"] == "Fallido"
    assert (
        client.get(
            f"/paneles/{panel_id}/contenido", params={"dispositivo_id": dispositivo.id_dspstv}
        ).json()["ubicaciones"][0]["ultimos_valores"][0]["valor"]
        == 10
    )
    assert (
        client.get(
            f"/paneles/{panel_id}/contenido", params={"dispositivo_id": recursos[2][4].id_dspstv}
        ).status_code
        == 404
    )
    widget = client.post(
        f"/paneles/{panel_id}/widgets",
        json={
            "tp": "tarjeta",
            "id_prmtr": parametro.id_prmtr,
            "id_ubccn": ubicacion.id_ubccn,
        },
    )
    assert widget.status_code == 201, widget.text
    assert (
        client.get(f"/paneles/{panel_id}/contenido").json()["widgets"][0]["id_wdgt"]
        == widget.json()["widget"]["id_wdgt"]
    )
    serie_id = client.get(f"/mediciones/series?ubicacion_id={ubicacion.id_ubccn}").json()["items"][
        0
    ]["id_serie"]
    ahora = datetime.now(timezone.utc)
    datos_widget = client.get(
        f"/mediciones/series/{serie_id}",
        params={
            "fecha_inicio": (ahora - timedelta(days=7)).isoformat(),
            "fecha_fin": (ahora + timedelta(minutes=1)).isoformat(),
        },
    )
    assert datos_widget.status_code == 200, datos_widget.text
    assert datos_widget.json()["items"][0]["vlr"] == 10
    assert (
        client.delete(
            f"/paneles/{panel_id}/widgets/{widget.json()['widget']['id_wdgt']}"
        ).status_code
        == 200
    )
    assert client.get("/mediciones").json()["total"] == respuesta.json()["total"]
    assert client.get(f"/paneles/{panel_id}/contenido").json()["ubicaciones"]
    client.headers["X-Proyecto-Id"] = str(recursos[1][0].id_ubccn)
    assert client.get("/mediciones").status_code == 403


def test_panel_compartido_respeta_proyectos_del_lector(entorno):
    client, _, _, recursos, cuentas, _ = entorno
    autenticar(client, cuentas["Administrador"])
    creado = client.post("/paneles", json={"nmbr": "Estado compartido"})
    assert creado.status_code == 201, creado.text
    panel_id = creado.json()["panel"]["id_pnl"]
    ids = [recursos[0][0].id_ubccn, recursos[1][0].id_ubccn]
    assert (
        client.post(f"/paneles/{panel_id}/ubicaciones/lote", json={"ids": ids}).status_code == 201
    )
    assert (
        client.put(f"/paneles/{panel_id}/visibilidad", json={"vsbldd": "Empresa"}).status_code
        == 200
    )

    autenticar(client, cuentas["Lector"])
    listado = client.get("/paneles").json()["items"]
    assert [item["id_pnl"] for item in listado] == [panel_id]
    assert listado[0]["es_propietario"] is False
    contenido = client.get(f"/paneles/{panel_id}/contenido").json()
    assert [u["id_ubccn"] for u in contenido["ubicaciones"]] == ids[:1]
    assert [d["id_ubccn"] for d in contenido["dispositivos"]] == ids[:1]
    assert client.post(f"/paneles/{panel_id}/duplicar").status_code == 404
    assert (
        client.put(f"/paneles/{panel_id}/visibilidad", json={"vsbldd": "Privado"}).status_code
        == 404
    )


def test_paneles_y_datos_cambian_con_el_proyecto_activo(entorno):
    client, _, empresas, recursos, cuentas, _ = entorno
    autenticar(client, cuentas["Administrador"])
    client.headers["X-Cliente-Id"] = str(empresas[0].id_clnt)
    proyecto_a = recursos[0][0]
    proyecto_b = recursos[1][0]

    client.headers["X-Proyecto-Id"] = str(proyecto_a.id_ubccn)
    creado_a = client.post("/paneles", json={"nmbr": "Panel proyecto A"})
    assert creado_a.status_code == 201, creado_a.text
    panel_a = creado_a.json()["panel"]["id_pnl"]
    listado_a = client.get("/paneles").json()
    assert [item["id_pnl"] for item in listado_a["items"]] == [panel_a]
    assert listado_a["items"][0]["proyectos"] == [
        {"id_ubccn": proyecto_a.id_ubccn, "nmbr": proyecto_a.nmbr}
    ]
    assert listado_a["proyecto_activo"]["id_ubccn"] == proyecto_a.id_ubccn

    client.headers["X-Proyecto-Id"] = str(proyecto_b.id_ubccn)
    assert client.get("/paneles").json()["items"] == []
    assert client.get(f"/paneles/{panel_a}").status_code == 404
    creado_b = client.post("/paneles", json={"nmbr": "Panel proyecto B"})
    assert creado_b.status_code == 201, creado_b.text
    panel_b = creado_b.json()["panel"]["id_pnl"]
    assert [item["id_pnl"] for item in client.get("/paneles").json()["items"]] == [panel_b]

    del client.headers["X-Proyecto-Id"]
    assert (
        client.post(
            f"/paneles/{panel_a}/ubicaciones/lote",
            json={"ids": [proyecto_a.id_ubccn, proyecto_b.id_ubccn]},
        ).status_code
        == 201
    )

    client.headers["X-Proyecto-Id"] = str(proyecto_b.id_ubccn)
    assert {item["id_pnl"] for item in client.get("/paneles").json()["items"]} == {panel_a, panel_b}
    contenido_b = client.get(f"/paneles/{panel_a}/contenido").json()
    assert [item["id_ubccn"] for item in contenido_b["ubicaciones"]] == [proyecto_b.id_ubccn]
    assert contenido_b["ubicaciones"][0]["ultimos_valores"][0]["valor"] == 11
    assert contenido_b["proyecto_activo"]["nmbr"] == proyecto_b.nmbr
    assert {item["id_dspstv"] for item in client.get("/mediciones").json()["items"]} == {
        recursos[1][4].id_dspstv
    }
    assert (
        client.get("/mediciones/series", params={"ubicacion_id": proyecto_a.id_ubccn}).json()[
            "items"
        ]
        == []
    )
    assert client.get("/mediciones/series", params={"ubicacion_id": proyecto_b.id_ubccn}).json()[
        "items"
    ]

    client.headers["X-Proyecto-Id"] = str(proyecto_a.id_ubccn)
    assert [item["id_pnl"] for item in client.get("/paneles").json()["items"]] == [panel_a]
    contenido_a = client.get(f"/paneles/{panel_a}/contenido").json()
    assert [item["id_ubccn"] for item in contenido_a["ubicaciones"]] == [proyecto_a.id_ubccn]
    assert contenido_a["ubicaciones"][0]["ultimos_valores"][0]["valor"] == 10
    assert {item["id_dspstv"] for item in client.get("/mediciones").json()["items"]} == {
        recursos[0][4].id_dspstv
    }


@pytest.mark.parametrize("rol", ["Administrador CENERIS", "Técnico CENERIS"])
def test_ceneris_global_y_selector_filtran_todos_los_modulos(entorno, rol):
    client, _, empresas, recursos, cuentas, _ = entorno
    autenticar(client, cuentas[rol])
    assert {e["id_clnt"] for e in client.get("/empresas").json()} >= {e.id_clnt for e in empresas}
    for empresa in empresas:
        assert client.get(f"/empresas/{empresa.id_clnt}/usuarios").status_code == 200
    for recurso in recursos:
        assert (
            client.put(
                f"/dispositivos/{recurso[4].id_dspstv}", json={"nmbr": "Servicio CENERIS"}
            ).status_code
            == 200
        )
    client.headers["X-Cliente-Id"] = str(empresas[0].id_clnt)
    client.headers["X-Proyecto-Id"] = str(recursos[1][0].id_ubccn)
    esperado = recursos[1]
    assert [x["id_sd"] for x in client.get("/sedes").json()] == [esperado[1].id_sd]
    assert [x["id_dspstv"] for x in client.get("/dispositivos").json()["items"]] == [
        esperado[4].id_dspstv
    ]
    assert [x["id_ubccn"] for x in client.get("/ubicaciones/mapa").json()] == [esperado[2].id_ubccn]
    assert [x["id_cnxn"] for x in client.get("/conexiones-ftp").json()["items"]] == [
        esperado[3].id_cnxn
    ]
    assert client.get("/ingesta/metricas").json()["total"] == 1
    assert {x["id_dspstv"] for x in client.get("/mediciones").json()["items"]} == {
        esperado[4].id_dspstv
    }
    assert client.get(f"/dispositivos/{recursos[0][4].id_dspstv}").status_code == 403


def test_revocar_membresia_invalida_operacion_con_token_existente(entorno):
    client, db, _, _, cuentas, _ = entorno
    autenticar(client, cuentas["Tecnico"])
    assert client.get("/dispositivos").status_code == 200
    cuentas["Tecnico"][1].estd = "Inactivo"
    db.flush()
    assert client.get("/dispositivos").status_code == 403


def test_websocket_respeta_proyecto_del_ticket_y_revocacion_del_lector(entorno):
    from fastapi import HTTPException

    from app.routers.mapa_cliente import _acceso_ws

    client, db, empresas, recursos, cuentas, _ = entorno
    autenticar(client, cuentas["Lector"])
    identidad = {
        "_token_crudo": client.headers["Authorization"].removeprefix("Bearer "),
        "cliente_id": empresas[0].id_clnt,
        "proyecto_id": recursos[0][0].id_ubccn,
    }
    assert _acceso_ws(db, identidad) == [recursos[0][2].id_ubccn]
    db.query(UsuarioProyecto).filter(UsuarioProyecto.id_mmb == cuentas["Lector"][1].id_mmb).delete()
    db.flush()
    with pytest.raises(HTTPException) as denegado:
        _acceso_ws(db, identidad)
    assert denegado.value.status_code == 403


def test_proyectos_de_una_misma_sede_no_comparten_acceso_del_lector(entorno):
    client, db, empresas, recursos, cuentas, parametro = entorno
    sede = recursos[0][1]
    hermano = crear_ubicacion(db, sede, "Otro proyecto en la misma sede")
    conexion = crear_conexion(db, sede)
    dispositivo = crear_dispositivo(db, hermano, conexion, "Otro datalogger")
    mapear_parametro(db, dispositivo, parametro)
    crear_medicion(db, dispositivo, parametro, sede, valor=99)
    autenticar(client, cuentas["Lector"])
    esperado = recursos[0][2].id_ubccn
    assert [
        p["id_ubccn"] for p in client.get(f"/empresas/{empresas[0].id_clnt}/proyectos").json()
    ] == [esperado]
    assert [p["id_ubccn"] for p in client.get("/ubicaciones/mapa").json()] == [esperado]
    assert {d["id_dspstv"] for d in client.get("/dispositivos").json()["items"]} == {
        recursos[0][4].id_dspstv
    }
    assert {d["id_dspstv"] for d in client.get("/mediciones").json()["items"]} == {
        recursos[0][4].id_dspstv
    }
    assert client.get(f"/ubicaciones/{hermano.id_ubccn}").status_code == 403
    assert client.get(f"/dispositivos/{dispositivo.id_dspstv}").status_code == 403
    # El selector del técnico también debe aislar proyectos, aunque compartan sede.
    autenticar(client, cuentas["Tecnico"])
    client.headers["X-Proyecto-Id"] = str(esperado)
    assert [p["id_ubccn"] for p in client.get("/ubicaciones/mapa").json()] == [esperado]
    assert client.get(f"/dispositivos/{dispositivo.id_dspstv}").status_code == 403
