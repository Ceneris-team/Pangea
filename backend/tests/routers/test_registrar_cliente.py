"""HU65 - Registrar cliente desde Gestión de Planes y Suscripciones.

CA2: con los campos obligatorios válidos, GUARDAR registra al cliente, lo
agrega al listado y responde "Cliente registrado correctamente".
Detalles: Razón social, RUC y Correo obligatorios; Teléfono opcional; RUC
de exactamente 11 dígitos y único; correo usuario@dominio.com; solo el
Administrador Comercial registra en este módulo.

CA1 (formulario), CA3 (ASIGNAR PLAN) y CA4 (CANCELAR) son de la pantalla y
se prueban en el frontend.
"""

import random

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Cliente, LogAuditoria, PermisoUsuarioSede
from app.security.dependencies import get_current_user
from app.services.clientes import (
    MSG_CORREO,
    MSG_RAZON_SOCIAL,
    MSG_RUC,
    MSG_RUC_DUPLICADO,
    MSG_TELEFONO,
)


def _ruc() -> str:
    # Prefijo 20 (persona jurídica) y 9 dígitos al azar, para no chocar con
    # los RUC correlativos de la fábrica de conftest.py.
    return "20" + "".join(random.choices("0123456789", k=9))


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
    clientes = []

    def crear(rol_nombre: str, scope: str = "global") -> TestClient:
        cliente = _cliente_http(db_session, fabrica, rol_nombre, scope)
        clientes.append(cliente)
        return cliente

    try:
        yield crear
    finally:
        app.dependency_overrides.clear()


def _datos(**cambios) -> dict:
    datos = {
        "razon_social": "Minera Andina S.A.C.",
        "ruc": _ruc(),
        "correo_contacto": "contacto@mineraandina.pe",
        "telefono_contacto": "+51 999 888 777",
    }
    datos.update(cambios)
    return datos


# --- CA2: registro correcto -------------------------------------------------


def test_registra_cliente_con_los_cuatro_campos(comercial, db_session):
    datos = _datos(correo_contacto="Contacto@MineraAndina.PE")
    respuesta = comercial.post("/comercial/clientes", json=datos)

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["mensaje"] == "Cliente registrado correctamente"
    assert cuerpo["cliente"]["ruc"] == datos["ruc"]
    assert cuerpo["cliente"]["plan_id"] is None

    cliente = db_session.get(Cliente, cuerpo["cliente"]["id_clnt"])
    assert cliente.rzn_scl == "Minera Andina S.A.C."
    assert cliente.crr_cntct == "contacto@mineraandina.pe"
    assert cliente.tlfn_cntct == "+51 999 888 777"
    assert cliente.estd == "Activo"


def test_telefono_es_opcional(comercial, db_session):
    sin_campo = _datos()
    del sin_campo["telefono_contacto"]
    for datos in (sin_campo, _datos(telefono_contacto=""), _datos(telefono_contacto=None)):
        respuesta = comercial.post("/comercial/clientes", json=datos)
        assert respuesta.status_code == 201, respuesta.text
        cliente = db_session.get(Cliente, respuesta.json()["cliente"]["id_clnt"])
        assert cliente.tlfn_cntct is None


def test_cliente_registrado_aparece_en_el_listado(comercial):
    datos = _datos(razon_social="Minera Listado S.A.")
    creado = comercial.post("/comercial/clientes", json=datos)
    assert creado.status_code == 201, creado.text

    listado = comercial.get("/comercial/clientes")
    assert listado.status_code == 200
    assert datos["ruc"] in [cliente["ruc"] for cliente in listado.json()]


def test_registro_queda_en_la_auditoria(comercial, db_session):
    creado = comercial.post("/comercial/clientes", json=_datos())
    id_clnt = creado.json()["cliente"]["id_clnt"]

    registro = (
        db_session.query(LogAuditoria)
        .filter(LogAuditoria.entdd == "Cliente", LogAuditoria.accn == "crear")
        .order_by(LogAuditoria.id_evnt.desc())
        .first()
    )
    assert registro is not None
    assert registro.vlrs_nvs["cliente_id"] == id_clnt


def test_cliente_registrado_puede_recibir_plan(comercial):
    """CA3: el cliente nuevo queda listo para el flujo de HU45."""
    creado = comercial.post("/comercial/clientes", json=_datos())
    id_clnt = creado.json()["cliente"]["id_clnt"]

    historial = comercial.get(f"/comercial/clientes/{id_clnt}/historial")
    assert historial.status_code == 200, historial.text


# --- Obligatorios y formato -------------------------------------------------


@pytest.mark.parametrize("razon_social", ["", "   "])
def test_razon_social_obligatoria(comercial, razon_social):
    respuesta = comercial.post("/comercial/clientes", json=_datos(razon_social=razon_social))
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == MSG_RAZON_SOCIAL


@pytest.mark.parametrize(
    "ruc",
    ["", "2012345678", "201234567890", "20A23456789", "20 12345678", "-2012345678"],
    ids=["vacio", "10-digitos", "12-digitos", "con-letra", "con-espacio", "con-signo"],
)
def test_ruc_debe_tener_11_digitos_numericos(comercial, db_session, ruc):
    antes = db_session.query(Cliente).count()
    respuesta = comercial.post("/comercial/clientes", json=_datos(ruc=ruc))

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == MSG_RUC
    assert db_session.query(Cliente).count() == antes


def test_ruc_con_espacios_alrededor_se_acepta_sin_ellos(comercial):
    ruc = _ruc()
    respuesta = comercial.post("/comercial/clientes", json=_datos(ruc=f"  {ruc} "))
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["cliente"]["ruc"] == ruc


def test_ruc_repetido_no_se_registra(comercial, db_session):
    ruc = _ruc()
    primero = comercial.post("/comercial/clientes", json=_datos(ruc=ruc))
    assert primero.status_code == 201, primero.text

    segundo = comercial.post(
        "/comercial/clientes", json=_datos(ruc=ruc, razon_social="Otra razón social")
    )
    assert segundo.status_code == 409
    assert segundo.json()["detail"] == MSG_RUC_DUPLICADO
    assert db_session.query(Cliente).filter(Cliente.rc == ruc).count() == 1


@pytest.mark.parametrize(
    "correo",
    [
        "",
        "contacto",
        "contacto@",
        "@minera.pe",
        "contacto@minera",
        "con espacio@minera.pe",
        "a@@minera.pe",
        "contacto@minera..pe",
    ],
)
def test_correo_debe_tener_formato_usuario_dominio(comercial, correo):
    respuesta = comercial.post("/comercial/clientes", json=_datos(correo_contacto=correo))
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == MSG_CORREO


@pytest.mark.parametrize("telefono", ["abc", "999-ABC", "+-  ", "1" * 21])
def test_telefono_invalido(comercial, telefono):
    respuesta = comercial.post("/comercial/clientes", json=_datos(telefono_contacto=telefono))
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == MSG_TELEFONO


# --- Solo el Administrador Comercial ---------------------------------------


@pytest.mark.parametrize(
    ("rol", "scope"),
    [("Administrador", "global"), ("Técnico CENERIS", "global"), ("Cliente Final", "por_sede")],
)
def test_solo_el_administrador_comercial_registra(otro_rol, db_session, rol, scope):
    datos = _datos()
    respuesta = otro_rol(rol, scope).post("/comercial/clientes", json=datos)

    assert respuesta.status_code == 403
    assert db_session.query(Cliente).filter(Cliente.rc == datos["ruc"]).count() == 0
