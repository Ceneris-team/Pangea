"""HT-11: criterios completos sobre PostgreSQL real, sin simular triggers o privilegios."""

import json
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.database import RuntimeSession, get_db
from app.main import app
from app.models import LogAuditoria, PermisoUbicacion, UsuarioCliente, UsuarioProyecto
from app.security.auditoria import limpiar_contexto_auditoria, marcar_contexto_auditoria
from app.security.auditoria_contexto import marcar_actor
from app.security.dependencies import get_current_user
from tests.routers.test_mediciones import crear_ubicacion


@pytest.fixture()
def auditoria(db_session, fabrica):
    db = db_session
    admin = fabrica.usuario(fabrica.rol("Administrador"), scp="global")
    empresas = [fabrica.cliente(), fabrica.cliente()]
    sedes = [fabrica.sede(e) for e in empresas]
    proyectos = [crear_ubicacion(db, sede, f"Proyecto {i}") for i, sede in enumerate(sedes)]
    personas = [
        fabrica.usuario(fabrica.rol("Usuario Empresa"), scp="por_cliente") for _ in empresas
    ]
    miembros = [
        UsuarioCliente(id_usr=u.id_usr, id_clnt=e.id_clnt, rol_emp="Administrador", estd="Activo")
        for u, e in zip(personas, empresas)
    ]
    db.add_all(miembros)
    db.commit()
    actor = {"sub": str(admin.id_usr), "scope": "global", "rol": "Administrador", "sede_id": None}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: actor
    try:
        with TestClient(app) as client:
            yield client, db, actor, admin, empresas, sedes, proyectos, personas, miembros
    finally:
        app.dependency_overrides.clear()


def de_empresa(actor, persona, empresa):
    actor.clear()
    actor.update(
        sub=str(persona.id_usr),
        scope="por_cliente",
        rol="Usuario Empresa",
        cliente_id=empresa.id_clnt,
        sede_id=None,
    )


def eventos(db, afectado):
    return (
        db.query(LogAuditoria).filter_by(id_afectado=afectado).order_by(LogAuditoria.id_evnt).all()
    )


def test_cambios_sql_y_proceso_se_auditan_sin_endpoint(db_session, fabrica):
    db = db_session
    usuario = fabrica.usuario()
    assert eventos(db, usuario.id_usr)[-1].accn == "crear_usuario"
    db.execute(
        text("UPDATE usr SET nmbr_cmplt='Nombre por SQL' WHERE id_usr=:id"), {"id": usuario.id_usr}
    )
    sql = eventos(db, usuario.id_usr)[-1]
    assert sql.origen == "SQL" and sql.ejecutor.startswith("proceso:")
    assert sql.vlrs_nvs["nmbr_cmplt"] == "Nombre por SQL"
    marcar_contexto_auditoria(db, usuario.id_usr)
    db.execute(text("UPDATE usr SET estd='Inactivo' WHERE id_usr=:id"), {"id": usuario.id_usr})
    proceso = eventos(db, usuario.id_usr)[-1]
    assert proceso.origen == "Proceso" and proceso.id_usr == usuario.id_usr
    assert proceso.accn == "desactivar_usuario"
    db.execute(text("UPDATE usr SET estd='Activo' WHERE id_usr=:id"), {"id": usuario.id_usr})
    assert eventos(db, usuario.id_usr)[-1].accn == "activar_usuario"
    limpiar_contexto_auditoria(db)


def test_alta_edicion_rol_y_baja_de_usuario_se_auditan(db_session, fabrica):
    usuario = fabrica.usuario()
    rol = fabrica.rol("Cliente Final")
    usuario.id_rl = rol.id_rl
    db_session.flush()
    assert eventos(db_session, usuario.id_usr)[-1].vlrs_nvs["id_rl"] == rol.id_rl
    id_usr = usuario.id_usr
    db_session.delete(usuario)
    db_session.flush()
    ultimo = eventos(db_session, id_usr)[-1]
    assert ultimo.accn == "eliminar_usuario" and ultimo.vlrs_antrrs["id_usr"] == id_usr


