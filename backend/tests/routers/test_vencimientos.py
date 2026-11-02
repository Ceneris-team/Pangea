"""PP-68 - Consultar vencimientos (GET /comercial/vencimientos).

CA1: tabla con los clientes con suscripción activa: razón social, plan,
fecha de vencimiento y días restantes.
CA2: el filtro por rango de días restantes deja solo los clientes dentro
del rango.
Detalles: orden ascendente por vencimiento; rangos vencidos, vencen hoy,
próximos 7 días, próximos 30 días y todos; los vencidos se marcan para
resaltarlos; solo el Administrador Comercial accede.

CA3 (Renovar) es de la pantalla y se prueba en el frontend.
"""

import random
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import PermisoUsuarioSede, Suscripcion
from app.security.dependencies import get_current_user
from app.services.limites_plan import fecha_comercial
from app.services.vencimientos import MSG_RANGO


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


@pytest.fixture()
def plan_id(comercial) -> int:
    nombre = f"Plan Vencimientos {random.randint(0, 10**9)}"
    creado = comercial.post(
        "/comercial/planes", json={"nombre": nombre, "precio_mensual": "300.00"}
    )
    assert creado.status_code == 201, creado.text
    return creado.json()["plan"]["id_pln"]


def _contrato(
    db_session, fabrica, plan_id: int, dias: int, *, estado="Activa", gracia=0, nombre=None
):
    """Cliente con un contrato que vence dentro de `dias` días (negativo = ya venció).

    Se inserta directo: la API no deja crear contratos con vencimiento pasado.
    """
    cliente = fabrica.cliente()
    if nombre:
        cliente.rzn_scl = nombre
    hoy = fecha_comercial()
    vencimiento = hoy + timedelta(days=dias)
    contrato = Suscripcion(
        id_clnt=cliente.id_clnt,
        id_pln=plan_id,
        # Empieza a más tardar hoy: un inicio futuro sería un plan programado, no activo.
        fch_inc=min(hoy, vencimiento - timedelta(days=30)),
        fch_vncmnt=vencimiento,
        estd=estado,
        condiciones={"plan_nombre": "Plan Vencimientos", "dias_gracia": gracia, "moneda": "PEN"},
    )
    db_session.add(contrato)
    db_session.flush()
    return cliente.id_clnt


def _tabla(comercial: TestClient, rango: str | None = None) -> list[dict]:
    url = "/comercial/vencimientos" + (f"?rango={rango}" if rango else "")
    respuesta = comercial.get(url)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _ids(filas: list[dict], propios: set[int]) -> list[int]:
    return [f["id_clnt"] for f in filas if f["id_clnt"] in propios]


@pytest.fixture()
def escenario(db_session, fabrica, plan_id):
    """Un cliente por caso; los días son relativos a hoy (Lima)."""
    return {
        dias: _contrato(db_session, fabrica, plan_id, dias)
        for dias in (-10, -1, 0, 3, 7, 8, 30, 31, 90)
    }


# --- CA1: tabla y orden ------------------------------------------------------


def test_tabla_muestra_razon_social_plan_vencimiento_y_dias(comercial, escenario):
    hoy = fecha_comercial()
    filas = {f["id_clnt"]: f for f in _tabla(comercial)}

    fila = filas[escenario[3]]
    assert fila["razon_social"].startswith("Cliente de prueba")
    assert fila["plan_nombre"] == "Plan Vencimientos"
    assert fila["fecha_vencimiento"] == (hoy + timedelta(days=3)).isoformat()
    assert fila["dias_restantes"] == 3
    assert fila["estado"] == "Vigente"
    assert fila["vencida"] is False


def test_orden_ascendente_por_vencimiento(comercial, escenario):
    propios = set(escenario.values())
    esperado = [escenario[d] for d in sorted(escenario)]
    assert _ids(_tabla(comercial), propios) == esperado
    filas = _tabla(comercial)
    fechas = [f["fecha_vencimiento"] for f in filas]
    assert fechas == sorted(fechas)


def test_a_igual_fecha_ordena_por_razon_social(comercial, db_session, fabrica, plan_id):
    b = _contrato(db_session, fabrica, plan_id, 5, nombre="Minera Beta")
    a = _contrato(db_session, fabrica, plan_id, 5, nombre="minera alfa")
    assert _ids(_tabla(comercial), {a, b}) == [a, b]


