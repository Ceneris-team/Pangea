"""
HU21 - Conceder permisos: tests de GET y PUT
/usuarios/{id_usr}/permisos-ubicaciones.

Cobertura por CA:
  CA1  el panel lista TODAS las ubicaciones registradas con el estado de
       acceso actual del usuario, y solo para usuarios Cliente Final
  CA2  PUT reemplaza el conjunto y responde el mensaje exacto
       "Permisos actualizados correctamente"
  CA3  VERIFICACIÓN: tras cambiar los permisos, el usuario afectado ve en
       el módulo de consulta de datos únicamente las ubicaciones y
       parámetros habilitados. El filtrado en sí ya existe (HU07/HU13, vía
       security/ubicaciones_permitidas.py); acá se comprueba que RESPONDE
       al cambio de permisos, que es lo que afirma el CA
  CA4  "CANCELAR" descarta los cambios: sin PUT no se modifica nada

Y las reglas de negocio del .docx:
  - la gestión aplica ÚNICAMENTE a Cliente Final; Administrador y Técnico
    CENERIS ya tienen acceso completo y no admiten asignación
  - un Cliente Final sin ubicaciones ve el módulo de consulta vacío
  - los cambios son inmediatos, sin cerrar sesión: el conjunto permitido
    NO viaja en el JWT, se resuelve contra prms_ubccn en cada request
"""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import PermisoUbicacion, Ubicacion
from app.models.suscripcion import PermisoUsuarioSede
from app.security.dependencies import get_current_user

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


def crear_ubicacion(db, sede, nombre):
    ubicacion = Ubicacion(
        id_sd=sede.id_sd,
        nmbr=nombre,
        dscrpcn=f"Descripción de {nombre}",
        lttd=-12.0464,
        lngtd=-77.0428,
        plgn_gjsn=POLIGONO_VALIDO,
    )
    db.add(ubicacion)
    db.flush()
    return ubicacion


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
def cliente_final(db_session, fabrica, admin_editor):
    """Un Cliente Final en la misma sede del administrador, sin permisos
    de ubicación todavía."""
    _, sede, _ = admin_editor
    rol = fabrica.rol("Cliente Final")
    usuario = fabrica.usuario(rol=rol)
    return usuario, sede, rol


@pytest.fixture()
def dos_ubicaciones(db_session, admin_editor):
    _, sede, _ = admin_editor
    return (
        crear_ubicacion(db_session, sede, "Ubicación Norte"),
        crear_ubicacion(db_session, sede, "Ubicación Sur"),
    )


# ---------------------------------------------------------------------------
# CA1 - El panel muestra todas las ubicaciones y el acceso actual
# ---------------------------------------------------------------------------