def test_identidad_global_no_se_atribuye_a_empresa_del_ejecutor(auditoria):
    client, db, actor, admin, empresas, _, _, personas, _ = auditoria
    marcar_actor(db, actor, origen="API")
    personas[0].nmbr_cmplt = "Cambio global de identidad"
    db.flush()
    evento = eventos(db, personas[0].id_usr)[-1]
    assert evento.id_usr == admin.id_usr
    assert evento.id_clnt is None and evento.id_sd is None
    de_empresa(actor, personas[0], empresas[0])
    respuesta = client.get(f"/auditoria/{evento.id_evnt}")
    assert respuesta.status_code == 404


def test_membresia_rol_revocacion_y_proyectos_con_ambito_correcto(auditoria):
    _, db, actor, admin, empresas, sedes, proyectos, personas, miembros = auditoria
    marcar_actor(db, actor, origen="API")
    miembros[0].rol_emp = "Lector"
    db.flush()
    permiso = UsuarioProyecto(id_mmb=miembros[0].id_mmb, id_ubccn=proyectos[0].id_ubccn)
    db.add(permiso)
    db.flush()
    concedido = eventos(db, personas[0].id_usr)[-1]
    assert (concedido.id_clnt, concedido.id_sd, concedido.id_ubccn) == (
        empresas[0].id_clnt,
        sedes[0].id_sd,
        proyectos[0].id_ubccn,
    )
    assert concedido.id_usr == admin.id_usr
    assert concedido.vlrs_antrrs["proyecto_ids"] == []
    assert concedido.vlrs_nvs["proyecto_ids"] == [proyectos[0].id_ubccn]
    assert concedido.vlrs_nvs["rol"] == "Lector"
    db.delete(permiso)
    db.flush()
    revocado = eventos(db, personas[0].id_usr)[-1]
    assert revocado.accn == "revocar" and revocado.vlrs_nvs["proyecto_ids"] == []
    miembros[0].estd = "Inactivo"
    db.flush()
    assert eventos(db, personas[0].id_usr)[-1].vlrs_nvs["estado"] == "Inactivo"
    db.delete(miembros[0])
    db.flush()
    assert eventos(db, personas[0].id_usr)[-1].accn == "revocar"


def test_guardar_sin_cambios_no_genera_eventos(auditoria):
    _, db, _, _, _, _, _, personas, miembros = auditoria
    antes = len(eventos(db, personas[0].id_usr))
    miembros[0].rol_emp = miembros[0].rol_emp
    miembros[0].estd = miembros[0].estd
    db.flush()
    assert len(eventos(db, personas[0].id_usr)) == antes


def test_permisos_de_dos_empresas_no_mezclan_snapshots(auditoria):
    _, db, actor, _, empresas, _, proyectos, personas, _ = auditoria
    marcar_actor(db, actor, origen="API")
    for proyecto in proyectos:
        db.add(PermisoUbicacion(id_usr=personas[0].id_usr, id_ubccn=proyecto.id_ubccn))
        db.flush()
    for evento in eventos(db, personas[0].id_usr):
        if evento.entdd.startswith("permisos_ubicacion:"):
            indice = [e.id_clnt for e in empresas].index(evento.id_clnt)
            assert evento.vlrs_nvs["proyecto_ids"] == [proyectos[indice].id_ubccn]


@pytest.mark.parametrize("rol", ["Tecnico", "Lector"])
def test_roles_empresariales_sin_autorizacion_no_consultan(auditoria, rol):
    client, db, actor, _, empresas, _, _, personas, miembros = auditoria
    miembros[0].rol_emp = rol
    db.commit()
    de_empresa(actor, personas[0], empresas[0])
    assert client.get("/auditoria").status_code == 403


