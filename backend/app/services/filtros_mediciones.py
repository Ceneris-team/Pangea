"""HU32: condiciones por parámetro, compartidas por consulta y exportación."""

from decimal import Decimal
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator
from sqlalchemy import and_, or_

from app.models import Dispositivo, MapeoColumna, MapeoFormato, Parametro, Telemetria


class CondicionParametro(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    parametro_id: int = Field(gt=0)
    minimo: Decimal | None = None
    maximo: Decimal | None = None
    modo: Literal["dentro", "fuera"] = "dentro"

    @model_validator(mode="after")
    def validar_rango(self):
        if self.minimo is None and self.maximo is None:
            raise ValueError("Introduce al menos un límite para cada condición")
        if self.minimo is not None and self.maximo is not None and self.minimo > self.maximo:
            raise ValueError("El valor mínimo no puede ser mayor que el máximo")
        return self


Condiciones = Annotated[list[CondicionParametro], Field(max_length=100)]
ADAPTADOR_CONDICIONES = TypeAdapter(Condiciones)


def validar_unicas(condiciones):
    if len({c.parametro_id for c in condiciones}) != len(condiciones):
        raise ValueError("Solo se admite una condición por parámetro")
    return condiciones


def leer_condiciones(crudo: str | None):
    try:
        return validar_unicas(ADAPTADOR_CONDICIONES.validate_json(crudo or "[]"))
    except (ValidationError, ValueError) as exc:
        mensaje = "Las condiciones por parámetro no son válidas"
        if isinstance(exc, ValidationError):
            mensaje = ". ".join(
                dict.fromkeys(e["msg"].removeprefix("Value error, ") for e in exc.errors())
            )
        else:
            mensaje = str(exc)
        raise HTTPException(422, mensaje) from None


def fuentes_parametros(db, ids_dispositivos):
    return (
        db.query(Parametro, Dispositivo.id_dspstv, Dispositivo.id_ubccn, MapeoColumna.visualizacion)
        .join(MapeoColumna, MapeoColumna.id_prmtr == Parametro.id_prmtr)
        .join(MapeoFormato, MapeoFormato.id_mp == MapeoColumna.id_mp)
        .join(Dispositivo, Dispositivo.id_dspstv == MapeoFormato.id_dspstv)
        .filter(Dispositivo.id_dspstv.in_(ids_dispositivos))
        .order_by(Parametro.nmbr, Dispositivo.id_dspstv)
        .all()
    )


def admite_rango(parametro, visualizacion):
    significado = (visualizacion or {}).get("significado", parametro.tipo_visualizacion)
    return parametro.tipo_dato == "numerico" and significado != "estado"


def validar_contexto(db, condiciones, ids_dispositivos, parametro_ids=None):
    if not condiciones:
        return
    elegibles = {}
    for parametro, _equipo, _proyecto, visualizacion in fuentes_parametros(db, ids_dispositivos):
        elegibles[parametro.id_prmtr] = elegibles.get(parametro.id_prmtr, True) and admite_rango(
            parametro, visualizacion
        )
    if any(
        not elegibles.get(c.parametro_id, False)
        or (parametro_ids and c.parametro_id not in parametro_ids)
        for c in condiciones
    ):
        raise HTTPException(
            422,
            "Selecciona parámetros numéricos disponibles en los proyectos y equipos de la consulta; los estados binarios no admiten rangos",
        )


def aplicar_condiciones(query, modelo, condiciones):
    if not condiciones or modelo is not Telemetria:
        return query
    ramas = [modelo.id_prmtr.notin_([c.parametro_id for c in condiciones])]
    for condicion in condiciones:
        limites = []
        if condicion.minimo is not None:
            limites.append(
                modelo.vlr >= condicion.minimo
                if condicion.modo == "dentro"
                else modelo.vlr < condicion.minimo
            )
        if condicion.maximo is not None:
            limites.append(
                modelo.vlr <= condicion.maximo
                if condicion.modo == "dentro"
                else modelo.vlr > condicion.maximo
            )
        predicado = and_(*limites) if condicion.modo == "dentro" else or_(*limites)
        ramas.append(and_(modelo.id_prmtr == condicion.parametro_id, predicado))
    return query.filter(or_(*ramas))