def test_vencidas_se_marcan_para_resaltarlas(comercial, escenario):
    """PP-316."""
    filas = {f["id_clnt"]: f for f in _tabla(comercial)}
    assert filas[escenario[-10]]["vencida"] is True
    assert filas[escenario[-10]]["estado"] == "Vencida"
    assert filas[escenario[-10]]["dias_restantes"] == -10
    assert filas[escenario[0]]["vencida"] is False


def test_en_gracia_aparece_como_vencida_con_su_estado(comercial, db_session, fabrica, plan_id):
    id_clnt = _contrato(db_session, fabrica, plan_id, -2, gracia=5)
    fila = next(f for f in _tabla(comercial) if f["id_clnt"] == id_clnt)
    assert fila["estado"] == "En gracia"
    assert fila["vencida"] is True


@pytest.mark.parametrize("estado", ["Reemplazada", "Cancelada", "Suspendida"])
def test_contratos_no_activos_no_aparecen(comercial, db_session, fabrica, plan_id, estado):
    id_clnt = _contrato(db_session, fabrica, plan_id, 10, estado=estado)
    assert id_clnt not in [f["id_clnt"] for f in _tabla(comercial)]


def test_clientes_sin_plan_o_con_plan_futuro_no_aparecen(comercial, db_session, fabrica, plan_id):
    sin_plan = fabrica.cliente().id_clnt
    futuro = fabrica.cliente()
    hoy = fecha_comercial()
    db_session.add(
        Suscripcion(
            id_clnt=futuro.id_clnt,
            id_pln=plan_id,
            fch_inc=hoy + timedelta(days=3),
            fch_vncmnt=hoy + timedelta(days=33),
            estd="Programada",
            condiciones={"plan_nombre": "Plan Vencimientos", "dias_gracia": 0},
        )
    )
    db_session.flush()
    ids = [f["id_clnt"] for f in _tabla(comercial)]
    assert sin_plan not in ids
    assert futuro.id_clnt not in ids


def test_plan_asignado_por_hu45_aparece_a_30_dias(comercial, fabrica, plan_id):
    comercial.put(
        f"/comercial/planes/{plan_id}/limites",
        json={"ubicaciones": 1, "dispositivos": 1, "usuarios": 1},
    )
    cliente = fabrica.cliente()
    asignado = comercial.post(
        f"/comercial/clientes/{cliente.id_clnt}/plan",
        json={"plan_id": plan_id, "fecha_inicio": fecha_comercial().isoformat()},
    )
    assert asignado.status_code == 200, asignado.text
    fila = next(f for f in _tabla(comercial) if f["id_clnt"] == cliente.id_clnt)
    assert fila["dias_restantes"] == 30


# --- CA2 y PP-315: filtro por rango -----------------------------------------


@pytest.mark.parametrize(
    ("rango", "dias_esperados"),
    [
        ("vencidos", [-10, -1]),
        ("hoy", [0]),
        ("7", [0, 3, 7]),
        ("30", [0, 3, 7, 8, 30]),
        ("todos", [-10, -1, 0, 3, 7, 8, 30, 31, 90]),
    ],
)
def test_filtro_por_rango_de_dias(comercial, escenario, rango, dias_esperados):
    propios = set(escenario.values())
    assert _ids(_tabla(comercial, rango), propios) == [escenario[d] for d in dias_esperados]


def test_sin_rango_es_todos(comercial, escenario):
    propios = set(escenario.values())
    assert _ids(_tabla(comercial), propios) == _ids(_tabla(comercial, "todos"), propios)


@pytest.mark.parametrize("rango", ["15", "proximos", "", "-1"])
def test_rango_invalido(comercial, rango):
    respuesta = comercial.get(f"/comercial/vencimientos?rango={rango}")
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == MSG_RANGO


# --- Solo el Administrador Comercial ----------------------------------------


@pytest.mark.parametrize(
    ("rol", "scope"),
    [("Administrador", "global"), ("Técnico CENERIS", "global"), ("Cliente Final", "por_sede")],
)
def test_solo_el_administrador_comercial_accede(otro_rol, rol, scope):
    respuesta = otro_rol(rol, scope).get("/comercial/vencimientos")
    assert respuesta.status_code == 403
