"""
HU08 - Agregar ubicación: tests del POST /ubicaciones.

Corren contra la Postgres real de test (ver tests/conftest.py): plgn_gjsn
es JSONB y el nombre único por sede lo garantiza un UniqueConstraint real
(uq_ubccn_sd_nombre), dos cosas que SQLite no reproduce.

Cobertura por CA:
  CA2  campos obligatorios, rangos de lat/lng, estado "Activa" por
       defecto, 201 con "Ubicación registrada correctamente", 409 si el
       nombre ya existe en la sede
  Permisos: solo con Edición sobre "Ubicaciones" (HT-09)
"""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Ubicacion
from app.models.suscripcion import PermisoUsuarioSede
from app.security.dependencies import get_current_user

# Polígono de 4 vértices, anillo exterior cerrado, en formato GeoJSON
# ([lng, lat]). Representa el contorno irregular de un terreno, que es lo
# que plgn_gjsn delimita.
POLIGONO_VALIDO = {
    "type": "Polygon",
    "coordinates": [
        [
            [-77.043000, -12.046000],
            [-77.042000, -12.046200],
            [-77.042100, -12.047000],
            [-77.043200, -12.046800],
            [-77.043000, -12.046000],
        ]
    ],
}


def usuario_jwt(usuario_db, rol_nombre, sede_id=None, scope="por_sede"):
    return {"sub": str(usuario_db.id_usr), "sede_id": sede_id, "scope": scope, "rol": rol_nombre}


def agregar_permiso(db, usuario_db, sede_db, modulo, nivel, rol_db):
    db.add(
        PermisoUsuarioSede(
            id_usr=usuario_db.id_usr, id_sd=sede_db.id_sd, id_rl=rol_db.id_rl, mdl=modulo, nvl=nivel
        )
    )
    db.flush()


def cuerpo_valido(**overrides):
    cuerpo = {
        "nmbr": "Estación Río Rímac",
        "dscrpcn": "Punto de monitoreo aguas abajo",
        "lttd": -12.0464,
        "lngtd": -77.0428,
        "plgn_gjsn": POLIGONO_VALIDO,
    }
    cuerpo.update(overrides)
    return cuerpo


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def tecnico_editor(db_session, fabrica):
    """Técnico CENERIS con Edición sobre Ubicaciones en su sede, ya
    autenticado. Devuelve la sede para los tests que la necesiten."""
    rol = fabrica.rol("Técnico CENERIS")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Ubicaciones", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )
    return sede


# ---------------------------------------------------------------------------
# CA2 - Guardar
# ---------------------------------------------------------------------------


def test_crear_ubicacion_devuelve_201_y_mensaje(client, db_session, tecnico_editor):
    respuesta = client.post("/ubicaciones", json=cuerpo_valido())

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["mensaje"] == "Ubicación registrada correctamente"

    guardada = (
        db_session.query(Ubicacion)
        .filter(Ubicacion.id_ubccn == cuerpo["ubicacion"]["id_ubccn"])
        .one()
    )
    assert guardada.nmbr == "Estación Río Rímac"
    assert guardada.id_sd == tecnico_editor.id_sd
    assert float(guardada.lttd) == pytest.approx(-12.0464)
    assert float(guardada.lngtd) == pytest.approx(-77.0428)


def test_crear_ubicacion_guarda_el_poligono_completo(client, db_session, tecnico_editor):
    """El polígono es el contorno real de la zona: tiene que llegar a
    JSONB con todos sus vértices, no reducido a un centro o a un radio."""
    respuesta = client.post("/ubicaciones", json=cuerpo_valido())

    assert respuesta.status_code == 201
    guardada = (
        db_session.query(Ubicacion)
        .filter(Ubicacion.id_ubccn == respuesta.json()["ubicacion"]["id_ubccn"])
        .one()
    )
    assert guardada.plgn_gjsn == POLIGONO_VALIDO
    assert len(guardada.plgn_gjsn["coordinates"][0]) == 5  # 4 vértices + cierre


def test_crear_ubicacion_queda_activa_por_defecto(client, db_session, tecnico_editor):
    """CA2: 'Registre con estado Activa por defecto' (server_default)."""
    respuesta = client.post("/ubicaciones", json=cuerpo_valido())

    assert respuesta.status_code == 201
    assert respuesta.json()["ubicacion"]["estd"] == "Activa"
    guardada = (
        db_session.query(Ubicacion)
        .filter(Ubicacion.id_ubccn == respuesta.json()["ubicacion"]["id_ubccn"])
        .one()
    )
    assert guardada.estd == "Activa"


def test_descripcion_es_opcional(client, tecnico_editor):
    respuesta = client.post("/ubicaciones", json=cuerpo_valido(dscrpcn=None))

    assert respuesta.status_code == 201
    assert respuesta.json()["ubicacion"]["dscrpcn"] is None


@pytest.mark.parametrize("campo", ["nmbr", "lttd", "lngtd", "plgn_gjsn"])
def test_campos_obligatorios_faltantes_devuelven_422(client, tecnico_editor, campo):
    cuerpo = cuerpo_valido()
    del cuerpo[campo]

    assert client.post("/ubicaciones", json=cuerpo).status_code == 422


def test_nombre_en_blanco_devuelve_422(client, tecnico_editor):
    assert client.post("/ubicaciones", json=cuerpo_valido(nmbr="   ")).status_code == 422


@pytest.mark.parametrize("latitud", [-90.1, 90.1, 100])
def test_latitud_fuera_de_rango_devuelve_422(client, tecnico_editor, latitud):
    assert client.post("/ubicaciones", json=cuerpo_valido(lttd=latitud)).status_code == 422


