"""
HU04 - Agregar usuario: tests de POST /usuarios más allá de los permisos
(esos ya están en test_autorizacion_endpoints.py::TestUsuarios).

Cobertura por CA:
  CA1  campos del formulario: obligatorios nmbr_cmplt/crr/rol_nombre,
       teléfono opcional
  CA2  201 con "Usuario creado exitosamente", credencial temporal que
       cumple la política (8+, 1 mayúscula, 1 número), correo de bienvenida
       encolado, correo duplicado rechazado
  CA3  el usuario nuevo queda en estado "Activo" y aparece en el listado

También cubre HU03 (listado): búsqueda insensible a mayúsculas por nombre y
por fragmento de correo, filtros por rol/estado y paginado de 10.
"""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Usuario
from app.models.suscripcion import PermisoUsuarioSede
from app.security.dependencies import get_current_user
from app.security.password_policy import es_password_valido


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
def correos_encolados(monkeypatch):
    """Spy sobre la task de Celery: HU04 CA2 pide que se envíe el correo de
    bienvenida, y lo que corresponde verificar acá es que el endpoint la
    ENCOLA con los datos correctos -no que el correo salga, que hoy es un
    stub (HT-14, Sprint 4) y además correría fuera de este proceso-.

    Se parchea el nombre ya importado en el router, no el módulo de origen.
    """
    llamadas = []

    class TaskFalsa:
        @staticmethod
        def delay(**kwargs):
            llamadas.append(kwargs)

    monkeypatch.setattr("app.routers.usuarios.enviar_correo_bienvenida", TaskFalsa)
    return llamadas


@pytest.fixture()
def admin_editor(db_session, fabrica):
    """Administrador con Edición sobre el módulo Usuarios, autenticado."""
    rol = fabrica.rol("Administrador")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Usuarios", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )
    return usuario, sede, rol


def cuerpo_valido(**overrides):
    cuerpo = {
        "nmbr_cmplt": "Nuevo Usuario de Prueba",
        "crr": "nuevo.usuario@pangea-test.com",
        "rol_nombre": "Cliente Final",
    }
    cuerpo.update(overrides)
    return cuerpo


# ---------------------------------------------------------------------------
# CA2 - Guardar
# ---------------------------------------------------------------------------


class TestCrearUsuario:
    def test_crear_devuelve_201_y_mensaje_de_exito(
        self, client, db_session, fabrica, admin_editor, correos_encolados
    ):
        fabrica.rol("Cliente Final")

        resp = client.post("/usuarios", json=cuerpo_valido())

        assert resp.status_code == 201
        cuerpo = resp.json()
        assert cuerpo["mensaje"] == "Usuario creado exitosamente"
        assert cuerpo["nmbr_cmplt"] == "Nuevo Usuario de Prueba"
        assert cuerpo["crr"] == "nuevo.usuario@pangea-test.com"
        assert cuerpo["rol_nombre"] == "Cliente Final"

    def test_el_usuario_queda_activo(
        self, client, db_session, fabrica, admin_editor, correos_encolados
    ):
        """CA3: el nuevo usuario aparece en estado 'Activo'."""
        fabrica.rol("Cliente Final")

        resp = client.post("/usuarios", json=cuerpo_valido())

        assert resp.json()["estd"] == "Activo"
        guardado = db_session.query(Usuario).filter(Usuario.id_usr == resp.json()["id_usr"]).one()
        assert guardado.estd == "Activo"

    def test_marca_debe_cambiar_contrasena(
        self, client, db_session, fabrica, admin_editor, correos_encolados
    ):
        """La credencial es temporal: debe cambiarse en el primer login."""
        fabrica.rol("Cliente Final")

        resp = client.post("/usuarios", json=cuerpo_valido())

        guardado = db_session.query(Usuario).filter(Usuario.id_usr == resp.json()["id_usr"]).one()
        assert guardado.dbe_cmbr_pswrd is True

    def test_el_correo_se_guarda_en_minusculas(
        self, client, db_session, fabrica, admin_editor, correos_encolados
    ):
        fabrica.rol("Cliente Final")

        resp = client.post("/usuarios", json=cuerpo_valido(crr="MAYUSCULAS@Pangea-Test.com"))

        assert resp.json()["crr"] == "mayusculas@pangea-test.com"

    def test_telefono_es_opcional(self, client, fabrica, admin_editor, correos_encolados):
        """CA1: obligatorios Nombre, Correo y Rol; Teléfono opcional."""
        fabrica.rol("Cliente Final")

        assert client.post("/usuarios", json=cuerpo_valido()).status_code == 201

    def test_guarda_el_telefono_cuando_se_envia(
        self, client, db_session, fabrica, admin_editor, correos_encolados
    ):
        fabrica.rol("Cliente Final")

        resp = client.post("/usuarios", json=cuerpo_valido(tlfn="+51987654321"))

        guardado = db_session.query(Usuario).filter(Usuario.id_usr == resp.json()["id_usr"]).one()
        assert guardado.tlfn == "+51987654321"

    @pytest.mark.parametrize("campo", ["nmbr_cmplt", "crr", "rol_nombre"])
    def test_campos_obligatorios_faltantes_devuelven_422(
        self, client, fabrica, admin_editor, correos_encolados, campo
    ):
        fabrica.rol("Cliente Final")
        cuerpo = cuerpo_valido()
        del cuerpo[campo]

        assert client.post("/usuarios", json=cuerpo).status_code == 422

    def test_correo_con_formato_invalido_devuelve_422(
        self, client, fabrica, admin_editor, correos_encolados
    ):
        fabrica.rol("Cliente Final")

        assert (
            client.post("/usuarios", json=cuerpo_valido(crr="no-es-un-correo")).status_code == 422
        )

    def test_rol_inexistente_devuelve_400(self, client, admin_editor, correos_encolados):
        resp = client.post("/usuarios", json=cuerpo_valido(rol_nombre="Rol Que No Existe"))

        assert resp.status_code == 400
        assert "no existe" in resp.json()["detail"].lower()

    def test_correo_duplicado_devuelve_409(self, client, fabrica, admin_editor, correos_encolados):
        """Conversación HU04: 'el correo debe ser único, si ya existe se
        rechaza'."""
        fabrica.rol("Cliente Final")
        assert client.post("/usuarios", json=cuerpo_valido()).status_code == 201

        repetido = client.post("/usuarios", json=cuerpo_valido(nmbr_cmplt="Otro Nombre"))
        assert repetido.status_code == 409
        assert "ya existe" in repetido.json()["detail"].lower()


