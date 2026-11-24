"""Consulta y registro de definiciones calculadas, sin ejecutar fórmulas."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Cliente, ParametroCalculado, Sede, Ubicacion
from app.security.entorno import contexto, filtrar_sedes, permiso_del_entorno, puede_operar
from app.security.permisos import EDICION, LECTURA, require_permiso, tiene_permiso
from app.services.parametros_calculados import (
    describir_formula,
    origenes_por_sede,
    preparar_formula,
)

router = APIRouter(prefix="/parametros-calculados", tags=["Parámetros calculados"])


def exigir_tecnico(db, usuario):
    if not puede_operar(db, usuario):
        raise HTTPException(
            403,
            "Solo los usuarios técnicos y administradores autorizados pueden consultar estas definiciones",
        )


def consulta(db, usuario):
    query = (
        db.query(ParametroCalculado, Sede.nmbr, Cliente.rzn_scl)
        .join(Sede, Sede.id_sd == ParametroCalculado.id_sd)
        .join(Cliente, Cliente.id_clnt == Sede.id_clnt)
    )
    # Las definiciones se comparten por sede; el proyecto acota a su sede.
    return filtrar_sedes(query, ParametroCalculado.id_sd, db, usuario)


def sedes_visibles(db, usuario):
    return (
        filtrar_sedes(db.query(Sede), Sede.id_sd, db, usuario).order_by(Sede.nmbr, Sede.id_sd).all()
    )


def puede_crear(db, usuario):
    permiso = permiso_del_entorno(db, usuario, "Ingesta", EDICION)
    if permiso is None:
        permiso = tiene_permiso(db, int(usuario["sub"]), usuario.get("sede_id"), "Ingesta", EDICION)
    return bool(permiso and (usuario.get("cliente_id") or usuario.get("sede_id")))


def serializar(fila, origenes, detalle=False):
    p, sede, empresa = fila
    formula = describir_formula(p.frml, origenes)
    resultado = {
        "id_prm_clc": p.id_prm_clc,
        "nmbr": p.nmbr,
        "frml": formula["frml"],
        "undd": p.undd,
        "dscrpcn": p.dscrpcn,
        "estd": p.estd,
        "empresa_nombre": empresa,
        "sede_nombre": sede,
        "ambito": f"Compartido por los proyectos de {sede}",
    }
    if detalle:
        resultado["referencias"] = formula["referencias"]
    return resultado


@router.get("")
def listar_parametros_calculados(
    q: str = Query(default="", max_length=200),
    estado: Literal["Activo", "Inactivo"] | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    exigir_tecnico(db, usuario)
    ambito = contexto(db, usuario)
    query = consulta(db, ambito)
    nombre = q.strip().lower()
    normalizado = func.translate(func.lower(ParametroCalculado.nmbr), "ÁÉÍÓÚÜÑ", "áéíóúüñ")
    if nombre:
        query = query.filter(normalizado.contains(nombre, autoescape=True))
    if estado:
        query = query.filter(ParametroCalculado.estd == estado)
    total = query.count()
    filas = (
        query.order_by(normalizado, ParametroCalculado.id_prm_clc)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )
    origenes = origenes_por_sede(db, list({fila[0].id_sd for fila in filas}))
    empresa_id = ambito.get("cliente_id")
    if empresa_id is None and ambito.get("sede_id"):
        sede = db.get(Sede, ambito["sede_id"])
        empresa_id = sede.id_clnt if sede else None
    empresa = db.get(Cliente, empresa_id) if empresa_id is not None else None
    proyecto = db.get(Ubicacion, ambito["proyecto_id"]) if ambito.get("proyecto_id") else None
    return {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "contexto": {
            "empresa": empresa.rzn_scl if empresa else None,
            "proyecto": proyecto.nmbr if proyecto else None,
        },
        "permisos": {"crear": puede_crear(db, ambito) and bool(sedes_visibles(db, ambito))},
        "items": [serializar(fila, origenes[fila[0].id_sd]) for fila in filas],
    }


@router.get("/opciones-creacion")
def opciones_creacion(
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", EDICION)),
):
    exigir_tecnico(db, usuario)
    ambito = contexto(db, usuario)
    if not puede_crear(db, ambito):
        raise HTTPException(403, "Selecciona una empresa para registrar una definición")
    sedes = sedes_visibles(db, ambito)
    origenes = origenes_por_sede(db, [s.id_sd for s in sedes])
    return {
        "sedes": [
            {
                "id_sd": s.id_sd,
                "nombre": s.nmbr,
                "origenes": [
                    {"id_prmtr": p.id_prmtr, "nombre": p.nmbr, "unidad": p.undd}
                    for p in origenes[s.id_sd]
                    if p.estd == "Activo"
                ],
            }
            for s in sedes
        ]
    }


@router.get("/{parametro_id}")
def detalle_parametro_calculado(
    parametro_id: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    exigir_tecnico(db, usuario)
    fila = consulta(db, usuario).filter(ParametroCalculado.id_prm_clc == parametro_id).first()
    if fila is None:
        raise HTTPException(404, "Parámetro calculado no disponible en este contexto")
    sede = fila[0].id_sd
    return serializar(fila, origenes_por_sede(db, [sede])[sede], detalle=True)


class NuevaDefinicion(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    id_sd: int = Field(gt=0)
    nmbr: str = Field(min_length=1, max_length=100)
    frml: str = Field(min_length=1, max_length=2000)
    undd: str = Field(min_length=1, max_length=30)
    dscrpcn: str | None = Field(default=None, max_length=300)
    estd: Literal["Activo", "Inactivo"] = "Activo"


@router.post("", status_code=201)
def crear_parametro_calculado(
    body: NuevaDefinicion,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", EDICION)),
):
    exigir_tecnico(db, usuario)
    ambito = contexto(db, usuario)
    if not puede_crear(db, ambito):
        raise HTTPException(403, "Selecciona una empresa para registrar una definición")
    sede = next((s for s in sedes_visibles(db, ambito) if s.id_sd == body.id_sd), None)
    if sede is None:
        raise HTTPException(403, "El ámbito elegido no está disponible en este contexto")
    origenes = origenes_por_sede(db, [sede.id_sd])[sede.id_sd]
    try:
        formula = preparar_formula(body.frml, origenes)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    existente = (
        db.query(ParametroCalculado.id_prm_clc)
        .filter(
            ParametroCalculado.id_sd == sede.id_sd,
            func.translate(func.lower(ParametroCalculado.nmbr), "ÁÉÍÓÚÜÑ", "áéíóúüñ")
            == body.nmbr.lower(),
        )
        .first()
    )
    if existente:
        raise HTTPException(
            409, "Ya existe un parámetro calculado con ese nombre en el ámbito elegido"
        )
    p = ParametroCalculado(**body.model_dump(exclude={"frml"}), frml=formula)
    db.add(p)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409, "Ya existe un parámetro calculado con ese nombre en el ámbito elegido"
        ) from exc
    db.refresh(p)
    empresa = db.get(Cliente, sede.id_clnt)
    return serializar((p, sede.nmbr, empresa.rzn_scl), origenes, detalle=True)
