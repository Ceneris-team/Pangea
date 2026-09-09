"""
HU23 - Listar paneles: tests del GET /paneles.

Corre contra la Postgres real de test (ver tests/conftest.py).

Cobertura por CA:
  CA1  listado con nombre y fecha de creación de TODOS los paneles del
       usuario autenticado, ordenado por fecha de creación descendente
  CA2  el listado no expone paneles de otro usuario (no se comparten en
       v1.0)
  CA3  búsqueda por nombre/fragmento, insensible a mayúsculas
  Estado vacío: un usuario sin paneles recibe una lista vacía (el mensaje
       "Aún no tienes paneles creados" y el botón "Crear panel" son de
       frontend)
  Permisos: exige Lectura sobre "Tableros" (HT-09)

HU24 - Crear panel: tests del POST /paneles (CA2/CA3 contra el backend;
CA1/CA4 son de frontend puro, ver la sección correspondiente más abajo).
Incluye un test de integración con LOGIN REAL (POST /auth/login, no un
JWT simulado) para confirmar el fix de sede_id de HT-04 de punta a punta.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.main import limiter as limiter_app
from app.models import Panel
from app.models.suscripcion import PermisoUsuarioSede
from app.routers.auth import limiter as limiter_auth
from app.security.dependencies import get_current_user
from app.security.hashing import hash_password
from tests.conftest import Fabrica


def usuario_jwt(usuario_db, rol_nombre, sede_id=None, scope="por_sede"):
    return {"sub": str(usuario_db.id_usr), "sede_id": sede_id, "scope": scope, "rol": rol_nombre}


def agregar_permiso(db, usuario_db, sede_db, modulo, nivel, rol_db):
    db.add(
        PermisoUsuarioSede(
            id_usr=usuario_db.id_usr, id_sd=sede_db.id_sd, id_rl=rol_db.id_rl, mdl=modulo, nvl=nivel
        )
    )
    db.flush()


def crear_panel(db, usuario_db, sede_db, nombre, fch_crcn=None):
    panel = Panel(id_usr=usuario_db.id_usr, id_sd=sede_db.id_sd, nmbr=nombre)
    if fch_crcn is not None:
        panel.fch_crcn = fch_crcn
    db.add(panel)
    db.flush()
    return panel


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def client_https(db_session):
    """Mismo fixture que `client`, pero con base_url https:// y el rate
    limit de /auth/login desactivado -mismo patrón que test_auth.py-.

    La cookie de sesión que deja el login se marca Secure (ver
    _setear_cookie_sesion en routers/auth.py); un TestClient que conecta
    por http://, como el fixture `client` normal, la descarta sin
    guardarla. Solo hace falta para el test de integración con login
    real de HU24 (ver más abajo); el resto de este archivo sigue
    autenticando con dependency_overrides de get_current_user, que no
    pasa por la cookie."""
    app.dependency_overrides[get_db] = lambda: db_session
    limiter_app.enabled = False
    limiter_auth.enabled = False
    try:
        yield TestClient(app, base_url="https://testserver")
    finally:
        limiter_app.enabled = True
        limiter_auth.enabled = True
        app.dependency_overrides.clear()


@pytest.fixture()
def cliente_con_edicion_tableros(db_session, fabrica):
    """Cliente Final con Edición sobre 'Tableros' en su sede -mismo nivel
    que el seed real desde HU24 (ver seed_usuarios_prueba.py)-, ya
    autenticado. Devuelve (usuario, sede).

    Edición porque Edición ya incluye Lectura en _NIVELES_QUE_PERMITEN
    (security/permisos.py) -así que los tests de HU23 (GET, que solo
    exige Lectura) pasan igual con este fixture- y los de HU24 (POST)
    necesitan Edición de verdad.
    """
    rol = fabrica.rol("Cliente Final")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Tableros", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )
    return usuario, sede


# ---------------------------------------------------------------------------
# CA1 - Listado
# ---------------------------------------------------------------------------


def test_listar_paneles_devuelve_nombre_y_fecha(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    crear_panel(db_session, usuario, sede, "Panel de temperatura")

    respuesta = client.get("/paneles")

    assert respuesta.status_code == 200
    items = respuesta.json()["items"]
    assert len(items) == 1
    assert items[0]["nmbr"] == "Panel de temperatura"
    assert items[0]["fch_crcn"] is not None
    assert "id_pnl" in items[0]


def test_listar_paneles_ordena_por_fecha_creacion_descendente(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    ahora = datetime.now(timezone.utc)
    crear_panel(db_session, usuario, sede, "Panel más antiguo", fch_crcn=ahora - timedelta(days=2))
    crear_panel(db_session, usuario, sede, "Panel más reciente", fch_crcn=ahora)
    crear_panel(db_session, usuario, sede, "Panel intermedio", fch_crcn=ahora - timedelta(days=1))

    respuesta = client.get("/paneles")

    nombres = [item["nmbr"] for item in respuesta.json()["items"]]
    assert nombres == ["Panel más reciente", "Panel intermedio", "Panel más antiguo"]


def test_listar_paneles_usuario_sin_paneles_devuelve_lista_vacia(client, cliente_con_edicion_tableros):
    respuesta = client.get("/paneles")

    assert respuesta.status_code == 200
    assert respuesta.json()["items"] == []


# ---------------------------------------------------------------------------
# CA2 (regla de negocio) - Paneles no compartidos entre usuarios
# ---------------------------------------------------------------------------


def test_listar_paneles_no_incluye_paneles_de_otro_usuario(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    crear_panel(db_session, usuario, sede, "Panel propio")

    fabrica_otro = Fabrica(db_session)
    rol_otro = fabrica_otro.rol("Cliente Final")
    otro_usuario = fabrica_otro.usuario(rol=rol_otro)
    crear_panel(db_session, otro_usuario, sede, "Panel ajeno")

    respuesta = client.get("/paneles")

    nombres = [item["nmbr"] for item in respuesta.json()["items"]]
    assert nombres == ["Panel propio"]


# ---------------------------------------------------------------------------
# CA3 - Búsqueda por nombre
# ---------------------------------------------------------------------------


def test_buscar_paneles_por_fragmento_de_nombre(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    crear_panel(db_session, usuario, sede, "Estación Norte")
    crear_panel(db_session, usuario, sede, "Estación Sur")
    crear_panel(db_session, usuario, sede, "Resumen mensual")

    respuesta = client.get("/paneles", params={"busqueda": "estación"})

    nombres = {item["nmbr"] for item in respuesta.json()["items"]}
    assert nombres == {"Estación Norte", "Estación Sur"}


def test_buscar_paneles_es_insensible_a_mayusculas(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    crear_panel(db_session, usuario, sede, "Panel ABC")

    respuesta = client.get("/paneles", params={"busqueda": "abc"})

    assert len(respuesta.json()["items"]) == 1


def test_buscar_paneles_sin_coincidencias_devuelve_lista_vacia(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    crear_panel(db_session, usuario, sede, "Panel ABC")

    respuesta = client.get("/paneles", params={"busqueda": "xyz"})

    assert respuesta.json()["items"] == []


# ---------------------------------------------------------------------------
# Permisos (HT-09)
# ---------------------------------------------------------------------------


def test_listar_paneles_sin_permiso_sobre_tableros_devuelve_403(client, db_session, fabrica):
    rol = fabrica.rol("Cliente Final")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    # Sin agregar_permiso: ninguna fila en prms_usr_sd para "Tableros".
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )

    respuesta = client.get("/paneles")

    assert respuesta.status_code == 403


# ---------------------------------------------------------------------------
# CA2 - Abrir un panel (GET /paneles/{id_pnl})
# ---------------------------------------------------------------------------


def test_obtener_panel_devuelve_nombre_y_fecha(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros
    panel = crear_panel(db_session, usuario, sede, "Panel de temperatura")

    respuesta = client.get(f"/paneles/{panel.id_pnl}")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["id_pnl"] == panel.id_pnl
    assert cuerpo["nmbr"] == "Panel de temperatura"
    assert cuerpo["fch_crcn"] is not None


def test_obtener_panel_inexistente_devuelve_404(client, cliente_con_edicion_tableros):
    respuesta = client.get("/paneles/999999")

    assert respuesta.status_code == 404


def test_obtener_panel_de_otro_usuario_devuelve_404(client, db_session, cliente_con_edicion_tableros):
    _, sede = cliente_con_edicion_tableros

    fabrica_otro = Fabrica(db_session)
    rol_otro = fabrica_otro.rol("Cliente Final")
    otro_usuario = fabrica_otro.usuario(rol=rol_otro)
    panel_ajeno = crear_panel(db_session, otro_usuario, sede, "Panel ajeno")

    respuesta = client.get(f"/paneles/{panel_ajeno.id_pnl}")

    assert respuesta.status_code == 404


# ---------------------------------------------------------------------------
# HU24 - Crear panel: tests del POST /paneles.
#
# CA1 (mostrar el formulario) y CA4 (CANCELAR descarta sin crear nada) son
# de frontend puro -no hay nada que verificar contra el backend, CANCELAR
# ni siquiera dispara un request-. Acá se cubre CA2 (POST real: 201,
# mensaje, el panel queda en el listado del usuario) y la base de CA3 (el
# panel se crea vacío, sin ubicaciones/widgets, listo para que el
# frontend redirija a GET /paneles/{id_pnl}).
# ---------------------------------------------------------------------------


def test_crear_panel_devuelve_201_y_mensaje(client, db_session, cliente_con_edicion_tableros):
    usuario, sede = cliente_con_edicion_tableros

    respuesta = client.post("/paneles", json={"nmbr": "Panel de temperatura"})

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["mensaje"] == "Panel creado correctamente"
    assert cuerpo["panel"]["nmbr"] == "Panel de temperatura"
    assert cuerpo["panel"]["fch_crcn"] is not None

    guardado = db_session.query(Panel).filter(Panel.id_pnl == cuerpo["panel"]["id_pnl"]).one()
    assert guardado.id_usr == usuario.id_usr
    assert guardado.id_sd == sede.id_sd
    assert guardado.nmbr == "Panel de temperatura"


def test_crear_panel_lo_agrega_al_listado_del_usuario(client, db_session, cliente_con_edicion_tableros):
    """CA2: '...lo agrega al listado de paneles del usuario'."""
    client.post("/paneles", json={"nmbr": "Panel nuevo"})

    respuesta = client.get("/paneles")

    nombres = [item["nmbr"] for item in respuesta.json()["items"]]
    assert nombres == ["Panel nuevo"]


def test_crear_panel_queda_sin_ubicaciones_ni_widgets(client, db_session, cliente_con_edicion_tableros):
    """CA3: el panel nace vacío -HU26/HU34 están fuera de alcance-. Se
    verifica indirectamente: GET /paneles/{id} (que sí incluiría ese
    contenido cuando exista) hoy solo trae nombre y fecha."""
    creado = client.post("/paneles", json={"nmbr": "Panel vacío"}).json()["panel"]

    detalle = client.get(f"/paneles/{creado['id_pnl']}")

    assert detalle.status_code == 200
    assert detalle.json() == creado


def test_crear_panel_nombre_duplicado_devuelve_409(client, db_session, cliente_con_edicion_tableros):
    client.post("/paneles", json={"nmbr": "Panel repetido"})

    respuesta = client.post("/paneles", json={"nmbr": "Panel repetido"})

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "Ya tienes un panel con ese nombre"


def test_crear_panel_nombre_duplicado_es_insensible_a_mayusculas(client, cliente_con_edicion_tableros):
    client.post("/paneles", json={"nmbr": "Panel Repetido"})

    respuesta = client.post("/paneles", json={"nmbr": "panel repetido"})

    assert respuesta.status_code == 409


def test_crear_panel_incluye_solo_al_propio_usuario_en_el_chequeo_de_duplicado(
    client, db_session, cliente_con_edicion_tableros
):
    """El UNIQUE es por usuario (uq_pnl_usr_nombre), no global: otro
    usuario puede tener un panel con el mismo nombre sin chocar."""
    usuario, sede = cliente_con_edicion_tableros
    fabrica_otro = Fabrica(db_session)
    rol_otro = fabrica_otro.rol("Cliente Final")
    otro_usuario = fabrica_otro.usuario(rol=rol_otro)
    crear_panel(db_session, otro_usuario, sede, "Resumen")

    respuesta = client.post("/paneles", json={"nmbr": "Resumen"})

    assert respuesta.status_code == 201


def test_crear_panel_nombre_vacio_es_rechazado(client, cliente_con_edicion_tableros):
    respuesta = client.post("/paneles", json={"nmbr": "   "})

    assert respuesta.status_code == 422


def test_crear_panel_nombre_faltante_es_rechazado(client, cliente_con_edicion_tableros):
    respuesta = client.post("/paneles", json={})

    assert respuesta.status_code == 422


def test_crear_panel_nombre_muy_largo_es_rechazado(client, cliente_con_edicion_tableros):
    respuesta = client.post("/paneles", json={"nmbr": "A" * 101})

    assert respuesta.status_code == 422


def test_crear_panel_nombre_de_100_caracteres_es_aceptado(client, cliente_con_edicion_tableros):
    respuesta = client.post("/paneles", json={"nmbr": "A" * 100})

    assert respuesta.status_code == 201


def test_crear_panel_recorta_espacios_del_nombre(client, db_session, cliente_con_edicion_tableros):
    respuesta = client.post("/paneles", json={"nmbr": "  Panel con espacios  "})

    assert respuesta.status_code == 201
    assert respuesta.json()["panel"]["nmbr"] == "Panel con espacios"


def test_crear_panel_sin_permiso_sobre_tableros_devuelve_403(client, db_session, fabrica):
    rol = fabrica.rol("Cliente Final")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    # Sin agregar_permiso: ninguna fila en prms_usr_sd para "Tableros".
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )

    respuesta = client.post("/paneles", json={"nmbr": "Panel cualquiera"})

    assert respuesta.status_code == 403


# ---------------------------------------------------------------------------
# HU24 (regla de negocio confirmada) - Crear panel es EXCLUSIVO del rol
# Cliente Final ("YO COMO Cliente Final..."), sin importar el permiso de
# módulo que tenga otro rol sobre "Tableros". El chequeo de rol
# (ROL_CREADOR_DE_PANELES en routers/panel.py) corta ANTES de resolver la
# sede: un Administrador nunca debe ver el 422 de sede, siempre el 403 de
# rol.
# ---------------------------------------------------------------------------


def test_crear_panel_administrador_con_edicion_en_tableros_devuelve_403_por_rol(
    client, db_session, fabrica
):
    """Un Administrador con Edición sobre 'Tableros' -el mismo nivel que
    exige el endpoint- igual queda afuera: el permiso de módulo no
    alcanza, hace falta ser Cliente Final. Se verifica el mensaje de rol,
    no el 422 de sede, para confirmar que el chequeo de rol corta antes
    de llegar a _resolver_sede_panel."""
    rol = fabrica.rol("Administrador")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol, scp="global")
    agregar_permiso(db_session, usuario, sede, "Tableros", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=None, scope="global"
    )

    respuesta = client.post("/paneles", json={"nmbr": "Panel de admin"})

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "Solo Cliente Final puede crear paneles"


def test_crear_panel_tecnico_ceneris_con_edicion_en_tableros_devuelve_403_por_rol(
    client, db_session, fabrica
):
    """Mismo caso que el Administrador, con Técnico CENERIS -el otro rol
    con Edición sobre 'Tableros' en el seed real-."""
    rol = fabrica.rol("Técnico CENERIS")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol, scp="global")
    agregar_permiso(db_session, usuario, sede, "Tableros", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=None, scope="global"
    )

    respuesta = client.post("/paneles", json={"nmbr": "Panel de técnico"})

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "Solo Cliente Final puede crear paneles"


def test_crear_panel_cliente_final_scope_global_sin_sede_devuelve_422(client, db_session, fabrica):
    """Red de seguridad de _resolver_sede_panel: el seed real nunca arma
    esta combinación (Cliente Final es siempre 'por_sede'), pero el
    esquema no lo impide -y el chequeo de rol por sí solo no alcanza
    para resolver una sede. Se fuerza el caso a mano (rol correcto,
    scope/sede_id que no deberían darse juntos) para probar que, si
    ocurriera, sigue rechazando con 422 en vez de una sede adivinada."""
    rol = fabrica.rol("Cliente Final")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol, scp="global")
    agregar_permiso(db_session, usuario, sede, "Tableros", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=None, scope="global"
    )

    respuesta = client.post("/paneles", json={"nmbr": "Panel sin sede"})

    assert respuesta.status_code == 422


# ---------------------------------------------------------------------------
# HU24 - Test de integración con LOGIN REAL (no un JWT simulado).
#
# Cierra el hueco que quedó pendiente de la Fase 1 del fix de HT-04:
# ningún test hasta ahora ejercitaba el login real con el sede_id
# resuelto desde prms_usr_sd. Acá se hace POST /auth/login de verdad
# (con contraseña, igual que un usuario real) y con la cookie de sesión
# que deja esa respuesta se llama a POST /paneles real, confirmando que
# el id_sd que termina en la fila de `pnl` es el que vino del login, no
# uno fabricado a mano en el test.
# ---------------------------------------------------------------------------


def test_crear_panel_con_login_real_guarda_la_sede_del_jwt(client_https, db_session, fabrica):
    rol = fabrica.rol("Cliente Final")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol, scp="por_sede")
    usuario.cntrsn_hsh = hash_password("Pangea2026")
    # Edición, no Lectura: HU24 (regla de rol confirmada) exige Edición
    # sobre "Tableros" para POST /paneles -mismo nivel que el seed real
    # desde ese cambio (seed_usuarios_prueba.py)-.
    agregar_permiso(db_session, usuario, sede, "Tableros", "Edición", rol)
    db_session.flush()

    # Sin dependency_overrides de get_current_user: este login pasa por
    # el handler real de /auth/login, incluido _resolver_sede_id_login.
    # client_https (no client): la cookie de sesión es Secure, y un
    # cliente que conecta por http:// la descartaría sin guardarla.
    login = client_https.post(
        "/auth/login", json={"correo": usuario.crr, "contrasena": "Pangea2026"}
    )
    assert login.status_code == 200

    payload = jwt.decode(login.json()["access_token"], options={"verify_signature": False})
    assert payload["sede_id"] == sede.id_sd

    respuesta = client_https.post("/paneles", json={"nmbr": "Panel con login real"})

    assert respuesta.status_code == 201
    guardado = (
        db_session.query(Panel)
        .filter(Panel.id_pnl == respuesta.json()["panel"]["id_pnl"])
        .one()
    )
    assert guardado.id_sd == sede.id_sd
    assert guardado.id_usr == usuario.id_usr
