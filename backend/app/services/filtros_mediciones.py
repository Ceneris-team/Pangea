"""HU32: condiciones por parámetro, compartidas por consulta y exportación."""

import re
import sys
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    model_validator,
)
from sqlalchemy import and_, or_

from app.models import (
    Dispositivo,
    MapeoColumna,
    MapeoFormato,
    Parametro,
    ResultadoCalculo,
    Telemetria,
)

# Las condiciones también alcanzan resultados calculados (double precision).
# Validar antes de SQL evita tanto desbordamientos como subdesbordamientos.
# No se redondean los límites a los cuatro decimales de la telemetría.
MAXIMO_LIMITE = Decimal.from_float(sys.float_info.max)
PATRON_LIMITE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def validar_texto_limite(valor):
    if isinstance(valor, str):
        valor = valor.strip()
        if len(valor) > 60:
            raise ValueError("El límite admite hasta 60 caracteres")
        if not PATRON_LIMITE.fullmatch(valor):
            raise ValueError("El límite debe ser un decimal válido con dígitos del 0 al 9")
    return valor


def validar_limite_representable(valor: Decimal) -> Decimal:
    if not valor.is_finite() or valor.copy_abs() > MAXIMO_LIMITE:
        raise ValueError("El límite está fuera del rango numérico admitido")
    if valor != 0 and float(valor) == 0:
        raise ValueError("El límite es demasiado pequeño para el rango numérico admitido")
    return Decimal(0) if valor == 0 else valor


LimiteNumerico = Annotated[
    Decimal, BeforeValidator(validar_texto_limite), AfterValidator(validar_limite_representable)
]


class CondicionParametro(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    parametro_id: int
    minimo: LimiteNumerico | None = None
    maximo: LimiteNumerico | None = None
    modo: Literal["dentro", "fuera"] = "dentro"

    @model_validator(mode="after")
    def validar_rango(self):
        if self.parametro_id == 0:
            raise ValueError("Selecciona un parámetro válido")
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


def validar_contexto(db, condiciones, ids_dispositivos, parametro_ids=None, puntos_calculados=None):
    if not condiciones:
        return
    elegibles = {}
    for parametro, _equipo, _proyecto, visualizacion in fuentes_parametros(db, ids_dispositivos):
        elegibles[parametro.id_prmtr] = elegibles.get(parametro.id_prmtr, True) and admite_rango(
            parametro, visualizacion
        )
    from app.services.consulta_calculos import catalogo_calculados

    puntos = (
        puntos_calculados
        if puntos_calculados is not None
        else [
            id_
            for (id_,) in db.query(Dispositivo.id_ubccn)
            .filter(Dispositivo.id_dspstv.in_(ids_dispositivos))
            .distinct()
        ]
    )
    for p in catalogo_calculados(db, puntos):
        elegibles[p["id_prmtr"]] = True
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
    if not condiciones or modelo not in (Telemetria, ResultadoCalculo):
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
