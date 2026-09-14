"""
HU20 - Editar usuario: tests de GET /usuarios/{id_usr} y PUT /usuarios/{id_usr}.

Cobertura por CA:
  CA1  el formulario se precarga con los datos ACTUALES del usuario:
       Nombre completo, Correo electrónico, Rol y Teléfono
  CA2  PUT actualiza y responde el mensaje exacto
       "Usuario actualizado correctamente"
  CA3  los datos actualizados se reflejan en el listado (HU03) al volver

Y las reglas de negocio de la conversación del .docx:
  - el correo se puede editar mientras no lo tenga OTRO usuario (409)
  - el Administrador no puede editar su PROPIO rol (sí sus otros campos)
  - solo quien tiene Edición sobre "Usuarios" puede editar (403 si no)
  - aislamiento entre sedes en el chequeo de permisos (HT-09)

El historial de cambios no se prueba porque no se expone en v1.0 (decisión
del .docx) y la auditoría formal es alcance de HT-11.
"""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.suscripcion import PermisoUsuarioSede
from app.security.dependencies import get_current_user


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


@pytest.fixture()
def usuario_editable(db_session, fabrica):
    """Un Cliente Final con todos los campos poblados, para editarlo."""
    rol = fabrica.rol("Cliente Final")
    usuario = fabrica.usuario(rol=rol)
    usuario.nmbr_cmplt = "Nombre Original"
    usuario.tlfn = "+51900000000"
    db_session.flush()
    return usuario


# ---------------------------------------------------------------------------
# CA1 - El formulario se precarga con los datos actuales
# ---------------------------------------------------------------------------


