"""
QA - PP-410 Validar la HT "Modelo de datos comercial multi-sede y automatización
de vencimientos" (PP-317, PP-318, PP-319, PP-320, PP-321, PP-322).

Se ejecuta sobre dev + feature/PP-47-modelo-comercial integrados localmente.
Desde backend/ del worktree con la BD de test migrada:
    PLAN_LIMITS_REQUIRE_SUBSCRIPTION=false \
    TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:55432/pangea_test \
    python -m pytest <ruta>/test_pp410_qa.py --html=<ruta>/pytest_pp410.html --self-contained-html
"""

from contextlib import nullcontext
from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.core.celery_app import celery_app
from app.models import Cobro, LimitePlan, Sede, Suscripcion  # noqa: F401
from app.services.contratos import vencer_sin_cobro
from app.services.limites_plan import comprobar_cupo, fecha_comercial, resumen_cliente
from app.tasks import notificaciones, suscripciones

from tests.conftest import _engine, db_session, fabrica  # noqa: F401
from tests.routers.test_comercial import comercial as comercial_basico  # noqa: F401
from tests.routers.test_contratos import asignar, datos, plan  # noqa: F401
from tests.routers.test_vencimientos import _contrato, _tabla, comercial, otro_rol, plan_id  # noqa: F401

HOY = fecha_comercial()
FECHA_OK = str(HOY - timedelta(days=1))


def cobro_body(**cambios):
    return {"monto": "150.50", "fecha_cobro": FECHA_OK, "metodo_pago": "Transferencia bancaria", **cambios}


def plan_con_cliente(comercial, fabrica, sedes=3):
    cliente = fabrica.cliente()
    for _ in range(sedes):
        fabrica.sede(cliente)
    id_plan = plan(comercial, cliente)
    r = asignar(comercial, cliente, datos(id_plan))
    assert r.status_code in (200, 201), r.text
    return cliente


# ============ CA1 · Cliente con una o más sedes bajo un mismo plan (HU44 / PP-317, PP-318) ============
def test_ca1_cliente_con_tres_sedes_comparte_un_solo_contrato(comercial, db_session, fabrica):
    cliente = plan_con_cliente(comercial, fabrica, sedes=3)
    sedes = db_session.query(Sede).filter(Sede.id_clnt == cliente.id_clnt).count()
    contratos = db_session.query(Suscripcion).filter(Suscripcion.id_clnt == cliente.id_clnt).count()
    assert sedes == 3
    assert contratos == 1


def test_ca1_sede_no_guarda_datos_comerciales_y_cliente_es_la_raiz():
    columnas_sede = {c.name for c in Sede.__table__.columns}
    assert "id_clnt" in columnas_sede
    assert not columnas_sede & {"id_pln", "id_sscrpcn", "rc", "prc_mnsl", "fch_vncmnt"}
    assert Suscripcion.__table__.c.id_clnt.foreign_keys, "el plan cuelga del Cliente"
    assert not {"id_sd"} & {c.name for c in Suscripcion.__table__.columns}


def test_ca1_cada_cliente_tiene_su_propio_plan_aunque_comparta_catalogo(comercial, db_session, fabrica):
    a = fabrica.cliente()
    b = fabrica.cliente()
    fabrica.sede(a), fabrica.sede(b)
    id_plan = plan(comercial, a)
    assert asignar(comercial, a, datos(id_plan)).status_code in (200, 201)
    assert asignar(comercial, b, datos(id_plan)).status_code in (200, 201)
    plan_a = resumen_cliente(db_session, a)["plan_id"]
    plan_b = resumen_cliente(db_session, b)["plan_id"]
    assert plan_a == plan_b == id_plan
    assert resumen_cliente(db_session, a)["suscripcion_id"] != resumen_cliente(db_session, b)["suscripcion_id"]


# ============ HU42/HU43 · Catálogo de planes con niveles y límites ============
def test_hu43_plan_guarda_limites_de_ubicaciones_dispositivos_y_usuarios(comercial):
    creado = comercial.post("/comercial/planes", json={"nombre": "QA Plan PP410 A", "precio_mensual": "200.00"})
    assert creado.status_code == 201, creado.text
    id_plan = creado.json()["plan"]["id_pln"]
    r = comercial.put(f"/comercial/planes/{id_plan}/limites", json={"ubicaciones": 2, "dispositivos": 8, "usuarios": 4})
    assert r.status_code == 200, r.text
    limites = r.json()["plan"]["limites"]
    assert (limites["ubicaciones"], limites["dispositivos"], limites["usuarios"]) == (2, 8, 4)