@pytest.mark.parametrize("rol", ["Técnico CENERIS", "Administrador Comercial", "Cliente Final"])
def test_roles_globales_sin_autorizacion_no_consultan(auditoria, rol):
    client, _, actor, *_ = auditoria
    actor["rol"] = rol
    assert client.get("/auditoria").status_code == 403


def test_admin_empresa_no_puede_saltar_aislamiento_con_filtros_o_id(auditoria):
    client, db, actor, _, empresas, sedes, proyectos, personas, miembros = auditoria
    ajeno = eventos(db, personas[1].id_usr)[-1]
    de_empresa(actor, personas[0], empresas[0])
    respuesta = client.get("/auditoria", params={"por_pagina": 100})
    assert respuesta.status_code == 200
    assert respuesta.json()["items"]
    assert all(i["id_clnt"] == empresas[0].id_clnt for i in respuesta.json()["items"])
    for filtro in (
        {"empresa_id": empresas[1].id_clnt},
        {"sede_id": sedes[1].id_sd},
        {"proyecto_id": proyectos[1].id_ubccn},
    ):
        assert client.get("/auditoria", params=filtro).json()["items"] == []
    assert client.get(f"/auditoria/{ajeno.id_evnt}").status_code == 404
    assert (
        client.get("/auditoria", headers={"X-Cliente-Id": str(empresas[1].id_clnt)}).json()["items"]
        == respuesta.json()["items"]
    )


def test_filtros_combinados_paginacion_y_zona_horaria(auditoria):
    client, db, actor, admin, empresas, sedes, proyectos, personas, miembros = auditoria
    marcar_actor(db, actor, origen="API")
    permiso = UsuarioProyecto(id_mmb=miembros[0].id_mmb, id_ubccn=proyectos[0].id_ubccn)
    db.add(permiso)
    db.commit()
    filtros = {
        "empresa_id": empresas[0].id_clnt,
        "proyecto_id": proyectos[0].id_ubccn,
        "sede_id": sedes[0].id_sd,
        "ejecutor_id": admin.id_usr,
        "usuario_afectado_id": personas[0].id_usr,
        "accion": "conceder",
        "resultado": "Exitoso",
        "fecha_inicio": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        "fecha_fin": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "por_pagina": 1,
    }
    respuesta = client.get("/auditoria", params=filtros)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["total"] == 1
    assert datetime.fromisoformat(respuesta.json()["items"][0]["fch_evnt"]).utcoffset() is not None
    assert client.get("/auditoria", params={**filtros, "pagina": 2}).json()["items"] == []
    assert (
        client.get("/auditoria", params={"fecha_inicio": "2026-11-01T00:00:00"}).status_code == 422
    )
    assert (
        client.get(
            "/auditoria",
            params={"fecha_inicio": filtros["fecha_fin"], "fecha_fin": filtros["fecha_inicio"]},
        ).status_code
        == 422
    )


def test_denegacion_una_vez_con_operacion_sin_query_sensible(auditoria):
    client, db, actor, _, empresas, _, _, personas, _ = auditoria
    de_empresa(actor, personas[0], empresas[0])
    assert (
        client.get(f"/empresas/{empresas[1].id_clnt}/usuarios?token=NO_GUARDAR").status_code == 403
    )
    registros = (
        db.query(LogAuditoria).filter_by(id_usr=personas[0].id_usr, resultado="Denegado").all()
    )
    assert len(registros) == 1
    assert registros[0].motivo and registros[0].operacion == "GET /empresas/{cliente_id}/usuarios"
    assert "NO_GUARDAR" not in registros[0].operacion


def test_revocacion_vigente_bloquea_auditoria_y_queda_registrada(auditoria):
    client, db, actor, _, empresas, _, _, personas, miembros = auditoria
    miembros[0].estd = "Inactivo"
    db.commit()
    de_empresa(actor, personas[0], empresas[0])
    assert client.get("/auditoria").status_code == 403
    assert (
        db.query(LogAuditoria).filter_by(id_usr=personas[0].id_usr, resultado="Denegado").count()
        == 1
    )


