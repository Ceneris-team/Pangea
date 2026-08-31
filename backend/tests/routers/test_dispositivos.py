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

from app.database import get_db
from app.main import app
from app.models import ConexionFTP, Dispositivo, MapeoFormato, Ubicacion
from app.models.permiso_ubicacion import PermisoUbicacion
from app.models.suscripcion import PermisoUsuarioSede
from app.security.dependencies import get_current_user

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
        id_sd=sede.id_sd,
        nmbr=nombre,
        lttd=0,
        lngtd=0,
        plgn_gjsn=POLIGONO_DUMMY,
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


def crear_mapeo(db_session, dispositivo, tp_trm="H"):
    """DEC-09: el mapeo cuelga del dispositivo. El índice único parcial
    (id_dspstv, tp_trm) WHERE estd='Activo' admite como máximo uno activo
    por tipo de trama, así que se reusa si ya existe."""
    existente = (
        db_session.query(MapeoFormato)
        .filter(
            MapeoFormato.id_dspstv == dispositivo.id_dspstv,
            MapeoFormato.tp_trm == tp_trm,
            MapeoFormato.estd == "Activo",
        )
        .first()
    )
    if existente is not None:
        return existente
    mapeo = MapeoFormato(
        id_dspstv=dispositivo.id_dspstv,
        tp_trm=tp_trm,
        dlmtdr=",",
        fl_inc_dts=1,
        frmt_fch="%Y-%m-%d %H:%M:%S",
    )
    db_session.add(mapeo)
    db_session.flush()
    return mapeo


def crear_dispositivo(
    db_session, ubicacion, conexion, nombre="CR1000-01", marca="Campbell", estado="Activo"
):
    """DEC-09: ya no recibe un mapeo. El dispositivo existe primero y el
    mapeo se le cuelga después (o nunca: es un estado válido)."""
    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn,
        id_cnxn=conexion.id_cnxn,
        nmbr=nombre,
        mrc=marca,
        lttd=0,
        lngtd=0,
        estd=estado,
    )
    db_session.add(dispositivo)
    db_session.flush()
    return dispositivo