class TestPanelDePermisos:
    def test_lista_todas_las_ubicaciones_registradas(self, client, cliente_final, dos_ubicaciones):
        """CA1: 'el listado de TODAS las ubicaciones registradas'."""
        usuario, _, _ = cliente_final

        resp = client.get(f"/usuarios/{usuario.id_usr}/permisos-ubicaciones")

        assert resp.status_code == 200
        nombres = [i["nmbr"] for i in resp.json()["items"]]
        assert nombres == ["Ubicación Norte", "Ubicación Sur"]

    def test_marca_el_estado_de_acceso_actual(
        self, client, db_session, cliente_final, dos_ubicaciones
    ):
        """CA1: '...y el estado de acceso actual de ese usuario'."""
        usuario, _, _ = cliente_final
        norte, _sur = dos_ubicaciones
        db_session.add(PermisoUbicacion(id_usr=usuario.id_usr, id_ubccn=norte.id_ubccn))
        db_session.flush()

        resp = client.get(f"/usuarios/{usuario.id_usr}/permisos-ubicaciones")

        accesos = {i["nmbr"]: i["tiene_acceso"] for i in resp.json()["items"]}
        assert accesos == {"Ubicación Norte": True, "Ubicación Sur": False}

    def test_sin_permisos_todas_salen_en_falso(self, client, cliente_final, dos_ubicaciones):
        usuario, _, _ = cliente_final

        resp = client.get(f"/usuarios/{usuario.id_usr}/permisos-ubicaciones")

        assert all(i["tiene_acceso"] is False for i in resp.json()["items"])

    def test_incluye_los_datos_del_usuario_gestionado(self, client, cliente_final):
        usuario, _, _ = cliente_final

        cuerpo = client.get(f"/usuarios/{usuario.id_usr}/permisos-ubicaciones").json()

        assert cuerpo["id_usr"] == usuario.id_usr
        assert cuerpo["nmbr_cmplt"] == usuario.nmbr_cmplt
        assert cuerpo["rol_nombre"] == "Cliente Final"

    def test_usuario_inexistente_devuelve_404(self, client, admin_editor):
        assert client.get("/usuarios/99999999/permisos-ubicaciones").status_code == 404

    def test_sin_permiso_de_lectura_devuelve_403(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        assert client.get(f"/usuarios/{usuario.id_usr}/permisos-ubicaciones").status_code == 403


# ---------------------------------------------------------------------------
# Regla de negocio - Solo aplica a Cliente Final
# ---------------------------------------------------------------------------


class TestSoloClienteFinal:
    @pytest.mark.parametrize("rol_nombre", ["Administrador", "Técnico CENERIS"])
    def test_el_panel_no_se_ofrece_para_roles_con_acceso_total(
        self, client, db_session, fabrica, admin_editor, rol_nombre
    ):
        """'Administrador y Técnico CENERIS tienen acceso completo por
        defecto y no requieren asignación.'"""
        objetivo = fabrica.usuario(rol=fabrica.rol(rol_nombre))

        resp = client.get(f"/usuarios/{objetivo.id_usr}/permisos-ubicaciones")

        assert resp.status_code == 409
        assert "acceso completo" in resp.json()["detail"].lower()

    @pytest.mark.parametrize("rol_nombre", ["Administrador", "Técnico CENERIS"])
    def test_tampoco_se_les_pueden_guardar_permisos(
        self, client, db_session, fabrica, admin_editor, dos_ubicaciones, rol_nombre
    ):
        objetivo = fabrica.usuario(rol=fabrica.rol(rol_nombre))
        norte, _ = dos_ubicaciones

        resp = client.put(
            f"/usuarios/{objetivo.id_usr}/permisos-ubicaciones",
            json={"ubicacion_ids": [norte.id_ubccn]},
        )

        assert resp.status_code == 409

    def test_no_se_escriben_filas_para_esos_roles(
        self, client, db_session, fabrica, admin_editor, dos_ubicaciones
    ):
        objetivo = fabrica.usuario(rol=fabrica.rol("Administrador"))
        norte, _ = dos_ubicaciones

        client.put(
            f"/usuarios/{objetivo.id_usr}/permisos-ubicaciones",
            json={"ubicacion_ids": [norte.id_ubccn]},
        )

        filas = (
            db_session.query(PermisoUbicacion)
            .filter(PermisoUbicacion.id_usr == objetivo.id_usr)
            .count()
        )
        assert filas == 0


# ---------------------------------------------------------------------------
# CA2 - Guardar permisos
# ---------------------------------------------------------------------------


class TestGuardarPermisos:
    def test_devuelve_el_mensaje_exacto_del_ca(self, client, cliente_final, dos_ubicaciones):
        """CA2: 'Permisos actualizados correctamente', literal."""
        usuario, _, _ = cliente_final
        norte, _ = dos_ubicaciones

        resp = client.put(
            f"/usuarios/{usuario.id_usr}/permisos-ubicaciones",
            json={"ubicacion_ids": [norte.id_ubccn]},
        )

        assert resp.status_code == 200
        assert resp.json()["mensaje"] == "Permisos actualizados correctamente"

    def test_marcar_una_ubicacion_crea_la_fila(
        self, client, db_session, cliente_final, dos_ubicaciones
    ):
        usuario, _, _ = cliente_final
        norte, _ = dos_ubicaciones

        client.put(
            f"/usuarios/{usuario.id_usr}/permisos-ubicaciones",
            json={"ubicacion_ids": [norte.id_ubccn]},
        )

        concedidas = {
            f.id_ubccn
            for f in db_session.query(PermisoUbicacion)
            .filter(PermisoUbicacion.id_usr == usuario.id_usr)
            .all()
        }
        assert concedidas == {norte.id_ubccn}

    def test_desmarcar_elimina_la_fila(self, client, db_session, cliente_final, dos_ubicaciones):
        """CA2: 'marco/desmarco ubicaciones'."""
        usuario, _, _ = cliente_final
        norte, sur = dos_ubicaciones
        db_session.add(PermisoUbicacion(id_usr=usuario.id_usr, id_ubccn=norte.id_ubccn))
        db_session.add(PermisoUbicacion(id_usr=usuario.id_usr, id_ubccn=sur.id_ubccn))
        db_session.flush()

        client.put(
            f"/usuarios/{usuario.id_usr}/permisos-ubicaciones",
            json={"ubicacion_ids": [sur.id_ubccn]},
        )

        concedidas = {
            f.id_ubccn
            for f in db_session.query(PermisoUbicacion)
            .filter(PermisoUbicacion.id_usr == usuario.id_usr)
            .all()
        }
        assert concedidas == {sur.id_ubccn}

    def test_reemplaza_el_conjunto_completo(
        self, client, db_session, cliente_final, dos_ubicaciones
    ):
        usuario, _, _ = cliente_final
        norte, sur = dos_ubicaciones
        db_session.add(PermisoUbicacion(id_usr=usuario.id_usr, id_ubccn=norte.id_ubccn))
        db_session.flush()

        client.put(
            f"/usuarios/{usuario.id_usr}/permisos-ubicaciones",
            json={"ubicacion_ids": [norte.id_ubccn, sur.id_ubccn]},
        )

        resp = client.get(f"/usuarios/{usuario.id_usr}/permisos-ubicaciones")
        assert all(i["tiene_acceso"] for i in resp.json()["items"])

    def test_lista_vacia_quita_todos_los_accesos(
        self, client, db_session, cliente_final, dos_ubicaciones
    ):
        """Desmarcar todo es una operación válida, no un body inválido."""
        usuario, _, _ = cliente_final
        norte, _ = dos_ubicaciones
        db_session.add(PermisoUbicacion(id_usr=usuario.id_usr, id_ubccn=norte.id_ubccn))
        db_session.flush()

        resp = client.put(
            f"/usuarios/{usuario.id_usr}/permisos-ubicaciones", json={"ubicacion_ids": []}
        )

        assert resp.status_code == 200
        filas = (
            db_session.query(PermisoUbicacion)
            .filter(PermisoUbicacion.id_usr == usuario.id_usr)
            .count()
        )
        assert filas == 0

    def test_guardar_dos_veces_lo_mismo_no_duplica(
        self, client, db_session, cliente_final, dos_ubicaciones
    ):
        """uq_prmsubccn_usr_ubccn: reenviar el mismo conjunto es idempotente."""
        usuario, _, _ = cliente_final
        norte, _ = dos_ubicaciones
        cuerpo = {"ubicacion_ids": [norte.id_ubccn]}

        client.put(f"/usuarios/{usuario.id_usr}/permisos-ubicaciones", json=cuerpo)
        segunda = client.put(f"/usuarios/{usuario.id_usr}/permisos-ubicaciones", json=cuerpo)

        assert segunda.status_code == 200
        filas = (
            db_session.query(PermisoUbicacion)
            .filter(PermisoUbicacion.id_usr == usuario.id_usr)
            .count()
        )
        assert filas == 1

    def test_ids_repetidos_en_el_body_no_duplican(
        self, client, db_session, cliente_final, dos_ubicaciones
    ):
        usuario, _, _ = cliente_final
        norte, _ = dos_ubicaciones

        resp = client.put(
            f"/usuarios/{usuario.id_usr}/permisos-ubicaciones",
            json={"ubicacion_ids": [norte.id_ubccn, norte.id_ubccn]},
        )

        assert resp.status_code == 200
        filas = (
            db_session.query(PermisoUbicacion)
            .filter(PermisoUbicacion.id_usr == usuario.id_usr)
            .count()
        )
        assert filas == 1

    def test_ubicacion_inexistente_devuelve_400(self, client, cliente_final):
        usuario, _, _ = cliente_final

        resp = client.put(
            f"/usuarios/{usuario.id_usr}/permisos-ubicaciones",
            json={"ubicacion_ids": [99999999]},
        )

        assert resp.status_code == 400
        assert "no existe" in resp.json()["detail"].lower()

    def test_body_sin_el_campo_devuelve_422(self, client, cliente_final):
        """Un body sin ubicacion_ids sería ambiguo entre 'ninguna' y 'no lo
        toques': se exige explícito."""
        usuario, _, _ = cliente_final

        assert (
            client.put(f"/usuarios/{usuario.id_usr}/permisos-ubicaciones", json={}).status_code
            == 422
        )

    def test_usuario_inexistente_devuelve_404(self, client, admin_editor):
        resp = client.put("/usuarios/99999999/permisos-ubicaciones", json={"ubicacion_ids": []})

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Permisos (HT-09): guardar exige Edición sobre "Usuarios"
# ---------------------------------------------------------------------------


class TestPermisosDeEdicion:
    def test_sin_permiso_devuelve_403(self, client, db_session, fabrica, admin_editor):
        _, sede, _ = admin_editor
        rol = fabrica.rol("Cliente Final")
        objetivo = fabrica.usuario(rol=rol)
        intruso = fabrica.usuario(rol=rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            intruso, rol.nmbr, sede_id=sede.id_sd
        )

        resp = client.put(
            f"/usuarios/{objetivo.id_usr}/permisos-ubicaciones", json={"ubicacion_ids": []}
        )

        assert resp.status_code == 403

    def test_con_solo_lectura_devuelve_403(self, client, db_session, fabrica, admin_editor):
        """Ver el panel es Lectura; guardarlo exige Edición."""
        _, sede, _ = admin_editor
        rol_admin = fabrica.rol("Administrador")
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        lector = fabrica.usuario(rol=rol_admin)
        agregar_permiso(db_session, lector, sede, "Usuarios", "Lectura", rol_admin)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            lector, rol_admin.nmbr, sede_id=sede.id_sd
        )

        assert client.get(f"/usuarios/{objetivo.id_usr}/permisos-ubicaciones").status_code == 200
        assert (
            client.put(
                f"/usuarios/{objetivo.id_usr}/permisos-ubicaciones", json={"ubicacion_ids": []}
            ).status_code
            == 403
        )

    def test_el_permiso_no_cruza_de_sede(self, client, db_session, fabrica, admin_editor):
        """HT-09 CA3: el permiso otorgado en una sede no vale autenticado
        en otra."""
        rol_admin = fabrica.rol("Administrador")
        sede_con_permiso = fabrica.sede()
        sede_de_la_sesion = fabrica.sede()
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        usuario = fabrica.usuario(rol=rol_admin)
        agregar_permiso(db_session, usuario, sede_con_permiso, "Usuarios", "Edición", rol_admin)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol_admin.nmbr, sede_id=sede_de_la_sesion.id_sd
        )

        resp = client.put(
            f"/usuarios/{objetivo.id_usr}/permisos-ubicaciones", json={"ubicacion_ids": []}
        )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# CA4 - "CANCELAR" descarta los cambios