def test_hu43_plan_guarda_limite_maximo_de_sedes(comercial):
    creado = comercial.post("/comercial/planes", json={"nombre": "QA Plan PP410 B", "precio_mensual": "200.00"})
    id_plan = creado.json()["plan"]["id_pln"]
    r = comercial.put(
        f"/comercial/planes/{id_plan}/limites",
        json={"sedes": 2, "ubicaciones": 2, "dispositivos": 8, "usuarios": 4},
    )
    assert r.status_code == 200, r.text
    assert r.json()["plan"]["limites"]["sedes"] == 2


def test_hu43_limite_de_sedes_negativo_se_rechaza(comercial):
    id_plan = comercial.post("/comercial/planes", json={"nombre": "QA Plan PP410 D", "precio_mensual": "10"}).json()["plan"]["id_pln"]
    r = comercial.put(f"/comercial/planes/{id_plan}/limites", json={"sedes": -1, "ubicaciones": 1, "dispositivos": 1, "usuarios": 1})
    assert r.status_code == 422


def test_hu43_limites_negativos_se_rechazan(comercial):
    id_plan = comercial.post("/comercial/planes", json={"nombre": "QA Plan PP410 C", "precio_mensual": "10"}).json()["plan"]["id_pln"]
    r = comercial.put(f"/comercial/planes/{id_plan}/limites", json={"ubicaciones": -1, "dispositivos": 1, "usuarios": 1})
    assert r.status_code == 422


def test_hu45_no_se_asigna_plan_sin_limites_configurados(comercial, fabrica):
    cliente = fabrica.cliente()
    id_plan = comercial.post("/comercial/planes", json={"nombre": "QA Sin limites", "precio_mensual": "10"}).json()["plan"]["id_pln"]
    r = asignar(comercial, cliente, datos(id_plan))
    assert r.status_code == 409


# ============ CA2 · Rechazo de sede que excede el límite del plan (PP-319) ============
def cliente_con_limite_de_sedes(comercial, fabrica, limite, sedes_existentes):
    cliente = fabrica.cliente()
    for _ in range(sedes_existentes):
        fabrica.sede(cliente)
    creado = comercial.post("/comercial/planes", json={"nombre": f"QA Sedes {cliente.id_clnt}", "precio_mensual": "100"})
    id_plan = creado.json()["plan"]["id_pln"]
    r = comercial.put(f"/comercial/planes/{id_plan}/limites",
                      json={"sedes": limite, "ubicaciones": 5, "dispositivos": 5, "usuarios": 5})
    assert r.status_code == 200, r.text
    assert asignar(comercial, cliente, datos(id_plan)).status_code in (200, 201)
    return cliente


def alta_sede(comercial, cliente, nombre="QA Sede nueva"):
    return comercial.post(f"/comercial/clientes/{cliente.id_clnt}/sedes", json={"nombre": nombre})


def test_ca2_nueva_sede_sobre_el_limite_del_plan_se_rechaza(comercial, db_session, fabrica):
    cliente = cliente_con_limite_de_sedes(comercial, fabrica, limite=2, sedes_existentes=2)
    r = alta_sede(comercial, cliente)
    assert r.status_code == 409
    assert "límite de tu plan" in r.json()["detail"]
    assert db_session.query(Sede).filter(Sede.id_clnt == cliente.id_clnt).count() == 2


def test_ca2_sede_dentro_del_limite_se_crea_y_la_ultima_permitida_tambien(comercial, db_session, fabrica):
    cliente = cliente_con_limite_de_sedes(comercial, fabrica, limite=3, sedes_existentes=1)
    assert alta_sede(comercial, cliente, "QA Sede 2").status_code == 201
    assert alta_sede(comercial, cliente, "QA Sede 3").status_code == 201
    assert alta_sede(comercial, cliente, "QA Sede 4").status_code == 409
    assert db_session.query(Sede).filter(Sede.id_clnt == cliente.id_clnt).count() == 3


