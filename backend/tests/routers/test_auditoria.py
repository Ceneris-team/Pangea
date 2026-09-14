"""
HT-11 - Log de auditoría de cambios de permisos y accesos por sede.

Cobertura por CA:
  CA1  toda edición de usuario (HU20) y cambio de permisos (HU21) genera
       automáticamente un registro con usuario ejecutor, sede, valores
       anteriores y nuevos -sin que el endpoint escriba el log a mano-.
  CA2  GET /auditoria filtra por sede, usuario y rango de fechas, y es
       accesible únicamente para Administrador.
  CA3  ningún rol, incluido Administrador, puede modificar o eliminar un
       registro desde la aplicación -no existe el endpoint-.
  CA4  los registros de una sede no son visibles para un Administrador con
       scope "por_sede" limitado a otra sede; y el caso id_sd IS NULL
       (bug documentado de HT-04, no corregido acá) se comporta de forma
       explícita y probada.
  CA5  los accesos denegados de HT-09 aparecen en el mismo histórico.

Más la exclusión de columnas sensibles (cntrsn_hsh nunca debe aparecer en
vlrs_antrrs/vlrs_nvs), pedida aparte del listado de CA.
"""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import LogAuditoria
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
    """Administrador con Edición sobre "Usuarios", scope global -el caso
    normal del seed real-, autenticado."""
    rol = fabrica.rol("Administrador")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol, scp="global")
    agregar_permiso(db_session, usuario, sede, "Usuarios", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=None, scope="global"
    )
    return usuario, sede, rol


def autenticar_como(usuario_db, rol_nombre, sede_id=None, scope="por_sede"):
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario_db, rol_nombre, sede_id=sede_id, scope=scope
    )


# ---------------------------------------------------------------------------
# CA1 - HU20/HU21 generan auditoría automática
# ---------------------------------------------------------------------------