# ---------------------------------------------------------------------------


class TestCancelar:
    def test_sin_guardar_no_se_modifica_nada(
        self, client, db_session, cliente_final, dos_ubicaciones
    ):
        """CA4: 'descarta los cambios y regresa al listado sin modificar
        nada'. Cancelar es puramente de interfaz -no hay request-, así que
        lo que se verifica es que abrir el panel y NO guardar deja el
        estado intacto."""
        usuario, _, _ = cliente_final
        norte, _ = dos_ubicaciones
        db_session.add(PermisoUbicacion(id_usr=usuario.id_usr, id_ubccn=norte.id_ubccn))
        db_session.flush()

        # Se abre el panel (CA1) y se cancela: ningún PUT.
        client.get(f"/usuarios/{usuario.id_usr}/permisos-ubicaciones")

        concedidas = {
            f.id_ubccn
            for f in db_session.query(PermisoUbicacion)
            .filter(PermisoUbicacion.id_usr == usuario.id_usr)
            .all()
        }
        assert concedidas == {norte.id_ubccn}

    def test_el_panel_sigue_mostrando_el_estado_original(
        self, client, db_session, cliente_final, dos_ubicaciones
    ):
        usuario, _, _ = cliente_final
        norte, _ = dos_ubicaciones
        db_session.add(PermisoUbicacion(id_usr=usuario.id_usr, id_ubccn=norte.id_ubccn))
        db_session.flush()

        client.get(f"/usuarios/{usuario.id_usr}/permisos-ubicaciones")
        despues = client.get(f"/usuarios/{usuario.id_usr}/permisos-ubicaciones")

        accesos = {i["nmbr"]: i["tiene_acceso"] for i in despues.json()["items"]}
        assert accesos == {"Ubicación Norte": True, "Ubicación Sur": False}