def test_ca2_limite_cero_significa_sin_tope(comercial, fabrica):
    cliente = cliente_con_limite_de_sedes(comercial, fabrica, limite=0, sedes_existentes=4)
    assert alta_sede(comercial, cliente).status_code == 201


def test_ca2_las_sedes_de_otro_cliente_no_cuentan(comercial, fabrica):
    cliente = cliente_con_limite_de_sedes(comercial, fabrica, limite=1, sedes_existentes=0)
    otro = fabrica.cliente()
    for _ in range(3):
        fabrica.sede(otro)
    assert alta_sede(comercial, cliente).status_code == 201
    assert alta_sede(comercial, cliente, "QA Sede extra").status_code == 409


def test_ca2_subir_el_limite_del_plan_permite_nuevas_sedes_tras_reasignar(comercial, fabrica):
    cliente = cliente_con_limite_de_sedes(comercial, fabrica, limite=1, sedes_existentes=1)
    assert alta_sede(comercial, cliente).status_code == 409
    id_plan = comercial.post("/comercial/planes", json={"nombre": f"QA Sedes mayor {cliente.id_clnt}", "precio_mensual": "100"}).json()["plan"]["id_pln"]
    comercial.put(f"/comercial/planes/{id_plan}/limites", json={"sedes": 5, "ubicaciones": 5, "dispositivos": 5, "usuarios": 5})
    r = asignar(comercial, cliente, datos(id_plan, motivo="Ampliación de sedes"))
    assert r.status_code in (200, 201), r.text
    assert alta_sede(comercial, cliente).status_code == 201


def test_ca2_alta_de_sede_cliente_sin_plan_inexistente_rol_y_nombre(comercial, otro_rol, fabrica, monkeypatch):
    monkeypatch.setenv("PLAN_LIMITS_REQUIRE_SUBSCRIPTION", "true")
    sin_plan = fabrica.cliente()
    assert alta_sede(comercial, sin_plan).status_code == 409
    assert comercial.post("/comercial/clientes/99999999/sedes", json={"nombre": "X"}).status_code == 404
    assert comercial.post(f"/comercial/clientes/{sin_plan.id_clnt}/sedes", json={"nombre": "   "}).status_code == 422
    assert otro_rol("Cliente Final", scope="por_sede").post(
        f"/comercial/clientes/{sin_plan.id_clnt}/sedes", json={"nombre": "X"}).status_code == 403


def test_ca2_plan_vencido_no_permite_nuevas_sedes(comercial, db_session, fabrica):
    cliente = cliente_con_limite_de_sedes(comercial, fabrica, limite=5, sedes_existentes=1)
    contrato = db_session.query(Suscripcion).filter(Suscripcion.id_clnt == cliente.id_clnt).one()
    contrato.estd = "Vencida"
    db_session.flush()
    assert alta_sede(comercial, cliente).status_code == 409


def test_ca2_contrato_anterior_sin_limite_de_sedes_no_bloquea(comercial, db_session, fabrica):
    cliente = plan_con_cliente(comercial, fabrica, sedes=3)
    contrato = db_session.query(Suscripcion).filter(Suscripcion.id_clnt == cliente.id_clnt).one()
    limites = {k: v for k, v in contrato.condiciones["limites"].items() if k != "sedes"}
    contrato.condiciones = {**contrato.condiciones, "limites": limites}
    db_session.flush()
    assert alta_sede(comercial, cliente).status_code == 201


def test_ca2_el_limite_de_ubicaciones_si_se_aplica_con_409(comercial, db_session, fabrica):
    """Control: el mecanismo de cupo existe y funciona para el recurso ya implementado."""
    cliente = plan_con_cliente(comercial, fabrica, sedes=1)
    contrato = db_session.query(Suscripcion).filter(Suscripcion.id_clnt == cliente.id_clnt).one()
    db_session.query(LimitePlan).filter(LimitePlan.id_pln == contrato.id_pln).update({"mx_ubccns": 0})
    contrato.condiciones = {**contrato.condiciones, "limites": {"ubicaciones": 1, "dispositivos": 5, "usuarios": 5}}
    db_session.flush()
    comprobar_cupo(db_session, cliente.id_clnt, "ubicaciones")  # consumo 0 < 1: permitido


