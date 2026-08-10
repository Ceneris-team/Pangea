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


@pytest.fixture()
def tecnico_editor(db_session, fabrica):
    """Técnico CENERIS con permiso de Edición sobre Dispositivos en su
    sede, ya autenticado (HU11: POST /dispositivos exige EDICION)."""
    rol = fabrica.rol("Técnico CENERIS")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Dispositivos", "Edición", rol)
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


# ---------------------------------------------------------------------------
# HU11 - Añadir dispositivo (POST /dispositivos)
# ---------------------------------------------------------------------------


def cuerpo_valido(ubicacion, conexion, **overrides):
    cuerpo = {
        "nmbr": "CR1000-Nuevo",
        "mrc": "Campbell",
        "id_ubccn": ubicacion.id_ubccn,
        "id_cnxn": conexion.id_cnxn,
    }
    cuerpo.update(overrides)
    return cuerpo


class TestCrearDispositivo:
    """CA1/CA2: formulario con Nombre, Marca, Modelo (opcional), Ubicación
    y Conexión FTP. id_mp y lttd/lngtd se resuelven solos (ver decisiones
    de diseño documentadas en routers/dispositivos.py)."""

    def test_crear_devuelve_201_y_mensaje(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        crear_mapeo(db_session, sede, mrc="Campbell")

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion))

        assert resp.status_code == 201
        cuerpo = resp.json()
        assert cuerpo["mensaje"] == "Dispositivo añadido correctamente"
        assert cuerpo["dispositivo"]["nmbr"] == "CR1000-Nuevo"

        guardado = db_session.query(Dispositivo).filter(
            Dispositivo.id_dspstv == cuerpo["dispositivo"]["id_dspstv"]
        ).one()
        assert guardado.mrc == "Campbell"
        assert guardado.id_ubccn == ubicacion.id_ubccn
        assert guardado.id_cnxn == conexion.id_cnxn

    def test_queda_activo_por_defecto(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        crear_mapeo(db_session, sede, mrc="Campbell")

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion))
        assert resp.json()["dispositivo"]["estd"] == "Activo"

    def test_modelo_es_opcional(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        crear_mapeo(db_session, sede, mrc="Campbell")

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion))
        assert resp.status_code == 201
        assert resp.json()["dispositivo"]["mdl"] is None

    def test_guarda_el_modelo_cuando_se_envia(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        crear_mapeo(db_session, sede, mrc="Campbell")

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion, mdl="CR1000X"))
        assert resp.json()["dispositivo"]["mdl"] == "CR1000X"

    @pytest.mark.parametrize("campo", ["nmbr", "mrc", "id_ubccn", "id_cnxn"])
    def test_campos_obligatorios_faltantes_devuelven_422(self, client, db_session, tecnico_editor, campo):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        crear_mapeo(db_session, sede, mrc="Campbell")

        cuerpo = cuerpo_valido(ubicacion, conexion)
        del cuerpo[campo]

        assert client.post("/dispositivos", json=cuerpo).status_code == 422

    def test_lttd_lngtd_copian_los_de_la_ubicacion(self, client, db_session, tecnico_editor):
        """Decisión de diseño HU11: el dispositivo no tiene campo propio de
        punto GPS en el formulario; se copian de la Ubicación asociada."""
        sede, _ = tecnico_editor
        ubicacion = Ubicacion(
            id_sd=sede.id_sd, nmbr="Ubicacion con coordenadas",
            lttd=-12.046400, lngtd=-77.042800, plgn_gjsn=POLIGONO_DUMMY,
        )
        db_session.add(ubicacion)
        db_session.flush()
        conexion = crear_conexion(db_session, sede)
        crear_mapeo(db_session, sede, mrc="Campbell")

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion))
        assert resp.status_code == 201

        guardado = db_session.query(Dispositivo).filter(
            Dispositivo.id_dspstv == resp.json()["dispositivo"]["id_dspstv"]
        ).one()
        assert float(guardado.lttd) == pytest.approx(-12.046400)
        assert float(guardado.lngtd) == pytest.approx(-77.042800)

    def test_ubicacion_inexistente_devuelve_422(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        conexion = crear_conexion(db_session, sede)
        crear_mapeo(db_session, sede, mrc="Campbell")

        cuerpo = cuerpo_valido(crear_ubicacion(db_session, sede), conexion, id_ubccn=999999)
        assert client.post("/dispositivos", json=cuerpo).status_code == 422

    def test_ubicacion_inactiva_devuelve_422(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        ubicacion.estd = "Inactiva"
        db_session.flush()
        conexion = crear_conexion(db_session, sede)
        crear_mapeo(db_session, sede, mrc="Campbell")

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion))
        assert resp.status_code == 422

    def test_conexion_inexistente_devuelve_422(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        crear_mapeo(db_session, sede, mrc="Campbell")

        cuerpo = cuerpo_valido(ubicacion, crear_conexion(db_session, sede), id_cnxn=999999)
        assert client.post("/dispositivos", json=cuerpo).status_code == 422

    def test_sin_mapeo_de_formato_activo_devuelve_422(self, client, db_session, tecnico_editor):
        """No se crea ningún MapeoFormato para esta marca: HU06 no se
        configuró todavía y el POST debe fallar con causa clara, no un 500
        por FK nula al insertar id_mp."""
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion, mrc="MarcaSinMapeo"))
        assert resp.status_code == 422
        assert "mapeo" in resp.json()["detail"].lower()

    def test_conexion_con_dispositivo_activo_devuelve_409(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        mapeo = crear_mapeo(db_session, sede, mrc="Campbell")
        crear_dispositivo(db_session, ubicacion, conexion, mapeo, nombre="Ya-Activo")

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion, nmbr="Otro-Dispositivo"))
        assert resp.status_code == 409
        assert "ya tiene un dispositivo activo" in resp.json()["detail"].lower()

    def test_conexion_con_dispositivo_inactivo_permite_crear(self, client, db_session, tecnico_editor):
        """El 409 es solo contra un dispositivo Activo: uno desactivado no
        bloquea reemplazarlo por uno nuevo en la misma conexión."""
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        mapeo = crear_mapeo(db_session, sede, mrc="Campbell")
        crear_dispositivo(db_session, ubicacion, conexion, mapeo, nombre="Inactivo-Viejo", estado="Inactivo")

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion, nmbr="Reemplazo"))
        assert resp.status_code == 201

    def test_usuario_por_sede_no_crea_en_ubicacion_de_otra_sede(self, client, db_session, tecnico_editor, fabrica):
        """HT-09 CA3: verificar_sede() bloquea aunque el usuario conozca el
        id_ubccn de una sede ajena."""
        sede, _ = tecnico_editor
        conexion = crear_conexion(db_session, sede)
        crear_mapeo(db_session, sede, mrc="Campbell")

        otra_sede = fabrica.sede()
        ubicacion_ajena = crear_ubicacion(db_session, otra_sede, nombre="Ubicacion de otra sede")

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion_ajena, conexion))
        assert resp.status_code == 403

    def test_denegado_sin_permiso_de_edicion(self, client, db_session, fabrica):
        """Cliente Final con solo Lectura ve el listado (HU10) pero no
        puede añadir dispositivos."""
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Dispositivos", "Lectura", rol)
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        crear_mapeo(db_session, sede, mrc="Campbell")

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion))
        assert resp.status_code == 403

    def test_denegado_sin_ninguna_fila_de_permiso(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        crear_mapeo(db_session, sede, mrc="Campbell")

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion))
        assert resp.status_code == 403
