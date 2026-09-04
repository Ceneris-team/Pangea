"""
HT-09 CA1/CA3, a nivel de los endpoints que existen hoy: HU07 (listar
ubicaciones), HU09 (métricas de ingesta) y HU03/HU04 (listar/crear
usuarios). Cada uno tiene un caso autorizado y uno denegado, como pide la
HT. Los otros 4 endpoints del PMV que menciona CA1 (HU08 Agregar
ubicación, HU10 Listar dispositivos, HU11 Añadir dispositivo, HU12/HU13)
todavía no están implementados en el backend -no hay router de
dispositivos ni de tableros-, así que no se pueden probar aquí; queda
documentado como pendiente en el resumen de cierre de HT-09.
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


def autenticar_como(usuario_dict):
    app.dependency_overrides[get_current_user] = lambda: usuario_dict


class TestUbicacionesListar:
    """HU07 - GET /ubicaciones, ya usaba require_permiso("Ubicaciones", LECTURA)."""

    def test_autorizado_con_permiso_de_lectura(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario_db = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario_db, sede, "Ubicaciones", "Lectura", rol)
        autenticar_como(usuario_jwt(usuario_db, rol.nmbr, sede_id=sede.id_sd))

        resp = client.get("/ubicaciones")
        assert resp.status_code == 200

    def test_denegado_sin_permiso(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario_db = fabrica.usuario(rol=rol)
        autenticar_como(usuario_jwt(usuario_db, rol.nmbr, sede_id=sede.id_sd))

        resp = client.get("/ubicaciones")
        assert resp.status_code == 403


class TestIngestaMetricas:
    """HU09 - GET /ingesta/metricas, antes usaba un set de roles hardcodeado."""

    def test_autorizado_con_permiso_de_lectura(self, client, db_session, fabrica):
        rol = fabrica.rol("Técnico CENERIS")
        sede = fabrica.sede()
        usuario_db = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario_db, sede, "Ingesta", "Lectura", rol)
        autenticar_como(usuario_jwt(usuario_db, rol.nmbr, sede_id=sede.id_sd))

        resp = client.get("/ingesta/metricas")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_denegado_sin_permiso(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario_db = fabrica.usuario(rol=rol)
        autenticar_como(usuario_jwt(usuario_db, rol.nmbr, sede_id=sede.id_sd))

        resp = client.get("/ingesta/metricas")
        assert resp.status_code == 403


class TestUsuarios:
    """HU03/HU04 - GET y POST /usuarios, antes exigían rol=='Administrador' a mano."""

    def test_listar_autorizado_con_permiso_de_lectura(self, client, db_session, fabrica):
        rol = fabrica.rol("Técnico CENERIS")
        sede = fabrica.sede()
        usuario_db = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario_db, sede, "Usuarios", "Lectura", rol)
        autenticar_como(usuario_jwt(usuario_db, rol.nmbr, sede_id=sede.id_sd))

        resp = client.get("/usuarios")
        assert resp.status_code == 200

    def test_listar_denegado_sin_permiso(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario_db = fabrica.usuario(rol=rol)
        autenticar_como(usuario_jwt(usuario_db, rol.nmbr, sede_id=sede.id_sd))

        resp = client.get("/usuarios")
        assert resp.status_code == 403

    def test_crear_autorizado_con_permiso_de_edicion(self, client, db_session, fabrica):
        rol_admin = fabrica.rol("Administrador")
        rol_cliente = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario_db = fabrica.usuario(rol=rol_admin)
        agregar_permiso(db_session, usuario_db, sede, "Usuarios", "Edición", rol_admin)
        autenticar_como(usuario_jwt(usuario_db, rol_admin.nmbr, sede_id=sede.id_sd))

        resp = client.post(
            "/usuarios",
            json={
                "nmbr_cmplt": "Nuevo Usuario",
                "crr": "nuevo@pangea-dev.com",
                "rol_nombre": rol_cliente.nmbr,
            },
        )
        assert resp.status_code == 201

    def test_crear_denegado_con_permiso_de_solo_lectura(self, client, db_session, fabrica):
        # CA2: solo-lectura en el módulo -> 403 al intentar editar (crear).
        rol_admin = fabrica.rol("Administrador")
        rol_cliente = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario_db = fabrica.usuario(rol=rol_admin)
        agregar_permiso(db_session, usuario_db, sede, "Usuarios", "Lectura", rol_admin)
        autenticar_como(usuario_jwt(usuario_db, rol_admin.nmbr, sede_id=sede.id_sd))

        resp = client.post(
            "/usuarios",
            json={
                "nmbr_cmplt": "Nuevo Usuario",
                "crr": "nuevo@pangea-dev.com",
                "rol_nombre": rol_cliente.nmbr,
            },
        )
        assert resp.status_code == 403
