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
from app.models import ConexionFTP, Dispositivo, Ubicacion
from app.models.permiso_ubicacion import PermisoUbicacion
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


# ---------------------------------------------------------------------------
# HU22 - Ver ubicaciones en mapa (GET /ubicaciones/mapa)
# ---------------------------------------------------------------------------


def crear_ubicacion_directa(db_session, sede, nombre, estado="Activa"):
    """Ubicación insertada por ORM, sin pasar por el POST: estos tests
    verifican la LECTURA del mapa, no el alta."""
    ubicacion = Ubicacion(
        id_sd=sede.id_sd,
        nmbr=nombre,
        dscrpcn=f"Descripción de {nombre}",
        lttd=-12.0464,
        lngtd=-77.0428,
        plgn_gjsn=POLIGONO_VALIDO,
        estd=estado,
    )
    db_session.add(ubicacion)
    db_session.flush()
    return ubicacion


def crear_dispositivo_en(db_session, ubicacion, sede, nombre):
    """Un dispositivo colgado de esa ubicación, con su conexión FTP propia
    (cnxn_ftp es NOT NULL en dspstv)."""
    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr=f"Conexion {nombre}",
        prtcl="FTP",
        hst="127.0.0.1",
        prt=21,
        usr_ftp="usr",
        crdncl_cfrd="cifrado-de-prueba",
        rt_rmt="/data",
        frcnc_mnts=15,
        estd="Activa",
    )
    db_session.add(conexion)
    db_session.flush()

    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn,
        id_cnxn=conexion.id_cnxn,
        nmbr=nombre,
        mrc="Campbell",
        lttd=-12.0464,
        lngtd=-77.0428,
        estd="Activo",
    )
    db_session.add(dispositivo)
    db_session.flush()
    return dispositivo


def test_mapa_devuelve_el_poligono_y_el_punto(client, db_session, tecnico_editor):
    """CA1: el mapa necesita el punto (marcador) y el polígono (contorno)
    en la misma respuesta, sin pedir el detalle de cada ubicación."""
    sede = tecnico_editor
    crear_ubicacion_directa(db_session, sede, "Estación Norte")

    respuesta = client.get("/ubicaciones/mapa")

    assert respuesta.status_code == 200
    item = respuesta.json()[0]
    assert item["nmbr"] == "Estación Norte"
    assert item["lttd"] == -12.0464
    assert item["lngtd"] == -77.0428
    assert item["plgn_gjsn"] == POLIGONO_VALIDO


def test_mapa_cuenta_los_dispositivos_de_cada_ubicacion(client, db_session, tecnico_editor):
    """CA2: el panel emergente muestra "la cantidad de dispositivos
    asociados"; cada ubicación cuenta los suyos, no los de la vecina."""
    sede = tecnico_editor
    con_dos = crear_ubicacion_directa(db_session, sede, "Con dos")
    con_uno = crear_ubicacion_directa(db_session, sede, "Con uno")
    crear_dispositivo_en(db_session, con_dos, sede, "CR1000-A")
    crear_dispositivo_en(db_session, con_dos, sede, "CR1000-B")
    crear_dispositivo_en(db_session, con_uno, sede, "CR1000-C")

    por_nombre = {u["nmbr"]: u for u in client.get("/ubicaciones/mapa").json()}

    assert por_nombre["Con dos"]["dispositivos_count"] == 2
    assert por_nombre["Con uno"]["dispositivos_count"] == 1


def test_ubicacion_sin_dispositivos_aparece_con_cero(client, db_session, tecnico_editor):
    """El LEFT JOIN importa: una ubicación recién creada tiene que salir en
    el mapa igual, con 0. Con un INNER JOIN desaparecería del mapa."""
    sede = tecnico_editor
    crear_ubicacion_directa(db_session, sede, "Recién creada")

    items = client.get("/ubicaciones/mapa").json()

    assert len(items) == 1
    assert items[0]["dispositivos_count"] == 0


def test_mapa_incluye_las_inactivas(client, db_session, tecnico_editor):
    """CA1 pide "todas las ubicaciones registradas" y los detalles de la HU
    piden pintar las Inactivas en gris: si el endpoint las filtrara, el
    frontend no tendría nada que pintar de ese color."""
    sede = tecnico_editor
    crear_ubicacion_directa(db_session, sede, "Activa 1", estado="Activa")
    crear_ubicacion_directa(db_session, sede, "Inactiva 1", estado="Inactiva")

    estados = {u["nmbr"]: u["estd"] for u in client.get("/ubicaciones/mapa").json()}

    assert estados == {"Activa 1": "Activa", "Inactiva 1": "Inactiva"}


def test_mapa_trae_nombre_descripcion_y_estado(client, db_session, tecnico_editor):
    """CA2: los otros tres datos del panel emergente."""
    sede = tecnico_editor
    crear_ubicacion_directa(db_session, sede, "Estación Sur")

    item = client.get("/ubicaciones/mapa").json()[0]

    assert item["nmbr"] == "Estación Sur"
    assert item["dscrpcn"] == "Descripción de Estación Sur"
    assert item["estd"] == "Activa"


