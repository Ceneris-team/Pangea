"""Condiciones comerciales inmutables y derechos efectivos por empresa."""

import hashlib
import json
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    Cliente,
    ComplementoComercial,
    FuncionalidadComercial,
    LimitePlan,
    LogAuditoria,
    PlanSuscripcion,
    Suscripcion,
)

RECURSOS = ("ubicaciones", "dispositivos", "usuarios")
MESES = {"Mensual": 1, "Trimestral": 3, "Anual": 12}
ESTADOS_CONTRATO = {"Activa", "Programada", "Suspendida", "Cancelada", "Reemplazada"}


def auditar(db, actor, accion, entidad, antes=None, despues=None):
    db.add(LogAuditoria(id_usr=int(actor["sub"]), id_sd=None, accn=accion, entdd=entidad,
                        vlrs_antrrs=antes, vlrs_nvs=despues))


def condiciones_de(db: Session, contrato: Suscripcion) -> dict:
    if contrato.condiciones is not None:
        return contrato.condiciones
    # Fixtures o integraciones anteriores a la migración: solo hasta que
    # se escriban condiciones; los contratos creados por API siempre las fijan.
    plan = db.get(PlanSuscripcion, contrato.id_pln)
    limite = db.query(LimitePlan).filter(LimitePlan.id_pln == contrato.id_pln).first()
    return {
        "plan_nombre": plan.nmbr, "revision_plan": plan.revision,
        "moneda": plan.moneda, "precio_acordado": str(plan.prc_mnsl), "periodicidad": "Mensual",
        "referencia": None, "motivo": "Contrato anterior", "dias_gracia": 0, "es_prueba": False,
        "funcionalidades": plan.funcionalidades or [], "complementos": [], "importe_servicios": "0.00",
        "limites": dict(zip(RECURSOS, [limite.mx_ubccns, limite.mx_dspstvs, limite.mx_usrs])) if limite else None,
        "politica_vencimiento": "Solo lectura; ingesta preservada",
    }


def ultimo_contrato(db, cliente_id, hoy):
    # Una programación comienza a dar derechos exactamente en su fecha,
    # aunque Beat se encuentre temporalmente detenido.
    return db.query(Suscripcion).filter(
        Suscripcion.id_clnt == cliente_id,
        Suscripcion.estd.in_(["Activa", "Programada", "Suspendida", "Cancelada"]),
        Suscripcion.fch_inc <= hoy,
    ).order_by(Suscripcion.fch_inc.desc(), Suscripcion.id_sscrpcn.desc()).first()


def estado_contrato(db, contrato, hoy):
    if contrato is None:
        return "Sin suscripción"
    if contrato.estd in {"Reemplazada", "Cancelada", "Suspendida", "Anulada"}:
        return contrato.estd
    if contrato.fch_inc > hoy:
        return "Programada"
    if contrato.fch_vncmnt >= hoy:
        return "Vigente"
    gracia = condiciones_de(db, contrato).get("dias_gracia", 0)
    if hoy <= contrato.fch_vncmnt + timedelta(days=gracia):
        return "En gracia"
    return "Vencida"


def contrato_dict(db, contrato, hoy):
    actual = ultimo_contrato(db, contrato.id_clnt, hoy)
    estado = estado_contrato(db, contrato, hoy)
    if estado in {"Vigente", "En gracia", "Vencida"} and actual and actual.id_sscrpcn != contrato.id_sscrpcn:
        estado = "Reemplazada"
    return {
        "id": contrato.id_sscrpcn, "plan_id": contrato.id_pln,
        "fecha_inicio": contrato.fch_inc, "fecha_vencimiento": contrato.fch_vncmnt,
        "estado": estado, "condiciones": condiciones_de(db, contrato),
    }


def validar_funcionalidades(db, codigos, exigir_disponibles=True):
    ids = set(codigos)
    filas = db.query(FuncionalidadComercial).filter(FuncionalidadComercial.codigo.in_(ids)).all()
    if {f.codigo for f in filas} != ids:
        raise HTTPException(422, "Hay funcionalidades que no existen en el catálogo")
    if exigir_disponibles and any(not f.disponible for f in filas):
        raise HTTPException(422, "Hay funcionalidades todavía no disponibles para contratar")
    return sorted(ids)