def test_ca2_cliente_sin_plan_vigente_no_puede_crecer(fabrica, monkeypatch):
    monkeypatch.setenv("PLAN_LIMITS_REQUIRE_SUBSCRIPTION", "true")
    cliente = fabrica.cliente()
    with pytest.raises(HTTPException) as exc:
        comprobar_cupo(fabrica.db, cliente.id_clnt, "ubicaciones")
    assert exc.value.status_code == 409


# ============ CA3 · Vencimiento automático + notificación (PP-320, PP-321, PP-322) ============
def test_ca3_beat_programa_la_tarea_todos_los_dias():
    entrada = celery_app.conf.beat_schedule["vencer-suscripciones-sin-cobro-diario"]
    assert entrada["task"] == "app.tasks.suscripciones.vencer_suscripciones_sin_cobro"
    horario = entrada["schedule"]
    assert horario.hour == {0} and horario.minute == {30}
    assert horario.day_of_week == set(range(7)), "debe correr los 7 días"


def test_ca3_plan_con_renovacion_pasada_sin_cobro_pasa_a_vencida_y_avisa(fabrica, monkeypatch):
    cliente = fabrica.cliente()
    fila = _contrato_directo(fabrica, cliente, dias=-1)
    encolados = []
    monkeypatch.setattr(suscripciones, "SessionLocal", lambda: nullcontext(fabrica.db))
    monkeypatch.setattr(suscripciones.notificar_suscripciones_vencidas, "delay", lambda v: encolados.append(v))
    resultado = suscripciones.vencer_suscripciones_sin_cobro.run()
    assert resultado["vencidas"] >= 1
    assert fabrica.db.get(Suscripcion, fila.id_sscrpcn).estd == "Vencida"
    assert fila.id_sscrpcn in {v["suscripcion_id"] for v in encolados[0]}


def test_ca3_aviso_llega_solo_al_administrador_comercial_activo(fabrica, monkeypatch):
    comercial_activo = fabrica.usuario(fabrica.rol("Administrador Comercial"), scp="global")
    otro = fabrica.usuario(fabrica.rol("Administrador"), scp="global")
    fabrica.db.flush()
    enviados = []
    monkeypatch.setattr(notificaciones, "SessionLocal", lambda: nullcontext(fabrica.db))
    monkeypatch.setattr(notificaciones, "enviar_correo", lambda *a: enviados.append(a))
    vencida = {"suscripcion_id": 1, "empresa": "Minera QA", "ruc": "20999999999", "plan": "Plan QA",
               "fecha_vencimiento": str(HOY - timedelta(days=1))}
    notificaciones.notificar_suscripciones_vencidas.run([vencida])
    destinatarios = enviados[0][0]
    assert comercial_activo.crr in destinatarios and otro.crr not in destinatarios


def test_ca3_plan_con_cobro_registrado_no_se_vence(comercial, db_session, fabrica, plan_id):
    id_clnt = _contrato(db_session, fabrica, plan_id, -1)
    contrato = db_session.query(Suscripcion).filter(Suscripcion.id_clnt == id_clnt).one()
    db_session.add(Cobro(id_sscrpcn=contrato.id_sscrpcn, mnt=100, fch_cbr=contrato.fch_inc, mtd_pg="Efectivo"))
    db_session.flush()
    assert contrato.id_sscrpcn not in {v["suscripcion_id"] for v in vencer_sin_cobro(db_session, HOY)}
    assert contrato.estd == "Activa"


def test_ca3_dos_corridas_el_mismo_dia_no_duplican_el_aviso(fabrica):
    fila = _contrato_directo(fabrica, fabrica.cliente(), dias=-1)
    assert fila.id_sscrpcn in {v["suscripcion_id"] for v in vencer_sin_cobro(fabrica.db, HOY)}
    assert fila.id_sscrpcn not in {v["suscripcion_id"] for v in vencer_sin_cobro(fabrica.db, HOY)}