def test_headers_y_membresia_revocada_con_autenticacion_real(auditoria):
    from app.security.jwt_auth import create_access_token

    client, db, _, _, empresas, _, proyectos, personas, miembros = auditoria
    app.dependency_overrides.pop(get_current_user)
    token = create_access_token(personas[0].id_usr, None, "por_cliente", "Usuario Empresa")
    headers = {"Authorization": f"Bearer {token}", "X-Cliente-Id": str(empresas[0].id_clnt)}
    assert client.get("/auditoria", headers=headers).status_code == 200
    assert (
        client.get(
            "/auditoria", headers={**headers, "X-Cliente-Id": str(empresas[1].id_clnt)}
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/auditoria", headers={**headers, "X-Proyecto-Id": str(proyectos[1].id_ubccn)}
        ).status_code
        == 403
    )
    miembros[0].estd = "Inactivo"
    db.commit()
    assert client.get("/auditoria", headers=headers).status_code == 403
    assert (
        db.query(LogAuditoria).filter_by(id_usr=personas[0].id_usr, resultado="Denegado").count()
        == 3
    )


def test_fallo_de_registro_denegado_conserva_403_y_emite_alerta(auditoria, monkeypatch, caplog):
    from app.security import auditoria_denegaciones

    client, _, actor, _, empresas, _, _, personas, _ = auditoria
    de_empresa(actor, personas[0], empresas[0])

    def fallar(*args, **kwargs):
        raise RuntimeError("password=NO_GUARDAR")

    monkeypatch.setattr(auditoria_denegaciones, "Session", fallar)
    assert client.get(f"/empresas/{empresas[1].id_clnt}/usuarios").status_code == 403
    assert "HT11_ALERTA_DENEGACION_NO_REGISTRADA" in caplog.text
    assert "NO_GUARDAR" not in caplog.text


def test_rollback_revierte_cambio_y_evento_juntos(auditoria):
    _, db, _, _, _, _, _, personas, miembros = auditoria
    antes = len(eventos(db, personas[0].id_usr))
    with pytest.raises(RuntimeError), db.begin_nested():
        miembros[0].estd = "Inactivo"
        db.flush()
        assert len(eventos(db, personas[0].id_usr)) == antes + 1
        raise RuntimeError("Revertir operacion")
    assert miembros[0].estd == "Activo"
    assert len(eventos(db, personas[0].id_usr)) == antes


def test_fallo_auditoria_impide_confirmar_cambio(auditoria):
    _, db, _, _, _, _, _, personas, miembros = auditoria
    # Un fallo real del INSERT de auditoria, no un mock del endpoint.
    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(
            text(
                "CREATE FUNCTION pg_temp.rechazar_auditoria() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fallo de auditoria'; END $$"
            )
        )
        db.execute(
            text(
                "CREATE TRIGGER fallo_prueba BEFORE INSERT ON lg_adtr FOR EACH ROW EXECUTE FUNCTION pg_temp.rechazar_auditoria()"
            )
        )
        miembros[0].estd = "Inactivo"
        db.flush()
    db.refresh(miembros[0])
    assert miembros[0].estd == "Activo"


def test_secretos_excluidos_en_json_anidado_y_cambio_identidad(auditoria):
    _, db, _, admin, _, _, _, personas, _ = auditoria
    datos = {
        "password": "NO_GUARDAR",
        "anidado": [{"token": "NO_GUARDAR", "credenciales_ftp": "NO_GUARDAR", "dato": 7}],
        "error": "NO_GUARDAR",
    }
    db.add(
        LogAuditoria(
            id_usr=admin.id_usr, accn="prueba", entdd="prueba", vlrs_antrrs=datos, vlrs_nvs=datos
        )
    )
    db.flush()
    evento = db.query(LogAuditoria).filter_by(entdd="prueba").one()
    db.refresh(evento)
    assert "NO_GUARDAR" not in json.dumps([evento.vlrs_antrrs, evento.vlrs_nvs])
    assert evento.vlrs_nvs["anidado"][0]["dato"] == 7
    assert all(
        "cntrsn_hsh" not in json.dumps([e.vlrs_antrrs, e.vlrs_nvs])
        for e in eventos(db, personas[0].id_usr)
    )


