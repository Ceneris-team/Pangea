"""Contratos conservados, programación, vigencia y derechos comerciales."""

from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.main import app
from app.models import LogAuditoria, PlanSuscripcion, Suscripcion, Ubicacion
from app.security.dependencies import get_current_user
from app.services.contratos import aplicar_programadas, exigir_funcionalidad, exigir_operacion
from app.services.limites_plan import comprobar_cupo, fecha_comercial, resumen_cliente
from tests.routers.test_comercial import comercial as comercial
from tests.routers.test_entorno_operativo import autenticar
from tests.routers.test_entorno_operativo import entorno as entorno


def plan(client, cliente, usuarios=5):
    creado = client.post("/comercial/planes", json={"nombre": f"Contrato {cliente.id_clnt}", "precio_mensual": "100.00"})
    assert creado.status_code == 201, creado.text
    id_plan = creado.json()["plan"]["id_pln"]
    assert client.put(f"/comercial/planes/{id_plan}/limites", json={"ubicaciones": 3, "dispositivos": 10, "usuarios": usuarios}).status_code == 200
    return id_plan


def datos(id_plan, **cambios):
    return {"plan_id": id_plan, "fecha_inicio": str(fecha_comercial()),
            "fecha_vencimiento": str(fecha_comercial() + timedelta(days=30)),
            "motivo": "Contrato de prueba", **cambios}


def asignar(client, cliente, body):
    return client.put(f"/comercial/clientes/{cliente.id_clnt}/suscripcion", json=body)


def test_contrato_conserva_cupos_y_funciones_tras_editar_catalogo(comercial, fabrica):
    empresa = fabrica.cliente()
    id_plan = plan(comercial, empresa)
    creado = asignar(comercial, empresa, datos(id_plan, precio_acordado="85.50", referencia="OC-2026"))
    assert creado.status_code == 200, creado.text
    contratado = creado.json()["cliente"]["condiciones"]
    assert contratado["precio_acordado"] == "85.50"
    assert comercial.put(f"/comercial/planes/{id_plan}/limites", json={"ubicaciones": 1, "dispositivos": 1, "usuarios": 1}).status_code == 200
    assert comercial.put(f"/comercial/planes/{id_plan}/funcionalidades", json={"funcionalidades": []}).status_code == 200
    resumen = resumen_cliente(fabrica.db, empresa)
    assert resumen["condiciones"] == contratado
    assert resumen["limites"]["usuarios"] == 5
    assert resumen["condiciones"]["funcionalidades"] == ["tableros"]
    assert fabrica.db.get(PlanSuscripcion, id_plan).revision > contratado["revision_plan"]


def test_complementos_periodicos_y_servicios_separan_importes(comercial, fabrica):
    empresa = fabrica.cliente()
    id_plan = plan(comercial, empresa)
    for nombre, tipo, precio, cupos in [("Usuarios extra", "Recurrente", "10", 2), ("Instalación", "Servicio", "250", 0)]:
        res = comercial.post("/comercial/complementos", json={"nombre": nombre, "tipo": tipo, "precio": precio,
                "cupos": {"ubicaciones": 0, "dispositivos": 0, "usuarios": cupos}})
        assert res.status_code == 201, res.text
    extras = comercial.get("/comercial/catalogo").json()["complementos"]
    ids = {e["nombre"]: e["id"] for e in extras}
    body = datos(id_plan, periodicidad="Anual", complementos=[{"id": ids["Usuarios extra"], "cantidad": 2}, {"id": ids["Instalación"], "cantidad": 1}])
    guardada = asignar(comercial, empresa, body)
    assert guardada.status_code == 200, guardada.text
    condiciones = guardada.json()["cliente"]["condiciones"]
    assert condiciones["precio_acordado"] == "1440.00"
    assert condiciones["importe_servicios"] == "250.00"
    assert condiciones["limites"]["usuarios"] == 9
    body["moneda"] = "USD"
    assert asignar(comercial, empresa, body).status_code == 422


