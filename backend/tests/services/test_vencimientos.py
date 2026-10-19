"""PP-320 y PP-321: vencimiento automático sin cobro y aviso al comercial."""

from contextlib import nullcontext
from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.core.celery_app import celery_app
from app.models import Cobro, LimitePlan, LogAuditoria, PlanSuscripcion, Suscripcion
from app.services.contratos import vencer_sin_cobro
from app.services.limites_plan import comprobar_cupo, fecha_comercial, resumen_cliente
from app.tasks import notificaciones, suscripciones

HOY = fecha_comercial()


def contrato(db, cliente, fin, gracia=0, estado="Activa"):
    plan = PlanSuscripcion(nmbr=f"Plan vencimiento {cliente.id_clnt}", prc_mnsl=100)
    db.add(plan)
    db.flush()
    db.add(LimitePlan(id_pln=plan.id_pln, mx_sds=0, mx_ubccns=5, mx_dspstvs=5, mx_usrs=5))
    fila = Suscripcion(
        id_clnt=cliente.id_clnt,
        id_pln=plan.id_pln,
        fch_inc=fin - timedelta(days=30),
        fch_vncmnt=fin,
        estd=estado,
        condiciones={
            "plan_nombre": plan.nmbr,
            "dias_gracia": gracia,
            "limites": {"ubicaciones": 5, "dispositivos": 5, "usuarios": 5},
            "funcionalidades": [],
        },
    )
    db.add(fila)
    db.flush()
    return fila


def ids(vencidas):
    return {v["suscripcion_id"] for v in vencidas}


def test_vence_el_contrato_sin_cobro_y_lo_audita(fabrica):
    empresa = fabrica.cliente()
    fila = contrato(fabrica.db, empresa, fin=HOY - timedelta(days=1))

    vencidas = vencer_sin_cobro(fabrica.db, HOY)

    assert fila.id_sscrpcn in ids(vencidas)
    assert fabrica.db.get(Suscripcion, fila.id_sscrpcn).estd == "Vencida"
    aviso = next(v for v in vencidas if v["suscripcion_id"] == fila.id_sscrpcn)
    assert aviso["empresa"] == empresa.rzn_scl
    assert aviso["fecha_vencimiento"] == fila.fch_vncmnt.isoformat()
    auditoria = (
        fabrica.db.query(LogAuditoria)
        .filter(LogAuditoria.accn == "vencer_sin_cobro")
        .order_by(LogAuditoria.id_evnt.desc())
        .first()
    )
    assert auditoria.vlrs_nvs["suscripcion_id"] == fila.id_sscrpcn
    assert auditoria.vlrs_nvs["estado"] == "Vencida"


def test_respeta_los_dias_de_gracia(fabrica):
    empresa = fabrica.cliente()
    fila = contrato(fabrica.db, empresa, fin=HOY - timedelta(days=2), gracia=5)

    assert fila.id_sscrpcn not in ids(vencer_sin_cobro(fabrica.db, HOY))
    assert fila.estd == "Activa"
    # La gracia termina en fin + 5 = HOY + 3: al día siguiente ya vence.
    assert fila.id_sscrpcn not in ids(vencer_sin_cobro(fabrica.db, HOY + timedelta(days=3)))
    assert fila.id_sscrpcn in ids(vencer_sin_cobro(fabrica.db, HOY + timedelta(days=4)))


def test_no_toca_un_contrato_con_cobro_registrado(fabrica):
    empresa = fabrica.cliente()
    fila = contrato(fabrica.db, empresa, fin=HOY - timedelta(days=1))
    fabrica.db.add(
        Cobro(id_sscrpcn=fila.id_sscrpcn, mnt=100, fch_cbr=fila.fch_inc, mtd_pg="Transferencia")
    )
    fabrica.db.flush()

    assert fila.id_sscrpcn not in ids(vencer_sin_cobro(fabrica.db, HOY))
    assert fila.estd == "Activa"


@pytest.mark.parametrize("estado", ["Suspendida", "Cancelada", "Reemplazada"])
def test_solo_vence_contratos_activos(fabrica, estado):
    empresa = fabrica.cliente()
    fila = contrato(fabrica.db, empresa, fin=HOY - timedelta(days=1), estado=estado)

    assert fila.id_sscrpcn not in ids(vencer_sin_cobro(fabrica.db, HOY))
    assert fila.estd == estado


