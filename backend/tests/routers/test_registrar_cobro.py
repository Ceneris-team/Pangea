"""PP-67 - Registrar cobro (POST/GET /comercial/clientes/{id}/cobros).

CA2: con los obligatorios completos, GUARDAR registra el cobro asociado al
cliente y al período y responde "Cobro registrado correctamente".
CA3: el historial de cobros del cliente muestra monto, fecha y método.
Detalles: obligatorios Monto, Fecha y Método; monto decimal; métodos
Transferencia bancaria, Efectivo y Cheque; fecha no futura; solo el
Administrador Comercial registra.

CA1 (formulario) y CA4 (CANCELAR) son de la pantalla y se prueban en el frontend.
"""

import random
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Cobro, LogAuditoria, PermisoUsuarioSede, Suscripcion
from app.security.dependencies import get_current_user
from app.services.cobros import (
    MSG_COBRO_REGISTRADO,
    MSG_FECHA,
    MSG_FECHA_FUTURA,
    MSG_METODO,
    MSG_MONTO,
    MSG_MONTO_MAXIMO,
    MSG_SIN_PLAN,
)
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


def _plan(comercial: TestClient, nombre: str = "Plan Cobros") -> int:
    nombre = f"{nombre} {random.randint(0, 10**9)}"
    creado = comercial.post(
        "/comercial/planes", json={"nombre": nombre, "precio_mensual": "350.00"}
    )
    assert creado.status_code == 201, creado.text
    plan_id = creado.json()["plan"]["id_pln"]
    limites = comercial.put(
        f"/comercial/planes/{plan_id}/limites",
        json={"ubicaciones": 3, "dispositivos": 10, "usuarios": 5},
    )
    assert limites.status_code == 200, limites.text
    return plan_id


@pytest.fixture()
def cliente_con_plan(comercial, fabrica):
    cliente = fabrica.cliente()
    asignado = comercial.post(
        f"/comercial/clientes/{cliente.id_clnt}/plan",
        json={"plan_id": _plan(comercial), "fecha_inicio": fecha_comercial().isoformat()},
    )
    assert asignado.status_code == 200, asignado.text
    return cliente.id_clnt, asignado.json()["suscripcion_id"]


def _datos(**cambios) -> dict:
    datos = {
        "monto": "350.00",
        "fecha_cobro": fecha_comercial().isoformat(),
        "metodo_pago": "Transferencia bancaria",
    }
    datos.update(cambios)
    return datos


def _cobrar(comercial: TestClient, id_clnt: int, **cambios):
    return comercial.post(f"/comercial/clientes/{id_clnt}/cobros", json=_datos(**cambios))


def _cobros(db_session, id_clnt: int) -> list[Cobro]:
    return (
        db_session.query(Cobro)
        .join(Suscripcion, Suscripcion.id_sscrpcn == Cobro.id_sscrpcn)
        .filter(Suscripcion.id_clnt == id_clnt)
        .all()
    )


# --- CA2 y PP-313: registrar asociado al cliente y al período ----------------


def test_registra_cobro_en_el_periodo_actual(comercial, cliente_con_plan, db_session):
    id_clnt, suscripcion_id = cliente_con_plan

    respuesta = _cobrar(comercial, id_clnt)

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["mensaje"] == MSG_COBRO_REGISTRADO
    assert cuerpo["cobro"]["monto"] == "350.00"
    assert cuerpo["cobro"]["metodo_pago"] == "Transferencia bancaria"
    assert cuerpo["cobro"]["suscripcion_id"] == suscripcion_id
    hoy = fecha_comercial()
    assert cuerpo["cobro"]["periodo_inicio"] == hoy.isoformat()
    assert cuerpo["cobro"]["periodo_fin"] == (hoy + timedelta(days=30)).isoformat()

    [cobro] = _cobros(db_session, id_clnt)
    assert cobro.id_sscrpcn == suscripcion_id
    assert str(cobro.mnt) == "350.00"
    assert cobro.fch_cbr == hoy


