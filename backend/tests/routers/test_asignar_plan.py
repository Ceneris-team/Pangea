"""HU45 - Asignar plan a cliente (POST /comercial/clientes/{id}/plan).

CA2: con plan y fecha de inicio, CONFIRMAR ASIGNACIÓN asocia el plan, calcula
el vencimiento y responde "Plan asignado correctamente".
CA3: el detalle del cliente muestra plan activo, fecha de inicio y vencimiento.
CA4: si ya tenía plan, el nuevo reemplaza al anterior y responde "Plan
actualizado correctamente".
Detalles: solo planes Activos; vencimiento = inicio + 30 días calendario; un
solo plan activo por cliente; solo el Administrador Comercial asigna.

CA1 (formulario) es de la pantalla y se prueba en el frontend.
"""

import random
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import PermisoUsuarioSede, PlanSuscripcion, Suscripcion
from app.routers.comercial import MSG_PLAN_ACTUALIZADO, MSG_PLAN_ASIGNADO
from app.security.dependencies import get_current_user
from app.services.limites_plan import fecha_comercial


def _cliente_http(db_session, fabrica, rol_nombre: str, scope: str = "global") -> TestClient:
    rol = fabrica.rol(rol_nombre)
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol, scp=scope)
    db_session.add(
        PermisoUsuarioSede(
            id_usr=usuario.id_usr, id_sd=sede.id_sd, id_rl=rol.id_rl, mdl="Comercial", nvl="Edición"
        )
    )
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(usuario.id_usr),
        "sede_id": None if scope == "global" else sede.id_sd,
        "scope": scope,
        "rol": rol.nmbr,
    }
    return TestClient(app)


@pytest.fixture()
def comercial(db_session, fabrica):
    try:
        yield _cliente_http(db_session, fabrica, "Administrador Comercial")
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def otro_rol(db_session, fabrica):
    def crear(rol_nombre: str, scope: str = "global") -> TestClient:
        return _cliente_http(db_session, fabrica, rol_nombre, scope)

    try:
        yield crear
    finally:
        app.dependency_overrides.clear()


def _plan(comercial: TestClient, nombre: str, con_limites: bool = True) -> int:
    nombre = f"{nombre} {random.randint(0, 10**9)}"
    creado = comercial.post(
        "/comercial/planes", json={"nombre": nombre, "precio_mensual": "199.00"}
    )
    assert creado.status_code == 201, creado.text
    plan_id = creado.json()["plan"]["id_pln"]
    if con_limites:
        limites = comercial.put(
            f"/comercial/planes/{plan_id}/limites",
            json={"ubicaciones": 3, "dispositivos": 10, "usuarios": 5},
        )
        assert limites.status_code == 200, limites.text
    return plan_id


def _asignar(comercial: TestClient, id_clnt: int, plan_id: int, inicio=None):
    inicio = inicio or fecha_comercial()
    return comercial.post(
        f"/comercial/clientes/{id_clnt}/plan",
        json={"plan_id": plan_id, "fecha_inicio": inicio.isoformat()},
    )


def _activas(db_session, id_clnt: int) -> list[Suscripcion]:
    db_session.expire_all()
    return (
        db_session.query(Suscripcion)
        .filter(Suscripcion.id_clnt == id_clnt, Suscripcion.estd == "Activa")
        .all()
    )


# --- CA2 y PP-310: asignar y calcular el vencimiento -------------------------


def test_asigna_plan_y_vence_a_los_30_dias(comercial, fabrica, db_session):
    cliente = fabrica.cliente()
    plan_id = _plan(comercial, "Plan Básico")
    hoy = fecha_comercial()

    respuesta = _asignar(comercial, cliente.id_clnt, plan_id, hoy)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["mensaje"] == MSG_PLAN_ASIGNADO
    assert cuerpo["estado"] == "Activa"
    assert cuerpo["fecha_inicio"] == hoy.isoformat()
    assert cuerpo["fecha_vencimiento"] == (hoy + timedelta(days=30)).isoformat()
    activas = _activas(db_session, cliente.id_clnt)
    assert [s.id_pln for s in activas] == [plan_id]


@pytest.mark.parametrize("dias", [0, 1, 15])
def test_vencimiento_es_inicio_mas_30_dias_calendario(comercial, fabrica, dias):
    cliente = fabrica.cliente()
    plan_id = _plan(comercial, "Plan Fechas")
    inicio = fecha_comercial() + timedelta(days=dias)

    respuesta = _asignar(comercial, cliente.id_clnt, plan_id, inicio)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["fecha_vencimiento"] == (inicio + timedelta(days=30)).isoformat()


def test_inicio_futuro_queda_programada(comercial, fabrica):
    cliente = fabrica.cliente()
    plan_id = _plan(comercial, "Plan Futuro")
    respuesta = _asignar(comercial, cliente.id_clnt, plan_id, fecha_comercial() + timedelta(days=5))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "Programada"
    assert respuesta.json()["mensaje"] == MSG_PLAN_ASIGNADO


