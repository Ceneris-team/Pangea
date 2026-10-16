"""Ampliaciones comerciales solicitadas y aceptadas por la propia empresa."""

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Cliente,
    FuncionalidadComercial,
    LimitePlan,
    LogAuditoria,
    PlanSuscripcion,
    SolicitudSuscripcion,
    Suscripcion,
    Usuario,
)
from app.routers.comercial import (
    LimitesGuardar,
    SuscripcionAsignar,
    _plan_dict,
    previsualizar_suscripcion,
)
from app.security.dependencies import get_current_user
from app.security.entorno import contexto
from app.services.contratos import (
    auditar,
    contrato_dict,
    registrar_contrato,
    ultimo_contrato,
    validar_funcionalidades,
)
from app.services.limites_plan import fecha_comercial

router = APIRouter(prefix="/solicitudes-suscripcion", tags=["Solicitudes de suscripción"])
ABIERTAS = {"Pendiente", "En evaluación", "Esperando aceptación", "Aceptada"}


class Solicitar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tipo: Literal["Cambiar plan", "Ampliar cupos", "Contratar módulo", "Renovar"]
    plan_id: int | None = None
    incrementos: LimitesGuardar = Field(default_factory=lambda: LimitesGuardar(ubicaciones=0, dispositivos=0, usuarios=0))
    funcionalidades: list[str] = Field(default_factory=list, max_length=50)
    descripcion: str = Field(min_length=10, max_length=2000)
    clave_idempotencia: str = Field(min_length=16, max_length=64)

    @field_validator("descripcion")
    @classmethod
    def texto(cls, valor):
        if len(valor.strip()) < 10:
            raise ValueError("Describe la necesidad con al menos diez caracteres")
        return valor.strip()


class Accion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    accion: Literal["Evaluar", "Rechazar", "Cancelar", "Reabrir", "Aceptar", "Pedir revisión", "Aplicar"]
    motivo: str = Field(min_length=3, max_length=300)

    @field_validator("motivo")
    @classmethod
    def texto(cls, valor):
        if len(valor.strip()) < 3:
            raise ValueError("Indica el motivo")
        return valor.strip()


class Proponer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    contrato: SuscripcionAsignar
    mensaje: str = Field(min_length=10, max_length=2000)
    valida_hasta: date
    inicio_al_activar: bool = True

    @field_validator("mensaje")
    @classmethod
    def texto(cls, valor):
        return Solicitar.texto(valor)


def acceso(db, usuario):
    if usuario.get("scope") == "global" and usuario.get("rol") in {"Administrador", "Administrador Comercial"}:
        return True, None
    usuario = contexto(db, usuario)
    if usuario.get("scope") == "por_cliente" and usuario.get("rol_empresa") == "Administrador":
        return False, usuario["cliente_id"]
    raise HTTPException(403, "Solo los administradores de empresa y la administración CENERIS pueden acceder")


def consulta(db, usuario):
    comercial, empresa = acceso(db, usuario)
    query = db.query(SolicitudSuscripcion)
    return query if comercial else query.filter(SolicitudSuscripcion.id_clnt == empresa)


def obtener(db, usuario, id_solicitud, bloquear=False):
    fila = consulta(db, usuario).filter(SolicitudSuscripcion.id == id_solicitud).first()
    if fila is None:
        raise HTTPException(404, "Solicitud no encontrada")
    if bloquear:
        # Mismo orden de bloqueos que la asignación directa y el worker.
        db.query(Cliente).filter(Cliente.id_clnt == fila.id_clnt).with_for_update().one()
        fila = db.query(SolicitudSuscripcion).filter(SolicitudSuscripcion.id == id_solicitud).populate_existing().with_for_update().one()
    return fila


def propuesta_vencida(propuesta):
    if not propuesta:
        return False
    hoy = fecha_comercial()
    return date.fromisoformat(propuesta["valida_hasta"]) < hoy or (
        not propuesta["inicio_al_activar"] and date.fromisoformat(propuesta["contrato"]["fecha_inicio"]) < hoy
    )