def test_no_toca_un_contrato_vigente(fabrica):
    empresa = fabrica.cliente()
    fila = contrato(fabrica.db, empresa, fin=HOY)

    assert fila.id_sscrpcn not in ids(vencer_sin_cobro(fabrica.db, HOY))
    assert fila.estd == "Activa"


def test_correr_dos_veces_no_vuelve_a_avisar(fabrica):
    empresa = fabrica.cliente()
    fila = contrato(fabrica.db, empresa, fin=HOY - timedelta(days=1))

    assert fila.id_sscrpcn in ids(vencer_sin_cobro(fabrica.db, HOY))
    assert fila.id_sscrpcn not in ids(vencer_sin_cobro(fabrica.db, HOY))


def test_el_contrato_vencido_se_sigue_viendo_y_bloquea_altas(fabrica):
    empresa = fabrica.cliente()
    fila = contrato(fabrica.db, empresa, fin=HOY - timedelta(days=1))
    vencer_sin_cobro(fabrica.db, HOY)

    resumen = resumen_cliente(fabrica.db, empresa)
    assert resumen["suscripcion_id"] == fila.id_sscrpcn
    assert resumen["estado_suscripcion"] == "Vencida"
    with pytest.raises(HTTPException) as exc:
        comprobar_cupo(fabrica.db, empresa.id_clnt, "ubicaciones")
    assert exc.value.status_code == 409


def test_la_tarea_diaria_esta_programada():
    tarea = celery_app.conf.beat_schedule["vencer-suscripciones-sin-cobro-diario"]
    assert tarea["task"] == "app.tasks.suscripciones.vencer_suscripciones_sin_cobro"


def test_la_tarea_vence_y_encola_el_aviso(fabrica, monkeypatch):
    empresa = fabrica.cliente()
    fila = contrato(fabrica.db, empresa, fin=HOY - timedelta(days=1))
    encolados = []
    monkeypatch.setattr(suscripciones, "SessionLocal", lambda: nullcontext(fabrica.db))
    monkeypatch.setattr(
        suscripciones.notificar_suscripciones_vencidas, "delay", lambda v: encolados.append(v)
    )

    resultado = suscripciones.vencer_suscripciones_sin_cobro.run()

    assert resultado["vencidas"] >= 1
    assert fila.id_sscrpcn in ids(encolados[0])


def test_aviso_llega_solo_a_comerciales_activos(fabrica, monkeypatch):
    comercial = fabrica.rol("Administrador Comercial")
    activo = fabrica.usuario(comercial, scp="global")
    inactivo = fabrica.usuario(comercial, scp="global")
    inactivo.estd = "Inactivo"
    otro_rol = fabrica.usuario(fabrica.rol("Administrador"), scp="global")
    fabrica.db.flush()
    enviados = []
    monkeypatch.setattr(notificaciones, "SessionLocal", lambda: nullcontext(fabrica.db))
    monkeypatch.setattr(notificaciones, "enviar_correo", lambda *args: enviados.append(args))
    vencida = {
        "suscripcion_id": 1,
        "empresa": "Minera Andina",
        "ruc": "20123456789",
        "plan": "Plan Pro",
        "fecha_vencimiento": "2026-10-15",
    }

    resultado = notificaciones.notificar_suscripciones_vencidas.run([vencida])

    assert len(enviados) == 1
    destinatarios, asunto, cuerpo = enviados[0]
    assert activo.crr in destinatarios
    assert inactivo.crr not in destinatarios
    assert otro_rol.crr not in destinatarios
    assert resultado["enviados"] == len(destinatarios)
    assert asunto == "Pangea: 1 suscripción vencida sin cobro"
    assert "Minera Andina (RUC 20123456789) · Plan Pro · venció el 15/10/2026" in cuerpo


def test_sin_vencidas_no_se_envia_nada(monkeypatch):
    enviados = []
    monkeypatch.setattr(notificaciones, "enviar_correo", lambda *args: enviados.append(args))

    assert notificaciones.notificar_suscripciones_vencidas.run([]) == {"enviados": 0}
    assert enviados == []


def test_asunto_en_plural():
    vencida = {"empresa": "A", "ruc": "1", "plan": None, "fecha_vencimiento": "2026-10-01"}
    asunto, cuerpo = notificaciones.aviso_vencidas([vencida, {**vencida, "empresa": "B"}])
    assert asunto == "Pangea: 2 suscripciones vencidas sin cobro"
    assert "A (RUC 1) · sin plan · venció el 01/10/2026" in cuerpo