@pytest.mark.parametrize("longitud", [-180.1, 180.1, 200])
def test_longitud_fuera_de_rango_devuelve_422(client, tecnico_editor, longitud):
    assert client.post("/ubicaciones", json=cuerpo_valido(lngtd=longitud)).status_code == 422


@pytest.mark.parametrize(
    "poligono",
    [
        {},  # sin type ni coordinates
        {"type": "Point", "coordinates": [-77.04, -12.04]},  # un punto no delimita una zona
        {"type": "Polygon", "coordinates": []},  # sin anillos
        # Solo 2 vértices: no encierra un área.
        {
            "type": "Polygon",
            "coordinates": [[[-77.04, -12.04], [-77.03, -12.04], [-77.04, -12.04]]],
        },
        # Anillo abierto: el último vértice no coincide con el primero.
        {
            "type": "Polygon",
            "coordinates": [
                [[-77.04, -12.04], [-77.03, -12.04], [-77.03, -12.05], [-77.04, -12.05]]
            ],
        },
        # Vértice con latitud fuera de rango.
        {
            "type": "Polygon",
            "coordinates": [[[-77.04, -12.04], [-77.03, 95.0], [-77.03, -12.05], [-77.04, -12.04]]],
        },
    ],
)
def test_poligono_invalido_devuelve_422(client, tecnico_editor, poligono):
    assert client.post("/ubicaciones", json=cuerpo_valido(plgn_gjsn=poligono)).status_code == 422


# ---------------------------------------------------------------------------
# CA2 - Nombre único por sede (uq_ubccn_sd_nombre)
# ---------------------------------------------------------------------------


def test_nombre_duplicado_en_la_misma_sede_devuelve_409(client, tecnico_editor):
    assert client.post("/ubicaciones", json=cuerpo_valido()).status_code == 201

    repetida = client.post("/ubicaciones", json=cuerpo_valido())
    assert repetida.status_code == 409
    assert "ya existe" in repetida.json()["detail"].lower()


def test_nombre_duplicado_ignora_mayusculas(client, tecnico_editor):
    assert client.post("/ubicaciones", json=cuerpo_valido(nmbr="Planta Norte")).status_code == 201

    repetida = client.post("/ubicaciones", json=cuerpo_valido(nmbr="PLANTA NORTE"))
    assert repetida.status_code == 409


def test_mismo_nombre_en_otra_sede_si_se_permite(client, db_session, fabrica):
    """El modelo real hace el nombre único POR SEDE (uq_ubccn_sd_nombre),
    no único en todo el sistema: dos sedes distintas pueden tener cada una
    su 'Planta Norte'."""
    rol = fabrica.rol("Administrador")
    sede_a = fabrica.sede()
    sede_b = fabrica.sede()
    usuario = fabrica.usuario(rol=rol, scp="global")
    agregar_permiso(db_session, usuario, sede_a, "Ubicaciones", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=None, scope="global"
    )

    primera = client.post("/ubicaciones", json=cuerpo_valido(id_sd=sede_a.id_sd))
    segunda = client.post("/ubicaciones", json=cuerpo_valido(id_sd=sede_b.id_sd))

    assert primera.status_code == 201
    assert segunda.status_code == 201


def test_usuario_global_sin_id_sd_devuelve_422(client, db_session, fabrica):
    rol = fabrica.rol("Administrador")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol, scp="global")
    agregar_permiso(db_session, usuario, sede, "Ubicaciones", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=None, scope="global"
    )

    respuesta = client.post("/ubicaciones", json=cuerpo_valido())
    assert respuesta.status_code == 422
    assert "id_sd" in respuesta.json()["detail"]


def test_sede_inexistente_devuelve_422(client, db_session, fabrica):
    rol = fabrica.rol("Administrador")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol, scp="global")
    agregar_permiso(db_session, usuario, sede, "Ubicaciones", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=None, scope="global"
    )

    respuesta = client.post("/ubicaciones", json=cuerpo_valido(id_sd=999999))
    assert respuesta.status_code == 422
    assert "no existe" in respuesta.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Permisos: solo Administrador y Técnico CENERIS (Edición en "Ubicaciones")
# ---------------------------------------------------------------------------


def test_sin_permiso_de_edicion_devuelve_403(client, db_session, fabrica):
    """Un Cliente Final con solo Lectura ve el listado (HU07) pero no puede
    registrar ubicaciones."""
    rol = fabrica.rol("Cliente Final")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Ubicaciones", "Lectura", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )

    assert client.post("/ubicaciones", json=cuerpo_valido()).status_code == 403


def test_sin_ninguna_fila_de_permiso_devuelve_403(client, db_session, fabrica):
    rol = fabrica.rol("Cliente Final")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )

    assert client.post("/ubicaciones", json=cuerpo_valido()).status_code == 403


def test_permiso_de_edicion_en_otro_modulo_no_habilita(client, db_session, fabrica):
    """Edición sobre Ingesta no da acceso a Ubicaciones (HT-09 CA: el
    permiso es por módulo)."""
    rol = fabrica.rol("Técnico CENERIS")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Ingesta", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )

    assert client.post("/ubicaciones", json=cuerpo_valido()).status_code == 403


# ---------------------------------------------------------------------------
# CA3 - la nueva ubicación aparece en el listado (HU07), que no se tocó
# ---------------------------------------------------------------------------


def test_la_ubicacion_creada_aparece_en_el_listado(client, tecnico_editor):
    creada = client.post("/ubicaciones", json=cuerpo_valido(nmbr="Estación CA3"))
    assert creada.status_code == 201

    listado = client.get("/ubicaciones", params={"busqueda": "Estación CA3"})
    assert listado.status_code == 200
    nombres = [item["nmbr"] for item in listado.json()["items"]]
    assert "Estación CA3" in nombres