def test_fecha_de_inicio_anterior_a_hoy_se_rechaza(comercial, fabrica, db_session):
    cliente = fabrica.cliente()
    plan_id = _plan(comercial, "Plan Pasado")
    respuesta = _asignar(comercial, cliente.id_clnt, plan_id, fecha_comercial() - timedelta(days=1))

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == "La fecha de inicio no puede ser anterior a hoy"
    assert _activas(db_session, cliente.id_clnt) == []


# --- CA3: detalle del cliente ------------------------------------------------


def test_detalle_muestra_plan_inicio_y_vencimiento(comercial, fabrica):
    cliente = fabrica.cliente()
    plan_id = _plan(comercial, "Plan Detalle")
    hoy = fecha_comercial()
    _asignar(comercial, cliente.id_clnt, plan_id, hoy)

    listado = comercial.get("/comercial/clientes").json()
    detalle = next(c for c in listado if c["id_clnt"] == cliente.id_clnt)
    assert detalle["plan_id"] == plan_id
    assert detalle["plan_nombre"].startswith("Plan Detalle")
    assert detalle["estado_suscripcion"] == "Vigente"
    assert detalle["fecha_inicio"] == hoy.isoformat()
    assert detalle["fecha_vencimiento"] == (hoy + timedelta(days=30)).isoformat()


# --- CA4 y PP-309: un solo plan activo ---------------------------------------


def test_nuevo_plan_reemplaza_al_anterior(comercial, fabrica, db_session):
    cliente = fabrica.cliente()
    primero = _plan(comercial, "Plan Inicial")
    segundo = _plan(comercial, "Plan Superior")
    assert _asignar(comercial, cliente.id_clnt, primero).json()["mensaje"] == MSG_PLAN_ASIGNADO

    respuesta = _asignar(comercial, cliente.id_clnt, segundo)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["mensaje"] == MSG_PLAN_ACTUALIZADO
    activas = _activas(db_session, cliente.id_clnt)
    assert [s.id_pln for s in activas] == [segundo]
    estados = {
        s.id_pln: s.estd
        for s in db_session.query(Suscripcion).filter(Suscripcion.id_clnt == cliente.id_clnt)
    }
    assert estados == {primero: "Reemplazada", segundo: "Activa"}


def test_tres_asignaciones_dejan_un_solo_plan_activo(comercial, fabrica, db_session):
    cliente = fabrica.cliente()
    planes = [_plan(comercial, f"Plan {n}") for n in range(3)]
    for plan_id in planes:
        assert _asignar(comercial, cliente.id_clnt, plan_id).status_code == 200

    assert [s.id_pln for s in _activas(db_session, cliente.id_clnt)] == [planes[-1]]


def test_repetir_la_misma_asignacion_no_duplica(comercial, fabrica, db_session):
    cliente = fabrica.cliente()
    plan_id = _plan(comercial, "Plan Repetido")
    _asignar(comercial, cliente.id_clnt, plan_id)

    otra_vez = _asignar(comercial, cliente.id_clnt, plan_id)

    assert otra_vez.status_code == 200
    assert len(_activas(db_session, cliente.id_clnt)) == 1


# --- Planes que no se pueden asignar ----------------------------------------


def test_plan_inactivo_no_se_puede_asignar(comercial, fabrica, db_session):
    cliente = fabrica.cliente()
    plan_id = _plan(comercial, "Plan Retirado")
    db_session.get(PlanSuscripcion, plan_id).estd = "Inactivo"
    db_session.flush()

    respuesta = _asignar(comercial, cliente.id_clnt, plan_id)

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == "El plan no existe o no está activo"


def test_plan_sin_limites_no_se_puede_asignar(comercial, fabrica):
    cliente = fabrica.cliente()
    plan_id = _plan(comercial, "Plan Incompleto", con_limites=False)
    respuesta = _asignar(comercial, cliente.id_clnt, plan_id)
    assert respuesta.status_code == 409


def test_cliente_inexistente(comercial):
    plan_id = _plan(comercial, "Plan Huérfano")
    assert _asignar(comercial, 999_999_999, plan_id).status_code == 404


# --- Solo el Administrador Comercial ----------------------------------------


@pytest.mark.parametrize(
    ("rol", "scope"),
    [("Administrador", "global"), ("Técnico CENERIS", "global"), ("Cliente Final", "por_sede")],
)
def test_solo_el_administrador_comercial_asigna(
    comercial, otro_rol, fabrica, db_session, rol, scope
):
    cliente = fabrica.cliente()
    plan_id = _plan(comercial, "Plan Roles")

    respuesta = _asignar(otro_rol(rol, scope), cliente.id_clnt, plan_id)

    assert respuesta.status_code == 403
    assert _activas(db_session, cliente.id_clnt) == []