@pytest.mark.parametrize(
    ("metodo", "guardado"),
    [
        ("Transferencia bancaria", "Transferencia bancaria"),
        ("Efectivo", "Efectivo"),
        ("Cheque", "Cheque"),
        (" efectivo ", "Efectivo"),
        ("TRANSFERENCIA BANCARIA", "Transferencia bancaria"),
    ],
)
def test_acepta_los_tres_metodos_de_pago(comercial, cliente_con_plan, metodo, guardado):
    id_clnt, _ = cliente_con_plan
    respuesta = _cobrar(comercial, id_clnt, metodo_pago=metodo)
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["cobro"]["metodo_pago"] == guardado


@pytest.mark.parametrize(
    ("monto", "guardado"),
    [("100", "100.00"), ("99.9", "99.90"), (120.5, "120.50"), ("0.01", "0.01")],
)
def test_monto_decimal(comercial, cliente_con_plan, monto, guardado):
    id_clnt, _ = cliente_con_plan
    respuesta = _cobrar(comercial, id_clnt, monto=monto)
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["cobro"]["monto"] == guardado


def test_fecha_pasada_se_acepta(comercial, cliente_con_plan):
    id_clnt, _ = cliente_con_plan
    ayer = (fecha_comercial() - timedelta(days=1)).isoformat()
    respuesta = _cobrar(comercial, id_clnt, fecha_cobro=ayer)
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["cobro"]["fecha_cobro"] == ayer


def test_registro_queda_en_la_auditoria(comercial, cliente_con_plan, db_session):
    id_clnt, _ = cliente_con_plan
    cobro_id = _cobrar(comercial, id_clnt).json()["cobro"]["id"]
    registro = (
        db_session.query(LogAuditoria)
        .filter(LogAuditoria.entdd == "Cobro", LogAuditoria.accn == "registrar")
        .order_by(LogAuditoria.id_evnt.desc())
        .first()
    )
    assert registro is not None
    assert registro.vlrs_nvs["cobro_id"] == cobro_id
    assert registro.vlrs_nvs["monto"] == "350.00"


# --- CA3: historial ----------------------------------------------------------


def test_historial_muestra_monto_fecha_y_metodo(comercial, cliente_con_plan):
    id_clnt, _ = cliente_con_plan
    hoy = fecha_comercial()
    _cobrar(
        comercial,
        id_clnt,
        monto="100.00",
        fecha_cobro=(hoy - timedelta(days=2)).isoformat(),
        metodo_pago="Cheque",
    )
    _cobrar(comercial, id_clnt, monto="250.50", metodo_pago="Efectivo")

    historial = comercial.get(f"/comercial/clientes/{id_clnt}/cobros")

    assert historial.status_code == 200, historial.text
    filas = historial.json()
    assert [(f["monto"], f["fecha_cobro"], f["metodo_pago"]) for f in filas] == [
        ("250.50", hoy.isoformat(), "Efectivo"),
        ("100.00", (hoy - timedelta(days=2)).isoformat(), "Cheque"),
    ]
    assert all(f["plan_nombre"].startswith("Plan Cobros") for f in filas)


def test_historial_solo_trae_cobros_del_cliente(comercial, cliente_con_plan, fabrica):
    id_clnt, _ = cliente_con_plan
    _cobrar(comercial, id_clnt)
    otro = fabrica.cliente()
    comercial.post(
        f"/comercial/clientes/{otro.id_clnt}/plan",
        json={
            "plan_id": _plan(comercial, "Plan Otro"),
            "fecha_inicio": fecha_comercial().isoformat(),
        },
    )
    _cobrar(comercial, otro.id_clnt, monto="1.00")

    assert len(comercial.get(f"/comercial/clientes/{id_clnt}/cobros").json()) == 1
    assert comercial.get(f"/comercial/clientes/{otro.id_clnt}/cobros").json()[0]["monto"] == "1.00"