def test_cliente_final_solo_ve_sus_ubicaciones_asignadas(client, db_session, fabrica):
    """El filtro por rol de listar_ubicaciones (HU21) se mantiene: es una
    regla de acceso, no de presentación. Un Cliente Final no ve en el mapa
    ubicaciones que no le fueron asignadas."""
    rol = fabrica.rol("Cliente Final")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Ubicaciones", "Lectura", rol)

    asignada = crear_ubicacion_directa(db_session, sede, "Asignada")
    crear_ubicacion_directa(db_session, sede, "Ajena")
    db_session.add(PermisoUbicacion(id_usr=usuario.id_usr, id_ubccn=asignada.id_ubccn))
    db_session.flush()

    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )

    nombres = [u["nmbr"] for u in client.get("/ubicaciones/mapa").json()]

    assert nombres == ["Asignada"]


def test_mapa_denegado_sin_permiso_de_lectura(client, db_session, fabrica):
    rol = fabrica.rol("Cliente Final")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )

    assert client.get("/ubicaciones/mapa").status_code == 403


def test_ruta_mapa_no_la_captura_el_endpoint_de_detalle(client, tecnico_editor):
    """GET /ubicaciones/{id_ubccn} está declarado después de /mapa; si se
    invirtiera el orden, "mapa" entraría como id y esto daría 422."""
    respuesta = client.get("/ubicaciones/mapa")

    assert respuesta.status_code == 200
    assert isinstance(respuesta.json(), list)


# ---------------------------------------------------------------------------
# HU08 (ampliación) - Editar ubicación (PUT /ubicaciones/{id_ubccn})
# ---------------------------------------------------------------------------


OTRO_POLIGONO = {
    "type": "Polygon",
    "coordinates": [
        [
            [-77.060000, -12.030000],
            [-77.058000, -12.030000],
            [-77.058000, -12.028000],
            [-77.060000, -12.028000],
            [-77.060000, -12.030000],
        ]
    ],
}


def crear_para_editar(client, **overrides):
    """Crea una ubicación vía POST y devuelve su id, para editarla."""
    respuesta = client.post("/ubicaciones", json=cuerpo_valido(**overrides))
    assert respuesta.status_code == 201
    return respuesta.json()["ubicacion"]["id_ubccn"]


