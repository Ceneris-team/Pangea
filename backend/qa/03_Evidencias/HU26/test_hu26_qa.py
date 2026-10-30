"""
QA - HU26 Añadir ubicaciones al panel (PP-219 selector, PP-220 filtro por
permisos HU 21, PP-221 asociar sin duplicados, PP-415 validación QA).

Ejecutar desde backend/ con la BD de test migrada:
    TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/pangea_test \
    venv/Scripts/python.exe -m pytest qa/03_Evidencias/HU26/test_hu26_qa.py \
        --html=qa/03_Evidencias/HU26/pytest_hu26.html --self-contained-html
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Panel, PanelUbicacion, PermisoUbicacion, Telemetria, Ubicacion, Widget
from app.security.dependencies import get_current_user

# Fixtures y helpers del propio proyecto (mismo patrón que los tests de HU23-HU25).
from tests.conftest import _engine, db_session, fabrica  # noqa: F401
from tests.routers.test_dispositivos import preparar_dispositivo
from tests.routers.test_paneles import (  # noqa: F401
    agregar_permiso,
    client,
    cliente_con_edicion_tableros,
    crear_panel,
    crear_parametro,
    crear_ubicacion,
    usuario_jwt,
)

MSG_ANADIDAS = "Ubicaciones añadidas correctamente"
MSG_RETIRADA = "Ubicación retirada del panel"


@pytest.fixture()
def escenario(db_session, cliente_con_edicion_tableros):
    """Panel propio + 3 ubicaciones asignadas al usuario (HU 21) + 1 no asignada."""
    usuario, sede = cliente_con_edicion_tableros
    panel = crear_panel(db_session, usuario, sede, "Panel QA HU26")
    asignadas = [crear_ubicacion(db_session, sede, f"QA Estación {i}") for i in range(3)]
    for u in asignadas:
        db_session.add(PermisoUbicacion(id_usr=usuario.id_usr, id_ubccn=u.id_ubccn))
    no_asignada = crear_ubicacion(db_session, sede, "QA Estación NO asignada")
    db_session.flush()
    return usuario, sede, panel, asignadas, no_asignada


def ids(ubicaciones):
    return [u.id_ubccn for u in ubicaciones]


def lote(client, panel, id_list):
    return client.post(f"/paneles/{panel.id_pnl}/ubicaciones/lote", json={"ids": id_list})


# ----------------------- CA1 : listado de ubicaciones disponibles -----------------------
def test_ca1_listado_muestra_solo_ubicaciones_asignadas(client, escenario):
    _, _, panel, asignadas, no_asignada = escenario
    r = client.get(f"/paneles/{panel.id_pnl}/ubicaciones/disponibles")
    assert r.status_code == 200
    resp = [i["id_ubccn"] for i in r.json()["items"]]
    assert sorted(resp) == sorted(ids(asignadas))
    assert no_asignada.id_ubccn not in resp


def test_ca1_listado_trae_nombre_y_va_ordenado(client, escenario):
    _, _, panel, asignadas, _ = escenario
    items = client.get(f"/paneles/{panel.id_pnl}/ubicaciones/disponibles").json()["items"]
    assert [i["nmbr"] for i in items] == sorted(u.nmbr for u in asignadas)


def test_ca1_usuario_sin_ubicaciones_asignadas_recibe_lista_vacia(client, db_session, fabrica):
    rol = fabrica.rol("Cliente Final")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Tableros", "Edición", rol)
    crear_ubicacion(db_session, sede, "QA sin permiso")
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )
    panel = crear_panel(db_session, usuario, sede, "Panel vacío")
    r = client.get(f"/paneles/{panel.id_pnl}/ubicaciones/disponibles")
    assert r.status_code == 200 and r.json()["items"] == []


# ----------------------- CA2 : agregar al panel -----------------------
def test_ca2_agregar_una_o_mas_muestra_mensaje_y_asocia(client, escenario):
    _, _, panel, asignadas, _ = escenario
    r = lote(client, panel, ids(asignadas[:2]))
    assert r.status_code == 201
    assert r.json()["mensaje"] == MSG_ANADIDAS
    contenido = client.get(f"/paneles/{panel.id_pnl}/contenido").json()
    assert {u["id_ubccn"] for u in contenido["ubicaciones"]} == set(ids(asignadas[:2]))


def test_ca2_agregar_una_sola_ubicacion_por_lote_usa_el_mensaje_del_criterio(client, escenario):
    _, _, panel, asignadas, _ = escenario
    r = lote(client, panel, ids(asignadas[:1]))
    assert r.status_code == 201 and r.json()["mensaje"] == MSG_ANADIDAS


@pytest.mark.xfail(reason="OBS-HU26: POST /ubicaciones (individual, sin uso en la UI) responde en singular", strict=True)
def test_ca2_endpoint_individual_usa_el_mensaje_del_criterio(client, escenario):
    """Observación: POST /ubicaciones (una sola) responde en singular, distinto al CA."""
    _, _, panel, asignadas, _ = escenario
    r = client.post(
        f"/paneles/{panel.id_pnl}/ubicaciones", json={"id_ubccn": asignadas[0].id_ubccn}
    )
    assert r.status_code == 201
    assert r.json()["mensaje"] == MSG_ANADIDAS


def test_ca2_no_permite_duplicar_ubicacion_en_el_mismo_panel(client, escenario):
    _, _, panel, asignadas, _ = escenario
    assert lote(client, panel, ids(asignadas[:1])).status_code == 201
    assert lote(client, panel, ids(asignadas[:1])).status_code == 409
    r = client.post(
        f"/paneles/{panel.id_pnl}/ubicaciones", json={"id_ubccn": asignadas[0].id_ubccn}
    )
    assert r.status_code == 409


def test_ca2_duplicado_dentro_del_lote_se_rechaza_y_no_asocia_nada(client, db_session, escenario):
    _, _, panel, asignadas, _ = escenario
    a = asignadas[0].id_ubccn
    assert lote(client, panel, [a, a]).status_code == 422
    assert db_session.query(PanelUbicacion).filter_by(id_pnl=panel.id_pnl).count() == 0


def test_ca2_lote_con_una_ya_asociada_es_atomico(client, db_session, escenario):
    _, _, panel, asignadas, _ = escenario
    lote(client, panel, ids(asignadas[:1]))
    assert lote(client, panel, [asignadas[0].id_ubccn, asignadas[1].id_ubccn]).status_code == 409
    assert db_session.query(PanelUbicacion).filter_by(id_pnl=panel.id_pnl).count() == 1


def test_ca2_misma_ubicacion_si_puede_estar_en_otro_panel(client, db_session, escenario):
    usuario, sede, panel, asignadas, _ = escenario
    otro = crear_panel(db_session, usuario, sede, "Segundo panel QA")
    assert lote(client, panel, ids(asignadas[:1])).status_code == 201
    assert lote(client, otro, ids(asignadas[:1])).status_code == 201


# ----------------------- Errores y seguridad -----------------------
def test_err_ubicacion_no_asignada_no_se_puede_agregar(client, db_session, escenario):
    _, _, panel, _, no_asignada = escenario
    assert lote(client, panel, [no_asignada.id_ubccn]).status_code == 404
    r = client.post(
        f"/paneles/{panel.id_pnl}/ubicaciones", json={"id_ubccn": no_asignada.id_ubccn}
    )
    assert r.status_code == 404
    assert db_session.query(PanelUbicacion).filter_by(id_pnl=panel.id_pnl).count() == 0


def test_err_lote_vacio_o_ids_invalidos(client, escenario):
    _, _, panel, _, _ = escenario
    assert lote(client, panel, []).status_code == 422
    assert lote(client, panel, [0]).status_code == 422
    assert lote(client, panel, [-5]).status_code == 422
    assert lote(client, panel, [999999]).status_code == 404
    r = client.post(f"/paneles/{panel.id_pnl}/ubicaciones/lote", json={"ids": ["x"]})
    assert r.status_code == 422


def test_err_panel_inexistente_o_ajeno(client, db_session, fabrica, escenario):
    usuario, sede, _, asignadas, _ = escenario
    assert lote(client, Panel(id_pnl=999999), ids(asignadas[:1])).status_code == 404
    ajeno = crear_panel(db_session, fabrica.usuario(rol=usuario.rol), sede, "Panel ajeno QA")
    assert lote(client, ajeno, ids(asignadas[:1])).status_code == 404
    ruta = f"/paneles/{ajeno.id_pnl}/ubicaciones/{asignadas[0].id_ubccn}"
    assert client.delete(ruta).status_code == 404
    assert client.get(f"/paneles/{ajeno.id_pnl}/ubicaciones/disponibles").status_code == 404


def test_err_sin_autenticacion_401(db_session):
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        c = TestClient(app)
        assert c.get("/paneles/1/ubicaciones/disponibles").status_code == 401
        assert c.post("/paneles/1/ubicaciones/lote", json={"ids": [1]}).status_code == 401
        assert c.delete("/paneles/1/ubicaciones/1").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_err_rol_solo_lectura_no_puede_agregar_ni_quitar(client, db_session, fabrica, escenario):
    usuario, sede, panel, asignadas, _ = escenario
    rol = usuario.rol
    lector = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, lector, sede, "Tableros", "Lectura", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        lector, rol.nmbr, sede_id=sede.id_sd
    )
    assert lote(client, panel, ids(asignadas[:1])).status_code in {403, 404}
    ruta = f"/paneles/{panel.id_pnl}/ubicaciones/{asignadas[0].id_ubccn}"
    assert client.delete(ruta).status_code in {403, 404}


# ----------------------- CA3 : vista con nombre y últimos valores -----------------------
def test_ca3_ubicacion_anadida_muestra_nombre_y_ultimos_valores(client, db_session, escenario):
    _, sede, panel, asignadas, _ = escenario
    disp = preparar_dispositivo(db_session, sede, nombre="QA-DL-01", ubicacion=asignadas[0])
    p = crear_parametro(db_session, "QA Temperatura")
    db_session.add(
        Telemetria(
            fch_hr=dt.datetime.now(dt.timezone.utc),
            id_dspstv=disp.id_dspstv,
            id_prmtr=p.id_prmtr,
            id_sd=sede.id_sd,
            vlr=23.5,
        )
    )
    db_session.flush()
    lote(client, panel, ids(asignadas[:1]))
    u = client.get(f"/paneles/{panel.id_pnl}/contenido").json()["ubicaciones"][0]
    assert u["nmbr"] == asignadas[0].nmbr
    assert u["ultima_lectura"] is not None
    assert u["ultimos_valores"], "debe traer los últimos valores de telemetría"


def test_ca3_ubicacion_sin_telemetria_aparece_con_nombre_y_sin_valores(client, escenario):
    _, _, panel, asignadas, _ = escenario
    lote(client, panel, ids(asignadas[:1]))
    u = client.get(f"/paneles/{panel.id_pnl}/contenido").json()["ubicaciones"][0]
    assert u["nmbr"] == asignadas[0].nmbr and u["ultimos_valores"] == []


# ----------------------- CA4 : quitar -----------------------
def test_ca4_quitar_retira_del_panel_y_muestra_mensaje(client, escenario):
    _, _, panel, asignadas, _ = escenario
    lote(client, panel, ids(asignadas[:2]))
    r = client.delete(f"/paneles/{panel.id_pnl}/ubicaciones/{asignadas[0].id_ubccn}")
    assert r.status_code == 200 and r.json()["mensaje"] == MSG_RETIRADA
    contenido = client.get(f"/paneles/{panel.id_pnl}/contenido").json()
    assert [u["id_ubccn"] for u in contenido["ubicaciones"]] == [asignadas[1].id_ubccn]


def test_ca4_quitar_no_elimina_telemetria_ni_registro_de_ubicacion(client, db_session, escenario):
    _, sede, panel, asignadas, _ = escenario
    disp = preparar_dispositivo(db_session, sede, nombre="QA-DL-02", ubicacion=asignadas[0])
    p = crear_parametro(db_session, "QA Humedad")
    for i in range(3):
        db_session.add(
            Telemetria(
                fch_hr=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=i),
                id_dspstv=disp.id_dspstv,
                id_prmtr=p.id_prmtr,
                id_sd=sede.id_sd,
                vlr=50 + i,
            )
        )
    db_session.flush()
    lote(client, panel, ids(asignadas[:1]))
    ruta = f"/paneles/{panel.id_pnl}/ubicaciones/{asignadas[0].id_ubccn}"
    assert client.delete(ruta).status_code == 200
    assert db_session.query(Telemetria).filter_by(id_dspstv=disp.id_dspstv).count() == 3
    assert db_session.get(Ubicacion, asignadas[0].id_ubccn) is not None


def test_ca4_quitar_ubicacion_que_no_esta_en_el_panel_404(client, escenario):
    _, _, panel, asignadas, _ = escenario
    ruta = f"/paneles/{panel.id_pnl}/ubicaciones/{asignadas[0].id_ubccn}"
    assert client.delete(ruta).status_code == 404


def test_ca4_quitar_dos_veces_la_segunda_da_404(client, escenario):
    _, _, panel, asignadas, _ = escenario
    lote(client, panel, ids(asignadas[:1]))
    ruta = f"/paneles/{panel.id_pnl}/ubicaciones/{asignadas[0].id_ubccn}"
    assert client.delete(ruta).status_code == 200
    assert client.delete(ruta).status_code == 404


def test_ca4_quitar_en_un_panel_no_afecta_a_otro_panel(client, db_session, escenario):
    usuario, sede, panel, asignadas, _ = escenario
    otro = crear_panel(db_session, usuario, sede, "Otro panel QA")
    lote(client, panel, ids(asignadas[:1]))
    lote(client, otro, ids(asignadas[:1]))
    client.delete(f"/paneles/{panel.id_pnl}/ubicaciones/{asignadas[0].id_ubccn}")
    assert db_session.query(PanelUbicacion).filter_by(id_pnl=otro.id_pnl).count() == 1


def test_ca4_ubicacion_quitada_vuelve_a_poder_agregarse(client, escenario):
    _, _, panel, asignadas, _ = escenario
    lote(client, panel, ids(asignadas[:1]))
    client.delete(f"/paneles/{panel.id_pnl}/ubicaciones/{asignadas[0].id_ubccn}")
    assert lote(client, panel, ids(asignadas[:1])).status_code == 201


def test_obs_quitar_ubicacion_borra_sus_widgets(client, db_session, escenario):
    """OBS: la HU no lo dice, pero quitar una ubicación elimina sus widgets (el modal lo avisa)."""
    _, _, panel, asignadas, _ = escenario
    lote(client, panel, ids(asignadas[:1]))
    p = crear_parametro(db_session, "QA Widget")
    client.post(
        f"/paneles/{panel.id_pnl}/widgets",
        json={"tp": "linea", "id_prmtr": p.id_prmtr, "id_ubccn": asignadas[0].id_ubccn},
    )
    assert db_session.query(Widget).filter_by(id_pnl=panel.id_pnl).count() == 1
    client.delete(f"/paneles/{panel.id_pnl}/ubicaciones/{asignadas[0].id_ubccn}")
    assert db_session.query(Widget).filter_by(id_pnl=panel.id_pnl).count() == 0