def test_preview_no_crea_contrato_ni_auditoria_y_avisa_sobrecupo(comercial, fabrica):
    from tests.services.test_limites_plan import ubicacion

    empresa = fabrica.cliente()
    id_plan = plan(comercial, empresa)
    sede = fabrica.sede(empresa)
    ubicacion(fabrica.db, sede, "A")
    ubicacion(fabrica.db, sede, "B")
    antes = fabrica.db.query(LogAuditoria).count()
    body = datos(id_plan, limites_acordados={"ubicaciones": 1, "dispositivos": 10, "usuarios": 5})
    preview = comercial.post(f"/comercial/clientes/{empresa.id_clnt}/suscripcion/preview", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["recursos_excedidos"] == ["ubicaciones"]
    assert fabrica.db.query(Suscripcion).filter(Suscripcion.id_clnt == empresa.id_clnt).count() == 0
    assert fabrica.db.query(LogAuditoria).count() == antes
    assert asignar(comercial, empresa, body).status_code == 200
    assert fabrica.db.query(Ubicacion).filter(Ubicacion.id_sd == sede.id_sd).count() == 2


def test_reintento_idempotente_y_clave_no_se_reutiliza_para_otras_condiciones(comercial, fabrica):
    empresa = fabrica.cliente()
    body = datos(plan(comercial, empresa), clave_idempotencia="contrato-unico-123456")
    primera = asignar(comercial, empresa, body)
    segunda = asignar(comercial, empresa, body)
    assert primera.status_code == segunda.status_code == 200
    assert primera.json()["cliente"]["suscripcion_id"] == segunda.json()["cliente"]["suscripcion_id"]
    assert fabrica.db.query(Suscripcion).filter(Suscripcion.id_clnt == empresa.id_clnt).count() == 1
    assert asignar(comercial, empresa, {**body, "precio_acordado": "12"}).status_code == 409


def test_confirmacion_rechaza_plan_o_contrato_que_cambio_desde_preview(comercial, fabrica):
    empresa = fabrica.cliente()
    id_plan = plan(comercial, empresa)
    body = datos(id_plan)
    preview = comercial.post(f"/comercial/clientes/{empresa.id_clnt}/suscripcion/preview", json=body).json()
    comercial.put(f"/comercial/planes/{id_plan}/limites", json={"ubicaciones": 2, "dispositivos": 10, "usuarios": 5})
    assert asignar(comercial, empresa, {**body, "revision_plan": preview["revision_plan"]}).status_code == 409
    assert asignar(comercial, empresa, body).status_code == 200
    assert asignar(comercial, empresa, {**body, "precio_acordado": "50", "suscripcion_actual_id": None}).status_code == 409


def test_renovacion_futura_respeta_fechas_incluso_sin_worker(comercial, fabrica, monkeypatch):
    empresa = fabrica.cliente()
    id_plan = plan(comercial, empresa)
    actual = asignar(comercial, empresa, datos(id_plan)).json()["cliente"]
    inicio = fecha_comercial() + timedelta(days=31)
    futuro = datos(id_plan, operacion="Renovar", fecha_inicio=str(inicio), fecha_vencimiento=str(inicio + timedelta(days=365)), precio_acordado="90")
    pendiente = asignar(comercial, empresa, futuro)
    assert pendiente.status_code == 200, pendiente.text
    assert pendiente.json()["cliente"]["suscripcion_id"] == actual["suscripcion_id"]
    id_futuro = pendiente.json()["cliente"]["programada"]["id"]
    assert asignar(comercial, empresa, {**futuro, "precio_acordado": "80"}).status_code == 409
    monkeypatch.setattr("app.services.limites_plan.fecha_comercial", lambda: inicio)
    assert resumen_cliente(fabrica.db, empresa)["suscripcion_id"] == id_futuro
    assert resumen_cliente(fabrica.db, empresa)["estado_suscripcion"] == "Vigente"
    assert aplicar_programadas(fabrica.db, inicio) == 1
    fabrica.db.flush()
    assert aplicar_programadas(fabrica.db, inicio) == 0
    assert fabrica.db.get(Suscripcion, actual["suscripcion_id"]).estd == "Reemplazada"
    assert fabrica.db.get(Suscripcion, id_futuro).estd == "Activa"


def test_cancelar_programacion_no_revoca_contrato_al_llegar_fecha(comercial, fabrica, monkeypatch):
    empresa = fabrica.cliente()
    id_plan = plan(comercial, empresa)
    actual = asignar(comercial, empresa, datos(id_plan)).json()["cliente"]
    inicio = fecha_comercial() + timedelta(days=5)
    futura = asignar(comercial, empresa, datos(id_plan, operacion="Cambiar", fecha_inicio=str(inicio))).json()["cliente"]["programada"]
    res = comercial.post(f"/comercial/clientes/{empresa.id_clnt}/suscripciones/{futura['id']}/estado", json={"accion": "Cancelar", "motivo": "Cliente desistió"})
    assert res.status_code == 200, res.text
    monkeypatch.setattr("app.services.limites_plan.fecha_comercial", lambda: inicio)
    assert resumen_cliente(fabrica.db, empresa)["suscripcion_id"] == actual["suscripcion_id"]
    assert aplicar_programadas(fabrica.db, inicio) == 0


def test_suspension_reactivacion_cancelacion_y_auditoria(comercial, fabrica):
    empresa = fabrica.cliente()
    actual = asignar(comercial, empresa, datos(plan(comercial, empresa))).json()["cliente"]
    inicio = fecha_comercial() + timedelta(days=31)
    futura = asignar(comercial, empresa, datos(actual["plan_id"], operacion="Renovar",
        fecha_inicio=str(inicio), fecha_vencimiento=str(inicio + timedelta(days=30))))
    assert futura.status_code == 200, futura.text
    id_futura = futura.json()["cliente"]["programada"]["id"]
    url = f"/comercial/clientes/{empresa.id_clnt}/suscripciones/{actual['suscripcion_id']}/estado"
    for accion, estado in [("Suspender", "Suspendida"), ("Reactivar", "Vigente"), ("Cancelar", "Cancelada")]:
        res = comercial.post(url, json={"accion": accion, "motivo": f"Solicitud: {accion}"})
        assert res.status_code == 200, res.text
        assert res.json()["cliente"]["estado_suscripcion"] == estado
        if accion != "Reactivar":
            with pytest.raises(HTTPException):
                exigir_operacion(fabrica.db, empresa.id_clnt)
    historial = comercial.get(f"/comercial/clientes/{empresa.id_clnt}/historial").json()
    assert fabrica.db.get(Suscripcion, id_futura).estd == "Anulada"
    assert {e["accion"] for e in historial["eventos"]} >= {"crear", "suspender", "reactivar", "cancelar"}
    assert all(e["actor_nombre"] for e in historial["eventos"])


def test_prueba_es_explicita_y_gracia_tiene_fin(comercial, fabrica, monkeypatch):
    empresa = fabrica.cliente()
    id_plan = plan(comercial, empresa)
    hoy = fecha_comercial()
    invalida = datos(id_plan, es_prueba=True, fecha_vencimiento=str(hoy + timedelta(days=40)))
    assert asignar(comercial, empresa, invalida).status_code == 422
    body = datos(id_plan, es_prueba=True, dias_gracia=3, fecha_vencimiento=str(hoy + timedelta(days=14)))
    res = asignar(comercial, empresa, body)
    assert res.status_code == 200, res.text
    assert res.json()["cliente"]["condiciones"]["precio_acordado"] == "0.00"
    monkeypatch.setattr("app.services.limites_plan.fecha_comercial", lambda: hoy + timedelta(days=17))
    assert resumen_cliente(fabrica.db, empresa)["estado_suscripcion"] == "En gracia"
    exigir_operacion(fabrica.db, empresa.id_clnt)
    monkeypatch.setattr("app.services.limites_plan.fecha_comercial", lambda: hoy + timedelta(days=18))
    with pytest.raises(HTTPException):
        exigir_operacion(fabrica.db, empresa.id_clnt)


def test_sin_suscripcion_no_hay_cupo_por_defecto(fabrica, monkeypatch):
    monkeypatch.delenv("PLAN_LIMITS_REQUIRE_SUBSCRIPTION", raising=False)
    empresa = fabrica.cliente()
    with pytest.raises(HTTPException) as exc:
        comprobar_cupo(fabrica.db, empresa.id_clnt, "usuarios")
    assert exc.value.status_code == 409


def test_funcionalidades_futuras_no_se_venden_y_derechos_se_validan(comercial, fabrica):
    empresa = fabrica.cliente()
    id_plan = plan(comercial, empresa)
    assert comercial.put(f"/comercial/planes/{id_plan}/funcionalidades", json={"funcionalidades": ["ml_predicciones"]}).status_code == 200
    assert asignar(comercial, empresa, datos(id_plan)).status_code == 422
    assert comercial.post("/comercial/funcionalidades", json={"codigo": "modulo_prueba", "nombre": "Módulo de prueba", "disponible": True}).status_code == 201
    comercial.put(f"/comercial/planes/{id_plan}/funcionalidades", json={"funcionalidades": ["modulo_prueba"]})
    assert asignar(comercial, empresa, datos(id_plan)).status_code == 200
    exigir_funcionalidad(fabrica.db, empresa.id_clnt, "modulo_prueba")
    with pytest.raises(HTTPException):
        exigir_funcionalidad(fabrica.db, empresa.id_clnt, "ml_predicciones")


def test_historial_solo_admin_empresa_y_sin_precios_para_lector(comercial, fabrica):
    empresa = fabrica.cliente()
    otra = fabrica.cliente()
    assert asignar(comercial, empresa, datos(plan(comercial, empresa))).status_code == 200
    actor = {"sub": "1", "scope": "por_cliente", "rol": "Usuario Empresa", "cliente_id": empresa.id_clnt,
             "rol_empresa": "Administrador", "_entorno_resuelto": True}
    app.dependency_overrides[get_current_user] = lambda: actor
    assert comercial.get(f"/comercial/clientes/{empresa.id_clnt}/historial").status_code == 200
    assert comercial.get(f"/comercial/clientes/{otra.id_clnt}/historial").status_code == 403
    actor["rol_empresa"] = "Lector"
    assert comercial.get(f"/comercial/clientes/{empresa.id_clnt}/historial").status_code == 403
    acceso = comercial.get("/comercial/mi-acceso")
    assert acceso.status_code == 200
    assert "precio_acordado" not in acceso.text


def test_vencimiento_bloquea_edicion_y_conserva_lectura_de_telemetria(entorno):
    client, db, empresas, recursos, cuentas, _ = entorno
    empresa = empresas[0]
    base = PlanSuscripcion(nmbr="Contrato expirado", prc_mnsl=100)
    db.add(base)
    db.flush()
    contrato = db.query(Suscripcion).filter(Suscripcion.id_clnt == empresa.id_clnt).one()
    contrato.id_pln = base.id_pln
    contrato.fch_inc = fecha_comercial() - timedelta(days=40)
    contrato.fch_vncmnt = fecha_comercial() - timedelta(days=1)
    db.flush()
    autenticar(client, cuentas["Tecnico"])
    assert client.get("/mediciones").status_code == 200
    assert client.get("/dispositivos").status_code == 200
    dispositivo = recursos[0][4]
    assert client.put(f"/dispositivos/{dispositivo.id_dspstv}", json={"nmbr": "No debe guardar"}).status_code == 409
    assert dispositivo.nmbr != "No debe guardar"
    acceso = client.get("/comercial/mi-acceso").json()
    assert acceso["consulta_historica"] and acceso["recepcion_telemetria"]
    assert not acceso["operacion_habilitada"]
    assert not client.get("/auth/perfil").json()["operacion_habilitada"]


def test_modulo_existente_exige_funcionalidad_contratada(comercial, fabrica):
    empresa = fabrica.cliente()
    id_plan = plan(comercial, empresa)
    comercial.put(f"/comercial/planes/{id_plan}/funcionalidades", json={"funcionalidades": []})
    assert asignar(comercial, empresa, datos(id_plan)).status_code == 200
    original = app.dependency_overrides[get_current_user]()
    actor = {**original, "rol": "Administrador", "cliente_id": empresa.id_clnt, "_entorno_resuelto": True}
    app.dependency_overrides[get_current_user] = lambda: actor
    assert comercial.get("/paneles").status_code == 403
    comercial.put(f"/comercial/planes/{id_plan}/funcionalidades", json={"funcionalidades": ["tableros"]})
    assert comercial.get("/paneles").status_code == 403  # El catálogo no altera el contrato ya firmado.


def test_lector_no_recibe_condiciones_negociadas_en_listado_operativo(entorno):
    client, db, empresas, _, cuentas, _ = entorno
    base = PlanSuscripcion(nmbr="Contrato privado", prc_mnsl=123)
    db.add(base)
    db.flush()
    contrato = db.query(Suscripcion).filter(Suscripcion.id_clnt == empresas[0].id_clnt).one()
    contrato.id_pln = base.id_pln
    contrato.condiciones = {"plan_nombre": "Contrato privado", "precio_acordado": "123.45", "limites": None,
                           "funcionalidades": ["tableros"], "dias_gracia": 0}
    db.flush()
    autenticar(client, cuentas["Lector"])
    respuesta = client.get("/empresas")
    assert respuesta.status_code == 200, respuesta.text
    assert "condiciones" not in respuesta.json()[0]
    assert "precio_acordado" not in respuesta.text
    assert client.get(f"/comercial/clientes/{empresas[0].id_clnt}/historial").status_code == 403
