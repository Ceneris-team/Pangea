"""Flujo de ampliaciones con sesiones, aislamiento y contratos reales en Postgres."""

from datetime import timedelta
from uuid import uuid4

import pytest

from app.models import (
    LogAuditoria,
    PlanSuscripcion,
    SolicitudSuscripcion,
    Suscripcion,
    UsuarioCliente,
)
from app.routers import solicitudes_suscripcion as solicitudes
from app.services.limites_plan import fecha_comercial, resumen_cliente
from tests.routers.test_contratos import datos
from tests.routers.test_entorno_operativo import autenticar
from tests.routers.test_entorno_operativo import entorno as entorno

BASE = "/solicitudes-suscripcion"


@pytest.fixture()
def flujo(entorno):
    client, db, empresas, recursos, cuentas, parametro = entorno
    autenticar(client, cuentas["Administrador CENERIS"])
    inicial = db.query(Suscripcion).filter(Suscripcion.id_clnt == empresas[0].id_clnt).one()
    return client, db, empresas, cuentas, inicial.id_pln, inicial.id_sscrpcn


def crear(flujo, **cambios):
    client, db, empresas, cuentas, id_plan, actual = flujo
    autenticar(client, cuentas["Administrador"])
    body = {"tipo": "Ampliar cupos", "incrementos": {"ubicaciones": 1, "dispositivos": 0, "usuarios": 5},
            "descripcion": "Necesitamos ampliar el equipo de monitoreo", "clave_idempotencia": str(uuid4()), **cambios}
    respuesta = client.post(BASE, json=body)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json(), body


def proponer(flujo, fila, **cambios):
    client, db, empresas, cuentas, id_plan, actual = flujo
    autenticar(client, cuentas["Administrador CENERIS"])
    contrato = datos(id_plan, operacion="Cambiar", suscripcion_actual_id=actual,
        revision_plan=db.get(PlanSuscripcion, id_plan).revision, precio_acordado="150.00",
        limites_acordados={"ubicaciones": 4, "dispositivos": 10, "usuarios": 15})
    body = {"revision": fila["revision"], "contrato": contrato, "mensaje": "Incluye cinco usuarios adicionales para la empresa",
            "valida_hasta": str(fecha_comercial() + timedelta(days=7)), "inicio_al_activar": True, **cambios}
    respuesta = client.post(f"{BASE}/{fila['id']}/propuesta", json=body)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def actuar(flujo, fila, accion, rol="Administrador", status=200):
    client, db, empresas, cuentas, id_plan, actual = flujo
    autenticar(client, cuentas[rol])
    respuesta = client.post(f"{BASE}/{fila['id']}/accion", json={"accion": accion, "revision": fila["revision"], "motivo": "Condiciones revisadas"})
    assert respuesta.status_code == status, respuesta.text
    return respuesta.json()


def test_flujo_completo_con_aceptacion_auditoria_y_notificaciones(flujo):
    client, db, empresas, cuentas, id_plan, actual = flujo
    fila, _ = crear(flujo)
    assert client.get(BASE + "/resumen").json()["total"] == 0
    autenticar(client, cuentas["Administrador CENERIS"])
    assert client.get(BASE + "/resumen").json()["total"] == 1
    fila = actuar(flujo, fila, "Evaluar", "Administrador CENERIS")
    actuar(flujo, fila, "Aplicar", "Administrador CENERIS", status=409)
    fila = proponer(flujo, fila)
    autenticar(client, cuentas["Administrador"])
    assert client.get(BASE + "/resumen").json()["total"] == 1
    assert resumen_cliente(db, empresas[0])["limites"]["usuarios"] == 10
    fila = actuar(flujo, fila, "Aceptar")
    assert fila["aceptante"] == cuentas["Administrador"][0].nmbr_cmplt
    assert resumen_cliente(db, empresas[0])["limites"]["usuarios"] == 10
    aplicada = actuar(flujo, fila, "Aplicar", "Administrador CENERIS")
    assert aplicada["estado"] == "Aplicada"
    assert aplicada["resultado"]["estado"] == "Vigente"
    assert resumen_cliente(db, empresas[0])["limites"]["usuarios"] == 15
    assert db.get(Suscripcion, actual).estd == "Reemplazada"
    assert actuar(flujo, fila, "Aplicar", "Administrador CENERIS")["resultado"]["id"] == aplicada["resultado"]["id"]
    eventos = client.get(f"{BASE}/{fila['id']}").json()["eventos"]
    assert {e["accion"] for e in eventos} == {"solicitar", "evaluar", "proponer", "aceptar", "aplicar"}
    assert db.query(Suscripcion).filter(Suscripcion.id_clnt == empresas[0].id_clnt).count() == 2