def preparar_condiciones(db, body, plan):
    limite = db.query(LimitePlan).filter(LimitePlan.id_pln == plan.id_pln).first()
    if limite is None:
        raise HTTPException(409, "Configura los límites antes de asignar el plan")
    if body.revision_plan is not None and body.revision_plan != plan.revision:
        raise HTTPException(409, "El plan cambió. Revisa nuevamente las condiciones")
    moneda = body.moneda or plan.moneda
    if moneda != plan.moneda:
        raise HTTPException(422, "La moneda debe coincidir con la del plan; no se realiza conversión automática")
    limites = dict(zip(RECURSOS, [limite.mx_ubccns, limite.mx_dspstvs, limite.mx_usrs]))
    funcionalidades = set(validar_funcionalidades(db, plan.funcionalidades or []))
    recurrente = Decimal(plan.prc_mnsl)
    servicios = Decimal("0")
    complementos = []
    ids = [item.id for item in body.complementos]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "No repitas el mismo complemento")
    for item in sorted(body.complementos, key=lambda x: x.id):
        extra = db.get(ComplementoComercial, item.id)
        if extra is None or not extra.activo or extra.moneda != moneda:
            raise HTTPException(422, "Complemento inexistente, inactivo o con otra moneda")
        funcionalidades.update(validar_funcionalidades(db, extra.funcionalidades or []))
        for recurso, incremento in (extra.cupos or {}).items():
            if limites[recurso] != 0:
                limites[recurso] += incremento * item.cantidad
        importe = Decimal(extra.precio) * item.cantidad
        if extra.tipo == "Servicio":
            servicios += importe
        else:
            recurrente += importe
        complementos.append({"id": extra.id, "nombre": extra.nombre, "tipo": extra.tipo,
                             "cantidad": item.cantidad, "precio_unitario": str(extra.precio),
                             "cupos": extra.cupos, "funcionalidades": extra.funcionalidades})
    if body.limites_acordados is not None:
        limites = body.limites_acordados.model_dump()
    precio = body.precio_acordado
    if precio is None:
        precio = recurrente * MESES[body.periodicidad]
    if body.es_prueba:
        precio = Decimal("0")
    return {
        "plan_nombre": plan.nmbr, "revision_plan": plan.revision, "moneda": moneda,
        "periodicidad": body.periodicidad, "precio_acordado": str(precio.quantize(Decimal("0.01"))),
        "referencia": body.referencia, "motivo": body.motivo, "dias_gracia": body.dias_gracia,
        "es_prueba": body.es_prueba, "limites": limites, "funcionalidades": sorted(funcionalidades),
        "complementos": complementos, "importe_servicios": str(servicios.quantize(Decimal("0.01"))),
        "politica_vencimiento": "Solo lectura; ingesta preservada",
    }


def validar_operacion(db, cliente_id, body, hoy):
    actual = ultimo_contrato(db, cliente_id, hoy)
    actual_id = actual.id_sscrpcn if actual else None
    if "suscripcion_actual_id" in body.model_fields_set and body.suscripcion_actual_id != actual_id:
        raise HTTPException(409, "La suscripción cambió. Revisa nuevamente la asignación")
    if body.fecha_vencimiento < body.fecha_inicio or body.fecha_vencimiento < hoy:
        raise HTTPException(422, "Revisa las fechas de vigencia")
    if body.es_prueba and (body.fecha_vencimiento - body.fecha_inicio).days > 30:
        raise HTTPException(422, "Una prueba no puede durar más de 30 días")
    operacion = body.operacion or ("Cambiar" if actual else "Crear")
    if operacion == "Crear" and actual and estado_contrato(db, actual, hoy) in {"Vigente", "En gracia", "Suspendida"}:
        raise HTTPException(409, "La empresa ya tiene una suscripción; usa cambiar o renovar")
    if operacion == "Renovar":
        if actual is None:
            raise HTTPException(409, "No hay una suscripción para renovar")
        inicio = max(hoy, actual.fch_vncmnt + timedelta(days=1))
        if body.fecha_inicio != inicio:
            raise HTTPException(422, f"La renovación debe comenzar el {inicio.isoformat()}")
    if operacion == "Cambiar" and actual is None:
        raise HTTPException(409, "No hay una suscripción para cambiar; usa crear")
    if body.fecha_inicio < hoy and body.operacion is not None:
        raise HTTPException(422, "Los cambios nuevos no pueden aplicarse con fecha retroactiva")
    pendiente = db.query(Suscripcion).filter(
        Suscripcion.id_clnt == cliente_id, Suscripcion.estd == "Programada",
        Suscripcion.fch_inc > hoy,
    ).first()
    if pendiente:
        raise HTTPException(409, "Ya existe un cambio programado. Cancélalo antes de programar otro")
    return actual, operacion


def exigir_operacion(db, cliente_id):
    import os

    from app.services.limites_plan import fecha_comercial

    hoy = fecha_comercial()
    contrato = ultimo_contrato(db, cliente_id, hoy)
    if contrato is None and os.getenv("PLAN_LIMITS_REQUIRE_SUBSCRIPTION", "true").lower() in {"false", "0", "no"}:
        if db.query(Suscripcion).filter(Suscripcion.id_clnt == cliente_id).first() is None:
            return  # Modo de migración explícito; deshabilitado por defecto.
    if estado_contrato(db, contrato, hoy) not in {"Vigente", "En gracia"}:
        raise HTTPException(409, "La empresa está en modo consulta: necesita una suscripción vigente para operar")
    if condiciones_de(db, contrato)["limites"] is None:
        raise HTTPException(409, "El contrato necesita límites configurados antes de operar")


def exigir_funcionalidad(db, cliente_id, codigo):
    from app.services.limites_plan import fecha_comercial

    exigir_operacion(db, cliente_id)
    contrato = ultimo_contrato(db, cliente_id, fecha_comercial())
    feature = db.get(FuncionalidadComercial, codigo)
    if feature is None or not feature.disponible or codigo not in condiciones_de(db, contrato)["funcionalidades"]:
        raise HTTPException(403, "La funcionalidad no está incluida o no se encuentra disponible")