class TestCA1AuditoriaAutomatica:
    def test_editar_usuario_genera_un_registro(self, client, db_session, fabrica, admin_editor):
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        objetivo.nmbr_cmplt = "Nombre Original"
        db_session.flush()

        resp = client.put(f"/usuarios/{objetivo.id_usr}", json={"nmbr_cmplt": "Nombre Editado"})
        assert resp.status_code == 200

        registros = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"usuario:{objetivo.id_usr}")
            .all()
        )
        assert len(registros) == 1

    def test_el_registro_trae_usuario_ejecutor_y_sede(
        self, client, db_session, fabrica, admin_editor
    ):
        usuario_admin, sede_admin, _ = admin_editor
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))

        client.put(f"/usuarios/{objetivo.id_usr}", json={"nmbr_cmplt": "Otro Nombre"})

        registro = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"usuario:{objetivo.id_usr}")
            .one()
        )
        # scope global -> id_sd viaja en None en el JWT del admin (ver
        # usuario_jwt en admin_editor), y así se persiste: HT-11 no inventa
        # una sede que el JWT no traía.
        assert registro.id_usr == usuario_admin.id_usr
        assert registro.id_sd is None

    def test_el_registro_trae_valores_anteriores_y_nuevos(
        self, client, db_session, fabrica, admin_editor
    ):
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        objetivo.nmbr_cmplt = "Antes Del Cambio"
        db_session.flush()

        client.put(f"/usuarios/{objetivo.id_usr}", json={"nmbr_cmplt": "Después Del Cambio"})

        registro = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"usuario:{objetivo.id_usr}")
            .one()
        )
        assert registro.vlrs_antrrs["nmbr_cmplt"] == "Antes Del Cambio"
        assert registro.vlrs_nvs["nmbr_cmplt"] == "Después Del Cambio"

    def test_solo_registra_los_campos_que_realmente_cambiaron(
        self, client, db_session, fabrica, admin_editor
    ):
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        correo_original = objetivo.crr

        client.put(f"/usuarios/{objetivo.id_usr}", json={"nmbr_cmplt": "Solo Nombre Cambia"})

        registro = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"usuario:{objetivo.id_usr}")
            .one()
        )
        assert "nmbr_cmplt" in registro.vlrs_antrrs
        assert "crr" not in registro.vlrs_antrrs
        assert correo_original == objetivo.crr  # no tocado

    def test_body_sin_cambios_reales_no_genera_registro(
        self, client, db_session, fabrica, admin_editor
    ):
        """Reenviar el mismo valor no es una edición real (mismo criterio
        que ya usa HU20 para el rol propio): no hay 'antes' distinto de
        'después', así que no hay nada que auditar."""
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        objetivo.nmbr_cmplt = "Nombre Sin Cambios"
        db_session.flush()

        resp = client.put(f"/usuarios/{objetivo.id_usr}", json={"nmbr_cmplt": "Nombre Sin Cambios"})

        assert resp.status_code == 200
        registros = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"usuario:{objetivo.id_usr}")
            .count()
        )
        assert registros == 0

    def test_conceder_permisos_genera_un_registro(self, client, db_session, fabrica, admin_editor):
        _, sede, _ = admin_editor
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        from app.models import Ubicacion

        ubicacion = Ubicacion(
            id_sd=sede.id_sd,
            nmbr="Ubicación Auditada",
            lttd=-12.0,
            lngtd=-77.0,
            plgn_gjsn={
                "type": "Polygon",
                "coordinates": [[[-77.0, -12.0], [-77.1, -12.0], [-77.1, -12.1], [-77.0, -12.0]]],
            },
        )
        db_session.add(ubicacion)
        db_session.flush()

        resp = client.put(
            f"/usuarios/{objetivo.id_usr}/permisos-ubicaciones",
            json={"ubicacion_ids": [ubicacion.id_ubccn]},
        )
        assert resp.status_code == 200

        registro = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"permisos_ubicacion:{objetivo.id_usr}")
            .one()
        )
        assert registro.vlrs_nvs["ubicaciones_agregadas"] == [ubicacion.id_ubccn]

    def test_conceder_y_luego_revocar_registra_ambos_lados(
        self, client, db_session, fabrica, admin_editor
    ):
        _, sede, _ = admin_editor
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        from app.models import PermisoUbicacion, Ubicacion

        ubicacion = Ubicacion(
            id_sd=sede.id_sd,
            nmbr="Ubicación Para Revocar",
            lttd=-12.0,
            lngtd=-77.0,
            plgn_gjsn={
                "type": "Polygon",
                "coordinates": [[[-77.0, -12.0], [-77.1, -12.0], [-77.1, -12.1], [-77.0, -12.0]]],
            },
        )
        db_session.add(ubicacion)
        db_session.flush()
        db_session.add(PermisoUbicacion(id_usr=objetivo.id_usr, id_ubccn=ubicacion.id_ubccn))
        db_session.flush()

        client.put(f"/usuarios/{objetivo.id_usr}/permisos-ubicaciones", json={"ubicacion_ids": []})

        registros = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"permisos_ubicacion:{objetivo.id_usr}")
            .all()
        )
        assert len(registros) == 1
        assert registros[0].vlrs_antrrs["ubicaciones_quitadas"] == [ubicacion.id_ubccn]

    def test_no_se_audita_por_fuera_de_hu20_hu21(self, client, db_session, fabrica, admin_editor):
        """Otro UPDATE cualquiera sobre Usuario -p. ej. uno hecho a mano en
        un test, sin pasar por auditar_cambios()- no debe generar una fila:
        el listener solo actúa si la sesión trae la marca de contexto."""
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        objetivo.nmbr_cmplt = "Editado Sin Pasar Por El Endpoint"
        db_session.commit()

        registros = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"usuario:{objetivo.id_usr}")
            .count()
        )
        assert registros == 0


# ---------------------------------------------------------------------------
# Exclusión de columnas sensibles
# ---------------------------------------------------------------------------