@pytest.mark.parametrize("rol", ["Tecnico", "Lector", "Técnico CENERIS"])
def test_roles_sin_acceso_comercial(flujo, rol):
    fila, body = crear(flujo)
    client, db, empresas, cuentas, id_plan, actual = flujo
    autenticar(client, cuentas[rol])
    for url in (BASE, BASE + "/opciones", BASE + "/resumen", f"{BASE}/{fila['id']}"):
        assert client.get(url).status_code == 403
    assert client.post(BASE, json=body).status_code == 403
    actuar(flujo, fila, "Aceptar", rol, status=403)


def test_admin_no_puede_ver_ni_aceptar_solicitud_ajena(flujo, fabrica):
    fila, _ = crear(flujo)
    client, db, empresas, cuentas, id_plan, actual = flujo
    otro = fabrica.usuario(fabrica.rol("Usuario Empresa"), scp="por_cliente")
    db.add(UsuarioCliente(id_usr=otro.id_usr, id_clnt=empresas[1].id_clnt, rol_emp="Administrador"))
    db.flush()
    autenticar(client, (otro, None))
    assert client.get(BASE).json() == []
    assert client.get(f"{BASE}/{fila['id']}").status_code == 404
    assert client.post(f"{BASE}/{fila['id']}/accion", json={"accion": "Aceptar", "revision": 0, "motivo": "Intento ajeno"}).status_code == 404
    client.headers["X-Cliente-Id"] = str(empresas[0].id_clnt)
    assert client.get(BASE).status_code == 403


def test_creacion_idempotente_duplicado_y_campos_no_permitidos(flujo):
    fila, body = crear(flujo)
    client = flujo[0]
    assert client.post(BASE, json=body).json()["id"] == fila["id"]
    assert client.post(BASE, json={**body, "descripcion": "Otra necesidad completamente diferente"}).status_code == 409
    assert client.post(BASE, json={**body, "clave_idempotencia": str(uuid4())}).status_code == 409
    assert client.post(BASE, json={**body, "cliente_id": flujo[2][1].id_clnt}).status_code == 422
    assert client.post(BASE, json={**body, "precio_acordado": 0}).status_code == 422


def test_version_y_reapertura_invalidan_aceptacion(flujo):
    original, _ = crear(flujo)
    fila = proponer(flujo, original)
    actuar(flujo, original, "Aceptar", status=409)
    aceptada = actuar(flujo, fila, "Aceptar")
    actuar(flujo, aceptada, "Aplicar", "Administrador", status=403)
    reabierta = actuar(flujo, aceptada, "Reabrir", "Administrador CENERIS")
    assert reabierta["aceptante"] is None
    actuar(flujo, reabierta, "Aplicar", "Administrador CENERIS", status=409)
    nueva = proponer(flujo, reabierta)
    actuar(flujo, fila, "Aceptar", status=409)
    assert actuar(flujo, nueva, "Aceptar")["estado"] == "Aceptada"


@pytest.mark.parametrize("fija", [False, True])
def test_propuesta_vencida_no_puede_aceptarse(flujo, monkeypatch, fija):
    fila, _ = crear(flujo)
    fila = proponer(flujo, fila, inicio_al_activar=not fija)
    futuro = fecha_comercial() + timedelta(days=1 if fija else 8)
    monkeypatch.setattr(solicitudes, "fecha_comercial", lambda: futuro)
    actuar(flujo, fila, "Aceptar", status=409)
    assert actuar(flujo, fila, "Pedir revisión")["estado"] == "En evaluación"