def test_editar_actualiza_los_campos(client, db_session, tecnico_editor):
    id_ubccn = crear_para_editar(client)

    respuesta = client.put(
        f"/ubicaciones/{id_ubccn}",
        json={
            "nmbr": "Estación Renombrada",
            "dscrpcn": "Nueva descripción",
            "lttd": -12.1,
            "lngtd": -77.1,
            "plgn_gjsn": OTRO_POLIGONO,
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["mensaje"] == "Ubicación actualizada correctamente"

    db_session.expire_all()
    guardada = db_session.query(Ubicacion).filter(Ubicacion.id_ubccn == id_ubccn).one()
    assert guardada.nmbr == "Estación Renombrada"
    assert guardada.dscrpcn == "Nueva descripción"
    assert float(guardada.lttd) == pytest.approx(-12.1)
    assert float(guardada.lngtd) == pytest.approx(-77.1)
    assert guardada.plgn_gjsn == OTRO_POLIGONO


def test_editar_cambia_el_estado(client, db_session, tecnico_editor):
    """El estado se edita desde este mismo formulario; es lo que pinta el
    marcador gris del mapa (HU22 CA1)."""
    id_ubccn = crear_para_editar(client)

    respuesta = client.put(f"/ubicaciones/{id_ubccn}", json={"estd": "Inactiva"})

    assert respuesta.status_code == 200
    assert respuesta.json()["ubicacion"]["estd"] == "Inactiva"
    db_session.expire_all()
    guardada = db_session.query(Ubicacion).filter(Ubicacion.id_ubccn == id_ubccn).one()
    assert guardada.estd == "Inactiva"


def test_estado_invalido_devuelve_422(client, tecnico_editor):
    """La columna es un String(20) sin CHECK: sin el validador entraría
    cualquier texto y el filtro del listado dejaría de encontrarla."""
    id_ubccn = crear_para_editar(client)

    respuesta = client.put(f"/ubicaciones/{id_ubccn}", json={"estd": "Archivada"})

    assert respuesta.status_code == 422


def test_guardar_el_mismo_nombre_sin_cambios_no_choca_consigo_misma(
    client, db_session, tecnico_editor
):
    """La unicidad por sede tiene que excluir el propio registro: si no,
    abrir el formulario y guardar sin tocar el nombre daría 409."""
    id_ubccn = crear_para_editar(client)

    respuesta = client.put(
        f"/ubicaciones/{id_ubccn}",
        json={"nmbr": "Estación Río Rímac", "dscrpcn": "Solo cambia la descripción"},
    )

    assert respuesta.status_code == 200
    db_session.expire_all()
    guardada = db_session.query(Ubicacion).filter(Ubicacion.id_ubccn == id_ubccn).one()
    assert guardada.dscrpcn == "Solo cambia la descripción"


def test_nombre_de_otra_ubicacion_de_la_misma_sede_devuelve_409(client, tecnico_editor):
    crear_para_editar(client, nmbr="Estación Norte")
    id_segunda = crear_para_editar(client, nmbr="Estación Sur")

    respuesta = client.put(f"/ubicaciones/{id_segunda}", json={"nmbr": "Estación Norte"})

    assert respuesta.status_code == 409
    assert "Ya existe una ubicación con ese nombre" in respuesta.json()["detail"]


def test_nombre_duplicado_ignora_mayusculas(client, tecnico_editor):
    crear_para_editar(client, nmbr="Estación Norte")
    id_segunda = crear_para_editar(client, nmbr="Estación Sur")

    respuesta = client.put(f"/ubicaciones/{id_segunda}", json={"nmbr": "estación norte"})

    assert respuesta.status_code == 409


@pytest.mark.parametrize(
    "campo,valor",
    [("lttd", 95), ("lttd", -91), ("lngtd", 181), ("lngtd", -180.5)],
)
def test_editar_con_rango_invalido_devuelve_422(client, tecnico_editor, campo, valor):
    id_ubccn = crear_para_editar(client)

    respuesta = client.put(f"/ubicaciones/{id_ubccn}", json={campo: valor})

    assert respuesta.status_code == 422


@pytest.mark.parametrize(
    "poligono",
    [
        {"type": "Point", "coordinates": [-77.04, -12.04]},
        {"type": "Polygon", "coordinates": []},
        # Anillo abierto: el último vértice no cierra sobre el primero.
        {
            "type": "Polygon",
            "coordinates": [
                [[-77.04, -12.04], [-77.03, -12.04], [-77.03, -12.05], [-77.04, -12.05]]
            ],
        },
    ],
)
def test_editar_con_poligono_invalido_devuelve_422(client, tecnico_editor, poligono):
    """Las mismas reglas del alta: el validador es compartido
    (_validar_poligono_geojson), no una copia."""
    id_ubccn = crear_para_editar(client)

    respuesta = client.put(f"/ubicaciones/{id_ubccn}", json={"plgn_gjsn": poligono})

    assert respuesta.status_code == 422


def test_id_sd_en_el_body_se_ignora(client, db_session, tecnico_editor, fabrica):
    """La sede no es editable: UbicacionActualizar no declara id_sd, así
    que Pydantic lo descarta. Lo importante es que NO se aplique en
    silencio -mover la ubicación de sede arrastraría a sus dispositivos y
    a los permisos ya concedidos sobre ella-."""
    id_ubccn = crear_para_editar(client)
    sede_original = (
        db_session.query(Ubicacion).filter(Ubicacion.id_ubccn == id_ubccn).one().id_sd
    )
    otra_sede = fabrica.sede()

    respuesta = client.put(
        f"/ubicaciones/{id_ubccn}", json={"nmbr": "Con sede ajena", "id_sd": otra_sede.id_sd}
    )

    assert respuesta.status_code == 200
    db_session.expire_all()
    guardada = db_session.query(Ubicacion).filter(Ubicacion.id_ubccn == id_ubccn).one()
    # El nombre sí cambió; la sede no.
    assert guardada.nmbr == "Con sede ajena"
    assert guardada.id_sd == sede_original
    assert guardada.id_sd != otra_sede.id_sd


def test_editar_solo_un_campo_no_toca_los_demas(client, db_session, tecnico_editor):
    """exclude_unset: el body es parcial."""
    id_ubccn = crear_para_editar(client)

    respuesta = client.put(f"/ubicaciones/{id_ubccn}", json={"dscrpcn": "Solo esto"})

    assert respuesta.status_code == 200
    db_session.expire_all()
    guardada = db_session.query(Ubicacion).filter(Ubicacion.id_ubccn == id_ubccn).one()
    assert guardada.dscrpcn == "Solo esto"
    assert guardada.nmbr == "Estación Río Rímac"
    assert guardada.plgn_gjsn == POLIGONO_VALIDO
    assert guardada.estd == "Activa"


def test_editar_ubicacion_inexistente_devuelve_404(client, tecnico_editor):
    assert client.put("/ubicaciones/999999", json={"nmbr": "Fantasma"}).status_code == 404


def test_editar_denegado_sin_permiso_de_edicion(client, db_session, fabrica):
    """Un Cliente Final con solo Lectura ve la ubicación (HU07) pero no
    puede editarla."""
    id_ubccn = None
    rol_editor = fabrica.rol("Técnico CENERIS")
    sede = fabrica.sede()
    editor = fabrica.usuario(rol=rol_editor)
    agregar_permiso(db_session, editor, sede, "Ubicaciones", "Edición", rol_editor)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        editor, rol_editor.nmbr, sede_id=sede.id_sd
    )
    id_ubccn = crear_para_editar(client)

    rol_lector = fabrica.rol("Cliente Final")
    lector = fabrica.usuario(rol=rol_lector)
    agregar_permiso(db_session, lector, sede, "Ubicaciones", "Lectura", rol_lector)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        lector, rol_lector.nmbr, sede_id=sede.id_sd
    )

    assert client.put(f"/ubicaciones/{id_ubccn}", json={"nmbr": "Hackeada"}).status_code == 403