class TestPrecargaDelFormulario:
    def test_devuelve_los_cuatro_campos_editables(self, client, admin_editor, usuario_editable):
        """CA1: Nombre completo, Correo electrónico, Rol y Teléfono."""
        resp = client.get(f"/usuarios/{usuario_editable.id_usr}")

        assert resp.status_code == 200
        cuerpo = resp.json()
        assert cuerpo["nmbr_cmplt"] == "Nombre Original"
        assert cuerpo["crr"] == usuario_editable.crr
        assert cuerpo["rol_nombre"] == "Cliente Final"
        assert cuerpo["tlfn"] == "+51900000000"

    def test_usuario_inexistente_devuelve_404(self, client, admin_editor):
        assert client.get("/usuarios/99999999").status_code == 404

    def test_sin_permiso_de_lectura_devuelve_403(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        assert client.get(f"/usuarios/{usuario.id_usr}").status_code == 403


# ---------------------------------------------------------------------------
# CA2 - Guardar los cambios
# ---------------------------------------------------------------------------


class TestActualizarUsuario:
    def test_devuelve_el_mensaje_exacto_del_ca(self, client, admin_editor, usuario_editable):
        """CA2: 'Usuario actualizado correctamente', literal."""
        resp = client.put(
            f"/usuarios/{usuario_editable.id_usr}", json={"nmbr_cmplt": "Nombre Editado"}
        )

        assert resp.status_code == 200
        assert resp.json()["mensaje"] == "Usuario actualizado correctamente"

    def test_persiste_el_cambio_de_nombre(self, client, db_session, admin_editor, usuario_editable):
        client.put(f"/usuarios/{usuario_editable.id_usr}", json={"nmbr_cmplt": "Nombre Editado"})

        db_session.refresh(usuario_editable)
        assert usuario_editable.nmbr_cmplt == "Nombre Editado"

    def test_actualiza_los_cuatro_campos_a_la_vez(
        self, client, db_session, fabrica, admin_editor, usuario_editable
    ):
        fabrica.rol("Técnico CENERIS")

        resp = client.put(
            f"/usuarios/{usuario_editable.id_usr}",
            json={
                "nmbr_cmplt": "Todo Cambiado",
                "crr": "todo.cambiado@pangea-test.com",
                "rol_nombre": "Técnico CENERIS",
                "tlfn": "+51911111111",
            },
        )

        assert resp.status_code == 200
        db_session.refresh(usuario_editable)
        assert usuario_editable.nmbr_cmplt == "Todo Cambiado"
        assert usuario_editable.crr == "todo.cambiado@pangea-test.com"
        assert usuario_editable.rol.nmbr == "Técnico CENERIS"
        assert usuario_editable.tlfn == "+51911111111"

    def test_body_parcial_no_toca_los_campos_ausentes(
        self, client, db_session, admin_editor, usuario_editable
    ):
        correo_original = usuario_editable.crr

        client.put(f"/usuarios/{usuario_editable.id_usr}", json={"nmbr_cmplt": "Solo El Nombre"})

        db_session.refresh(usuario_editable)
        assert usuario_editable.crr == correo_original
        assert usuario_editable.tlfn == "+51900000000"
        assert usuario_editable.rol.nmbr == "Cliente Final"

    def test_el_correo_se_guarda_en_minusculas(
        self, client, db_session, admin_editor, usuario_editable
    ):
        """Misma normalización que el alta (HU04)."""
        resp = client.put(
            f"/usuarios/{usuario_editable.id_usr}", json={"crr": "MAYUS@Pangea-Test.com"}
        )

        assert resp.json()["crr"] == "mayus@pangea-test.com"

    def test_telefono_vacio_se_guarda_como_nulo(
        self, client, db_session, admin_editor, usuario_editable
    ):
        """tlfn es la única columna nullable del conjunto editable."""
        client.put(f"/usuarios/{usuario_editable.id_usr}", json={"tlfn": ""})

        db_session.refresh(usuario_editable)
        assert usuario_editable.tlfn is None

    def test_usuario_inexistente_devuelve_404(self, client, admin_editor):
        resp = client.put("/usuarios/99999999", json={"nmbr_cmplt": "Fantasma"})

        assert resp.status_code == 404

    def test_rol_inexistente_devuelve_400(self, client, admin_editor, usuario_editable):
        """Mismo 400 que el alta de HU04."""
        resp = client.put(
            f"/usuarios/{usuario_editable.id_usr}", json={"rol_nombre": "Rol Que No Existe"}
        )

        assert resp.status_code == 400
        assert "no existe" in resp.json()["detail"].lower()

    def test_nombre_vacio_devuelve_422(self, client, admin_editor, usuario_editable):
        assert (
            client.put(f"/usuarios/{usuario_editable.id_usr}", json={"nmbr_cmplt": ""}).status_code
            == 422
        )

    def test_correo_con_formato_invalido_devuelve_422(self, client, admin_editor, usuario_editable):
        assert (
            client.put(
                f"/usuarios/{usuario_editable.id_usr}", json={"crr": "no-es-un-correo"}
            ).status_code
            == 422
        )


# ---------------------------------------------------------------------------
# Reglas de negocio del .docx - Correo único
# ---------------------------------------------------------------------------


class TestCorreoUnico:
    def test_correo_de_otro_usuario_devuelve_409(
        self, client, db_session, fabrica, admin_editor, usuario_editable
    ):
        """'El correo se puede editar siempre que no esté ya registrado por
        otro usuario' -> mismo 409 que HU04."""
        otro = fabrica.usuario(rol=fabrica.rol("Cliente Final"))

        resp = client.put(f"/usuarios/{usuario_editable.id_usr}", json={"crr": otro.crr})

        assert resp.status_code == 409
        assert "ya existe" in resp.json()["detail"].lower()

    def test_guardar_el_correo_propio_sin_cambios_no_choca_consigo_mismo(
        self, client, db_session, admin_editor, usuario_editable
    ):
        """Reenviar el correo que ya tiene no puede ser un duplicado."""
        resp = client.put(
            f"/usuarios/{usuario_editable.id_usr}",
            json={"nmbr_cmplt": "Otro Nombre", "crr": usuario_editable.crr},
        )

        assert resp.status_code == 200

    def test_el_correo_duplicado_no_deja_a_medias_los_otros_campos(
        self, client, db_session, fabrica, admin_editor, usuario_editable
    ):
        """El 409 corta antes del commit: no se guarda el nombre tampoco."""
        otro = fabrica.usuario(rol=fabrica.rol("Cliente Final"))

        client.put(
            f"/usuarios/{usuario_editable.id_usr}",
            json={"nmbr_cmplt": "No Debe Guardarse", "crr": otro.crr},
        )

        db_session.refresh(usuario_editable)
        assert usuario_editable.nmbr_cmplt == "Nombre Original"


# ---------------------------------------------------------------------------
# Reglas de negocio del .docx - El Administrador no edita su propio rol
# ---------------------------------------------------------------------------


class TestNoEditarSuPropioRol:
    def test_cambiar_su_propio_rol_se_rechaza(self, client, db_session, fabrica, admin_editor):
        """'El Administrador no puede editar su propio rol desde este
        módulo.'"""
        usuario_admin, _, _ = admin_editor
        fabrica.rol("Cliente Final")

        resp = client.put(f"/usuarios/{usuario_admin.id_usr}", json={"rol_nombre": "Cliente Final"})

        assert resp.status_code == 409
        assert "propio rol" in resp.json()["detail"].lower()

    def test_su_rol_no_cambia_en_la_base(self, client, db_session, fabrica, admin_editor):
        usuario_admin, _, rol_admin = admin_editor
        fabrica.rol("Cliente Final")

        client.put(f"/usuarios/{usuario_admin.id_usr}", json={"rol_nombre": "Cliente Final"})

        db_session.refresh(usuario_admin)
        assert usuario_admin.id_rl == rol_admin.id_rl

    def test_si_puede_editar_sus_otros_campos(self, client, db_session, admin_editor):
        """'El resto de sus campos sí puede editarlos.'"""
        usuario_admin, _, _ = admin_editor

        resp = client.put(
            f"/usuarios/{usuario_admin.id_usr}",
            json={"nmbr_cmplt": "Admin Renombrado", "tlfn": "+51922222222"},
        )

        assert resp.status_code == 200
        db_session.refresh(usuario_admin)
        assert usuario_admin.nmbr_cmplt == "Admin Renombrado"

    def test_reenviar_su_rol_actual_no_se_considera_cambio(self, client, db_session, admin_editor):
        """Guardar el formulario sin tocar el selector de rol debe pasar:
        solo se rechaza un cambio REAL de rol propio."""
        usuario_admin, _, rol_admin = admin_editor

        resp = client.put(
            f"/usuarios/{usuario_admin.id_usr}",
            json={"nmbr_cmplt": "Admin Igual", "rol_nombre": rol_admin.nmbr},
        )

        assert resp.status_code == 200

    def test_si_puede_cambiar_el_rol_de_otro_usuario(
        self, client, db_session, fabrica, admin_editor, usuario_editable
    ):
        """La restricción es solo sobre el rol PROPIO."""
        fabrica.rol("Técnico CENERIS")

        resp = client.put(
            f"/usuarios/{usuario_editable.id_usr}", json={"rol_nombre": "Técnico CENERIS"}
        )

        assert resp.status_code == 200
        db_session.refresh(usuario_editable)
        assert usuario_editable.rol.nmbr == "Técnico CENERIS"


# ---------------------------------------------------------------------------
# Permisos (HT-09): solo el Administrador -quien tiene Edición- edita
# ---------------------------------------------------------------------------


class TestPermisosDeEdicion:
    def test_sin_permiso_devuelve_403(self, client, db_session, fabrica, usuario_editable):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        resp = client.put(f"/usuarios/{usuario_editable.id_usr}", json={"nmbr_cmplt": "Hackeado"})

        assert resp.status_code == 403

    def test_con_solo_lectura_devuelve_403(self, client, db_session, fabrica, usuario_editable):
        """CA2 de HT-09: solo-lectura en el módulo no habilita editar."""
        rol = fabrica.rol("Administrador")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Usuarios", "Lectura", rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        resp = client.put(f"/usuarios/{usuario_editable.id_usr}", json={"nmbr_cmplt": "Hackeado"})

        assert resp.status_code == 403

    def test_el_permiso_no_cruza_de_sede(self, client, db_session, fabrica, usuario_editable):
        """HT-09 CA3: el permiso se otorga en UNA sede; un usuario
        'por_sede' autenticado en OTRA sede no lo hereda."""
        rol = fabrica.rol("Administrador")
        sede_con_permiso = fabrica.sede()
        sede_de_la_sesion = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede_con_permiso, "Usuarios", "Edición", rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede_de_la_sesion.id_sd
        )

        resp = client.put(f"/usuarios/{usuario_editable.id_usr}", json={"nmbr_cmplt": "Ajeno"})

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# CA3 - Los datos actualizados se reflejan en el listado (HU03)
# ---------------------------------------------------------------------------