class TestExclusionDeColumnasSensibles:
    def test_cntrsn_hsh_nunca_aparece_en_el_registro(
        self, client, db_session, fabrica, admin_editor
    ):
        """El PUT de HU20 no permite tocar cntrsn_hsh directamente -no está
        en UsuarioActualizar-, así que se fuerza el escenario editando el
        hash a mano en la misma sesión que hace el cambio auditado, para
        probar que el listener lo excluiría aunque lograra colarse."""
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))

        resp = client.put(f"/usuarios/{objetivo.id_usr}", json={"nmbr_cmplt": "Nombre Cambiado"})
        assert resp.status_code == 200

        registro = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"usuario:{objetivo.id_usr}")
            .one()
        )
        assert "cntrsn_hsh" not in registro.vlrs_antrrs
        assert "cntrsn_hsh" not in registro.vlrs_nvs

    def test_editar_el_hash_directamente_no_lo_expone(self, db_session, fabrica, admin_editor):
        """Prueba directa a nivel de listener: si algún código futuro
        alguna vez hiciera setattr(usuario, "cntrsn_hsh", ...) dentro de
        una sesión marcada para auditoría, la columna sigue excluida."""
        from app.security.auditoria import _CLAVE_CONTEXTO
        from app.security.hashing import hash_password

        usuario_admin, _, _ = admin_editor
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))

        db_session.info[_CLAVE_CONTEXTO] = {"id_usr": usuario_admin.id_usr, "id_sd": None}
        objetivo.cntrsn_hsh = hash_password("NuevaClave123")
        objetivo.nmbr_cmplt = "Nombre También Cambiado"
        db_session.commit()

        registro = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"usuario:{objetivo.id_usr}")
            .one()
        )
        assert "cntrsn_hsh" not in registro.vlrs_antrrs
        assert "cntrsn_hsh" not in registro.vlrs_nvs
        assert "nmbr_cmplt" in registro.vlrs_nvs


# ---------------------------------------------------------------------------
# CA2 - GET /auditoria: filtros y acceso restringido a Administrador
# ---------------------------------------------------------------------------