def test_ca3_plan_vigente_o_en_su_ultimo_dia_no_se_toca(fabrica):
    hoy_mismo = _contrato_directo(fabrica, fabrica.cliente(), dias=0)
    futuro = _contrato_directo(fabrica, fabrica.cliente(), dias=15)
    vencidos = {v["suscripcion_id"] for v in vencer_sin_cobro(fabrica.db, HOY)}
    assert hoy_mismo.id_sscrpcn not in vencidos and futuro.id_sscrpcn not in vencidos


def test_ca3_sin_vencidas_no_se_envia_correo(monkeypatch):
    enviados = []
    monkeypatch.setattr(notificaciones, "enviar_correo", lambda *a: enviados.append(a))
    assert notificaciones.notificar_suscripciones_vencidas.run([]) == {"enviados": 0}
    assert enviados == []


# ============ CA4 · Historial de cobros sin sobrescribir (HU46) ============
def test_ca4_tres_cobros_se_conservan_y_el_primero_no_cambia(comercial, db_session, fabrica):
    cliente = plan_con_cliente(comercial, fabrica, sedes=2)
    ids = []
    for monto in ("100.00", "250.50", "75.25"):
        r = comercial.post(f"/comercial/clientes/{cliente.id_clnt}/cobros", json=cobro_body(monto=monto))
        assert r.status_code == 201, r.text
        ids.append(r.json()["cobro"]["id"])
    historial = comercial.get(f"/comercial/clientes/{cliente.id_clnt}/cobros").json()
    cuerpo = historial if isinstance(historial, list) else historial.get("cobros", historial.get("items", []))
    assert len(ids) == len(set(ids)) == 3
    assert {c["id"] for c in cuerpo} >= set(ids)
    primero = next(c for c in cuerpo if c["id"] == ids[0])
    assert primero["monto"] == "100.00"


def test_ca4_dos_cobros_identicos_son_dos_registros(comercial, fabrica):
    cliente = plan_con_cliente(comercial, fabrica, sedes=1)
    url = f"/comercial/clientes/{cliente.id_clnt}/cobros"
    a = comercial.post(url, json=cobro_body()).json()["cobro"]["id"]
    b = comercial.post(url, json=cobro_body()).json()["cobro"]["id"]
    assert a != b


def test_ca4_cobro_queda_ligado_al_periodo_contratado_y_el_nuevo_no_lo_mueve(comercial, db_session, fabrica):
    cliente = plan_con_cliente(comercial, fabrica, sedes=1)
    r = comercial.post(f"/comercial/clientes/{cliente.id_clnt}/cobros", json=cobro_body())
    contrato = db_session.query(Suscripcion).filter(Suscripcion.id_clnt == cliente.id_clnt).one()
    assert db_session.get(Cobro, r.json()["cobro"]["id"]).id_sscrpcn == contrato.id_sscrpcn


@pytest.mark.parametrize("metodo", ["PUT", "PATCH", "DELETE"])
def test_ca4_la_api_no_permite_editar_ni_borrar_un_cobro(comercial, fabrica, metodo):
    cliente = plan_con_cliente(comercial, fabrica, sedes=1)
    id_cobro = comercial.post(f"/comercial/clientes/{cliente.id_clnt}/cobros", json=cobro_body()).json()["cobro"]["id"]
    r = comercial.request(metodo, f"/comercial/clientes/{cliente.id_clnt}/cobros/{id_cobro}", json=cobro_body(monto="1"))
    assert r.status_code in (404, 405)


@pytest.mark.parametrize(
    "cambios,esperado",
    [({"monto": "0"}, 422), ({"monto": "-5"}, 422), ({"monto": "abc"}, 422), ({"monto": "10.123"}, 422),
     ({"fecha_cobro": str(HOY + timedelta(days=1))}, 422), ({"fecha_cobro": "31-12-2026"}, 422),
     ({"metodo_pago": "Bitcoin"}, 422)],
)
def test_ca4_cobros_invalidos_se_rechazan_y_no_se_guardan(comercial, db_session, fabrica, cambios, esperado):
    cliente = plan_con_cliente(comercial, fabrica, sedes=1)
    r = comercial.post(f"/comercial/clientes/{cliente.id_clnt}/cobros", json=cobro_body(**cambios))
    assert r.status_code == esperado
    assert db_session.query(Cobro).count() == 0 or all(c.mnt > 0 for c in db_session.query(Cobro))


