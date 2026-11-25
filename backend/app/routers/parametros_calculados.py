"""Definiciones calculadas, validacion dimensional y seguimiento historico."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Cliente,
    ConfiguracionCalculo,
    DependenciaCalculo,
    ParametroCalculado,
    ResultadoCalculo,
    Sede,
    TrabajoCalculo,
    Ubicacion,
)
from app.security.entorno import contexto, filtrar_sedes, permiso_del_entorno, puede_operar
from app.security.permisos import EDICION, LECTURA, require_permiso, tiene_permiso
from app.security.ubicaciones_permitidas import ubicaciones_permitidas
from app.services.motor_calculos import configuracion, encolar_historico
from app.services.parametros_calculados import (
    describir_formula,
    todos_origenes,
    validar_definicion,
)
from app.services.unidades_calculo import CATALOGO

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
        "id_sd": p.id_sd,
        "nmbr": p.nmbr,
        "frml": formula["frml"],
        "undd": p.undd,
        "dscrpcn": p.dscrpcn,
        "estd": p.estd,
        "validada": p.validada,
        "creada_en": p.creada_en,
        "id_usr_creador": p.id_usr_creador,
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
    origenes = todos_origenes(db, list({fila[0].id_sd for fila in filas}))
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
    origenes = todos_origenes(db, [s.id_sd for s in sedes])
    return {
        "unidades": sorted(CATALOGO),
        "sedes": [
            {
                "id_sd": s.id_sd,
                "nombre": s.nmbr,
                "configuracion": configuracion(db, s.id_sd),
                "origenes": [
                    {
                        "id_prmtr": (
                            -p.id_prm_clc if isinstance(p, ParametroCalculado) else p.id_prmtr
                        ),
                        "nombre": p.nmbr,
                        "unidad": p.undd,
                        "tipo": "calculado" if isinstance(p, ParametroCalculado) else "telemetria",
                    }
                    for p in origenes[s.id_sd]
                    if p.estd == "Activo"
                ],
            }
            for s in sedes
        ],
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
    resultado = serializar(fila, todos_origenes(db, [sede])[sede], detalle=True)
    resultado["configuracion"] = configuracion(db, sede)
    puntos = ubicaciones_permitidas(db, usuario)
    trabajos = (
        db.query(TrabajoCalculo)
        .filter(
            TrabajoCalculo.id_sd == sede,
            (TrabajoCalculo.id_prm_clc == parametro_id) | TrabajoCalculo.id_prm_clc.is_(None),
            TrabajoCalculo.id_ubccn.is_(None) | TrabajoCalculo.id_ubccn.in_(puntos),
        )
        .order_by(TrabajoCalculo.id_trabajo.desc())
        .limit(10)
        .all()
    )
    resultado["trabajos"] = [
        {
            "id": t.id_trabajo,
            "estado": t.estado,
            "procesados": t.procesados,
            "incidencias": t.incidencias,
            "error": t.error,
            "historico": t.inicio is None,
        }
        for t in trabajos
    ]
    resultado["resultados"] = [
        {"estado": estado, "cantidad": cantidad}
        for estado, cantidad in db.query(ResultadoCalculo.estado, func.count())
        .filter(ResultadoCalculo.id_prm_clc == parametro_id, ResultadoCalculo.id_ubccn.in_(puntos))
        .group_by(ResultadoCalculo.estado)
    ]
    resultado["puede_crear"] = puede_crear(db, contexto(db, usuario))
    return resultado


class NuevaDefinicion(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    id_sd: int = Field(gt=0)
    nmbr: str = Field(min_length=1, max_length=100)
    frml: str = Field(min_length=1, max_length=2000)
    undd: str = Field(min_length=1, max_length=30)
    dscrpcn: str | None = Field(default=None, max_length=300)
    estd: Literal["Activo", "Inactivo"] = "Activo"


class ValidacionFormula(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    id_sd: int = Field(gt=0)
    frml: str = Field(min_length=1, max_length=2000)
    undd: str = Field(min_length=1, max_length=30)


def validar_ambito(db, usuario, sede_id):
    exigir_tecnico(db, usuario)
    ambito = contexto(db, usuario)
    if not puede_crear(db, ambito):
        raise HTTPException(403, "Selecciona una empresa con permisos de edición")
    if not any(s.id_sd == sede_id for s in sedes_visibles(db, ambito)):
        raise HTTPException(403, "El ámbito elegido no está disponible en este contexto")


@router.post("/validar-formula")
def validar_formula(
    body: ValidacionFormula,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", EDICION)),
):
    validar_ambito(db, usuario, body.id_sd)
    try:
        normalizada, _ = validar_definicion(db, body.id_sd, body.frml, body.undd)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"valida": True, "mensaje": "Fórmula válida", "formula": normalizada}


class ConfiguracionNueva(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tolerancia_segundos: int = Field(ge=0, le=3600)
    espera_horas: int = Field(ge=1, le=720)


@router.put("/configuracion/{sede_id}")
def guardar_configuracion(
    sede_id: int,
    body: ConfiguracionNueva,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", EDICION)),
):
    validar_ambito(db, usuario, sede_id)
    db.execute(text("SELECT pg_advisory_xact_lock(38001, :sede)"), {"sede": sede_id})
    db.execute(
        insert(ConfiguracionCalculo)
        .values(id_sd=sede_id, **body.model_dump())
        .on_conflict_do_update(index_elements=["id_sd"], set_=body.model_dump())
    )
    encolar_historico(db, sede_id)
    db.commit()
    return body.model_dump()


@router.post("/trabajos/{trabajo_id}/reintentar")
def reintentar_trabajo(
    trabajo_id: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", EDICION)),
):
    t = db.get(TrabajoCalculo, trabajo_id)
    if t is None:
        raise HTTPException(404, "Trabajo no disponible")
    validar_ambito(db, usuario, t.id_sd)
    if t.id_ubccn and t.id_ubccn not in ubicaciones_permitidas(db, usuario):
        raise HTTPException(404, "Trabajo no disponible")
    db.refresh(t, with_for_update=True)
    if t.estado != "Fallido":
        raise HTTPException(409, "Solo se reintentan trabajos fallidos")
    t.estado, t.error = "Pendiente", None
    db.commit()
    return {"mensaje": "Procesamiento pendiente de reintento"}


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
    db.execute(text("SELECT pg_advisory_xact_lock(38001, :sede)"), {"sede": sede.id_sd})
    origenes = todos_origenes(db, [sede.id_sd])[sede.id_sd]
    try:
        formula, seleccionados = validar_definicion(db, sede.id_sd, body.frml, body.undd)
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
    if any(p.nmbr.casefold() == body.nmbr.casefold() for p in origenes):
        raise HTTPException(
            409,
            "El nombre coincide con un parámetro de origen; utiliza un nombre distinto para evitar referencias ambiguas",
        )
    p = ParametroCalculado(
        **body.model_dump(exclude={"frml"}),
        frml=formula,
        validada=True,
        id_usr_creador=int(usuario["sub"]),
    )
    db.add(p)
    try:
        db.flush()
        for v, origen in seleccionados.items():
            db.add(
                DependenciaCalculo(
                    id_prm_clc=p.id_prm_clc,
                    variable=v,
                    unidad_origen=origen.undd,
                    id_prmtr=origen.id_prmtr if v.startswith("p_") else None,
                    id_origen_calculado=origen.id_prm_clc if v.startswith("c_") else None,
                )
            )
        encolar_historico(db, sede.id_sd, p.id_prm_clc)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409, "Ya existe un parámetro calculado con ese nombre en el ámbito elegido"
        ) from exc
    db.refresh(p)
    empresa = db.get(Cliente, sede.id_clnt)
    return serializar((p, sede.nmbr, empresa.rzn_scl), origenes, detalle=True)