def serializar(db, fila):
    resultado = db.get(Suscripcion, fila.suscripcion_resultante_id) if fila.suscripcion_resultante_id else None
    return {
        "id": fila.id, "cliente_id": fila.id_clnt, "empresa": db.get(Cliente, fila.id_clnt).rzn_scl,
        "solicitante": db.get(Usuario, fila.solicitante_id).nmbr_cmplt, "estado": fila.estado,
        "solicitud": fila.solicitud, "propuesta": fila.propuesta, "revision": fila.revision,
        "propuesta_vencida": propuesta_vencida(fila.propuesta),
        "aceptante": db.get(Usuario, fila.aceptante_id).nmbr_cmplt if fila.aceptante_id else None,
        "aceptada_en": fila.aceptada_en, "creada_en": fila.creada_en, "actualizada_en": fila.actualizada_en,
        "resultado": contrato_dict(db, resultado, fecha_comercial()) if resultado else None,
    }


def registrar_evento(db, usuario, fila, accion, motivo, antes=None):
    fila.actualizada_en = datetime.now(timezone.utc)
    auditar(db, usuario, accion, "SolicitudSuscripcion", antes, {
        "cliente_id": fila.id_clnt, "solicitud_id": fila.id, "estado": fila.estado,
        "revision": fila.revision, "motivo": motivo, "propuesta": fila.propuesta,
        "suscripcion_id": fila.suscripcion_resultante_id,
    })


def contrato_sin_cambios(db, fila):
    actual = ultimo_contrato(db, fila.id_clnt, fecha_comercial())
    if ((actual.id_sscrpcn if actual else None) != fila.propuesta["suscripcion_base_id"]
            or (actual.estd if actual else None) != fila.propuesta["estado_base"]):
        raise HTTPException(409, "La suscripción de la empresa cambió. CENERIS debe enviar una nueva propuesta")


@router.get("/opciones")
def opciones(db: Session = Depends(get_db), usuario: dict = Depends(get_current_user)):
    acceso(db, usuario)
    limites = {limite.id_pln: limite for limite in db.query(LimitePlan).all()}
    return {
        "planes": [_plan_dict(p, limites[p.id_pln]) for p in db.query(PlanSuscripcion).filter(PlanSuscripcion.estd == "Activo").order_by(PlanSuscripcion.prc_mnsl)
                   if p.id_pln in limites],
        "funcionalidades": [{"codigo": f.codigo, "nombre": f.nombre} for f in db.query(FuncionalidadComercial).filter(FuncionalidadComercial.disponible == 1).order_by(FuncionalidadComercial.nombre)],
    }


@router.get("/resumen")
def resumen(db: Session = Depends(get_db), usuario: dict = Depends(get_current_user)):
    comercial, _ = acceso(db, usuario)
    filas = consulta(db, usuario).filter(SolicitudSuscripcion.estado.in_(ABIERTAS)).all()
    return {"total": sum((fila.estado in {"Pendiente", "En evaluación", "Aceptada"} or propuesta_vencida(fila.propuesta))
                         if comercial else fila.estado == "Esperando aceptación" for fila in filas)}


@router.get("")
def listar(db: Session = Depends(get_db), usuario: dict = Depends(get_current_user)):
    filas = consulta(db, usuario).order_by(SolicitudSuscripcion.actualizada_en.desc(), SolicitudSuscripcion.id.desc()).limit(200).all()
    return [serializar(db, fila) for fila in filas]


