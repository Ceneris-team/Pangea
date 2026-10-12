"""Consumo y cupos de suscripción por cliente.

La ausencia de suscripción conserva el comportamiento de clientes existentes
durante la migración. Una vez asignado un plan, sus cupos son obligatorios.
"""

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    Cliente,
    Dispositivo,
    LimitePlan,
    PermisoUbicacion,
    PermisoUsuarioSede,
    PlanSuscripcion,
    Rol,
    Sede,
    Suscripcion,
    Ubicacion,
    Usuario,
)


def fecha_comercial() -> date:
    return datetime.now(ZoneInfo("America/Lima")).date()


def suscripcion_vigente(db: Session, id_clnt: int) -> Suscripcion | None:
    hoy = fecha_comercial()
    return (
        db.query(Suscripcion)
        .filter(
            Suscripcion.id_clnt == id_clnt,
            Suscripcion.estd == "Activa",
            Suscripcion.fch_inc <= hoy,
            Suscripcion.fch_vncmnt >= hoy,
        )
        .order_by(Suscripcion.fch_inc.desc(), Suscripcion.id_sscrpcn.desc())
        .first()
    )


def consumo_cliente(db: Session, id_clnt: int) -> dict[str, int]:
    ubicaciones = (
        db.query(Ubicacion)
        .join(Sede, Sede.id_sd == Ubicacion.id_sd)
        .filter(Sede.id_clnt == id_clnt, Ubicacion.estd == "Activa")
        .count()
    )
    dispositivos = (
        db.query(Dispositivo)
        .join(Ubicacion, Ubicacion.id_ubccn == Dispositivo.id_ubccn)
        .join(Sede, Sede.id_sd == Ubicacion.id_sd)
        .filter(Sede.id_clnt == id_clnt, Dispositivo.estd == "Activo")
        .count()
    )
    por_sede = (
        select(PermisoUsuarioSede.id_usr)
        .join(Sede, Sede.id_sd == PermisoUsuarioSede.id_sd)
        .where(Sede.id_clnt == id_clnt)
    )
    por_ubicacion = (
        select(PermisoUbicacion.id_usr)
        .join(Ubicacion, Ubicacion.id_ubccn == PermisoUbicacion.id_ubccn)
        .join(Sede, Sede.id_sd == Ubicacion.id_sd)
        .where(Sede.id_clnt == id_clnt)
    )
    usuarios = (
        db.query(Usuario)
        .join(Rol, Rol.id_rl == Usuario.id_rl)
        .filter(
            Rol.nmbr == "Cliente Final",
            Usuario.estd == "Activo",
            or_(Usuario.id_usr.in_(por_sede), Usuario.id_usr.in_(por_ubicacion)),
        )
        .count()
    )
    return {"ubicaciones": ubicaciones, "dispositivos": dispositivos, "usuarios": usuarios}


def resumen_cliente(db: Session, cliente: Cliente) -> dict:
    suscripcion = suscripcion_vigente(db, cliente.id_clnt)
    if suscripcion is None:
        # La vista comercial también debe identificar una suscripción vencida
        # o todavía no iniciada; los controles de cupo usan solo la vigente.
        suscripcion = (
            db.query(Suscripcion)
            .filter(Suscripcion.id_clnt == cliente.id_clnt, Suscripcion.estd == "Activa")
            .order_by(Suscripcion.fch_inc.desc(), Suscripcion.id_sscrpcn.desc())
            .first()
        )
    hoy = fecha_comercial()
    estado_suscripcion = (
        "Sin suscripción" if suscripcion is None else
        "Programada" if suscripcion.fch_inc > hoy else
        "Vencida" if suscripcion.fch_vncmnt < hoy else "Vigente"
    )
    plan = db.get(PlanSuscripcion, suscripcion.id_pln) if suscripcion else None
    limites = (
        db.query(LimitePlan).filter(LimitePlan.id_pln == plan.id_pln).first() if plan else None
    )
    return {
        "id_clnt": cliente.id_clnt,
        "nombre": cliente.rzn_scl,
        "ruc": cliente.rc,
        "suscripcion_id": suscripcion.id_sscrpcn if suscripcion else None,
        "plan_id": plan.id_pln if plan else None,
        "plan_nombre": plan.nmbr if plan else None,
        "estado_suscripcion": estado_suscripcion,
        "fecha_inicio": suscripcion.fch_inc if suscripcion else None,
        "fecha_vencimiento": suscripcion.fch_vncmnt if suscripcion else None,
        "consumo": consumo_cliente(db, cliente.id_clnt),
        "limites": {
            "ubicaciones": limites.mx_ubccns,
            "dispositivos": limites.mx_dspstvs,
            "usuarios": limites.mx_usrs,
        }
        if limites
        else None,
    }


def comprobar_cupo(db: Session, id_clnt: int, recurso: str) -> None:
    """Bloquea el cliente para serializar altas que compiten por el mismo cupo.

    Debe invocarse en la misma transacción que el INSERT o reactivación.
    """
    db.query(Cliente).filter(Cliente.id_clnt == id_clnt).with_for_update().one()
    suscripcion = suscripcion_vigente(db, id_clnt)
    if suscripcion is None:
        tenia_suscripcion = db.query(Suscripcion.id_sscrpcn).filter(Suscripcion.id_clnt == id_clnt).first()
        exigir = os.getenv("PLAN_LIMITS_REQUIRE_SUBSCRIPTION", "false").lower() in {"1", "true", "yes"}
        if tenia_suscripcion or exigir:
            raise HTTPException(status_code=409, detail="Este cliente no tiene un plan vigente")
        return  # Clientes históricos aún no migrados a un plan.
    limite = db.query(LimitePlan).filter(LimitePlan.id_pln == suscripcion.id_pln).first()
    if limite is None:
        raise HTTPException(status_code=409, detail="El plan vigente no tiene límites configurados")
    campo = {"ubicaciones": "mx_ubccns", "dispositivos": "mx_dspstvs", "usuarios": "mx_usrs"}[recurso]
    maximo = getattr(limite, campo)
    if maximo and consumo_cliente(db, id_clnt)[recurso] >= maximo:
        raise HTTPException(
            status_code=409,
            detail="Has alcanzado el límite de tu plan. Contacta al administrador para ampliar tu suscripción",
        )