def preparar_dispositivo(
    db_session, sede, nombre="CR1000-01", marca="Campbell", estado="Activo", ubicacion=None
):
    """Cadena completa (Ubicacion + ConexionFTP + Dispositivo).

    ubccn tiene UNIQUE (id_sd, nmbr): si no se pasa una ubicación explícita
    se crea una nueva con nombre derivado del dispositivo, para no chocar
    al llamar esta función varias veces en el mismo test/sede.

    DEC-09: no crea mapeo. Los tests que lo necesiten llaman a crear_mapeo()
    con el dispositivo ya creado.
    """
    ubicacion = ubicacion or crear_ubicacion(db_session, sede, nombre=f"Ubicacion de {nombre}")
    conexion = crear_conexion(db_session, sede, nombre=f"Conexion {nombre}")
    return crear_dispositivo(
        db_session, ubicacion, conexion, nombre=nombre, marca=marca, estado=estado
    )


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
        preparar_dispositivo(
            db_session, sede, nombre="Disp-A-Activo", estado="Activo", ubicacion=ubicacion_a
        )
        preparar_dispositivo(
            db_session, sede, nombre="Disp-A-Inactivo", estado="Inactivo", ubicacion=ubicacion_a
        )
        preparar_dispositivo(
            db_session, sede, nombre="Disp-B-Activo", estado="Activo", ubicacion=ubicacion_b
        )

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
    def test_usuario_por_sede_no_ve_dispositivos_de_otra_sede(
        self, client, db_session, tecnico_lector, fabrica
    ):
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
    def test_cliente_final_solo_ve_dispositivos_de_su_ubicacion_asignada(
        self, client, db_session, fabrica
    ):
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
    y Conexión FTP. DEC-28: lttd/lngtd son el punto GPS propio del
    dispositivo, opcionales, con fallback al centro de la Ubicación (ver
    TestPuntoGpsPropio y las decisiones en routers/dispositivos.py).

    DEC-09: el dispositivo ya no necesita un mapeo de formato previo; el
    mapeo se configura después y cuelga de él (mp_frmt.id_dspstv)."""

    def test_se_crea_sin_mapeo_de_formato_previo(self, client, db_session, tecnico_editor):
        """DEC-09: antes esto devolvía 422 ("No existe un mapeo de formato
        activo para la marca..."). Ahora es el flujo normal: primero el
        dispositivo, después su mapeo."""
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion))

        assert resp.status_code == 201
        creado = (
            db_session.query(Dispositivo)
            .filter(Dispositivo.id_dspstv == resp.json()["dispositivo"]["id_dspstv"])
            .one()
        )
        # Sin mapeos todavía: es un estado válido.
        assert (
            db_session.query(MapeoFormato)
            .filter(MapeoFormato.id_dspstv == creado.id_dspstv)
            .count()
            == 0
        )

    def test_crear_devuelve_201_y_mensaje(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion))

        assert resp.status_code == 201
        cuerpo = resp.json()
        assert cuerpo["mensaje"] == "Dispositivo añadido correctamente"
        assert cuerpo["dispositivo"]["nmbr"] == "CR1000-Nuevo"

        guardado = (
            db_session.query(Dispositivo)
            .filter(Dispositivo.id_dspstv == cuerpo["dispositivo"]["id_dspstv"])
            .one()
        )
        assert guardado.mrc == "Campbell"
        assert guardado.id_ubccn == ubicacion.id_ubccn
        assert guardado.id_cnxn == conexion.id_cnxn

    def test_queda_activo_por_defecto(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion))
        assert resp.json()["dispositivo"]["estd"] == "Activo"

    def test_modelo_es_opcional(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion))
        assert resp.status_code == 201
        assert resp.json()["dispositivo"]["mdl"] is None

    def test_guarda_el_modelo_cuando_se_envia(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion, mdl="CR1000X"))
        assert resp.json()["dispositivo"]["mdl"] == "CR1000X"

    @pytest.mark.parametrize("campo", ["nmbr", "mrc", "id_ubccn", "id_cnxn"])
    def test_campos_obligatorios_faltantes_devuelven_422(
        self, client, db_session, tecnico_editor, campo
    ):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)

        cuerpo = cuerpo_valido(ubicacion, conexion)
        del cuerpo[campo]

        assert client.post("/dispositivos", json=cuerpo).status_code == 422

    def test_lttd_lngtd_copian_los_de_la_ubicacion(self, client, db_session, tecnico_editor):
        """Decisión de diseño HU11: el dispositivo no tiene campo propio de
        punto GPS en el formulario; se copian de la Ubicación asociada."""
        sede, _ = tecnico_editor
        ubicacion = Ubicacion(
            id_sd=sede.id_sd,
            nmbr="Ubicacion con coordenadas",
            lttd=-12.046400,
            lngtd=-77.042800,
            plgn_gjsn=POLIGONO_DUMMY,
        )
        db_session.add(ubicacion)
        db_session.flush()
        conexion = crear_conexion(db_session, sede)

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion))
        assert resp.status_code == 201

        guardado = (
            db_session.query(Dispositivo)
            .filter(Dispositivo.id_dspstv == resp.json()["dispositivo"]["id_dspstv"])
            .one()
        )
        assert float(guardado.lttd) == pytest.approx(-12.046400)
        assert float(guardado.lngtd) == pytest.approx(-77.042800)

    def test_ubicacion_inexistente_devuelve_422(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        conexion = crear_conexion(db_session, sede)

        cuerpo = cuerpo_valido(crear_ubicacion(db_session, sede), conexion, id_ubccn=999999)
        assert client.post("/dispositivos", json=cuerpo).status_code == 422

    def test_ubicacion_inactiva_devuelve_422(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        ubicacion.estd = "Inactiva"
        db_session.flush()
        conexion = crear_conexion(db_session, sede)

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion))
        assert resp.status_code == 422

    def test_conexion_inexistente_devuelve_422(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)

        cuerpo = cuerpo_valido(ubicacion, crear_conexion(db_session, sede), id_cnxn=999999)
        assert client.post("/dispositivos", json=cuerpo).status_code == 422

    def test_conexion_con_dispositivo_activo_devuelve_409(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        crear_dispositivo(db_session, ubicacion, conexion, nombre="Ya-Activo")

        resp = client.post(
            "/dispositivos", json=cuerpo_valido(ubicacion, conexion, nmbr="Otro-Dispositivo")
        )
        assert resp.status_code == 409
        assert "ya tiene un dispositivo activo" in resp.json()["detail"].lower()

    def test_conexion_con_dispositivo_inactivo_permite_crear(
        self, client, db_session, tecnico_editor
    ):
        """El 409 es solo contra un dispositivo Activo: uno desactivado no
        bloquea reemplazarlo por uno nuevo en la misma conexión."""
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        crear_dispositivo(
            db_session, ubicacion, conexion, nombre="Inactivo-Viejo", estado="Inactivo"
        )

        resp = client.post(
            "/dispositivos", json=cuerpo_valido(ubicacion, conexion, nmbr="Reemplazo")
        )
        assert resp.status_code == 201

    def test_usuario_por_sede_no_crea_en_ubicacion_de_otra_sede(
        self, client, db_session, tecnico_editor, fabrica
    ):
        """HT-09 CA3: verificar_sede() bloquea aunque el usuario conozca el
        id_ubccn de una sede ajena."""
        sede, _ = tecnico_editor
        conexion = crear_conexion(db_session, sede)

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

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion))
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DEC-28 - Punto GPS propio del dispositivo (POST y PUT /dispositivos)
# ---------------------------------------------------------------------------


class TestPuntoGpsPropio:
    """DEC-28: lttd/lngtd dejan de ser una copia del centro de la Ubicación
    y pasan a ser el punto propio del dispositivo, enviable al crear y
    editable después.

    Van OPCIONALES en el body a propósito: las columnas ya existían
    llenándose por copia, así que exigirlas rompería a todo cliente y test
    que hoy crea dispositivos sin coordenadas. Sin ellas se mantiene el
    fallback de siempre.

    Fuera de alcance acá: que el punto caiga DENTRO del polígono de su
    Ubicación (R-06 del RAID) -esta tarea solo lo hace real y editable-."""

    def test_sin_coordenadas_cae_al_centro_de_la_ubicacion(
        self, client, db_session, tecnico_editor
    ):
        """El comportamiento previo a DEC-28 sigue intacto: quien no manda
        coordenadas hereda el centro de su Ubicación."""
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        ubicacion.lttd = -12.046400
        ubicacion.lngtd = -77.042800
        db_session.flush()
        conexion = crear_conexion(db_session, sede)

        resp = client.post("/dispositivos", json=cuerpo_valido(ubicacion, conexion))

        assert resp.status_code == 201
        guardado = (
            db_session.query(Dispositivo)
            .filter(Dispositivo.id_dspstv == resp.json()["dispositivo"]["id_dspstv"])
            .one()
        )
        assert float(guardado.lttd) == -12.046400
        assert float(guardado.lngtd) == -77.042800

    def test_con_coordenadas_propias_no_las_pisa_el_centro(
        self, client, db_session, tecnico_editor
    ):
        """El punto enviado se guarda tal cual: es el corazón de DEC-28.
        Antes el router ignoraba cualquier coordenada del body."""
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        ubicacion.lttd = -12.046400
        ubicacion.lngtd = -77.042800
        db_session.flush()
        conexion = crear_conexion(db_session, sede)

        resp = client.post(
            "/dispositivos",
            json=cuerpo_valido(ubicacion, conexion, lttd=-12.121200, lngtd=-77.030300),
        )

        assert resp.status_code == 201
        guardado = (
            db_session.query(Dispositivo)
            .filter(Dispositivo.id_dspstv == resp.json()["dispositivo"]["id_dspstv"])
            .one()
        )
        assert float(guardado.lttd) == -12.121200
        assert float(guardado.lngtd) == -77.030300
        # Y no quedó pegado al centro de su ubicación.
        assert float(guardado.lttd) != float(ubicacion.lttd)

    @pytest.mark.parametrize(
        "campo,valor",
        [
            ("lttd", 200),
            ("lttd", -91),
            ("lngtd", 181),
            ("lngtd", -180.5),
        ],
    )
    def test_rango_invalido_da_422(self, client, db_session, tecnico_editor, campo, valor):
        """Mismo criterio que UbicacionCrear: Pydantic responde 422 con la
        causa antes de que reviente el CheckConstraint de la BD."""
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)

        resp = client.post(
            "/dispositivos", json=cuerpo_valido(ubicacion, conexion, **{campo: valor})
        )

        assert resp.status_code == 422

    def test_la_ficha_expone_el_punto(self, client, db_session, tecnico_editor):
        """GET /dispositivos/{id} devuelve lttd/lngtd: sin eso el formulario
        de edición no tendría con qué precargar los campos."""
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        resp_crear = client.post(
            "/dispositivos",
            json=cuerpo_valido(ubicacion, conexion, lttd=-12.1212, lngtd=-77.0303),
        )
        id_dspstv = resp_crear.json()["dispositivo"]["id_dspstv"]

        resp = client.get(f"/dispositivos/{id_dspstv}")

        assert resp.status_code == 200
        assert resp.json()["lttd"] == -12.1212
        assert resp.json()["lngtd"] == -77.0303

    def test_editar_actualiza_el_punto(self, client, db_session, tecnico_editor):
        """PUT /dispositivos/{id}: antes lttd/lngtd estaban bloqueados."""
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        id_dspstv = client.post(
            "/dispositivos", json=cuerpo_valido(ubicacion, conexion)
        ).json()["dispositivo"]["id_dspstv"]

        resp = client.put(f"/dispositivos/{id_dspstv}", json={"lttd": -12.5, "lngtd": -77.5})

        assert resp.status_code == 200
        db_session.expire_all()
        guardado = db_session.query(Dispositivo).filter(Dispositivo.id_dspstv == id_dspstv).one()
        assert float(guardado.lttd) == -12.5
        assert float(guardado.lngtd) == -77.5

    def test_editar_rango_invalido_da_422(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        id_dspstv = client.post(
            "/dispositivos", json=cuerpo_valido(ubicacion, conexion)
        ).json()["dispositivo"]["id_dspstv"]

        resp = client.put(f"/dispositivos/{id_dspstv}", json={"lttd": 200})

        assert resp.status_code == 422

    def test_editar_otro_campo_no_toca_el_punto(self, client, db_session, tecnico_editor):
        """exclude_unset: un PUT que solo cambia el nombre no debe mover el
        punto GPS."""
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        id_dspstv = client.post(
            "/dispositivos",
            json=cuerpo_valido(ubicacion, conexion, lttd=-12.1212, lngtd=-77.0303),
        ).json()["dispositivo"]["id_dspstv"]

        resp = client.put(f"/dispositivos/{id_dspstv}", json={"nmbr": "Renombrado"})

        assert resp.status_code == 200
        db_session.expire_all()
        guardado = db_session.query(Dispositivo).filter(Dispositivo.id_dspstv == id_dspstv).one()
        assert guardado.nmbr == "Renombrado"
        assert float(guardado.lttd) == -12.1212
        assert float(guardado.lngtd) == -77.0303

    def test_null_explicito_no_rompe_la_columna_not_null(
        self, client, db_session, tecnico_editor
    ):
        """lttd/lngtd son NOT NULL. Un null explícito en el body pasa el
        filtro de exclude_unset (se envió, solo que vacío), así que el
        router lo descarta: 'null' significa 'no lo toques'. Sin esa
        guarda, esto reventaría como IntegrityError en el commit."""
        sede, _ = tecnico_editor
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        id_dspstv = client.post(
            "/dispositivos",
            json=cuerpo_valido(ubicacion, conexion, lttd=-12.1212, lngtd=-77.0303),
        ).json()["dispositivo"]["id_dspstv"]

        resp = client.put(f"/dispositivos/{id_dspstv}", json={"lttd": None, "lngtd": None})

        assert resp.status_code == 200
        db_session.expire_all()
        guardado = db_session.query(Dispositivo).filter(Dispositivo.id_dspstv == id_dspstv).one()
        assert float(guardado.lttd) == -12.1212
        assert float(guardado.lngtd) == -77.0303


# ---------------------------------------------------------------------------
# I-17 - Dispositivos en el mapa (GET /dispositivos/mapa)
# ---------------------------------------------------------------------------


class TestDispositivosParaMapa:
    """I-17: el mapa de HU22 pinta el punto propio de cada dispositivo
    (DEC-28) dentro del polígono de su ubicación.

    Endpoint separado de /ubicaciones/mapa a propósito: "Ubicaciones" y
    "Dispositivos" son módulos de permiso distintos (HT-03)."""

    def test_devuelve_el_punto_propio_de_cada_dispositivo(
        self, client, db_session, tecnico_lector
    ):
        """DEC-28: el punto es del dispositivo, no una copia del centro de
        su ubicación; el endpoint tiene que devolver el suyo."""
        sede, _ = tecnico_lector
        ubicacion = crear_ubicacion(db_session, sede)
        ubicacion.lttd = -12.0464
        ubicacion.lngtd = -77.0428
        conexion = crear_conexion(db_session, sede)
        dispositivo = crear_dispositivo(db_session, ubicacion, conexion, nombre="CR1000-Norte")
        dispositivo.lttd = -12.1212
        dispositivo.lngtd = -77.0303
        db_session.flush()

        respuesta = client.get("/dispositivos/mapa")

        assert respuesta.status_code == 200
        item = respuesta.json()[0]
        assert item["nmbr"] == "CR1000-Norte"
        assert item["lttd"] == -12.1212
        assert item["lngtd"] == -77.0303
        # Y no el centro de su ubicación.
        assert item["lttd"] != float(ubicacion.lttd)

    def test_trae_los_campos_del_panel(self, client, db_session, tecnico_lector):
        """El InfoWindow muestra nombre, marca y estado; id_ubccn viaja
        para relacionar el punto con su zona."""
        sede, _ = tecnico_lector
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        crear_dispositivo(db_session, ubicacion, conexion, nombre="CR1000-A", marca="Campbell")

        item = client.get("/dispositivos/mapa").json()[0]

        assert item["nmbr"] == "CR1000-A"
        assert item["mrc"] == "Campbell"
        assert item["estd"] == "Activo"
        assert item["id_ubccn"] == ubicacion.id_ubccn

    def test_incluye_los_inactivos(self, client, db_session, tecnico_lector):
        """Igual que las ubicaciones Inactivas en HU22 CA1: se muestran, en
        otro color. Filtrarlos acá dejaría al frontend sin nada que pintar
        en gris."""
        sede, _ = tecnico_lector
        ubicacion = crear_ubicacion(db_session, sede)
        con_a = crear_conexion(db_session, sede, nombre="Conexion A")
        con_b = crear_conexion(db_session, sede, nombre="Conexion B")
        crear_dispositivo(db_session, ubicacion, con_a, nombre="Activo-1", estado="Activo")
        crear_dispositivo(db_session, ubicacion, con_b, nombre="Inactivo-1", estado="Inactivo")

        estados = {d["nmbr"]: d["estd"] for d in client.get("/dispositivos/mapa").json()}

        assert estados == {"Activo-1": "Activo", "Inactivo-1": "Inactivo"}

    def test_devuelve_los_de_todas_las_ubicaciones(self, client, db_session, tecnico_lector):
        """El mapa general los muestra todos, de todas las zonas."""
        sede, _ = tecnico_lector
        primera = crear_ubicacion(db_session, sede, nombre="Zona 1")
        segunda = crear_ubicacion(db_session, sede, nombre="Zona 2")
        crear_dispositivo(
            db_session, primera, crear_conexion(db_session, sede, nombre="C1"), nombre="D1"
        )
        crear_dispositivo(
            db_session, segunda, crear_conexion(db_session, sede, nombre="C2"), nombre="D2"
        )

        items = client.get("/dispositivos/mapa").json()

        assert {d["nmbr"] for d in items} == {"D1", "D2"}
        assert {d["id_ubccn"] for d in items} == {primera.id_ubccn, segunda.id_ubccn}

    def test_sin_dispositivos_devuelve_lista_vacia(self, client, db_session, tecnico_lector):
        """No es un error: el mapa igual pinta las ubicaciones."""
        sede, _ = tecnico_lector
        crear_ubicacion(db_session, sede)

        respuesta = client.get("/dispositivos/mapa")

        assert respuesta.status_code == 200
        assert respuesta.json() == []

    def test_cliente_final_solo_ve_los_de_sus_ubicaciones(self, client, db_session, fabrica):
        """Mismo filtro por rol que listar_dispositivos (HU21): es una regla
        de acceso, no de presentación."""
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Dispositivos", "Lectura", rol)

        asignada = crear_ubicacion(db_session, sede, nombre="Asignada")
        ajena = crear_ubicacion(db_session, sede, nombre="Ajena")
        crear_dispositivo(
            db_session, asignada, crear_conexion(db_session, sede, nombre="C-mia"), nombre="Mio"
        )
        crear_dispositivo(
            db_session, ajena, crear_conexion(db_session, sede, nombre="C-ajena"), nombre="Ajeno"
        )
        db_session.add(PermisoUbicacion(id_usr=usuario.id_usr, id_ubccn=asignada.id_ubccn))
        db_session.flush()

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        nombres = [d["nmbr"] for d in client.get("/dispositivos/mapa").json()]

        assert nombres == ["Mio"]

    def test_aislamiento_por_sede(self, client, db_session, fabrica):
        """HT-09 CA3: un usuario 'por_sede' no ve dispositivos de otra sede.
        Dispositivo no tiene id_sd propio: se resuelve por su ubicación."""
        rol = fabrica.rol("Técnico CENERIS")
        sede_propia = fabrica.sede()
        sede_ajena = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede_propia, "Dispositivos", "Lectura", rol)

        propia = crear_ubicacion(db_session, sede_propia, nombre="De mi sede")
        ajena = crear_ubicacion(db_session, sede_ajena, nombre="De otra sede")
        crear_dispositivo(
            db_session, propia, crear_conexion(db_session, sede_propia, nombre="C1"), nombre="Mio"
        )
        crear_dispositivo(
            db_session, ajena, crear_conexion(db_session, sede_ajena, nombre="C2"), nombre="Ajeno"
        )

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede_propia.id_sd
        )

        nombres = [d["nmbr"] for d in client.get("/dispositivos/mapa").json()]

        assert nombres == ["Mio"]

    def test_denegado_sin_permiso_de_lectura_en_dispositivos(self, client, db_session, fabrica):
        """La razón de que este endpoint exista aparte: exige permiso sobre
        "Dispositivos". Un usuario con Lectura solo sobre "Ubicaciones"
        -que sí podría ver /ubicaciones/mapa- no pasa de acá."""
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Ubicaciones", "Lectura", rol)

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        assert client.get("/dispositivos/mapa").status_code == 403

    def test_ruta_mapa_no_la_captura_el_endpoint_de_ficha(self, client, tecnico_lector):
        """GET /dispositivos/{id_dspstv} está declarado después de /mapa; si
        se invirtiera el orden, "mapa" entraría como id y daría 422."""
        respuesta = client.get("/dispositivos/mapa")

        assert respuesta.status_code == 200
        assert isinstance(respuesta.json(), list)


# ---------------------------------------------------------------------------
# Eliminar dispositivo (DELETE /dispositivos/{id_dspstv})
# ---------------------------------------------------------------------------


class TestEliminarDispositivo:
    """Borrado lógico (estd='Inactivo'), mismo criterio que
    eliminar_conexion (routers/conexiones_ftp.py): un borrado físico
    rompería la FK de Telemetria/MapeoFormato apenas el dispositivo tenga
    historial."""

    def test_desactiva_el_dispositivo(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        dispositivo = preparar_dispositivo(db_session, sede, estado="Activo")

        resp = client.delete(f"/dispositivos/{dispositivo.id_dspstv}")

        assert resp.status_code == 200
        assert resp.json()["mensaje"] == "Dispositivo eliminado correctamente"
        db_session.refresh(dispositivo)
        assert dispositivo.estd == "Inactivo"

    def test_no_lo_borra_fisicamente(self, client, db_session, tecnico_editor):
        """Sigue existiendo en la BD (a diferencia de eliminar_parametro):
        Telemetria/MapeoFormato pueden referenciarlo."""
        sede, _ = tecnico_editor
        dispositivo = preparar_dispositivo(db_session, sede, estado="Activo")
        id_dspstv = dispositivo.id_dspstv

        client.delete(f"/dispositivos/{id_dspstv}")

        assert db_session.query(Dispositivo).filter(Dispositivo.id_dspstv == id_dspstv).first() is not None

    def test_ya_inactivo_da_409(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        dispositivo = preparar_dispositivo(db_session, sede, estado="Inactivo")

        resp = client.delete(f"/dispositivos/{dispositivo.id_dspstv}")

        assert resp.status_code == 409

    def test_no_existe_da_404(self, client, tecnico_editor):
        resp = client.delete("/dispositivos/999999")
        assert resp.status_code == 404

    def test_denegado_sin_permiso_de_edicion(self, client, db_session, tecnico_lector):
        """Lectura sola no alcanza: DELETE exige EDICION, igual que POST/PUT."""
        sede, _ = tecnico_lector
        dispositivo = preparar_dispositivo(db_session, sede, estado="Activo")

        resp = client.delete(f"/dispositivos/{dispositivo.id_dspstv}")

        assert resp.status_code == 403

    def test_usuario_por_sede_no_puede_eliminar_de_otra_sede(
        self, client, db_session, tecnico_editor, fabrica
    ):
        _sede_propia, _ = tecnico_editor
        otra_sede = fabrica.sede()
        dispositivo = preparar_dispositivo(db_session, otra_sede, estado="Activo")

        resp = client.delete(f"/dispositivos/{dispositivo.id_dspstv}")

        assert resp.status_code == 403
        db_session.refresh(dispositivo)
        assert dispositivo.estd == "Activo"
