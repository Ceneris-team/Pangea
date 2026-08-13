"""
PP-99 (HU06): validaciones genéricas sobre la salida de PP-98
(estandarizador). Un valor o fila inválida se registra y se descarta,
pero nunca detiene el procesamiento del resto del archivo -HU06 pide
tolerancia por fila, no por archivo completo-.
"""

import dataclasses
import datetime as dt
import logging

from app.services.ingesta.estandarizador import LecturaEstandar

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class LecturaValidada:
    fecha_hora: dt.datetime
    id_cnxn: int
    parametro: str
    valor: float | None  # None = valor vacío en origen, válido pero sin dato numérico
    numero_fila: int


@dataclasses.dataclass
class ErrorValidacion:
    numero_fila: int
    parametro: str | None
    motivo: str


@dataclasses.dataclass
class ResultadoValidacion:
    validas: list  # list[LecturaValidada]
    errores: list  # list[ErrorValidacion]


def _es_valor_vacio(valor_crudo) -> bool:
    return valor_crudo is None or (isinstance(valor_crudo, str) and valor_crudo.strip() == "")


def _parsear_numero(valor_crudo, delimitador_decimal: str = "."):
    """Devuelve (valor_float_o_None, error_o_None). Vacío y "0" son
    válidos; texto no numérico no lo es.

    Con delimitador_decimal=',' (mp_frmt.dlmtdr_dcml) el valor viene en
    locale europeo -"23,5"-: se traduce a punto antes de float(), que es
    lo único que Python entiende. El separador de miles NO se soporta a
    propósito: un .dat de datalogger no lo usa, y aceptarlo obligaría a
    adivinar si "1,234" son mil doscientos treinta y cuatro o 1.234.
    """
    if _es_valor_vacio(valor_crudo):
        return None, None
    valor_normalizado = valor_crudo
    if delimitador_decimal == "," and isinstance(valor_crudo, str):
        valor_normalizado = valor_crudo.replace(",", ".", 1)
    try:
        return float(valor_normalizado), None
    except (TypeError, ValueError):
        return None, f"valor '{valor_crudo}' no es numérico"


def validar_lecturas(
    lecturas: list,
    ahora: dt.datetime = None,
    delimitador_decimal: str = ".",
) -> ResultadoValidacion:
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    validas = []
    errores = []

    for lectura in lecturas:
        if isinstance(lectura, LecturaEstandar) and lectura.parametro is None:
            errores.append(
                ErrorValidacion(
                    numero_fila=lectura.numero_fila,
                    parametro=None,
                    motivo=lectura.error_parseo or "fila con error de parseo",
                )
            )
            continue

        if lectura.fecha_hora is None:
            errores.append(
                ErrorValidacion(
                    numero_fila=lectura.numero_fila,
                    parametro=lectura.parametro,
                    motivo="timestamp ausente o no parseable",
                )
            )
            continue

        fecha_hora = lectura.fecha_hora
        if fecha_hora.tzinfo is None:
            fecha_hora = fecha_hora.replace(tzinfo=dt.timezone.utc)

        if fecha_hora > ahora:
            errores.append(
                ErrorValidacion(
                    numero_fila=lectura.numero_fila,
                    parametro=lectura.parametro,
                    motivo=f"timestamp futuro: {fecha_hora.isoformat()}",
                )
            )
            continue

        valor, error_numero = _parsear_numero(lectura.valor_crudo, delimitador_decimal)
        if error_numero:
            errores.append(
                ErrorValidacion(
                    numero_fila=lectura.numero_fila,
                    parametro=lectura.parametro,
                    motivo=error_numero,
                )
            )
            continue

        validas.append(
            LecturaValidada(
                fecha_hora=fecha_hora,
                id_cnxn=lectura.id_cnxn,
                parametro=lectura.parametro,
                valor=valor,
                numero_fila=lectura.numero_fila,
            )
        )

    if errores:
        logger.warning("Validación: %s lecturas rechazadas de %s", len(errores), len(lecturas))
        for err in errores:
            logger.warning(
                "  fila=%s parametro=%s motivo=%s",
                err.numero_fila,
                err.parametro,
                err.motivo,
            )

    return ResultadoValidacion(validas=validas, errores=errores)
