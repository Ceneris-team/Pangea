"""Aislamiento empresarial, proyectos y cupo de miembros activos."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import LimitePlan, PermisoUsuarioSede, PlanSuscripcion, Suscripcion, Usuario
from app.routers.auth import _resolver_sede_id_login
from app.security.dependencies import get_current_user
from app.services.limites_plan import fecha_comercial
from tests.routers.test_mediciones import crear_ubicacion


@pytest.fixture()
def escenario(db_session, fabrica):
    admin = fabrica.usuario(fabrica.rol("Administrador"), scp="global")
    andina = fabrica.cliente()
    sur = fabrica.cliente()
    sede_andina = fabrica.sede(andina)
    sede_sur = fabrica.sede(sur)
    proyectos_andina = [crear_ubicacion(db_session, sede_andina, nombre) for nombre in ("Norte", "Relaves")]
    proyecto_sur = crear_ubicacion(db_session, sede_sur, "Sur")
    plan = PlanSuscripcion(nmbr=f"Empresarial test {andina.id_clnt}", prc_mnsl=100)
    db_session.add(plan)
    db_session.flush()
    db_session.add_all([
        LimitePlan(id_pln=plan.id_pln, mx_sds=0, mx_ubccns=10, mx_dspstvs=10, mx_usrs=2),
        Suscripcion(
            id_clnt=andina.id_clnt, id_pln=plan.id_pln,
            fch_inc=fecha_comercial(), fch_vncmnt=fecha_comercial() + timedelta(days=30), estd="Activa",
        ),
    ])
    db_session.flush()
    actor = {"sub": str(admin.id_usr), "sede_id": None, "scope": "global", "rol": "Administrador"}
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: actor
    try:
        yield TestClient(app), actor, andina, sur, proyectos_andina, proyecto_sur, db_session
    finally:
        app.dependency_overrides.clear()


def _crear_miembro(cliente, id_clnt, nombre, correo, rol, proyectos=None):
    return cliente.post(f"/empresas/{id_clnt}/usuarios", json={
        "nombre": nombre, "correo": correo, "rol": rol,
        "proyecto_ids": proyectos or [],
    })


def _usar_miembro(actor, respuesta):
    actor.update({
        "sub": str(respuesta["miembro"]["id_usr"]),
        "scope": "por_cliente", "rol": "Usuario Empresa", "sede_id": None,
    })


def test_administrador_empresa_ve_solo_su_cliente_y_puede_gestionar_usuarios(escenario):
    cliente, actor, andina, sur, proyectos, _, db = escenario
    creado = _crear_miembro(cliente, andina.id_clnt, "Admin Andina", "admin.andina@test.example", "Administrador")
    assert creado.status_code == 201, creado.text
    assert creado.json()["contrasena_temporal"]
    _usar_miembro(actor, creado.json())

    listado = cliente.get("/empresas")
    assert listado.status_code == 200, listado.text
    assert [empresa["id_clnt"] for empresa in listado.json()] == [andina.id_clnt]
    assert listado.json()[0]["consumo"]["usuarios"] == 1
    assert len(cliente.get(f"/empresas/{andina.id_clnt}/proyectos").json()) == 2
    assert cliente.get(f"/empresas/{sur.id_clnt}/proyectos").status_code == 403
    assert cliente.get(f"/empresas/{sur.id_clnt}/usuarios").status_code == 403
    assert _resolver_sede_id_login(db, db.get(Usuario, int(actor["sub"]))) is None

    tecnico = _crear_miembro(cliente, andina.id_clnt, "Técnico", "tecnico.andina@test.example", "Tecnico", [proyectos[0].id_ubccn])
    assert tecnico.status_code == 201, tecnico.text
    assert tecnico.json()["miembro"]["proyecto_ids"] == []  # Técnico: toda su empresa.


def test_tecnico_ve_toda_su_empresa_y_no_puede_gestionar_usuarios(escenario):
    cliente, actor, andina, sur, proyectos, proyecto_sur, _ = escenario
    tecnico = _crear_miembro(cliente, andina.id_clnt, "Técnico", "tecnico.aislado@test.example", "Tecnico", [proyectos[0].id_ubccn])
    assert tecnico.status_code == 201, tecnico.text
    _usar_miembro(actor, tecnico.json())

    visibles = cliente.get(f"/empresas/{andina.id_clnt}/proyectos")
    assert visibles.status_code == 200
    assert {p["id_ubccn"] for p in visibles.json()} == {p.id_ubccn for p in proyectos}
    assert cliente.get(f"/empresas/{andina.id_clnt}/proyectos/{proyectos[1].id_ubccn}/recursos").status_code == 200
    assert cliente.get(f"/empresas/{sur.id_clnt}/proyectos/{proyecto_sur.id_ubccn}/recursos").status_code == 403
    assert cliente.get(f"/empresas/{andina.id_clnt}/usuarios").status_code == 403
    assert _crear_miembro(cliente, andina.id_clnt, "Otro", "otro@test.example", "Lector", [proyectos[0].id_ubccn]).status_code == 403
    assert cliente.get("/ubicaciones").status_code == 200


def test_cupo_incluye_admin_y_no_permite_desactivar_el_ultimo(escenario):
    cliente, actor, andina, _, proyectos, _, _ = escenario
    admin = _crear_miembro(cliente, andina.id_clnt, "Admin", "admin.cupo@test.example", "Administrador")
    assert admin.status_code == 201, admin.text
    _usar_miembro(actor, admin.json())
    miembro_id = admin.json()["miembro"]["id_mmb"]
    desactivar = cliente.patch(f"/empresas/{andina.id_clnt}/usuarios/{miembro_id}", json={
        "rol": "Administrador", "estado": "Inactivo", "proyecto_ids": [],
    })
    assert desactivar.status_code == 409

    tecnico = _crear_miembro(cliente, andina.id_clnt, "Técnico", "tecnico.cupo@test.example", "Tecnico", [proyectos[0].id_ubccn])
    assert tecnico.status_code == 201, tecnico.text
    lleno = _crear_miembro(cliente, andina.id_clnt, "Lector", "lector.cupo@test.example", "Lector", [proyectos[1].id_ubccn])
    assert lleno.status_code == 409
    assert cliente.get("/empresas").json()[0]["consumo"]["usuarios"] == 2

    desactivado = cliente.patch(f"/empresas/{andina.id_clnt}/usuarios/{tecnico.json()['miembro']['id_mmb']}", json={
        "rol": "Tecnico", "estado": "Inactivo", "proyecto_ids": [proyectos[0].id_ubccn],
    })
    assert desactivado.status_code == 200, desactivado.text
    assert _crear_miembro(cliente, andina.id_clnt, "Lector", "lector.cupo@test.example", "Lector", [proyectos[1].id_ubccn]).status_code == 201


def test_asignaciones_son_proyectos_reales_y_rechazan_otra_empresa(escenario):
    cliente, _, andina, _, proyectos, proyecto_sur, _ = escenario
    respuesta = _crear_miembro(cliente, andina.id_clnt, "Lector", "lector.ajeno@test.example", "Lector", [proyecto_sur.id_ubccn])
    assert respuesta.status_code == 422
    correcta = _crear_miembro(cliente, andina.id_clnt, "Lector", "lector.real@test.example", "Lector", [proyectos[0].id_ubccn])
    assert correcta.status_code == 201, correcta.text
    assert correcta.json()["miembro"]["proyecto_ids"] == [proyectos[0].id_ubccn]
    # El endpoint antiguo ya no permite crear agrupadores.
    assert cliente.post(f"/empresas/{andina.id_clnt}/proyectos", json={"nombre": "Grupo"}).status_code == 405


def test_usuarios_anteriores_aparecen_en_empresa_sin_duplicar_membresias(escenario, fabrica):
    cliente, _, andina, _, proyectos, _, db = escenario
    sede_id = proyectos[0].id_sd
    usuario = fabrica.usuario(fabrica.rol("Cliente Final"))
    db.add(PermisoUsuarioSede(
        id_usr=usuario.id_usr, id_sd=sede_id, id_rl=usuario.id_rl,
        mdl="Ubicaciones", nvl="Lectura",
    ))
    db.flush()

    respuesta = cliente.get(f"/empresas/{andina.id_clnt}/usuarios")
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == [{
        "id_mmb": None, "id_usr": usuario.id_usr,
        "nombre": usuario.nmbr_cmplt, "correo": usuario.crr,
        "rol": "Cliente Final", "estado": usuario.estd,
        "proyecto_ids": sorted(p.id_ubccn for p in proyectos), "legado": True,
    }]


def test_primero_y_siguiente_proyecto_no_requieren_grupo_ni_sede_previa(escenario):
    from app.models import Sede

    cliente, actor, andina, sur, proyectos, _, db = escenario
    # Una empresa recién registrada todavía no tiene sedes ni proyectos.
    registrada = cliente.post("/empresas", json={
        "nombre": "Minera nueva", "ruc": "20999888777", "correo_contacto": "mina@test.example",
    })
    assert registrada.status_code == 201, registrada.text
    empresa_id = registrada.json()["id_clnt"]
    assert db.query(Sede).filter(Sede.id_clnt == empresa_id).count() == 0
    plan_id = db.query(Suscripcion.id_pln).filter(Suscripcion.id_clnt == andina.id_clnt).scalar()
    db.add(Suscripcion(
        id_clnt=empresa_id, id_pln=plan_id,
        fch_inc=fecha_comercial(), fch_vncmnt=fecha_comercial() + timedelta(days=30), estd="Activa",
    ))
    db.flush()
    actor["cliente_id"] = empresa_id
    for nombre in ("Primero", "Segundo"):
        respuesta = cliente.post("/ubicaciones", json={
            "nmbr": nombre, "lttd": -12.0, "lngtd": -77.0,
            "plgn_gjsn": proyectos[0].plgn_gjsn,
        })
        assert respuesta.status_code == 201, respuesta.text
    assert db.query(Sede).filter(Sede.id_clnt == empresa_id).count() == 1
    lista = cliente.get(f"/empresas/{empresa_id}/proyectos").json()
    assert {p["nombre"] for p in lista} == {"Primero", "Segundo"}