@router.post("", status_code=201)
def solicitar(body: Solicitar, db: Session = Depends(get_db), usuario: dict = Depends(get_current_user)):
    comercial, empresa = acceso(db, usuario)
    if comercial:
        raise HTTPException(403, "La solicitud debe presentarla el administrador de la empresa")
    db.query(Cliente).filter(Cliente.id_clnt == empresa).with_for_update().one()
    datos = body.model_dump(mode="json", exclude={"clave_idempotencia"})
    existente = db.query(SolicitudSuscripcion).filter(SolicitudSuscripcion.id_clnt == empresa,
        SolicitudSuscripcion.clave_idempotencia == body.clave_idempotencia).first()
    if existente:
        if existente.solicitud != datos:
            raise HTTPException(409, "Esta clave ya se usó con otra solicitud")
        return serializar(db, existente)
    if db.query(SolicitudSuscripcion).filter(SolicitudSuscripcion.id_clnt == empresa, SolicitudSuscripcion.estado.in_(ABIERTAS)).first():
        raise HTTPException(409, "Tu empresa ya tiene una solicitud abierta. Revísala antes de crear otra")
    if body.plan_id is not None:
        plan = db.get(PlanSuscripcion, body.plan_id)
        if plan is None or plan.estd != "Activo" or db.query(LimitePlan).filter(LimitePlan.id_pln == body.plan_id).first() is None:
            raise HTTPException(422, "Plan no disponible")
    if body.tipo == "Cambiar plan" and body.plan_id is None:
        raise HTTPException(422, "Selecciona el plan de interés")
    if body.tipo == "Ampliar cupos" and not any(body.incrementos.model_dump().values()):
        raise HTTPException(422, "Indica al menos un cupo adicional")
    validar_funcionalidades(db, body.funcionalidades)
    if body.tipo == "Contratar módulo" and not body.funcionalidades:
        raise HTTPException(422, "Selecciona una funcionalidad disponible")
    fila = SolicitudSuscripcion(id_clnt=empresa, solicitante_id=int(usuario["sub"]), solicitud=datos,
                               clave_idempotencia=body.clave_idempotencia, estado="Pendiente", revision=0)
    db.add(fila)
    db.flush()
    registrar_evento(db, usuario, fila, "solicitar", body.descripcion, {"solicitud": datos})
    db.commit()
    return serializar(db, fila)


@router.get("/{id_solicitud}")
def detalle(id_solicitud: int, db: Session = Depends(get_db), usuario: dict = Depends(get_current_user)):
    fila = obtener(db, usuario, id_solicitud)
    eventos = db.query(LogAuditoria).filter(LogAuditoria.entdd == "SolicitudSuscripcion",
        LogAuditoria.vlrs_nvs["solicitud_id"].as_integer() == fila.id).order_by(LogAuditoria.id_evnt.desc()).all()
    return {**serializar(db, fila), "eventos": [{"id": e.id_evnt, "accion": e.accn, "fecha": e.fch_evnt,
        "actor": db.get(Usuario, e.id_usr).nmbr_cmplt, "datos": e.vlrs_nvs} for e in eventos]}


@router.post("/{id_solicitud}/propuesta")
def proponer(id_solicitud: int, body: Proponer, db: Session = Depends(get_db), usuario: dict = Depends(get_current_user)):
    if not acceso(db, usuario)[0]:
        raise HTTPException(403, "Solo CENERIS puede enviar una propuesta")
    fila = obtener(db, usuario, id_solicitud, True)
    if body.revision != fila.revision or fila.estado not in {"Pendiente", "En evaluación", "Esperando aceptación"}:
        raise HTTPException(409, "La solicitud cambió. Actualiza antes de enviar la propuesta")
    hoy = fecha_comercial()
    if not hoy <= body.valida_hasta <= hoy + timedelta(days=30):
        raise HTTPException(422, "La propuesta debe vencer dentro de los próximos 30 días")
    if body.contrato.operacion is None or "suscripcion_actual_id" not in body.contrato.model_fields_set or body.contrato.revision_plan is None:
        raise HTTPException(422, "Revisa primero las condiciones y la suscripción vigente")
    db.query(PlanSuscripcion).filter(PlanSuscripcion.id_pln == body.contrato.plan_id).populate_existing().with_for_update().first()
    preview = previsualizar_suscripcion(fila.id_clnt, body.contrato, db, usuario)
    actual = ultimo_contrato(db, fila.id_clnt, hoy)
    antes = {"estado": fila.estado, "revision": fila.revision, "propuesta": fila.propuesta}
    fila.propuesta = {
        "condiciones": preview["condiciones"], "contrato": body.contrato.model_dump(mode="json", exclude={"clave_idempotencia"}),
        "suscripcion_base_id": preview["suscripcion_actual_id"], "inicio_al_activar": body.inicio_al_activar,
        "estado_base": actual.estd if actual else None,
        "duracion_dias": (body.contrato.fecha_vencimiento - body.contrato.fecha_inicio).days + 1,
        "valida_hasta": str(body.valida_hasta), "mensaje": body.mensaje,
        "advertencia": preview["advertencia"], "recursos_excedidos": preview["recursos_excedidos"],
    }
    fila.revision += 1
    fila.estado = "Esperando aceptación"
    fila.aceptante_id = fila.aceptada_en = None
    registrar_evento(db, usuario, fila, "proponer", body.mensaje, antes)
    db.commit()
    return serializar(db, fila)