def test_contrato_conserva_precio_cupos_aceptados_y_desplaza_vigencia(flujo, monkeypatch):
    from app.services import limites_plan

    fila, _ = crear(flujo)
    fila = actuar(flujo, proponer(flujo, fila), "Aceptar")
    client, db, empresas, cuentas, id_plan, actual = flujo
    autenticar(client, cuentas["Administrador CENERIS"])
    assert client.put(f"/comercial/planes/{id_plan}/limites", json={"ubicaciones": 1, "dispositivos": 1, "usuarios": 1}).status_code == 200
    futuro = fecha_comercial() + timedelta(days=2)
    monkeypatch.setattr(solicitudes, "fecha_comercial", lambda: futuro)
    monkeypatch.setattr(limites_plan, "fecha_comercial", lambda: futuro)
    aplicada = actuar(flujo, fila, "Aplicar", "Administrador CENERIS")
    assert aplicada["resultado"]["fecha_inicio"] == str(futuro)
    condiciones = aplicada["resultado"]["condiciones"]
    assert condiciones["precio_acordado"] == "150.00"
    assert condiciones["limites"]["usuarios"] == 15
    assert condiciones["revision_plan"] == fila["propuesta"]["condiciones"]["revision_plan"]


def test_cambio_de_contrato_o_suspension_requiere_nueva_propuesta(flujo):
    fila, _ = crear(flujo)
    fila = actuar(flujo, proponer(flujo, fila), "Aceptar")
    client, db, empresas, cuentas, id_plan, actual = flujo
    autenticar(client, cuentas["Administrador CENERIS"])
    assert client.post(f"/comercial/clientes/{empresas[0].id_clnt}/suscripciones/{actual}/estado", json={"accion": "Suspender", "motivo": "Cambio administrativo"}).status_code == 200
    actuar(flujo, fila, "Aplicar", "Administrador CENERIS", status=409)


def test_renovacion_programada_no_cambia_derechos_antes_de_inicio(flujo):
    fila, _ = crear(flujo, tipo="Renovar")
    client, db, empresas, cuentas, id_plan, actual = flujo
    inicio = db.get(Suscripcion, actual).fch_vncmnt + timedelta(days=1)
    contrato = datos(id_plan, operacion="Renovar", fecha_inicio=str(inicio), fecha_vencimiento=str(inicio + timedelta(days=364)),
                     revision_plan=db.get(PlanSuscripcion, id_plan).revision, suscripcion_actual_id=actual,
                     limites_acordados={"ubicaciones": 4, "dispositivos": 10, "usuarios": 15})
    fila = actuar(flujo, proponer(flujo, fila, contrato=contrato), "Aceptar")
    aplicada = actuar(flujo, fila, "Aplicar", "Administrador CENERIS")
    assert aplicada["resultado"]["estado"] == "Programada"
    assert aplicada["resultado"]["fecha_inicio"] == str(inicio)
    assert resumen_cliente(db, empresas[0])["limites"]["usuarios"] == 10


def test_aplicacion_y_solicitud_se_revierten_juntas_si_falla_auditoria(flujo, monkeypatch):
    fila, _ = crear(flujo)
    fila = actuar(flujo, proponer(flujo, fila), "Aceptar")
    client, db, empresas, cuentas, id_plan, actual = flujo
    eventos = db.query(LogAuditoria).count()
    def fallar(*args, **kwargs):
        raise RuntimeError("Fallo de escritura simulado")
    monkeypatch.setattr(solicitudes, "registrar_evento", fallar)
    with pytest.raises(RuntimeError):
        actuar(flujo, fila, "Aplicar", "Administrador CENERIS")
    db.rollback()
    assert db.get(SolicitudSuscripcion, fila["id"]).estado == "Aceptada"
    assert db.get(Suscripcion, actual).estd == "Activa"
    assert db.query(Suscripcion).filter(Suscripcion.id_clnt == empresas[0].id_clnt).count() == 1
    assert db.query(LogAuditoria).count() == eventos