# ---------------------------------------------------------------------------
# CA3 - VERIFICACIÓN: lo que el usuario afectado ve cambia con los permisos
# ---------------------------------------------------------------------------


class TestLoQueVeElUsuarioAfectado:
    """CA3: 'cuando el usuario afectado accede al módulo de consulta de
    datos, ve únicamente las ubicaciones y parámetros correspondientes a
    las que le fueron habilitadas'.

    El filtrado ya existe (HU07/HU13 vía security/ubicaciones_permitidas.py);
    lo que se verifica acá es que RESPONDE a los permisos que escribe HU21,
    y que lo hace de inmediato -sin reemitir el JWT-.
    """

    def _autenticar_como_cliente(self, db_session, usuario, sede, rol):
        agregar_permiso(db_session, usuario, sede, "Ubicaciones", "Lectura", rol)
        agregar_permiso(db_session, usuario, sede, "Tableros", "Lectura", rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

    def test_solo_ve_las_ubicaciones_habilitadas(
        self, client, db_session, cliente_final, dos_ubicaciones, admin_editor
    ):
        usuario, sede, rol = cliente_final
        norte, _sur = dos_ubicaciones

        # El administrador le habilita SOLO la Norte (CA2).
        client.put(
            f"/usuarios/{usuario.id_usr}/permisos-ubicaciones",
            json={"ubicacion_ids": [norte.id_ubccn]},
        )

        # Ahora entra el usuario afectado a consultar sus ubicaciones.
        self._autenticar_como_cliente(db_session, usuario, sede, rol)
        nombres = [u["nmbr"] for u in client.get("/ubicaciones").json()["items"]]

        assert nombres == ["Ubicación Norte"]

    def test_al_habilitar_otra_ubicacion_aparece_de_inmediato(
        self, client, db_session, cliente_final, dos_ubicaciones, admin_editor
    ):
        """'Los cambios toman efecto de forma inmediata, sin que el usuario
        cierre sesión': el mismo JWT ve el conjunto nuevo."""
        usuario, sede, rol = cliente_final
        norte, sur = dos_ubicaciones
        usuario_admin, sede_admin, rol_admin = admin_editor

        client.put(
            f"/usuarios/{usuario.id_usr}/permisos-ubicaciones",
            json={"ubicacion_ids": [norte.id_ubccn]},
        )

        self._autenticar_como_cliente(db_session, usuario, sede, rol)
        antes = [u["nmbr"] for u in client.get("/ubicaciones").json()["items"]]

        # El administrador agrega la Sur mientras el cliente sigue logueado.
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario_admin, rol_admin.nmbr, sede_id=sede_admin.id_sd
        )
        client.put(
            f"/usuarios/{usuario.id_usr}/permisos-ubicaciones",
            json={"ubicacion_ids": [norte.id_ubccn, sur.id_ubccn]},
        )

        # El cliente vuelve a consultar con el MISMO token: ya ve las dos.
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )
        despues = [u["nmbr"] for u in client.get("/ubicaciones").json()["items"]]

        assert antes == ["Ubicación Norte"]
        assert despues == ["Ubicación Norte", "Ubicación Sur"]

    def test_al_revocar_deja_de_verla_de_inmediato(
        self, client, db_session, cliente_final, dos_ubicaciones, admin_editor
    ):
        usuario, sede, rol = cliente_final
        norte, sur = dos_ubicaciones
        usuario_admin, sede_admin, rol_admin = admin_editor

        client.put(
            f"/usuarios/{usuario.id_usr}/permisos-ubicaciones",
            json={"ubicacion_ids": [norte.id_ubccn, sur.id_ubccn]},
        )

        self._autenticar_como_cliente(db_session, usuario, sede, rol)
        assert len(client.get("/ubicaciones").json()["items"]) == 2

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario_admin, rol_admin.nmbr, sede_id=sede_admin.id_sd
        )
        client.put(
            f"/usuarios/{usuario.id_usr}/permisos-ubicaciones",
            json={"ubicacion_ids": [sur.id_ubccn]},
        )

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )
        nombres = [u["nmbr"] for u in client.get("/ubicaciones").json()["items"]]

        assert nombres == ["Ubicación Sur"]

    def test_sin_ubicaciones_asignadas_el_modulo_sale_vacio(
        self, client, db_session, cliente_final, dos_ubicaciones, admin_editor
    ):
        """Regla del .docx: 'Un Cliente Final sin ninguna ubicación asignada
        ve el módulo de consulta vacío'. El mensaje exacto -'No tienes
        ubicaciones asignadas. Contacta al administrador.'- lo pinta el
        frontend (ConsultaDatos.tsx) sobre esta respuesta vacía."""
        usuario, sede, rol = cliente_final

        client.put(f"/usuarios/{usuario.id_usr}/permisos-ubicaciones", json={"ubicacion_ids": []})

        self._autenticar_como_cliente(db_session, usuario, sede, rol)

        assert client.get("/ubicaciones").json()["items"] == []
        assert client.get("/mediciones/parametros").json()["items"] == []

    def test_no_ve_mediciones_de_ubicaciones_no_habilitadas(
        self, client, db_session, cliente_final, dos_ubicaciones, admin_editor
    ):
        """CA3 sobre el listado de mediciones: sin permisos no hay datos."""
        usuario, sede, rol = cliente_final

        client.put(f"/usuarios/{usuario.id_usr}/permisos-ubicaciones", json={"ubicacion_ids": []})

        self._autenticar_como_cliente(db_session, usuario, sede, rol)
        resp = client.get("/mediciones")

        assert resp.status_code == 200
        assert resp.json()["items"] == []
