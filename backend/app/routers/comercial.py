"""Gestión de planes, límites y asignación de suscripciones."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Cliente, LimitePlan, PermisoUbicacion, PlanSuscripcion, Sede, Suscripcion, Ubicacion
from app.security.dependencies import get_current_user
from app.security.permisos import EDICION, LECTURA, require_permiso
from app.services.limites_plan import fecha_comercial, resumen_cliente

router = APIRouter(prefix="/comercial", tags=["Comercial"])


class PlanCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=300)
    precio_mensual: Decimal = Field(ge=0, decimal_places=2, max_digits=12)

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("El nombre es obligatorio")
        return valor


class LimitesGuardar(BaseModel):
    ubicaciones: int = Field(ge=0)
    dispositivos: int = Field(ge=0)
    usuarios: int = Field(ge=0)


class SuscripcionAsignar(BaseModel):
    plan_id: int
    fecha_inicio: date
    fecha_vencimiento: date


def _solo_comercial(usuario: dict) -> None:
    if usuario.get("rol") != "Administrador Comercial":
        raise HTTPException(status_code=403, detail="Solo el Administrador Comercial puede gestionar planes")


def _plan_dict(plan: PlanSuscripcion, limites: LimitePlan | None) -> dict:
    return {
        "id_pln": plan.id_pln,
        "nombre": plan.nmbr,
        "descripcion": plan.dscrpcn,
        "precio_mensual": str(plan.prc_mnsl),
        "estado": plan.estd,
        "limites": {
            "ubicaciones": limites.mx_ubccns,
            "dispositivos": limites.mx_dspstvs,
            "usuarios": limites.mx_usrs,
        }
        if limites
        else None,
    }


@router.get("/planes")
def listar_planes(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("Comercial", LECTURA)),
):
    planes = db.query(PlanSuscripcion).order_by(PlanSuscripcion.prc_mnsl, PlanSuscripcion.id_pln).all()
    limites = {fila.id_pln: fila for fila in db.query(LimitePlan).all()}
    return [_plan_dict(plan, limites.get(plan.id_pln)) for plan in planes]


@router.post("/planes", status_code=201)
def crear_plan(
    body: PlanCrear,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Comercial", EDICION)),
):
    _solo_comercial(usuario)
    if db.query(PlanSuscripcion).filter(func.lower(PlanSuscripcion.nmbr) == body.nombre.lower()).first():
        raise HTTPException(status_code=409, detail="Ya existe un plan con ese nombre")
    plan = PlanSuscripcion(nmbr=body.nombre, dscrpcn=body.descripcion, prc_mnsl=body.precio_mensual)
    db.add(plan)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe un plan con ese nombre") from None
    db.refresh(plan)
    return {"mensaje": "Plan de suscripción creado correctamente", "plan": _plan_dict(plan, None)}


@router.put("/planes/{id_pln}/limites")
def guardar_limites(
    id_pln: int,
    body: LimitesGuardar,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Comercial", EDICION)),
):
    _solo_comercial(usuario)
    plan = db.get(PlanSuscripcion, id_pln)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    limites = db.query(LimitePlan).filter(LimitePlan.id_pln == id_pln).first()
    nuevo = limites is None
    if nuevo:
        limites = LimitePlan(id_pln=id_pln, mx_sds=0)
        db.add(limites)
    limites.mx_ubccns = body.ubicaciones
    limites.mx_dspstvs = body.dispositivos
    limites.mx_usrs = body.usuarios
    db.commit()
    return {
        "mensaje": "Niveles y límites configurados correctamente" if nuevo else "Límites actualizados correctamente",
        "plan": _plan_dict(plan, limites),
    }


@router.get("/clientes")
def listar_clientes(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("Comercial", LECTURA)),
):
    return [resumen_cliente(db, cliente) for cliente in db.query(Cliente).order_by(Cliente.rzn_scl).all()]


@router.get("/mi-plan")
def mi_plan(
    db: Session = Depends(get_db),
    usuario: dict = Depends(get_current_user),
):
    if usuario.get("rol") != "Cliente Final":
        raise HTTPException(status_code=403, detail="Solo el Cliente Final puede consultar su plan")
    sede_id = usuario.get("sede_id")
    sede = db.get(Sede, sede_id) if sede_id is not None else None
    if sede is None:
        raise HTTPException(status_code=404, detail="No hay un cliente asociado a tu cuenta")
    cliente = db.get(Cliente, sede.id_clnt)
    resumen = resumen_cliente(db, cliente)
    resumen["ubicaciones_visibles"] = (
        db.query(Ubicacion)
        .join(Sede, Sede.id_sd == Ubicacion.id_sd)
        .join(PermisoUbicacion, PermisoUbicacion.id_ubccn == Ubicacion.id_ubccn)
        .filter(
            Sede.id_clnt == cliente.id_clnt,
            Ubicacion.estd == "Activa",
            PermisoUbicacion.id_usr == int(usuario["sub"]),
        )
        .count()
    )
    return resumen


@router.put("/clientes/{id_clnt}/suscripcion")
def asignar_suscripcion(
    id_clnt: int,
    body: SuscripcionAsignar,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Comercial", EDICION)),
):
    _solo_comercial(usuario)
    cliente = db.query(Cliente).filter(Cliente.id_clnt == id_clnt).with_for_update().first()
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    plan = db.get(PlanSuscripcion, body.plan_id)
    if plan is None or plan.estd != "Activo":
        raise HTTPException(status_code=422, detail="El plan no existe o no está activo")
    if db.query(LimitePlan).filter(LimitePlan.id_pln == plan.id_pln).first() is None:
        raise HTTPException(status_code=409, detail="Configura los límites antes de asignar el plan")
    if body.fecha_vencimiento < body.fecha_inicio:
        raise HTTPException(status_code=422, detail="El vencimiento debe ser posterior al inicio")
    if body.fecha_inicio > fecha_comercial() or body.fecha_vencimiento < fecha_comercial():
        raise HTTPException(status_code=422, detail="La suscripción debe incluir la fecha actual")
    anteriores = db.query(Suscripcion).filter(Suscripcion.id_clnt == id_clnt, Suscripcion.estd == "Activa").all()
    for anterior in anteriores:
        anterior.estd = "Reemplazada"
    db.add(
        Suscripcion(
            id_clnt=id_clnt,
            id_pln=plan.id_pln,
            fch_inc=body.fecha_inicio,
            fch_vncmnt=body.fecha_vencimiento,
            estd="Activa",
        )
    )
    db.commit()
    return {"mensaje": "Suscripción asignada correctamente", "cliente": resumen_cliente(db, cliente)}