def test_cobro_previo_queda_en_su_periodo_al_cambiar_de_plan(comercial, cliente_con_plan):
    id_clnt, primer_periodo = cliente_con_plan
    _cobrar(comercial, id_clnt)
    cambio = comercial.post(
        f"/comercial/clientes/{id_clnt}/plan",
        json={
            "plan_id": _plan(comercial, "Plan Nuevo"),
            "fecha_inicio": fecha_comercial().isoformat(),
        },
    )
    segundo_periodo = cambio.json()["suscripcion_id"]
    _cobrar(comercial, id_clnt, monto="500.00")

    filas = comercial.get(f"/comercial/clientes/{id_clnt}/cobros").json()
    assert {f["suscripcion_id"] for f in filas} == {primer_periodo, segundo_periodo}


# --- Obligatorios y formato -------------------------------------------------


@pytest.mark.parametrize("monto", [None, "", "abc", "0", "-10", "10.555", "NaN", "Infinity", True])
def test_monto_invalido(comercial, cliente_con_plan, db_session, monto):
    id_clnt, _ = cliente_con_plan
    respuesta = _cobrar(comercial, id_clnt, monto=monto)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == MSG_MONTO
    assert _cobros(db_session, id_clnt) == []


def test_monto_demasiado_grande(comercial, cliente_con_plan):
    id_clnt, _ = cliente_con_plan
    respuesta = _cobrar(comercial, id_clnt, monto="10000000000.00")
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == MSG_MONTO_MAXIMO


def test_fecha_futura_se_rechaza(comercial, cliente_con_plan, db_session):
    """PP-312: la fecha de cobro no puede ser futura."""
    id_clnt, _ = cliente_con_plan
    manana = (fecha_comercial() + timedelta(days=1)).isoformat()
    respuesta = _cobrar(comercial, id_clnt, fecha_cobro=manana)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == MSG_FECHA_FUTURA
    assert _cobros(db_session, id_clnt) == []


@pytest.mark.parametrize("fecha", [None, "", "02/11/2026", "2026-13-01", "mañana"])
def test_fecha_obligatoria_y_con_formato(comercial, cliente_con_plan, fecha):
    id_clnt, _ = cliente_con_plan
    respuesta = _cobrar(comercial, id_clnt, fecha_cobro=fecha)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == MSG_FECHA


@pytest.mark.parametrize("metodo", [None, "", "Tarjeta", "Yape", "Transferencia"])
def test_metodo_de_pago_fuera_de_la_lista(comercial, cliente_con_plan, metodo):
    id_clnt, _ = cliente_con_plan
    respuesta = _cobrar(comercial, id_clnt, metodo_pago=metodo)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == MSG_METODO


def test_cliente_sin_plan_no_puede_registrar_cobro(comercial, fabrica):
    cliente = fabrica.cliente()
    respuesta = _cobrar(comercial, cliente.id_clnt)
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == MSG_SIN_PLAN


def test_cliente_inexistente(comercial):
    assert _cobrar(comercial, 999_999_999).status_code == 404
    assert comercial.get("/comercial/clientes/999999999/cobros").status_code == 404


# --- Solo el Administrador Comercial ----------------------------------------


@pytest.mark.parametrize(
    ("rol", "scope"),
    [("Administrador", "global"), ("Técnico CENERIS", "global"), ("Cliente Final", "por_sede")],
)
def test_solo_el_administrador_comercial_registra(
    otro_rol, cliente_con_plan, db_session, rol, scope
):
    id_clnt, _ = cliente_con_plan
    respuesta = _cobrar(otro_rol(rol, scope), id_clnt)
    assert respuesta.status_code == 403
    assert _cobros(db_session, id_clnt) == []


def test_administrador_ceneris_puede_ver_el_historial(otro_rol, comercial, cliente_con_plan):
    id_clnt, _ = cliente_con_plan
    _cobrar(comercial, id_clnt)
    historial = otro_rol("Administrador").get(f"/comercial/clientes/{id_clnt}/cobros")
    assert historial.status_code == 200
    assert len(historial.json()) == 1


def test_cliente_final_no_ve_el_historial(otro_rol, cliente_con_plan):
    id_clnt, _ = cliente_con_plan
    assert (
        otro_rol("Cliente Final", "por_sede")
        .get(f"/comercial/clientes/{id_clnt}/cobros")
        .status_code
        == 403
    )