def test_particiones_mensuales_mantenimiento_e_idempotencia(db_session):
    db = db_session
    assert (
        db.execute(text("SELECT relkind FROM pg_class WHERE oid='lg_adtr'::regclass")).scalar_one()
        == "p"
    )
    assert (
        db.execute(
            text("SELECT count(*) FROM pg_inherits WHERE inhparent='lg_adtr'::regclass")
        ).scalar_one()
        >= 4
    )
    assert db.execute(text("SELECT auditoria_particiones(CURRENT_DATE,4)")).scalar_one() == 0
    assert (
        db.execute(
            text("SELECT auditoria_particiones((CURRENT_DATE + interval '1 year')::date,1)")
        ).scalar_one()
        == 1
    )
    assert (
        db.execute(
            text("SELECT auditoria_particiones((CURRENT_DATE + interval '1 year')::date,1)")
        ).scalar_one()
        == 0
    )


@pytest.fixture(scope="module")
def cuenta_runtime(_engine):
    from scripts.aprovisionar_auditoria import aprovisionar

    url = _engine.url.set(
        username="ht11_runtime_" + secrets.token_hex(6), password=secrets.token_urlsafe(24)
    )
    aprovisionar(
        _engine.url.render_as_string(hide_password=False), url.render_as_string(hide_password=False)
    )
    engine = create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "sql", ["UPDATE lg_adtr SET accn='alterado'", "DELETE FROM lg_adtr", "TRUNCATE lg_adtr"]
)
def test_cuenta_real_sin_privilegios_no_modifica_historial(cuenta_runtime, sql):
    with cuenta_runtime.connect() as conexion:
        assert not conexion.execute(
            text("SELECT rolsuper FROM pg_roles WHERE rolname=session_user")
        ).scalar_one()
        with pytest.raises(DBAPIError) as error:
            conexion.execute(text(sql))
        assert error.value.orig.pgcode == "42501"


def test_cuenta_runtime_no_puede_escalar_ni_desactivar_triggers(cuenta_runtime):
    with cuenta_runtime.connect() as conexion:
        with pytest.raises(DBAPIError):
            conexion.execute(text("SET ROLE pangea_auditoria"))
        conexion.rollback()
        with pytest.raises(DBAPIError):
            conexion.execute(text("ALTER TABLE usr DISABLE TRIGGER auditoria_cambios"))


def test_sesion_de_api_usa_rol_limitado_y_rechaza_cuenta_administrativa(cuenta_runtime, _engine):
    with RuntimeSession(bind=cuenta_runtime) as db:
        assert db.execute(text("SELECT current_user")).scalar_one() == "pangea_app"
    with (
        RuntimeSession(bind=_engine) as db,
        pytest.raises(RuntimeError, match="DATABASE_RUNTIME_URL"),
    ):
        db.execute(text("SELECT 1"))


def test_inmutabilidad_tambien_impide_truncar_particion_directa(cuenta_runtime, _engine):
    with _engine.connect() as conexion:
        particion = conexion.execute(
            text(
                "SELECT inhrelid::regclass::text FROM pg_inherits WHERE inhparent='lg_adtr'::regclass LIMIT 1"
            )
        ).scalar_one()
    with cuenta_runtime.connect() as conexion, pytest.raises(DBAPIError):
        conexion.exec_driver_sql(f"TRUNCATE {particion}")