# ---------------------------------------------------------------------------
# CA2 - Credencial temporal y correo de bienvenida
# ---------------------------------------------------------------------------


class TestCredencialTemporalYCorreo:
    def test_encola_el_correo_de_bienvenida(self, client, fabrica, admin_editor, correos_encolados):
        fabrica.rol("Cliente Final")

        client.post("/usuarios", json=cuerpo_valido())

        assert len(correos_encolados) == 1
        encolado = correos_encolados[0]
        assert encolado["correo"] == "nuevo.usuario@pangea-test.com"
        assert encolado["nombre_completo"] == "Nuevo Usuario de Prueba"

    def test_la_password_temporal_cumple_la_politica(
        self, client, fabrica, admin_editor, correos_encolados
    ):
        """CA2: '8+ caracteres, 1 mayúscula, 1 número'. Se lee la que viajó
        a la task, que es la única vez que existe en claro."""
        fabrica.rol("Cliente Final")

        client.post("/usuarios", json=cuerpo_valido())

        temporal = correos_encolados[0]["password_temporal"]
        assert len(temporal) >= 8
        assert any(c.isupper() for c in temporal)
        assert any(c.isdigit() for c in temporal)
        assert es_password_valido(temporal)

    def test_la_password_temporal_no_se_guarda_en_claro(
        self, client, db_session, fabrica, admin_editor, correos_encolados
    ):
        fabrica.rol("Cliente Final")

        resp = client.post("/usuarios", json=cuerpo_valido())

        temporal = correos_encolados[0]["password_temporal"]
        guardado = db_session.query(Usuario).filter(Usuario.id_usr == resp.json()["id_usr"]).one()
        assert guardado.cntrsn_hsh != temporal
        assert guardado.cntrsn_hsh.startswith("$2")  # hash bcrypt

    def test_cada_usuario_recibe_una_password_distinta(
        self, client, fabrica, admin_editor, correos_encolados
    ):
        fabrica.rol("Cliente Final")

        client.post("/usuarios", json=cuerpo_valido(crr="uno@pangea-test.com"))
        client.post("/usuarios", json=cuerpo_valido(crr="dos@pangea-test.com"))

        assert (
            correos_encolados[0]["password_temporal"] != correos_encolados[1]["password_temporal"]
        )

    def test_no_se_encola_correo_si_la_creacion_falla(
        self, client, fabrica, admin_editor, correos_encolados
    ):
        """Un rol inexistente corta antes de crear: no debe salir correo."""
        client.post("/usuarios", json=cuerpo_valido(rol_nombre="Rol Que No Existe"))

        assert correos_encolados == []


