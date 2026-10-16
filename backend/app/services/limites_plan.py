"""Consumo y derechos contratados por empresa."""

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    Cliente,
    Dispositivo,
    PermisoUbicacion,
    PermisoUsuarioSede,
    Rol,
    Sede,
    Suscripcion,
    Ubicacion,
    Usuario,
    UsuarioCliente,
)
from app.services.contratos import condiciones_de, estado_contrato, ultimo_contrato


def fecha_comercial() -> date:
    return datetime.now(ZoneInfo("America/Lima")).date()


def suscripcion_vigente(db: Session, id_clnt: int) -> Suscripcion | None:
    hoy = fecha_comercial()
    contrato = ultimo_contrato(db, id_clnt, hoy)
    return contrato if estado_contrato(db, contrato, hoy) in {"Vigente", "En gracia"} else None


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
    miembros_empresa = (
        select(UsuarioCliente.id_usr)
        .where(UsuarioCliente.id_clnt == id_clnt, UsuarioCliente.estd == "Activo")
    )
    usuarios = (
        db.query(Usuario)
        .join(Rol, Rol.id_rl == Usuario.id_rl)
        .filter(
            Usuario.estd == "Activo",
            or_(
                Usuario.id_usr.in_(miembros_empresa),
                (
                    (Rol.nmbr == "Cliente Final")
                    & or_(Usuario.id_usr.in_(por_sede), Usuario.id_usr.in_(por_ubicacion))
                ),
            ),
        )
        .count()
    )
    return {"ubicaciones": ubicaciones, "dispositivos": dispositivos, "usuarios": usuarios}


def resumen_cliente(db: Session, cliente: Cliente) -> dict:
    hoy = fecha_comercial()
    suscripcion = ultimo_contrato(db, cliente.id_clnt, hoy)
    programada = db.query(Suscripcion).filter(
        Suscripcion.id_clnt == cliente.id_clnt, Suscripcion.estd == "Programada", Suscripcion.fch_inc > hoy,
    ).first()
    condiciones = condiciones_de(db, suscripcion) if suscripcion else None
    return {
        "id_clnt": cliente.id_clnt,
        "nombre": cliente.rzn_scl,
        "ruc": cliente.rc,
        "suscripcion_id": suscripcion.id_sscrpcn if suscripcion else None,
        "plan_id": suscripcion.id_pln if suscripcion else None,
        "plan_nombre": condiciones["plan_nombre"] if condiciones else None,
        "estado_suscripcion": estado_contrato(db, suscripcion, hoy),
        "fecha_inicio": suscripcion.fch_inc if suscripcion else None,
        "fecha_vencimiento": suscripcion.fch_vncmnt if suscripcion else None,
        "consumo": consumo_cliente(db, cliente.id_clnt),
        "limites": condiciones["limites"] if condiciones else None,
        "condiciones": condiciones,
        "programada": {"id": programada.id_sscrpcn, "fecha_inicio": programada.fch_inc,
                       "fecha_vencimiento": programada.fch_vncmnt, "condiciones": condiciones_de(db, programada)} if programada else None,
        "aviso_vencimiento": ((suscripcion.fch_vncmnt - hoy).days <= 30) if suscripcion else False,
    }


def comprobar_cupo(db: Session, id_clnt: int, recurso: str) -> None:
    """Bloquea el cliente para serializar altas que compiten por el mismo cupo.

    Debe invocarse en la misma transacción que el INSERT o reactivación.
    """
    db.query(Cliente).filter(Cliente.id_clnt == id_clnt).with_for_update().one()
    suscripcion = suscripcion_vigente(db, id_clnt)
    if suscripcion is None:
        tenia_suscripcion = db.query(Suscripcion.id_sscrpcn).filter(Suscripcion.id_clnt == id_clnt).first()
        exigir = os.getenv("PLAN_LIMITS_REQUIRE_SUBSCRIPTION", "true").lower() in {"1", "true", "yes"}
        if tenia_suscripcion or exigir:
            raise HTTPException(status_code=409, detail="Este cliente no tiene un plan vigente")
        return  # Clientes históricos aún no migrados a un plan.
    limites = condiciones_de(db, suscripcion)["limites"]
    if limites is None:
        raise HTTPException(status_code=409, detail="El plan vigente no tiene límites configurados")
    maximo = limites[recurso]
    if maximo and consumo_cliente(db, id_clnt)[recurso] >= maximo:
        raise HTTPException(
            status_code=409,
            detail="Has alcanzado el límite de tu plan. Contacta al administrador para ampliar tu suscripción",
        )
