"""
HU10 - Listar dispositivos: tests del GET /dispositivos.

Cobertura por CA:
  CA1  tabla completa con columnas esperadas al cargar sin filtros
  CA2  búsqueda por nombre parcial/insensible y por marca
  CA3  filtro por id_ubccn, por estado y combinación de ambos
  Paginación: 10 por defecto, respeta por_pagina custom
  Permisos: 403 sin Lectura sobre "Dispositivos"
  Aislamiento por sede (HT-09 CA3) y restricción por rol (PermisoUbicacion)
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.security.dependencies import get_current_user
from app.models import ConexionFTP, Dispositivo, MapeoFormato, Ubicacion
from app.models.permiso_ubicacion import PermisoUbicacion
from app.models.suscripcion import PermisoUsuarioSede

POLIGONO_DUMMY = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}


def usuario_jwt(usuario_db, rol_nombre, sede_id=None, scope="por_sede"):
    return {"sub": str(usuario_db.id_usr), "sede_id": sede_id, "scope": scope, "rol": rol_nombre}


def agregar_permiso(db, usuario_db, sede_db, modulo, nivel, rol_db):
    db.add(
        PermisoUsuarioSede(
            id_usr=usuario_db.id_usr, id_sd=sede_db.id_sd, id_rl=rol_db.id_rl, mdl=modulo, nvl=nivel
        )
    )
    db.flush()


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def tecnico_lector(db_session, fabrica):
    """Técnico CENERIS con permiso de Lectura sobre Dispositivos en su sede."""
    rol = fabrica.rol("Técnico CENERIS")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Dispositivos", "Lectura", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )
    return sede, rol


def crear_ubicacion(db_session, sede, nombre="Ubicacion de prueba"):
    ubicacion = Ubicacion(
        id_sd=sede.id_sd, nmbr=nombre, lttd=0, lngtd=0, plgn_gjsn=POLIGONO_DUMMY,
    )
    db_session.add(ubicacion)
    db_session.flush()
    return ubicacion


def crear_conexion(db_session, sede, nombre="Datalogger Estacion A"):
    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr=nombre,
        prtcl="FTP",
        hst="127.0.0.1",
        prt=21,
        usr_ftp="usr",
        crdncl_cfrd="cifrado-de-prueba",
        rt_rmt="/data",
        frcnc_mnts=1,
        estd="Activa",
    )
    db_session.add(conexion)
    db_session.flush()
    return conexion


def crear_mapeo(db_session, sede, mrc="Campbell"):
    """mp_frmt tiene UNIQUE (id_sd, mrc, tp_trm): se reusa el mapeo si ya
    existe uno para esta sede+marca, en vez de reventar al crear varios
    dispositivos de la misma marca en un mismo test."""
    existente = (
        db_session.query(MapeoFormato)
        .filter(MapeoFormato.id_sd == sede.id_sd, MapeoFormato.mrc == mrc, MapeoFormato.tp_trm == "H")
        .first()
    )
    if existente is not None:
        return existente
    mapeo = MapeoFormato(
        id_sd=sede.id_sd, mrc=mrc, tp_trm="H", dlmtdr=",", fl_inc_dts=1, frmt_fch="%Y-%m-%d %H:%M:%S",
    )
    db_session.add(mapeo)
    db_session.flush()
    return mapeo


def crear_dispositivo(db_session, ubicacion, conexion, mapeo, nombre="CR1000-01", marca="Campbell", estado="Activo"):
    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn,
        id_cnxn=conexion.id_cnxn,
        id_mp=mapeo.id_mp,
        nmbr=nombre,
        mrc=marca,
        lttd=0,
        lngtd=0,
        estd=estado,
    )
    db_session.add(dispositivo)
    db_session.flush()
    return dispositivo


def preparar_dispositivo(db_session, sede, nombre="CR1000-01", marca="Campbell", estado="Activo", ubicacion=None):
    """Cadena completa (Ubicacion + ConexionFTP + MapeoFormato + Dispositivo).

    ubccn tiene UNIQUE (id_sd, nmbr): si no se pasa una ubicación explícita
    se crea una nueva con nombre derivado del dispositivo, para no chocar
    al llamar esta función varias veces en el mismo test/sede.
    """
    ubicacion = ubicacion or crear_ubicacion(db_session, sede, nombre=f"Ubicacion de {nombre}")
    conexion = crear_conexion(db_session, sede, nombre=f"Conexion {nombre}")
    mapeo = crear_mapeo(db_session, sede, mrc=marca)
    return crear_dispositivo(db_session, ubicacion, conexion, mapeo, nombre=nombre, marca=marca, estado=estado)


# ---------------------------------------------------------------------------
# CA1 - Tabla completa
# ---------------------------------------------------------------------------


class TestListarDispositivos:
    def test_devuelve_columnas_esperadas_sin_filtros(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        preparar_dispositivo(db_session, sede, nombre="CR1000-01")

        resp = client.get("/dispositivos")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert set(item.keys()) == {"id_dspstv", "nmbr", "mrc", "ubicacion_nombre", "estd"}
        assert item["nmbr"] == "CR1000-01"
        assert item["mrc"] == "Campbell"
        assert item["ubicacion_nombre"] == "Ubicacion de CR1000-01"
        assert item["estd"] == "Activo"

    def test_ordena_por_nombre(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        preparar_dispositivo(db_session, sede, nombre="Z-dispositivo")
        preparar_dispositivo(db_session, sede, nombre="A-dispositivo")

        resp = client.get("/dispositivos")
        nombres = [i["nmbr"] for i in resp.json()["items"]]
        assert nombres == ["A-dispositivo", "Z-dispositivo"]

    def test_denegado_sin_permiso(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )
        assert client.get("/dispositivos").status_code == 403

    def test_sin_ninguna_fila_de_permiso_devuelve_403(self, client, db_session, fabrica):
        rol = fabrica.rol("Técnico CENERIS")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )
        assert client.get("/dispositivos").status_code == 403


# ---------------------------------------------------------------------------
# CA2 - Búsqueda por nombre o marca
# ---------------------------------------------------------------------------


class TestBusqueda:
    def test_busqueda_por_nombre_parcial_e_insensible(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        preparar_dispositivo(db_session, sede, nombre="Estacion Norte")
        preparar_dispositivo(db_session, sede, nombre="Estacion Sur")

        resp = client.get("/dispositivos", params={"busqueda": "norte"})
        nombres = [i["nmbr"] for i in resp.json()["items"]]
        assert nombres == ["Estacion Norte"]

    def test_busqueda_por_marca(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        preparar_dispositivo(db_session, sede, nombre="Disp1", marca="Campbell")
        preparar_dispositivo(db_session, sede, nombre="Disp2", marca="Hobo")

        resp = client.get("/dispositivos", params={"busqueda": "hobo"})
        nombres = [i["nmbr"] for i in resp.json()["items"]]
        assert nombres == ["Disp2"]

    def test_busqueda_sin_coincidencias_devuelve_vacio(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        preparar_dispositivo(db_session, sede, nombre="Disp1")

        resp = client.get("/dispositivos", params={"busqueda": "inexistente"})
        assert resp.json()["items"] == []
        assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# CA3 - Filtro por ubicación y estado
# ---------------------------------------------------------------------------


class TestFiltros:
    def test_filtro_por_ubicacion(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        ubicacion_a = crear_ubicacion(db_session, sede, nombre="Ubicacion A")
        ubicacion_b = crear_ubicacion(db_session, sede, nombre="Ubicacion B")
        preparar_dispositivo(db_session, sede, nombre="Disp-A", ubicacion=ubicacion_a)
        preparar_dispositivo(db_session, sede, nombre="Disp-B", ubicacion=ubicacion_b)

        resp = client.get("/dispositivos", params={"id_ubccn": ubicacion_a.id_ubccn})
        nombres = [i["nmbr"] for i in resp.json()["items"]]
        assert nombres == ["Disp-A"]

    def test_filtro_por_estado(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        preparar_dispositivo(db_session, sede, nombre="Disp-Activo", estado="Activo")
        preparar_dispositivo(db_session, sede, nombre="Disp-Inactivo", estado="Inactivo")

        resp = client.get("/dispositivos", params={"estado": "Inactivo"})
        nombres = [i["nmbr"] for i in resp.json()["items"]]
        assert nombres == ["Disp-Inactivo"]

    def test_combinacion_de_ubicacion_y_estado(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        ubicacion_a = crear_ubicacion(db_session, sede, nombre="Ubicacion A")
        ubicacion_b = crear_ubicacion(db_session, sede, nombre="Ubicacion B")
        preparar_dispositivo(db_session, sede, nombre="Disp-A-Activo", estado="Activo", ubicacion=ubicacion_a)
        preparar_dispositivo(db_session, sede, nombre="Disp-A-Inactivo", estado="Inactivo", ubicacion=ubicacion_a)
        preparar_dispositivo(db_session, sede, nombre="Disp-B-Activo", estado="Activo", ubicacion=ubicacion_b)

        resp = client.get(
            "/dispositivos", params={"id_ubccn": ubicacion_a.id_ubccn, "estado": "Activo"}
        )
        nombres = [i["nmbr"] for i in resp.json()["items"]]
        assert nombres == ["Disp-A-Activo"]


# ---------------------------------------------------------------------------
# Paginación
# ---------------------------------------------------------------------------


class TestPaginacion:
    def test_por_defecto_pagina_de_10(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        for i in range(15):
            preparar_dispositivo(db_session, sede, nombre=f"Disp-{i:02d}")

        resp = client.get("/dispositivos")
        body = resp.json()
        assert body["total"] == 15
        assert body["por_pagina"] == 10
        assert len(body["items"]) == 10

    def test_respeta_por_pagina_custom(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        for i in range(15):
            preparar_dispositivo(db_session, sede, nombre=f"Disp-{i:02d}")

        resp = client.get("/dispositivos", params={"por_pagina": 5, "pagina": 2})
        body = resp.json()
        assert body["por_pagina"] == 5
        assert body["pagina"] == 2
        assert len(body["items"]) == 5


# ---------------------------------------------------------------------------
# Aislamiento por sede (HT-09 CA3)
# ---------------------------------------------------------------------------


class TestAislamientoPorSede:
    def test_usuario_por_sede_no_ve_dispositivos_de_otra_sede(self, client, db_session, tecnico_lector, fabrica):
        sede, _ = tecnico_lector
        preparar_dispositivo(db_session, sede, nombre="Disp-Sede-A")

        otra_sede = fabrica.sede()
        preparar_dispositivo(db_session, otra_sede, nombre="Disp-Sede-B")

        resp = client.get("/dispositivos")
        nombres = [i["nmbr"] for i in resp.json()["items"]]
        assert nombres == ["Disp-Sede-A"]
        assert resp.json()["total"] == 1


# ---------------------------------------------------------------------------
# Restricción por rol (Cliente Final + PermisoUbicacion)
# ---------------------------------------------------------------------------


class TestRestriccionPorRol:
    def test_cliente_final_solo_ve_dispositivos_de_su_ubicacion_asignada(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Dispositivos", "Lectura", rol)

        ubicacion_x = crear_ubicacion(db_session, sede, nombre="Ubicacion X")
        ubicacion_y = crear_ubicacion(db_session, sede, nombre="Ubicacion Y")
        preparar_dispositivo(db_session, sede, nombre="Disp-X", ubicacion=ubicacion_x)
        preparar_dispositivo(db_session, sede, nombre="Disp-Y", ubicacion=ubicacion_y)

        db_session.add(PermisoUbicacion(id_usr=usuario.id_usr, id_ubccn=ubicacion_x.id_ubccn))
        db_session.flush()

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        resp = client.get("/dispositivos")
        nombres = [i["nmbr"] for i in resp.json()["items"]]
        assert nombres == ["Disp-X"]
        assert resp.json()["total"] == 1

    def test_cliente_final_sin_ninguna_asignacion_no_ve_nada(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Dispositivos", "Lectura", rol)
        preparar_dispositivo(db_session, sede, nombre="Disp-Sin-Asignar")

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        resp = client.get("/dispositivos")
        assert resp.json()["total"] == 0