def aplicar_programadas(db, hoy, cliente_id=None):
    """El worker consolida estados; la fecha ya gobierna los derechos en HTTP."""
    from app.models import Cliente
    from app.services.ingesta.usuario_sistema import resolver_id_usuario_sistema

    consulta = db.query(Suscripcion.id_clnt).filter(
        Suscripcion.estd == "Programada", Suscripcion.fch_inc <= hoy,
    )
    if cliente_id is not None:
        consulta = consulta.filter(Suscripcion.id_clnt == cliente_id)
    pendientes = consulta.all()
    total = 0
    for (cliente_id,) in pendientes:
        db.query(Cliente).filter(Cliente.id_clnt == cliente_id).with_for_update().one()
        programada = db.query(Suscripcion).filter(
            Suscripcion.id_clnt == cliente_id, Suscripcion.estd == "Programada", Suscripcion.fch_inc <= hoy,
        ).first()
        if programada is None:
            continue
        for anterior in db.query(Suscripcion).filter(
            Suscripcion.id_clnt == cliente_id, Suscripcion.estd.in_(["Activa", "Suspendida"]),
        ).all():
            anterior.estd = "Reemplazada"
        db.flush()
        programada.estd = "Activa"
        actor = {"sub": str(resolver_id_usuario_sistema(db))}
        auditar(db, actor, "activar_programada", "Suscripcion", despues={"cliente_id": cliente_id, "suscripcion_id": programada.id_sscrpcn})
        total += 1
    return total


def huella_solicitud(body):
    datos = body.model_dump(mode="json", exclude={"clave_idempotencia", "suscripcion_actual_id", "revision_plan"})
    return hashlib.sha256(json.dumps(datos, sort_keys=True).encode()).hexdigest()



def registrar_contrato(db, id_clnt, body, usuario, condiciones_fijadas=None):
    from app.services.limites_plan import fecha_comercial

    cliente = db.query(Cliente).filter(Cliente.id_clnt == id_clnt).with_for_update().first()
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if cliente.estd != "Activo":
        raise HTTPException(422, "Activa la empresa antes de contratar una suscripción")
    aplicar_programadas(db, fecha_comercial(), id_clnt)
    if body.clave_idempotencia:
        existente = db.query(Suscripcion).filter(Suscripcion.id_clnt == id_clnt,
                  Suscripcion.clave_idempotencia == body.clave_idempotencia).first()
        if existente:
            if (existente.condiciones or {}).get("huella_solicitud") != huella_solicitud(body):
                raise HTTPException(409, "La clave ya se utilizó con condiciones diferentes")
            return existente, False
    plan = db.query(PlanSuscripcion).filter(PlanSuscripcion.id_pln == body.plan_id).with_for_update().first()
    if plan is None or (plan.estd != "Activo" and condiciones_fijadas is None):
        raise HTTPException(status_code=422, detail="El plan no existe o no está activo")
    hoy = fecha_comercial()
    if condiciones_fijadas is None:
        condiciones = preparar_condiciones(db, body, plan)
    else:
        condiciones = deepcopy(condiciones_fijadas)
        validar_funcionalidades(db, condiciones["funcionalidades"])
    condiciones["huella_solicitud"] = huella_solicitud(body)
    # PUT sin clave también es idempotente si repite exactamente lo guardado.
    repetida = db.query(Suscripcion).filter(Suscripcion.id_clnt == id_clnt,
        Suscripcion.id_pln == plan.id_pln, Suscripcion.estd.in_(["Activa", "Programada"]),
        Suscripcion.fch_inc == body.fecha_inicio, Suscripcion.fch_vncmnt == body.fecha_vencimiento).first()
    if repetida and repetida.condiciones == condiciones:
        return repetida, False
    actual, operacion = validar_operacion(db, id_clnt, body, hoy)
    programada = body.fecha_inicio > hoy
    if not programada:
        anteriores = db.query(Suscripcion).filter(Suscripcion.id_clnt == id_clnt,
                        Suscripcion.estd.in_(["Activa", "Suspendida", "Programada"])).all()
        for anterior in anteriores:
            anterior.estd = "Reemplazada"
        db.flush()
    contrato = Suscripcion(
            id_clnt=id_clnt,
            id_pln=plan.id_pln,
            fch_inc=body.fecha_inicio,
            fch_vncmnt=body.fecha_vencimiento,
            estd="Programada" if programada else "Activa",
            condiciones=condiciones, clave_idempotencia=body.clave_idempotencia,
        )
    db.add(contrato)
    db.flush()
    auditar(db, usuario, "programar" if programada else operacion.lower(), "Suscripcion",
            {"cliente_id": id_clnt, "suscripcion_id": actual.id_sscrpcn if actual else None},
            {"cliente_id": id_clnt, "suscripcion_id": contrato.id_sscrpcn, "operacion": operacion,
             "fecha_inicio": str(body.fecha_inicio), "fecha_vencimiento": str(body.fecha_vencimiento), **condiciones})
    return contrato, True
