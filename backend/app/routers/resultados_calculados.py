"""Consulta de definiciones y trazas con los mismos permisos de los datos."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ParametroCalculado, ResultadoCalculo, RevisionCalculo, Ubicacion
from app.security.permisos import LECTURA, require_permiso
from app.security.ubicaciones_permitidas import ubicaciones_permitidas
from app.services.parametros_calculados import describir_formula, todos_origenes

router = APIRouter(prefix="/mediciones/calculados", tags=["Mediciones calculadas"])


def definicion_visible(db, usuario, id_):
    puntos = ubicaciones_permitidas(db, usuario)
    p = (
        db.query(ParametroCalculado)
        .filter(
            ParametroCalculado.id_prm_clc == id_,
            ParametroCalculado.id_sd.in_(
                db.query(Ubicacion.id_sd).filter(Ubicacion.id_ubccn.in_(puntos))
            ),
        )
        .first()
    )
    if p is None:
        raise HTTPException(404, "Definición no disponible")
    return p, puntos


@router.get("/{id_calculado}")
def consultar_definicion(
    id_calculado: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", LECTURA)),
):
    p, _ = definicion_visible(db, usuario, id_calculado)
    return {
        "nombre": p.nmbr,
        "unidad": p.undd,
        "descripcion": p.dscrpcn,
        **describir_formula(p.frml, todos_origenes(db, [p.id_sd])[p.id_sd]),
    }


@router.get("/{id_calculado}/resultados")
def consultar_resultados(
    id_calculado: int,
    ubicacion_id: int | None = None,
    estado: str | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", LECTURA)),
):
    p, puntos = definicion_visible(db, usuario, id_calculado)
    q = (
        db.query(ResultadoCalculo, Ubicacion.nmbr)
        .join(Ubicacion)
        .filter(
            ResultadoCalculo.id_prm_clc == p.id_prm_clc,
            ResultadoCalculo.id_ubccn.in_(puntos),
            ResultadoCalculo.vigente,
        )
    )
    if ubicacion_id is not None:
        q = q.filter(ResultadoCalculo.id_ubccn == ubicacion_id)
    if estado:
        q = q.filter(ResultadoCalculo.estado == estado)
    return {
        "total": q.count(),
        "items": [
            {
                "id": r.id_resultado,
                "fecha": r.fch_hr,
                "ubicacion": punto,
                "valor": r.vlr,
                "unidad": p.undd,
                "estado": r.estado,
                "causa": r.causa,
                "revision": r.revision,
                "trazabilidad": r.trazabilidad,
            }
            for r, punto in q.order_by(
                ResultadoCalculo.fch_hr.desc(), ResultadoCalculo.id_resultado.desc()
            )
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        ],
    }


@router.get("/resultados/{id_resultado}/revisiones")
def consultar_revisiones(
    id_resultado: int,
    pagina: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", LECTURA)),
):
    r = (
        db.query(ResultadoCalculo)
        .filter(
            ResultadoCalculo.id_resultado == id_resultado,
            ResultadoCalculo.id_ubccn.in_(ubicaciones_permitidas(db, usuario)),
        )
        .first()
    )
    if r is None:
        raise HTTPException(404, "Resultado no disponible")
    q = db.query(RevisionCalculo).filter_by(id_resultado=id_resultado)
    return {
        "total": q.count(),
        "items": [
            {"revision": v.revision, "fecha": v.creada_en, **v.anterior}
            for v in q.order_by(RevisionCalculo.revision.desc()).offset((pagina - 1) * 20).limit(20)
        ],
    }