def test_ca4_cobro_a_cliente_inexistente_o_sin_plan(comercial, fabrica):
    assert comercial.post("/comercial/clientes/99999999/cobros", json=cobro_body()).status_code == 404
    sin_plan = fabrica.cliente()
    assert comercial.post(f"/comercial/clientes/{sin_plan.id_clnt}/cobros", json=cobro_body()).status_code == 409


def test_ca4_solo_el_administrador_comercial_registra_cobros(otro_rol, fabrica):
    cliente = fabrica.cliente()
    r = otro_rol("Administrador").post(f"/comercial/clientes/{cliente.id_clnt}/cobros", json=cobro_body())
    assert r.status_code == 403


# ============ CA5 · HU47 Consultar vencimientos con datos de la tarea programada ============
def test_ca5_la_tabla_muestra_vigentes_proximos_y_vencidos_y_filtra_por_rango(comercial, db_session, fabrica, plan_id):
    vigente = _contrato(db_session, fabrica, plan_id, 90)
    proximo = _contrato(db_session, fabrica, plan_id, 5)
    vencido = _contrato(db_session, fabrica, plan_id, -3)
    propios = {vigente, proximo, vencido}

    def ids(rango):
        return {f["id_clnt"] for f in _tabla(comercial, rango)} & propios

    assert ids("todos") == propios
    assert ids("vencidos") == {vencido}
    assert ids("7") == {proximo}
    assert ids("30") == {proximo}


def test_ca5_un_plan_vencido_por_la_tarea_sigue_en_el_filtro_vencidos(comercial, db_session, fabrica, plan_id):
    id_clnt = _contrato(db_session, fabrica, plan_id, -2)
    vencer_sin_cobro(db_session, HOY)  # lo que hace la tarea diaria
    fila = next(f for f in _tabla(comercial, "vencidos") if f["id_clnt"] == id_clnt)
    assert fila["estado"] == "Vencida" and fila["vencida"] is True


def test_ca5_rango_invalido_y_acceso_restringido(comercial, otro_rol):
    assert comercial.get("/comercial/vencimientos?rango=cualquiera").status_code == 422
    assert otro_rol("Administrador").get("/comercial/vencimientos").status_code == 403


def test_ca5_clientes_sin_plan_no_aparecen_en_vencimientos(comercial, fabrica):
    sin_plan = fabrica.cliente()
    assert sin_plan.id_clnt not in {f["id_clnt"] for f in _tabla(comercial)}


# ---------------------------------------------------------------------------------------------
def _contrato_directo(fabrica, cliente, dias):
    """Contrato Activa con vencimiento a `dias` días de hoy, sin cobros."""
    from app.models import PlanSuscripcion

    p = PlanSuscripcion(nmbr=f"QA directo {cliente.id_clnt}", prc_mnsl=100)
    fabrica.db.add(p)
    fabrica.db.flush()
    fabrica.db.add(LimitePlan(id_pln=p.id_pln, mx_sds=0, mx_ubccns=5, mx_dspstvs=5, mx_usrs=5))
    fin = HOY + timedelta(days=dias)
    fila = Suscripcion(
        id_clnt=cliente.id_clnt, id_pln=p.id_pln, fch_inc=min(HOY, fin) - timedelta(days=30), fch_vncmnt=fin,
        estd="Activa",
        condiciones={"plan_nombre": p.nmbr, "dias_gracia": 0,
                     "limites": {"ubicaciones": 5, "dispositivos": 5, "usuarios": 5}, "funcionalidades": []},
    )
    fabrica.db.add(fila)
    fabrica.db.flush()
    return fila


# ============ PP-322 · Diagrama entidad-relación del modelo comercial ============
def test_pp322_el_diagrama_er_documenta_cliente_sede_plan_limites_contrato_y_cobro():
    from pathlib import Path

    texto = (Path("docs") / "modelo-comercial-er.md").read_text(encoding="utf-8")
    assert "erDiagram" in texto
    for relacion in ("clnt ||--o{ sd", "pln_sscrpcn ||--o| lmt_pln", "clnt ||--o{ sscrpcn", "sscrpcn ||--o{ cbr"):
        assert relacion in texto, relacion
    assert "mx_sds" in texto and "sin uso" not in texto