@router.post("/{id_solicitud}/accion")
def actuar(id_solicitud: int, body: Accion, db: Session = Depends(get_db), usuario: dict = Depends(get_current_user)):
    comercial, _ = acceso(db, usuario)
    fila = obtener(db, usuario, id_solicitud, True)
    if body.accion == "Aplicar" and comercial and fila.estado == "Aplicada":
        return serializar(db, fila)  # Reintento de una activación ya completada.
    if fila.revision != body.revision or fila.estado not in ABIERTAS:
        raise HTTPException(409, "La solicitud cambió o ya está cerrada. Actualiza la vista")
    permitidas = {"Evaluar", "Rechazar", "Cancelar", "Reabrir", "Aplicar"} if comercial else {"Aceptar", "Rechazar", "Cancelar", "Pedir revisión"}
    if body.accion not in permitidas:
        raise HTTPException(403, "Tu rol no permite esta acción")
    antes = {"estado": fila.estado, "revision": fila.revision, "propuesta": fila.propuesta}
    if body.accion in {"Aceptar", "Aplicar"}:
        esperado = "Aceptada" if comercial else "Esperando aceptación"
        if fila.estado != esperado or not fila.propuesta:
            raise HTTPException(409, "La propuesta todavía no está lista para esta acción")
        if propuesta_vencida(fila.propuesta):
            raise HTTPException(409, "La propuesta venció. Solicita una nueva revisión")
        contrato_sin_cambios(db, fila)
        if body.accion == "Aceptar":
            fila.estado = "Aceptada"
            fila.aceptante_id = int(usuario["sub"])
            fila.aceptada_en = datetime.now(timezone.utc)
        else:
            propuesta = fila.propuesta
            contrato = SuscripcionAsignar.model_validate(propuesta["contrato"])
            if propuesta["inicio_al_activar"]:
                hoy = fecha_comercial()
                actual = ultimo_contrato(db, fila.id_clnt, hoy)
                inicio = max(hoy, actual.fch_vncmnt + timedelta(days=1)) if contrato.operacion == "Renovar" and actual else hoy
                contrato = contrato.model_copy(update={"fecha_inicio": inicio, "fecha_vencimiento": inicio + timedelta(days=propuesta["duracion_dias"] - 1)})
            contrato.clave_idempotencia = f"solicitud-{fila.id}-revision-{fila.revision}"
            resultado, _ = registrar_contrato(db, fila.id_clnt, contrato, usuario, condiciones_fijadas=propuesta["condiciones"])
            fila.suscripcion_resultante_id = resultado.id_sscrpcn
            fila.estado = "Aplicada"
    elif body.accion == "Evaluar":
        if fila.estado != "Pendiente":
            raise HTTPException(409, "La solicitud ya está en revisión")
        fila.estado = "En evaluación"
    elif body.accion in {"Reabrir", "Pedir revisión"}:
        if fila.estado not in {"Esperando aceptación", "Aceptada"}:
            raise HTTPException(409, "No hay una propuesta para revisar")
        fila.estado = "En evaluación"
        fila.aceptante_id = fila.aceptada_en = None
    elif body.accion == "Rechazar":
        if not comercial and fila.estado != "Esperando aceptación":
            raise HTTPException(409, "No hay una propuesta para rechazar")
        fila.estado = "Rechazada"
    elif body.accion == "Cancelar":
        fila.estado = "Cancelada"
    fila.revision += 1
    registrar_evento(db, usuario, fila, body.accion.lower(), body.motivo, antes)
    db.commit()
    return serializar(db, fila)