class TestCambiosReflejadosEnElListado:
    def test_el_nombre_editado_aparece_en_el_listado(self, client, admin_editor, usuario_editable):
        """CA3: 'redirige al listado donde los datos actualizados se
        reflejan en la tabla'."""
        client.put(f"/usuarios/{usuario_editable.id_usr}", json={"nmbr_cmplt": "Aparece Editado"})

        listado = client.get("/usuarios", params={"busqueda": "Aparece Editado"})

        assert listado.status_code == 200
        items = listado.json()["items"]
        assert [i["nmbr_cmplt"] for i in items] == ["Aparece Editado"]

    def test_el_correo_editado_aparece_en_el_listado(self, client, admin_editor, usuario_editable):
        client.put(
            f"/usuarios/{usuario_editable.id_usr}", json={"crr": "correo.nuevo@pangea-test.com"}
        )

        listado = client.get("/usuarios", params={"busqueda": "correo.nuevo"})

        assert [i["crr"] for i in listado.json()["items"]] == ["correo.nuevo@pangea-test.com"]

    def test_el_rol_editado_se_refleja_en_el_filtro_por_rol(
        self, client, db_session, fabrica, admin_editor, usuario_editable
    ):
        fabrica.rol("Técnico CENERIS")
        client.put(f"/usuarios/{usuario_editable.id_usr}", json={"rol_nombre": "Técnico CENERIS"})

        listado = client.get("/usuarios", params={"rol": "Técnico CENERIS"})

        ids = [i["id_usr"] for i in listado.json()["items"]]
        assert usuario_editable.id_usr in ids

    def test_el_nombre_viejo_ya_no_aparece(self, client, admin_editor, usuario_editable):
        client.put(f"/usuarios/{usuario_editable.id_usr}", json={"nmbr_cmplt": "Nombre Nuevo"})

        listado = client.get("/usuarios", params={"busqueda": "Nombre Original"})

        assert listado.json()["items"] == []