def test_escritura_real_y_captura_con_cuenta_de_ejecucion(cuenta_runtime):
    from app.models import Usuario
    from app.security.hashing import hash_password

    with RuntimeSession(bind=cuenta_runtime) as db:
        rol = db.execute(text("SELECT id_rl FROM rl WHERE nmbr='Cliente Final'")).scalar_one()
        usuario = Usuario(
            id_rl=rol,
            scp="por_sede",
            nmbr_cmplt="Prueba runtime",
            crr=f"{secrets.token_hex(8)}@runtime.test",
            cntrsn_hsh=hash_password(secrets.token_urlsafe(16)),
        )
        db.add(usuario)
        db.flush()
        assert eventos(db, usuario.id_usr)[-1].accn == "crear_usuario"
        usuario.estd = "Inactivo"
        db.flush()
        assert eventos(db, usuario.id_usr)[-1].accn == "desactivar_usuario"
        db.rollback()


def test_worker_restringido_mantiene_particiones_de_auditoria_y_telemetria(cuenta_runtime):
    from app.services.particiones import asegurar_particiones

    with RuntimeSession(bind=cuenta_runtime) as db:
        hoy = datetime.now(timezone.utc).date()
        # Forzar un mes fuera del colchon de la migracion para probar CREATE real.
        futuro = hoy.replace(year=hoy.year + 2)
        creadas = asegurar_particiones(db.connection(), futuro, 1)
        assert len(creadas) == 1
        assert asegurar_particiones(db.connection(), futuro, 1) == []
        assert (
            db.execute(
                text("SELECT auditoria_particiones(:fecha,1)"), {"fecha": futuro}
            ).scalar_one()
            == 1
        )
        assert (
            db.execute(
                text("SELECT auditoria_particiones(:fecha,1)"), {"fecha": futuro}
            ).scalar_one()
            == 0
        )
        db.rollback()


def test_historial_anterior_conservado_y_saneado_por_migracion(_engine):
    import os
    import subprocess
    import sys
    from pathlib import Path

    nombre = "ht11_migracion_" + secrets.token_hex(6)
    url = _engine.url.set(database=nombre)
    entorno = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)}
    backend = Path(__file__).resolve().parents[2]
    with _engine.connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
        admin.exec_driver_sql(f"CREATE DATABASE {nombre}")
        try:

            def migrar(revision):
                resultado = subprocess.run(
                    [sys.executable, "-m", "alembic", "upgrade", revision],
                    cwd=backend,
                    env=entorno,
                    capture_output=True,
                    text=True,
                )
                assert resultado.returncode == 0, resultado.stderr

            migrar("f71d3b8a902c")
            temporal = create_engine(url)
            with temporal.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO lg_adtr (id_usr,accn,entdd,vlrs_nvs,fch_evnt) "
                        "SELECT id_usr,'crear','historico',CAST(:datos AS jsonb),CURRENT_TIMESTAMP-interval '2 months' "
                        "FROM usr WHERE crr='sistema.ingesta@pangea.internal'"
                    ),
                    {"datos": json.dumps({"dato": 1, "password": "NO_GUARDAR"})},
                )
            migrar("head")
            with temporal.connect() as conn:
                fila = conn.execute(
                    text("SELECT origen,vlrs_nvs FROM lg_adtr WHERE entdd='historico'")
                ).one()
                assert fila.origen == "Legado" and fila.vlrs_nvs == {"dato": 1}
                assert (
                    conn.execute(
                        text("SELECT count(*) FROM pg_inherits WHERE inhparent='lg_adtr'::regclass")
                    ).scalar_one()
                    >= 6
                )
            temporal.dispose()
        finally:
            admin.exec_driver_sql(f"DROP DATABASE {nombre} WITH (FORCE)")