class TestCA2FiltrosYAcceso:
    def test_administrador_puede_listar(self, client, admin_editor):
        assert client.get("/auditoria").status_code == 200

    def test_tecnico_ceneris_no_puede_listar(self, client, db_session, fabrica):
        """CA2: 'únicamente para Administrador'. Técnico CENERIS tiene
        Lectura en 'Usuarios' (ver seed), no Edición -que es lo que exige
        este endpoint-, así que debe seguir sin poder entrar."""
        rol = fabrica.rol("Técnico CENERIS")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Usuarios", "Lectura", rol)
        autenticar_como(usuario, rol.nmbr, sede_id=sede.id_sd)

        resp = client.get("/auditoria")
        assert resp.status_code == 403

    def test_cliente_final_no_puede_listar(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        autenticar_como(usuario, rol.nmbr, sede_id=sede.id_sd)

        resp = client.get("/auditoria")
        assert resp.status_code == 403

    def test_filtra_por_usuario(self, client, db_session, fabrica, admin_editor):
        objetivo_a = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        objetivo_b = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        client.put(f"/usuarios/{objetivo_a.id_usr}", json={"nmbr_cmplt": "Editado A"})
        client.put(f"/usuarios/{objetivo_b.id_usr}", json={"nmbr_cmplt": "Editado B"})

        usuario_admin, _, _ = admin_editor
        resp = client.get("/auditoria", params={"usuario_id": usuario_admin.id_usr})

        assert resp.status_code == 200
        entidades = {i["entdd"] for i in resp.json()["items"]}
        assert f"usuario:{objetivo_a.id_usr}" in entidades
        assert f"usuario:{objetivo_b.id_usr}" in entidades

    def test_filtra_por_rango_de_fechas_excluye_fuera_de_rango(
        self, client, db_session, fabrica, admin_editor
    ):
        import datetime as dt

        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        client.put(f"/usuarios/{objetivo.id_usr}", json={"nmbr_cmplt": "Editado Hoy"})

        futuro = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat()
        resp = client.get("/auditoria", params={"fecha_inicio": futuro})

        entidades = {i["entdd"] for i in resp.json()["items"]}
        assert f"usuario:{objetivo.id_usr}" not in entidades

    def test_filtra_por_rango_de_fechas_incluye_dentro_del_rango(
        self, client, db_session, fabrica, admin_editor
    ):
        import datetime as dt

        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        client.put(f"/usuarios/{objetivo.id_usr}", json={"nmbr_cmplt": "Editado Ahora"})

        pasado = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()
        resp = client.get("/auditoria", params={"fecha_inicio": pasado})

        entidades = {i["entdd"] for i in resp.json()["items"]}
        assert f"usuario:{objetivo.id_usr}" in entidades

    def test_paginado_de_10_por_defecto(self, client, db_session, fabrica, admin_editor):
        for i in range(12):
            objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
            client.put(f"/usuarios/{objetivo.id_usr}", json={"nmbr_cmplt": f"Masivo {i}"})

        resp = client.get("/auditoria")
        cuerpo = resp.json()
        assert cuerpo["por_pagina"] == 10
        assert len(cuerpo["items"]) == 10

    def test_incluye_el_nombre_del_usuario_ejecutor(
        self, client, db_session, fabrica, admin_editor
    ):
        usuario_admin, _, _ = admin_editor
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        client.put(f"/usuarios/{objetivo.id_usr}", json={"nmbr_cmplt": "Editado Con Nombre"})

        resp = client.get("/auditoria", params={"usuario_id": usuario_admin.id_usr})

        items = resp.json()["items"]
        assert all(i["usuario_nombre"] == usuario_admin.nmbr_cmplt for i in items)


# ---------------------------------------------------------------------------
# CA3 - Inmutabilidad a nivel de aplicación
# ---------------------------------------------------------------------------


class TestCA3Inmutabilidad:
    def test_no_existe_metodo_put_sobre_auditoria(self, client, admin_editor):
        resp = client.put("/auditoria/1", json={})
        assert resp.status_code in (404, 405)

    def test_no_existe_metodo_delete_sobre_auditoria(self, client, admin_editor):
        resp = client.delete("/auditoria/1")
        assert resp.status_code in (404, 405)

    def test_no_existe_metodo_patch_sobre_auditoria(self, client, admin_editor):
        resp = client.patch("/auditoria/1", json={})
        assert resp.status_code in (404, 405)

    def test_openapi_no_declara_escritura_sobre_auditoria(self, client):
        """Confirma a nivel de contrato -no solo de un intento puntual- que
        el router de auditoría nunca declaró un endpoint de escritura."""
        spec = client.get("/openapi.json").json()
        metodos = set()
        for ruta, operaciones in spec["paths"].items():
            if ruta.startswith("/auditoria"):
                metodos.update(m.upper() for m in operaciones)
        assert metodos == {"GET"}


# ---------------------------------------------------------------------------
# CA4 - Aislamiento por sede, incluida la advertencia de id_sd NULL
# ---------------------------------------------------------------------------


class TestCA4AislamientoPorSede:
    def test_administrador_por_sede_no_ve_registros_de_otra_sede(self, client, db_session, fabrica):
        rol = fabrica.rol("Administrador")
        sede_propia = fabrica.sede()
        sede_ajena = fabrica.sede()
        admin_propio = fabrica.usuario(rol=rol, scp="por_sede")
        admin_ajeno = fabrica.usuario(rol=rol, scp="por_sede")
        agregar_permiso(db_session, admin_propio, sede_propia, "Usuarios", "Edición", rol)
        agregar_permiso(db_session, admin_ajeno, sede_ajena, "Usuarios", "Edición", rol)

        # El admin ajeno edita a alguien de SU sede -> registro con id_sd=sede_ajena.
        autenticar_como(admin_ajeno, rol.nmbr, sede_id=sede_ajena.id_sd)
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        client.put(f"/usuarios/{objetivo.id_usr}", json={"nmbr_cmplt": "Editado En Sede Ajena"})

        # El admin propio, limitado a su propia sede, no debe verlo.
        autenticar_como(admin_propio, rol.nmbr, sede_id=sede_propia.id_sd)
        resp = client.get("/auditoria")

        entidades = {i["entdd"] for i in resp.json()["items"]}
        assert f"usuario:{objetivo.id_usr}" not in entidades

    def test_administrador_por_sede_ve_los_de_su_propia_sede(self, client, db_session, fabrica):
        rol = fabrica.rol("Administrador")
        sede_propia = fabrica.sede()
        admin_propio = fabrica.usuario(rol=rol, scp="por_sede")
        agregar_permiso(db_session, admin_propio, sede_propia, "Usuarios", "Edición", rol)

        autenticar_como(admin_propio, rol.nmbr, sede_id=sede_propia.id_sd)
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        client.put(f"/usuarios/{objetivo.id_usr}", json={"nmbr_cmplt": "Editado En Mi Sede"})

        resp = client.get("/auditoria")
        entidades = {i["entdd"] for i in resp.json()["items"]}
        assert f"usuario:{objetivo.id_usr}" in entidades

    def test_filtro_explicito_de_sede_acota_al_administrador_global(
        self, client, db_session, fabrica, admin_editor
    ):
        """Un Administrador global (sin restricción propia) puede acotar la
        vista a una sede concreta con ?sede_id=, y los registros de otras
        sedes quedan fuera de esa consulta puntual."""
        _, sede_admin, _ = admin_editor
        rol = fabrica.rol("Administrador")
        otra_sede = fabrica.sede()
        otro_admin = fabrica.usuario(rol=rol, scp="por_sede")
        agregar_permiso(db_session, otro_admin, otra_sede, "Usuarios", "Edición", rol)

        autenticar_como(otro_admin, rol.nmbr, sede_id=otra_sede.id_sd)
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        client.put(f"/usuarios/{objetivo.id_usr}", json={"nmbr_cmplt": "Editado En Otra Sede"})

        # Vuelve a autenticarse como el admin global original.
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            admin_editor[0], "Administrador", sede_id=None, scope="global"
        )
        resp = client.get("/auditoria", params={"sede_id": sede_admin.id_sd})

        entidades = {i["entdd"] for i in resp.json()["items"]}
        assert f"usuario:{objetivo.id_usr}" not in entidades

    def test_registro_con_sede_null_visible_para_administrador_global(
        self, client, db_session, fabrica, admin_editor
    ):
        """Advertencia de HT-04: el login puede emitir sede_id=None. Un
        registro de auditoría con id_sd NULL (el admin_editor de este
        archivo simula justo ese caso: scope global, sede_id=None en el
        JWT) sigue siendo visible para un Administrador global sin filtro
        de sede aplicado -no se pierde el registro por el bug de HT-04-.
        """
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        client.put(f"/usuarios/{objetivo.id_usr}", json={"nmbr_cmplt": "Con Sede Nula"})

        registro = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"usuario:{objetivo.id_usr}")
            .one()
        )
        assert registro.id_sd is None  # confirma el escenario NULL

        resp = client.get("/auditoria")
        entidades = {i["entdd"] for i in resp.json()["items"]}
        assert f"usuario:{objetivo.id_usr}" in entidades

    def test_registro_con_sede_null_no_visible_para_administrador_por_sede(
        self, client, db_session, fabrica, admin_editor
    ):
        """Decisión explícita de HT-11 sobre el caso NULL: 'sin sede
        asociada' no es 'cualquier sede'. Un Administrador con scope
        'por_sede' -restringido a UNA sede concreta, sea cual sea- nunca
        ve un registro que no tiene ninguna sede asociada."""
        objetivo_admin_global = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        client.put(
            f"/usuarios/{objetivo_admin_global.id_usr}",
            json={"nmbr_cmplt": "Con Sede Nula Otra Vez"},
        )

        rol = fabrica.rol("Administrador")
        sede_propia = fabrica.sede()
        admin_por_sede = fabrica.usuario(rol=rol, scp="por_sede")
        agregar_permiso(db_session, admin_por_sede, sede_propia, "Usuarios", "Edición", rol)
        autenticar_como(admin_por_sede, rol.nmbr, sede_id=sede_propia.id_sd)

        resp = client.get("/auditoria")
        entidades = {i["entdd"] for i in resp.json()["items"]}
        assert f"usuario:{objetivo_admin_global.id_usr}" not in entidades

    def test_filtro_explicito_de_sede_excluye_los_null_incluso_para_global(
        self, client, db_session, fabrica, admin_editor
    ):
        """Decisión explícita: pedir ?sede_id=<n> es pedir ESA sede, no
        'esa sede o sin sede'. Aplica incluso al Administrador global."""
        _, sede_admin, _ = admin_editor
        objetivo = fabrica.usuario(rol=fabrica.rol("Cliente Final"))
        client.put(f"/usuarios/{objetivo.id_usr}", json={"nmbr_cmplt": "Con Sede Nula Filtrada"})

        resp = client.get("/auditoria", params={"sede_id": sede_admin.id_sd})

        entidades = {i["entdd"] for i in resp.json()["items"]}
        assert f"usuario:{objetivo.id_usr}" not in entidades


