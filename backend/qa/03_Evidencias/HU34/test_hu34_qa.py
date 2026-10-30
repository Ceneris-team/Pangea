"""
QA - HU34 Personalizar widgets del panel (PP-258 selector de tipo, PP-259
parámetro y ubicación, PP-260 guardar y renderizar, PP-261 eliminar sin
afectar datos, PP-418 validación QA).

Ejecutar desde backend/ con la BD de test migrada:
    TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/pangea_test \
    venv/Scripts/python.exe -m pytest qa/03_Evidencias/HU34/test_hu34_qa.py \
        --html=qa/03_Evidencias/HU34/pytest_hu34.html --self-contained-html
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Panel, PanelUbicacion, Parametro, PermisoUbicacion, Telemetria, Ubicacion, Widget
from app.security.dependencies import get_current_user

# Fixtures y helpers del propio proyecto (mismo patrón que los tests de HU23-HU26).
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

MSG_CREADO = "Widget creado correctamente"
MSG_ACTUALIZADO = "Widget actualizado correctamente"
MSG_ELIMINADO = "Widget eliminado correctamente"
MSG_ORDEN = "Orden de widgets guardado correctamente"
TIPOS_V1 = ["linea", "area", "tarjeta"]


@pytest.fixture()
def escenario(db_session, cliente_con_edicion_tableros):
    """Panel propio con 2 ubicaciones añadidas (HU26), 1 ubicación asignada pero
    no añadida, 2 parámetros numéricos y 1 de texto."""
    usuario, sede = cliente_con_edicion_tableros
    panel = crear_panel(db_session, usuario, sede, "Panel QA HU34")
    ubicaciones = [crear_ubicacion(db_session, sede, f"QA Estación {i}") for i in range(3)]
    for u in ubicaciones:
        db_session.add(PermisoUbicacion(id_usr=usuario.id_usr, id_ubccn=u.id_ubccn))
    for u in ubicaciones[:2]:
        db_session.add(PanelUbicacion(id_pnl=panel.id_pnl, id_ubccn=u.id_ubccn))
    temperatura = crear_parametro(db_session, "QA Temperatura")
    ph = crear_parametro(db_session, "QA pH")
    texto = Parametro(nmbr="QA Estado", undd="-", tipo_dato="texto")
    db_session.add(texto)
    db_session.flush()
    return {
        "usuario": usuario,
        "sede": sede,
        "panel": panel,
        "anadidas": ubicaciones[:2],
        "no_anadida": ubicaciones[2],
        "temperatura": temperatura,
        "ph": ph,
        "texto": texto,
    }


def ruta(panel):
    return f"/paneles/{panel.id_pnl}/widgets"


def cuerpo(e, tp="linea", parametro=None, ubicacion=None, **extra):
    return {
        "tp": tp,
        "id_prmtr": (parametro or e["temperatura"]).id_prmtr,
        "id_ubccn": (ubicacion or e["anadidas"][0]).id_ubccn,
        **extra,
    }


def crear(client, e, **kw):
    r = client.post(ruta(e["panel"]), json=cuerpo(e, **kw))
    assert r.status_code == 201, r.text
    return r.json()["widget"]


def widgets_contenido(client, panel):
    return client.get(f"/paneles/{panel.id_pnl}/contenido").json()["widgets"]


def con_telemetria(db_session, e, n=3):
    disp = preparar_dispositivo(db_session, e["sede"], nombre="QA-DL-HU34", ubicacion=e["anadidas"][0])
    for i in range(n):
        db_session.add(
            Telemetria(
                fch_hr=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=i),
                id_dspstv=disp.id_dspstv,
                id_prmtr=e["temperatura"].id_prmtr,
                id_sd=e["sede"].id_sd,
                vlr=20 + i,
            )
        )
    db_session.flush()
    return disp


# ----------------------- CA1 : tipos de widget disponibles -----------------------
@pytest.mark.parametrize("tp", TIPOS_V1)
def test_ca1_cada_tipo_v1_se_puede_crear(client, escenario, tp):
    w = crear(client, escenario, tp=tp)
    assert w["tp"] == tp


def test_ca1_tipo_fuera_del_catalogo_se_rechaza(client, escenario):
    for tp in ["medidor", "", "LINEA"]:
        assert client.post(ruta(escenario["panel"]), json=cuerpo(escenario, tp=tp)).status_code == 422


def test_obs_backend_acepta_tipo_tabla_fuera_de_v1(client, escenario):
    """La HU fija 3 tipos en v1.0; el backend acepta un 4.º («tabla»). Se registra como OBS para el PO."""
    r = client.post(ruta(escenario["panel"]), json=cuerpo(escenario, tp="tabla"))
    assert r.status_code == 201


# ----------------------- CA2 : guardar y mostrar con telemetría -----------------------
def test_ca2_guardar_devuelve_mensaje_y_configuracion(client, escenario):
    r = client.post(ruta(escenario["panel"]), json=cuerpo(escenario, tp="area"))
    assert r.status_code == 201
    body = r.json()
    assert body["mensaje"] == MSG_CREADO
    w = body["widget"]
    assert (w["tp"], w["id_prmtr"], w["id_ubccn"]) == (
        "area",
        escenario["temperatura"].id_prmtr,
        escenario["anadidas"][0].id_ubccn,
    )
    assert w["parametro_nombre"] == "QA Temperatura" and w["undd"] == "°C"


def test_ca2_widget_queda_en_el_contenido_del_panel(client, escenario):
    w = crear(client, escenario)
    assert widgets_contenido(client, escenario["panel"]) == [w]


def test_ca2_ubicacion_del_widget_trae_valor_de_telemetria_del_parametro(client, db_session, escenario):
    con_telemetria(db_session, escenario)
    w = crear(client, escenario, tp="tarjeta")
    contenido = client.get(f"/paneles/{escenario['panel'].id_pnl}/contenido").json()
    ubic = next(u for u in contenido["ubicaciones"] if u["id_ubccn"] == w["id_ubccn"])
    valores = [v for v in ubic["ultimos_valores"] if v["id_prmtr"] == w["id_prmtr"]]
    assert valores, "la tarjeta necesita el último valor del parámetro"
    assert float(valores[0]["valor"]) == 20.0


def test_ca2_parametro_y_ubicacion_de_cualquier_ubicacion_anadida(client, escenario):
    w = crear(client, escenario, parametro=escenario["ph"], ubicacion=escenario["anadidas"][1])
    assert w["id_ubccn"] == escenario["anadidas"][1].id_ubccn and w["parametro_nombre"] == "QA pH"


def test_ca2_sin_limite_de_widgets(client, escenario):
    creados = [crear(client, escenario, tp=TIPOS_V1[i % 3]) for i in range(25)]
    assert [w["pscn"] for w in creados] == list(range(25))
    assert len(widgets_contenido(client, escenario["panel"])) == 25


def test_err_ubicacion_no_anadida_al_panel_422(client, escenario):
    r = client.post(ruta(escenario["panel"]), json=cuerpo(escenario, ubicacion=escenario["no_anadida"]))
    assert r.status_code == 422
    assert r.json()["detail"] == "Añade la ubicación al panel antes de crear el widget"


def test_err_ubicacion_sin_permiso_404(client, db_session, escenario):
    ajena = crear_ubicacion(db_session, escenario["sede"], "QA Estación sin permiso")
    r = client.post(ruta(escenario["panel"]), json=cuerpo(escenario, ubicacion=ajena))
    assert r.status_code == 404


def test_err_parametro_de_texto_o_inexistente_422(client, escenario):
    r = client.post(ruta(escenario["panel"]), json=cuerpo(escenario, parametro=escenario["texto"]))
    assert r.status_code == 422
    assert r.json()["detail"] == "El widget necesita un parámetro numérico disponible"
    body = {**cuerpo(escenario), "id_prmtr": 999999}
    assert client.post(ruta(escenario["panel"]), json=body).status_code == 422


def test_err_campos_obligatorios_y_rangos_422(client, escenario):
    base = cuerpo(escenario)
    for falta in ["tp", "id_prmtr", "id_ubccn"]:
        assert client.post(ruta(escenario["panel"]), json={k: v for k, v in base.items() if k != falta}).status_code == 422
    assert client.post(ruta(escenario["panel"]), json={**base, "id_prmtr": 0}).status_code == 422
    assert client.post(ruta(escenario["panel"]), json={**base, "ancho": 3}).status_code == 422


def test_err_panel_inexistente_404(client, escenario):
    assert client.post("/paneles/999999/widgets", json=cuerpo(escenario)).status_code == 404


# ----------------------- CA3 : editar -----------------------
def test_ca3_editar_actualiza_y_muestra_mensaje(client, escenario):
    w = crear(client, escenario)
    nuevo = cuerpo(escenario, tp="tarjeta", parametro=escenario["ph"], ubicacion=escenario["anadidas"][1], ancho=2)
    r = client.put(f"{ruta(escenario['panel'])}/{w['id_wdgt']}", json=nuevo)
    assert r.status_code == 200 and r.json()["mensaje"] == MSG_ACTUALIZADO
    guardado = widgets_contenido(client, escenario["panel"])[0]
    assert (guardado["tp"], guardado["id_prmtr"], guardado["id_ubccn"], guardado["ancho"]) == (
        "tarjeta",
        escenario["ph"].id_prmtr,
        escenario["anadidas"][1].id_ubccn,
        2,
    )


def test_ca3_editar_conserva_la_posicion(client, escenario):
    a, b = crear(client, escenario), crear(client, escenario)
    client.put(f"{ruta(escenario['panel'])}/{a['id_wdgt']}", json=cuerpo(escenario, tp="area"))
    assert [w["id_wdgt"] for w in widgets_contenido(client, escenario["panel"])] == [a["id_wdgt"], b["id_wdgt"]]


def test_ca3_editar_con_ubicacion_no_anadida_422_y_no_cambia(client, escenario):
    w = crear(client, escenario)
    r = client.put(
        f"{ruta(escenario['panel'])}/{w['id_wdgt']}", json=cuerpo(escenario, ubicacion=escenario["no_anadida"])
    )
    assert r.status_code == 422
    assert widgets_contenido(client, escenario["panel"]) == [w]


def test_ca3_editar_widget_inexistente_o_de_otro_panel_404(client, db_session, escenario):
    otro = crear_panel(db_session, escenario["usuario"], escenario["sede"], "Panel QA HU34 otro")
    w = crear(client, escenario)
    assert client.put(f"{ruta(escenario['panel'])}/999999", json=cuerpo(escenario)).status_code == 404
    assert client.put(f"/paneles/{otro.id_pnl}/widgets/{w['id_wdgt']}", json=cuerpo(escenario)).status_code == 404


# ----------------------- CA4 : eliminar -----------------------
def test_ca4_eliminar_retira_y_muestra_mensaje(client, escenario):
    a, b = crear(client, escenario), crear(client, escenario, tp="area")
    r = client.delete(f"{ruta(escenario['panel'])}/{a['id_wdgt']}")
    assert r.status_code == 200 and r.json()["mensaje"] == MSG_ELIMINADO
    assert [w["id_wdgt"] for w in widgets_contenido(client, escenario["panel"])] == [b["id_wdgt"]]


def test_ca4_eliminar_no_afecta_telemetria_ubicaciones_ni_parametro(client, db_session, escenario):
    disp = con_telemetria(db_session, escenario, n=3)
    w = crear(client, escenario)
    assert client.delete(f"{ruta(escenario['panel'])}/{w['id_wdgt']}").status_code == 200
    assert db_session.query(Telemetria).filter_by(id_dspstv=disp.id_dspstv).count() == 3
    assert db_session.query(PanelUbicacion).filter_by(id_pnl=escenario["panel"].id_pnl).count() == 2
    assert db_session.get(Ubicacion, escenario["anadidas"][0].id_ubccn) is not None
    assert db_session.get(Parametro, escenario["temperatura"].id_prmtr) is not None
    contenido = client.get(f"/paneles/{escenario['panel'].id_pnl}/contenido").json()
    assert len(contenido["ubicaciones"]) == 2 and contenido["widgets"] == []


def test_ca4_eliminar_dos_veces_la_segunda_404(client, escenario):
    w = crear(client, escenario)
    assert client.delete(f"{ruta(escenario['panel'])}/{w['id_wdgt']}").status_code == 200
    assert client.delete(f"{ruta(escenario['panel'])}/{w['id_wdgt']}").status_code == 404


def test_ca4_eliminar_por_otro_panel_404_y_no_borra(client, db_session, escenario):
    otro = crear_panel(db_session, escenario["usuario"], escenario["sede"], "Panel QA HU34 otro")
    w = crear(client, escenario)
    assert client.delete(f"/paneles/{otro.id_pnl}/widgets/{w['id_wdgt']}").status_code == 404
    assert db_session.get(Widget, w["id_wdgt"]) is not None


# ----------------------- CA5 : reordenar y persistir -----------------------
def test_ca5_reordenar_persiste_al_recargar(client, db_session, escenario):
    ids = [crear(client, escenario, tp=t)["id_wdgt"] for t in TIPOS_V1]
    nuevo = [ids[2], ids[0], ids[1]]
    r = client.put(f"{ruta(escenario['panel'])}/orden", json={"ids": nuevo})
    assert r.status_code == 200 and r.json()["mensaje"] == MSG_ORDEN
    db_session.expire_all()
    assert [w["id_wdgt"] for w in widgets_contenido(client, escenario["panel"])] == nuevo
    assert [w["pscn"] for w in widgets_contenido(client, escenario["panel"])] == [0, 1, 2]


def test_ca5_orden_incompleto_duplicado_o_ajeno_422_y_no_cambia(client, escenario):
    ids = [crear(client, escenario)["id_wdgt"] for _ in range(3)]
    for malo in [ids[:2], [ids[0], ids[0], ids[1]], [*ids, 999999], [ids[0], ids[1], 999999], []]:
        assert client.put(f"{ruta(escenario['panel'])}/orden", json={"ids": malo}).status_code == 422
    assert [w["id_wdgt"] for w in widgets_contenido(client, escenario["panel"])] == ids


def test_ca5_widget_nuevo_va_al_final_tras_reordenar(client, escenario):
    a, b = crear(client, escenario)["id_wdgt"], crear(client, escenario)["id_wdgt"]
    client.put(f"{ruta(escenario['panel'])}/orden", json={"ids": [b, a]})
    c = crear(client, escenario)["id_wdgt"]
    assert [w["id_wdgt"] for w in widgets_contenido(client, escenario["panel"])] == [b, a, c]


def test_ca5_eliminar_mantiene_el_orden_de_los_demas(client, escenario):
    ids = [crear(client, escenario)["id_wdgt"] for _ in range(4)]
    client.put(f"{ruta(escenario['panel'])}/orden", json={"ids": [ids[3], ids[1], ids[2], ids[0]]})
    client.delete(f"{ruta(escenario['panel'])}/{ids[1]}")
    assert [w["id_wdgt"] for w in widgets_contenido(client, escenario["panel"])] == [ids[3], ids[2], ids[0]]


# ----------------------- Seguridad / acceso -----------------------
def test_err_sin_autenticacion_401(db_session):
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        c = TestClient(app)
        body = {"tp": "linea", "id_prmtr": 1, "id_ubccn": 1}
        assert c.post("/paneles/1/widgets", json=body).status_code == 401
        assert c.put("/paneles/1/widgets/1", json=body).status_code == 401
        assert c.put("/paneles/1/widgets/orden", json={"ids": [1]}).status_code == 401
        assert c.delete("/paneles/1/widgets/1").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_err_solo_lectura_en_tableros_403(client, db_session, fabrica, escenario):
    rol = escenario["usuario"].rol
    lector = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, lector, escenario["sede"], "Tableros", "Lectura", rol)
    propio = crear_panel(db_session, lector, escenario["sede"], "Panel del lector")
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(lector, rol.nmbr, sede_id=escenario["sede"].id_sd)
    assert client.post(f"/paneles/{propio.id_pnl}/widgets", json=cuerpo(escenario)).status_code == 403
    assert client.put(f"/paneles/{propio.id_pnl}/widgets/orden", json={"ids": []}).status_code == 403


def test_err_panel_de_otro_usuario_404_y_no_crea(client, db_session, fabrica, escenario):
    w = crear(client, escenario)
    rol = escenario["usuario"].rol
    otro = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, otro, escenario["sede"], "Tableros", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(otro, rol.nmbr, sede_id=escenario["sede"].id_sd)
    p = escenario["panel"]
    assert client.post(ruta(p), json=cuerpo(escenario)).status_code == 404
    assert client.put(f"{ruta(p)}/{w['id_wdgt']}", json=cuerpo(escenario, tp="area")).status_code == 404
    assert client.delete(f"{ruta(p)}/{w['id_wdgt']}").status_code == 404
    assert db_session.query(Widget).filter_by(id_pnl=p.id_pnl).count() == 1