def test_borrado_masivo_conserva_cada_transicion_de_permisos(auditoria):
    _, db, actor, _, _, sedes, proyectos, personas, _ = auditoria
    otro = crear_ubicacion(db, sedes[0], "Otro proyecto")
    marcar_actor(db, actor, origen="API")
    for proyecto in (proyectos[0], otro):
        db.add(PermisoUbicacion(id_usr=personas[0].id_usr, id_ubccn=proyecto.id_ubccn))
        db.flush()
    db.query(PermisoUbicacion).filter_by(id_usr=personas[0].id_usr).delete(
        synchronize_session=False
    )
    registros = [
        e
        for e in eventos(db, personas[0].id_usr)
        if e.entdd.startswith("permisos_ubicacion:") and e.accn == "revocar"
    ]
    assert len(registros) == 2
    assert set(registros[0].vlrs_antrrs["proyecto_ids"]) == {proyectos[0].id_ubccn, otro.id_ubccn}
    assert registros[0].vlrs_nvs["proyecto_ids"] == registros[1].vlrs_antrrs["proyecto_ids"]
    assert registros[-1].vlrs_nvs["proyecto_ids"] == []


def test_baja_membresia_conserva_proyectos_antes_de_cascada(auditoria):
    _, db, _, _, _, _, proyectos, personas, miembros = auditoria
    db.add(UsuarioProyecto(id_mmb=miembros[0].id_mmb, id_ubccn=proyectos[0].id_ubccn))
    db.flush()
    db.delete(miembros[0])
    db.flush()
    bajas = [
        e
        for e in eventos(db, personas[0].id_usr)
        if e.entdd.startswith("miembro_empresa:") and e.accn == "revocar"
    ]
    assert len(bajas) == 1
    assert bajas[0].vlrs_antrrs["proyecto_ids"] == [proyectos[0].id_ubccn]
    assert db.query(UsuarioProyecto).filter_by(id_ubccn=proyectos[0].id_ubccn).count() == 0


def test_denegacion_por_proyecto_registra_el_recurso_afectado(auditoria):
    from app.models import PermisoUsuarioSede

    client, db, actor, _, empresas, sedes, proyectos, personas, _ = auditoria
    # Cuenta por sede: tiene permiso local pero intenta editar un recurso ajeno.
    persona = personas[0]
    db.add(
        PermisoUsuarioSede(
            id_usr=persona.id_usr,
            id_sd=sedes[0].id_sd,
            id_rl=persona.id_rl,
            mdl="Ubicaciones",
            nvl="Edición",
        )
    )
    db.commit()
    actor.update(
        sub=str(persona.id_usr), scope="por_sede", rol="Cliente Final", sede_id=sedes[0].id_sd
    )
    assert (
        client.put(
            f"/ubicaciones/{proyectos[1].id_ubccn}", json={"nmbr": "Intento ajeno"}
        ).status_code
        == 403
    )
    registro = db.query(LogAuditoria).filter_by(id_usr=persona.id_usr, resultado="Denegado").one()
    assert (registro.id_clnt, registro.id_sd, registro.id_ubccn) == (
        empresas[1].id_clnt,
        sedes[1].id_sd,
        proyectos[1].id_ubccn,
    )


def test_denegacion_oculta_como_404_tambien_se_audita(auditoria):
    from app.models import Panel

    client, db, actor, _, empresas, sedes, _, personas, _ = auditoria
    panel = Panel(id_usr=personas[1].id_usr, id_sd=sedes[1].id_sd, nmbr="Panel ajeno")
    db.add(panel)
    db.commit()
    de_empresa(actor, personas[0], empresas[0])
    assert client.get(f"/paneles/{panel.id_pnl}").status_code == 404
    eventos = (
        db.query(LogAuditoria).filter_by(id_usr=personas[0].id_usr, resultado="Denegado").all()
    )
    assert len(eventos) == 1
    assert eventos[0].id_clnt == empresas[1].id_clnt
    assert eventos[0].motivo == "recurso_fuera_de_ambito"
    assert client.get("/paneles/2147483647").status_code == 404
    assert (
        db.query(LogAuditoria).filter_by(id_usr=personas[0].id_usr, resultado="Denegado").count()
        == 1
    )
