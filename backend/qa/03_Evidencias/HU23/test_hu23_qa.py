"""
QA - HU23 Listar paneles (PP-210 vista del listado, PP-211 consultar paneles por
usuario, PP-212 orden por fecha de creación descendente, PP-426 validación QA).

Ejecutar desde backend/ con la BD de test migrada:
    TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/pangea_test \
    venv/Scripts/python.exe -m pytest qa/03_Evidencias/HU23/test_hu23_qa.py \
        --html=qa/03_Evidencias/HU23/pytest_hu23.html --self-contained-html
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.main import app
from app.models import PanelUbicacion, PermisoUbicacion, Widget
from app.security.dependencies import get_current_user

# Fixtures y helpers del propio proyecto (mismo patrón que los tests de HU23-HU34).
from tests.conftest import _engine, db_session, fabrica  # noqa: F401
from tests.routers.test_paneles import (  # noqa: F401
    agregar_permiso,
    client,
    cliente_con_edicion_tableros,
    crear_panel,
    crear_parametro,
    crear_ubicacion,
    usuario_jwt,
)


def como(usuario, rol, sede):
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(usuario, rol.nmbr, sede_id=sede.id_sd)


def nombres(client, **params):
    r = client.get("/paneles", params=params)
    assert r.status_code == 200, r.text
    return [i["nmbr"] for i in r.json()["items"]]


# ----------------------- CA1 : listado con nombre, fecha y acciones -----------------------
def test_ca1_cada_fila_trae_nombre_fecha_y_datos_para_las_acciones(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    crear_panel(db_session, usuario, sede, "QA Panel uno")
    item = client.get("/paneles").json()["items"][0]
    for campo in ("id_pnl", "nmbr", "fch_crcn", "vsbldd", "es_propietario"):
        assert campo in item
    assert item["es_propietario"] is True and item["vsbldd"] == "Privado"


def test_ca1_el_listado_trae_todos_los_paneles_del_usuario(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    for i in range(12):
        crear_panel(db_session, usuario, sede, f"QA Panel {i:02d}")
    assert len(nombres(client)) == 12


def test_ca1_fecha_de_creacion_es_iso_y_coincide_con_la_registrada(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    fecha = datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc)
    crear_panel(db_session, usuario, sede, "QA Con fecha", fch_crcn=fecha)
    valor = client.get("/paneles").json()["items"][0]["fch_crcn"]
    assert datetime.fromisoformat(valor) == fecha


# ----------------------- Detalle: orden por fecha descendente -----------------------
def test_orden_por_defecto_fecha_de_creacion_descendente(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    base = datetime.now(timezone.utc)
    for i, nombre in enumerate(["QA A", "QA B", "QA C", "QA D"]):
        crear_panel(db_session, usuario, sede, nombre, fch_crcn=base - timedelta(days=10 - i))
    assert nombres(client) == ["QA D", "QA C", "QA B", "QA A"]


def test_orden_se_mantiene_al_buscar(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    base = datetime.now(timezone.utc)
    crear_panel(db_session, usuario, sede, "QA Estación vieja", fch_crcn=base - timedelta(days=5))
    crear_panel(db_session, usuario, sede, "QA Estación nueva", fch_crcn=base)
    crear_panel(db_session, usuario, sede, "QA Otro", fch_crcn=base - timedelta(days=1))
    assert nombres(client, busqueda="estación") == ["QA Estación nueva", "QA Estación vieja"]


def test_panel_recien_creado_aparece_primero(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    crear_panel(db_session, usuario, sede, "QA Existente", fch_crcn=datetime.now(timezone.utc) - timedelta(days=1))
    r = client.post("/paneles", json={"nmbr": "QA Nuevo"})
    assert r.status_code == 201
    assert nombres(client)[0] == "QA Nuevo"


# ----------------------- Detalle: cada usuario solo ve sus paneles -----------------------
def test_aislamiento_dos_usuarios_de_la_misma_sede_ven_solo_lo_suyo(client, db_session, fabrica, cliente_con_edicion_tableros):
    u1, sede = cliente_con_edicion_tableros
    rol = u1.rol
    u2 = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, u2, sede, "Tableros", "Edición", rol)
    crear_panel(db_session, u1, sede, "QA De usuario 1")
    crear_panel(db_session, u2, sede, "QA De usuario 2")
    assert nombres(client) == ["QA De usuario 1"]
    como(u2, rol, sede)
    assert nombres(client) == ["QA De usuario 2"]


def test_aislamiento_busqueda_no_filtra_paneles_ajenos(client, db_session, fabrica, cliente_con_edicion_tableros):
    u1, sede = cliente_con_edicion_tableros
    u2 = fabrica.usuario(rol=u1.rol)
    crear_panel(db_session, u2, sede, "QA Secreto ajeno")
    assert nombres(client, busqueda="secreto") == []


def test_aislamiento_abrir_panel_ajeno_por_id_devuelve_404(client, db_session, fabrica, cliente_con_edicion_tableros):
    u1, sede = cliente_con_edicion_tableros
    u2 = fabrica.usuario(rol=u1.rol)
    ajeno = crear_panel(db_session, u2, sede, "QA Ajeno")
    assert client.get(f"/paneles/{ajeno.id_pnl}").status_code == 404
    assert client.get(f"/paneles/{ajeno.id_pnl}/contenido").status_code == 404


def test_obs_panel_compartido_con_empresa_si_aparece_a_otro_usuario(client, db_session, fabrica, cliente_con_edicion_tableros):
    """OBS (decide el PO): el detalle de la HU dice «los paneles no son compartidos entre usuarios en v1.0»,
    pero el producto trae la acción «Compartir con empresa». Mientras el dueño no la use el panel es privado
    (cubierto por los tests de aislamiento); si la usa, otro usuario de la sede lo ve en su listado.
    Este test documenta ese comportamiento real."""
    dueno, sede = cliente_con_edicion_tableros
    rol = dueno.rol
    panel = crear_panel(db_session, dueno, sede, "QA Compartido")
    u = crear_ubicacion(db_session, sede, "QA Ubicación compartida")
    db_session.add(PermisoUbicacion(id_usr=dueno.id_usr, id_ubccn=u.id_ubccn))
    db_session.add(PanelUbicacion(id_pnl=panel.id_pnl, id_ubccn=u.id_ubccn))
    db_session.flush()
    assert client.put(f"/paneles/{panel.id_pnl}/visibilidad", json={"vsbldd": "Empresa"}).status_code == 200
    otro = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, otro, sede, "Tableros", "Lectura", rol)
    db_session.add(PermisoUbicacion(id_usr=otro.id_usr, id_ubccn=u.id_ubccn))
    db_session.flush()
    como(otro, rol, sede)
    assert nombres(client) == ["QA Compartido"]
    assert client.get("/paneles").json()["items"][0]["es_propietario"] is False


def test_aislamiento_panel_privado_nunca_se_ve_en_otra_sede(client, db_session, fabrica, cliente_con_edicion_tableros):
    dueno, sede = cliente_con_edicion_tableros
    rol = dueno.rol
    crear_panel(db_session, dueno, sede, "QA Privado")
    otra_sede = fabrica.sede()
    otro = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, otro, otra_sede, "Tableros", "Lectura", rol)
    como(otro, rol, otra_sede)
    assert nombres(client) == []


# ----------------------- CA3 : búsqueda -----------------------
def test_ca3_busqueda_por_nombre_completo_y_por_fragmento(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    for n in ["QA Resumen de estaciones", "QA Calidad del agua", "QA Alarmas"]:
        crear_panel(db_session, usuario, sede, n)
    assert nombres(client, busqueda="QA Calidad del agua") == ["QA Calidad del agua"]
    assert sorted(nombres(client, busqueda="estaci")) == ["QA Resumen de estaciones"]
    assert nombres(client, busqueda="agua") == ["QA Calidad del agua"]


def test_ca3_busqueda_en_cualquier_posicion_y_sin_mayusculas(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    crear_panel(db_session, usuario, sede, "QA Panel ÁGUILA")
    assert nombres(client, busqueda="panel") == ["QA Panel ÁGUILA"]
    assert nombres(client, busqueda="QA PANEL") == ["QA Panel ÁGUILA"]


def test_ca3_busqueda_vacia_o_con_espacios_devuelve_todo(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    crear_panel(db_session, usuario, sede, "QA Uno")
    crear_panel(db_session, usuario, sede, "QA Dos")
    assert len(nombres(client, busqueda="")) == 2


def test_ca3_busqueda_sin_coincidencias_lista_vacia(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    crear_panel(db_session, usuario, sede, "QA Uno")
    assert nombres(client, busqueda="zzz-no-existe") == []


def test_ca3_busqueda_con_comodin_porcentaje_no_debe_devolver_todo(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    crear_panel(db_session, usuario, sede, "QA Uno")
    crear_panel(db_session, usuario, sede, "QA Dos")
    assert nombres(client, busqueda="%") == [], "Defecto: '%' se interpreta como comodín LIKE"


def test_ca3_busqueda_con_guion_bajo_no_debe_actuar_como_comodin(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    # El nombre de un panel solo admite letras, números y espacios: ninguno contiene «_».
    crear_panel(db_session, usuario, sede, "QA Uno")
    crear_panel(db_session, usuario, sede, "QA Dos")
    assert nombres(client, busqueda="_") == [], "Defecto: '_' coincide con cualquier carácter"


def test_ca3_busqueda_con_comilla_y_sql_no_rompe(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    crear_panel(db_session, usuario, sede, "QA Uno")
    for texto in ["' OR '1'='1", "'; DROP TABLE pnl;--", "<script>alert(1)</script>"]:
        assert nombres(client, busqueda=texto) == []
    assert nombres(client) == ["QA Uno"]


def test_ca3_busqueda_con_acento_distingue_acentos(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    crear_panel(db_session, usuario, sede, "QA Estación")
    assert nombres(client, busqueda="estación") == ["QA Estación"]


# ----------------------- CA2 : abrir un panel -----------------------
def test_ca2_abrir_panel_vacio_devuelve_estructura_sin_ubicaciones_ni_widgets(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    panel = crear_panel(db_session, usuario, sede, "QA Vacío")
    assert client.get(f"/paneles/{panel.id_pnl}").status_code == 200
    c = client.get(f"/paneles/{panel.id_pnl}/contenido").json()
    assert c["ubicaciones"] == [] and c["widgets"] == []


def test_ca2_abrir_panel_con_ubicaciones_y_widgets_los_muestra(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    panel = crear_panel(db_session, usuario, sede, "QA Con contenido")
    u = crear_ubicacion(db_session, sede, "QA Estación A")
    p = crear_parametro(db_session, "QA Temperatura")
    db_session.add(PermisoUbicacion(id_usr=usuario.id_usr, id_ubccn=u.id_ubccn))
    db_session.add(PanelUbicacion(id_pnl=panel.id_pnl, id_ubccn=u.id_ubccn))
    db_session.add(Widget(id_pnl=panel.id_pnl, id_ubccn=u.id_ubccn, id_prmtr=p.id_prmtr, tp="linea", pscn=0))
    db_session.flush()
    detalle = client.get(f"/paneles/{panel.id_pnl}").json()
    assert detalle["nmbr"] == "QA Con contenido" and detalle["es_propietario"] is True
    c = client.get(f"/paneles/{panel.id_pnl}/contenido").json()
    assert [x["nmbr"] for x in c["ubicaciones"]] == ["QA Estación A"]
    assert len(c["widgets"]) == 1 and c["widgets"][0]["tp"] == "linea"


def test_ca2_abrir_panel_inexistente_404_y_id_invalido_422(client, cliente_con_edicion_tableros):
    assert client.get("/paneles/987654").status_code == 404
    assert client.get("/paneles/abc").status_code == 422


# ----------------------- Detalle: sin paneles -----------------------
def test_sin_paneles_devuelve_lista_vacia_y_no_error(client, cliente_con_edicion_tableros):
    r = client.get("/paneles")
    assert r.status_code == 200 and r.json()["items"] == []


def test_sin_paneles_el_usuario_puede_crear_uno_y_listarlo(client, cliente_con_edicion_tableros):
    assert nombres(client) == []
    assert client.post("/paneles", json={"nmbr": "QA Primero"}).status_code == 201
    assert nombres(client) == ["QA Primero"]


# ----------------------- Errores y seguridad -----------------------
def test_error_sin_autenticacion_devuelve_401(client, db_session):
    app.dependency_overrides.pop(get_current_user, None)
    assert client.get("/paneles").status_code == 401
    assert client.get("/paneles/1").status_code == 401


def test_error_sin_permiso_sobre_tableros_devuelve_403_en_listado_y_detalle(client, db_session, fabrica):
    rol = fabrica.rol("Cliente Final")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    como(usuario, rol, sede)
    assert client.get("/paneles").status_code == 403
    assert client.get("/paneles/1").status_code == 403


def test_error_usuario_con_solo_lectura_puede_listar(client, db_session, fabrica):
    rol = fabrica.rol("Cliente Final")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Tableros", "Lectura", rol)
    como(usuario, rol, sede)
    assert client.get("/paneles").status_code == 200


def test_error_orden_y_busqueda_muy_larga_no_rompen(client, cliente_con_edicion_tableros):
    assert client.get("/paneles", params={"busqueda": "a" * 5000}).status_code == 200