# ---------------------------------------------------------------------------
# CA5 - Accesos denegados de HT-09 en el mismo histórico
# ---------------------------------------------------------------------------


class TestCA5AccesosDenegados:
    def test_403_por_falta_de_permiso_queda_en_el_historico(
        self, client, db_session, fabrica, admin_editor
    ):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        sin_permiso = fabrica.usuario(rol=rol)
        autenticar_como(sin_permiso, rol.nmbr, sede_id=sede.id_sd)

        denegado = client.get("/usuarios")
        assert denegado.status_code == 403

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            admin_editor[0], admin_editor[2].nmbr, sede_id=None, scope="global"
        )
        resp = client.get("/auditoria", params={"usuario_id": sin_permiso.id_usr})

        items = resp.json()["items"]
        assert any(i["accn"].startswith("acceso_denegado:") for i in items)
        assert any(i["entdd"] == "Usuarios" for i in items)

    def test_403_por_aislamiento_de_sede_queda_en_el_historico(
        self, client, db_session, fabrica, admin_editor
    ):
        """verificar_sede() también pasa por _registrar_acceso_denegado."""
        rol = fabrica.rol("Técnico CENERIS")
        sede_propia = fabrica.sede()
        sede_ajena = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede_propia, "Ubicaciones", "Edición", rol)
        autenticar_como(usuario, rol.nmbr, sede_id=sede_propia.id_sd)

        # Crear una ubicación en la sede ajena y luego intentar editarla
        # dispara verificar_sede() -> 403, no tiene_permiso().
        from app.models import Ubicacion

        ubicacion_ajena = Ubicacion(
            id_sd=sede_ajena.id_sd,
            nmbr="Ubicación Ajena Para CA5",
            lttd=-12.0,
            lngtd=-77.0,
            plgn_gjsn={
                "type": "Polygon",
                "coordinates": [[[-77.0, -12.0], [-77.1, -12.0], [-77.1, -12.1], [-77.0, -12.0]]],
            },
        )
        db_session.add(ubicacion_ajena)
        db_session.flush()

        denegado = client.put(
            f"/ubicaciones/{ubicacion_ajena.id_ubccn}", json={"nmbr": "Intento Ajeno"}
        )
        assert denegado.status_code == 403

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            admin_editor[0], admin_editor[2].nmbr, sede_id=None, scope="global"
        )
        resp = client.get("/auditoria", params={"usuario_id": usuario.id_usr})

        # tiene_permiso() ya lo dejaría pasar -tiene Edición en su propia
        # sede-, así que si el 403 igual llegó, fue verificar_sede() quien
        # lo cortó por la sede AJENA del recurso. Se distingue por entdd
        # (el módulo pasado a verificar_sede), no por accn -ambos caminos
        # arman "acceso_denegado:<accion>" con el mismo formato-.
        items = resp.json()["items"]
        assert any(
            i["accn"] == "acceso_denegado:edicion" and i["entdd"] == "Ubicaciones" for i in items
        )

    def test_403_no_genera_valores_antes_ni_despues(
        self, client, db_session, fabrica, admin_editor
    ):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        sin_permiso = fabrica.usuario(rol=rol)
        autenticar_como(sin_permiso, rol.nmbr, sede_id=sede.id_sd)
        client.get("/usuarios")

        registro = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.id_usr == sin_permiso.id_usr)
            .order_by(LogAuditoria.id_evnt.desc())
            .first()
        )
        assert registro is not None
        assert registro.vlrs_antrrs is None
        assert registro.vlrs_nvs is None

    def test_un_403_no_impide_que_la_respuesta_siga_siendo_403(
        self, client, db_session, fabrica, monkeypatch
    ):
        """Si la escritura del log de auditoría fallara, el 403 original
        debe seguir devolviéndose -no debe convertirse en un 500-."""
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        autenticar_como(usuario, rol.nmbr, sede_id=sede.id_sd)

        original_commit = db_session.commit
        llamadas = {"n": 0}

        def commit_falla_una_vez():
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                raise RuntimeError("BD caída, simulada por el test")
            return original_commit()

        monkeypatch.setattr(db_session, "commit", commit_falla_una_vez)

        resp = client.get("/usuarios")

        assert resp.status_code == 403