# ---------------------------------------------------------------------------
# CA3 - El usuario nuevo aparece en el listado (HU03)
# ---------------------------------------------------------------------------


class TestUsuarioNuevoEnElListado:
    def test_el_usuario_creado_aparece_en_el_listado(
        self, client, fabrica, admin_editor, correos_encolados
    ):
        fabrica.rol("Cliente Final")
        creado = client.post("/usuarios", json=cuerpo_valido(nmbr_cmplt="Usuario Del CA3"))
        assert creado.status_code == 201

        listado = client.get("/usuarios", params={"busqueda": "Usuario Del CA3"})

        assert listado.status_code == 200
        items = listado.json()["items"]
        assert [i["nmbr_cmplt"] for i in items] == ["Usuario Del CA3"]
        assert items[0]["estd"] == "Activo"


# ---------------------------------------------------------------------------
# HU03 - Búsqueda, filtros y paginado del listado
# ---------------------------------------------------------------------------


class TestListarUsuarios:
    def test_busqueda_por_nombre_insensible_a_mayusculas(
        self, client, fabrica, admin_editor, correos_encolados
    ):
        fabrica.rol("Cliente Final")
        client.post(
            "/usuarios",
            json=cuerpo_valido(nmbr_cmplt="Zoraida Buscable", crr="zoraida@pangea-test.com"),
        )

        resp = client.get("/usuarios", params={"busqueda": "zoraida buscable"})

        nombres = [i["nmbr_cmplt"] for i in resp.json()["items"]]
        assert "Zoraida Buscable" in nombres

    def test_busqueda_por_fragmento_de_correo(
        self, client, fabrica, admin_editor, correos_encolados
    ):
        """CA2: 'busco por nombre o fragmento de correo'."""
        fabrica.rol("Cliente Final")
        client.post(
            "/usuarios",
            json=cuerpo_valido(nmbr_cmplt="Correo Buscable", crr="fragmento.unico@pangea-test.com"),
        )

        resp = client.get("/usuarios", params={"busqueda": "fragmento.unico"})

        correos = [i["crr"] for i in resp.json()["items"]]
        assert correos == ["fragmento.unico@pangea-test.com"]

    def test_filtro_por_rol(self, client, fabrica, admin_editor, correos_encolados):
        fabrica.rol("Cliente Final")
        client.post("/usuarios", json=cuerpo_valido(crr="cliente.filtrado@pangea-test.com"))

        resp = client.get("/usuarios", params={"rol": "Cliente Final"})

        assert resp.status_code == 200
        assert all(i["rol_nombre"] == "Cliente Final" for i in resp.json()["items"])

    def test_filtro_por_estado(self, client, db_session, fabrica, admin_editor, correos_encolados):
        fabrica.rol("Cliente Final")
        creado = client.post("/usuarios", json=cuerpo_valido(crr="inactivo@pangea-test.com"))
        usuario = db_session.query(Usuario).filter(Usuario.id_usr == creado.json()["id_usr"]).one()
        usuario.estd = "Inactivo"
        db_session.flush()

        resp = client.get("/usuarios", params={"estado": "Inactivo"})

        assert all(i["estd"] == "Inactivo" for i in resp.json()["items"])
        assert creado.json()["id_usr"] in [i["id_usr"] for i in resp.json()["items"]]

    def test_paginado_de_10_por_defecto(self, client, fabrica, admin_editor, correos_encolados):
        fabrica.rol("Cliente Final")
        for i in range(12):
            client.post("/usuarios", json=cuerpo_valido(crr=f"masivo{i}@pangea-test.com"))

        resp = client.get("/usuarios")

        cuerpo = resp.json()
        assert cuerpo["por_pagina"] == 10
        assert len(cuerpo["items"]) == 10

    def test_el_administrador_aparece_en_su_propio_listado(
        self, client, admin_editor, correos_encolados
    ):
        """Conversación HU03: 'el propio Administrador con sesión activa
        también aparece en el listado'."""
        usuario_admin, _, _ = admin_editor

        resp = client.get("/usuarios", params={"busqueda": usuario_admin.crr})

        ids = [i["id_usr"] for i in resp.json()["items"]]
        assert usuario_admin.id_usr in ids
