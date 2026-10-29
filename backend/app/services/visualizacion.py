"""Significado y presentación por columna; nunca inferir eventos por monotonía."""

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ConfigVisualizacion(BaseModel):
    significado: Literal["continuo", "contador", "secuencia", "estado", "desconocido"] = (
        "desconocido"
    )
    vista: Literal["linea", "area", "kpi", "barras", "escalon"] = "linea"
    reinicio: Literal["desconocido", "cero", "modulo"] = "desconocido"
    modulo: int | None = Field(default=None, gt=1)
    confirmada: bool = False

    @model_validator(mode="after")
    def validar(self):
        vistas = {
            "continuo": {"linea", "area", "kpi"},
            "contador": {"kpi", "barras", "escalon"},
            "secuencia": {"kpi", "barras", "escalon"},
            "estado": {"escalon", "kpi", "barras"},
            "desconocido": {"linea", "kpi"},
        }
        if self.vista not in vistas[self.significado]:
            raise ValueError("La vista no corresponde al significado seleccionado")
        if self.reinicio == "modulo" and self.modulo is None:
            raise ValueError("Indica el módulo del contador (por ejemplo, 65536)")
        if self.significado == "desconocido" and self.confirmada:
            raise ValueError("Selecciona el significado antes de confirmar")
        return self


def sugerir_visualizacion(nombre, unidad="", muestras=()):
    nombre = re.sub(r"([a-z])([A-Z])", r"\1_\2", nombre)
    nombre = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    tokens = set(re.findall(r"[a-z]+", nombre))
    # Un COUNT genérico o una serie 1,2,3 nunca bastan para afirmar eventos.
    significado = "desconocido"
    if tokens & {"sequence", "seq", "secuencia", "record", "consecutivo"} or (
        tokens & {"trama", "tramas", "packet", "packets"}
        and tokens & {"counter", "count", "contador", "numero"}
    ):
        significado = "secuencia"
    elif tokens & {"contador", "counter", "count", "total"} and tokens & {
        "aperturas",
        "apertura",
        "puerta",
        "door",
        "eventos",
        "events",
        "pulsos",
        "pulses",
    }:
        significado = "contador"
    elif tokens & {"estado", "state", "status"}:
        try:
            valores = {float(v) for v in muestras if v is not None and str(v).strip()}
        except (TypeError, ValueError):
            valores = {2}
        if not valores or valores <= {0, 1}:
            significado = "estado"
    elif tokens & {
        "temperatura",
        "temperature",
        "presion",
        "pressure",
        "nivel",
        "level",
        "voltaje",
        "voltage",
        "humedad",
        "humidity",
        "ph",
    } or unidad.lower() in {"°c", "°f", "c", "v", "bar", "kpa", "m", "mm", "%"}:
        significado = "continuo"
    vista = {"contador": "kpi", "secuencia": "kpi", "estado": "escalon"}.get(significado, "linea")
    return ConfigVisualizacion(significado=significado, vista=vista).model_dump()


def configuracion_columna(columna, parametro):
    if columna.visualizacion:
        return ConfigVisualizacion.model_validate(columna.visualizacion)
    # Respetar la clasificación explícita del catálogo anterior.
    tipo = parametro.tipo_visualizacion or "continuo"
    if parametro.orgn_crcn == "Manual" or tipo != "continuo":
        return ConfigVisualizacion(
            significado=tipo,
            vista={"contador": "kpi", "estado": "escalon"}.get(tipo, "linea"),
            confirmada=True,
        )
    return ConfigVisualizacion.model_validate(sugerir_visualizacion(parametro.nmbr, parametro.undd))


def incremento(anterior, actual, config):
    """Devuelve (incremento conocido, discontinuidad sin resolver)."""
    if actual >= anterior:
        return actual - anterior, False
    if config.reinicio == "cero":
        return actual, False
    if (
        config.reinicio == "modulo"
        and 0 <= anterior < config.modulo
        and 0 <= actual < config.modulo
    ):
        return config.modulo - anterior + actual, False
    return 0, True


class ResumenSerieAcumulado:
    """Calcula el resumen sobre lecturas únicas ordenadas, sin retenerlas."""

    def __init__(self, anterior, config, *, guardar_deltas=False):
        self.config = config
        self.tiene_referencia = anterior is not None
        self.previo = anterior[1] if anterior else None
        self.parcial = False
        self.total = 0
        self.reinicios = 0
        self.huecos = 0
        self.lecturas = 0
        self.ultimo = None
        self.ultima_lectura = None
        self.minimo = None
        self.maximo = None
        self.suma = 0
        self.deltas = [] if guardar_deltas else None

    def agregar(self, fecha, valor):
        config = self.config
        previo = self.previo
        if (
            self.lecturas == 0
            and not self.tiene_referencia
            and config.significado in {"contador", "estado"}
        ):
            self.parcial = True
        delta = 0
        if config.significado == "secuencia":
            delta = 1
            if previo is not None:
                salto, incierto = incremento(previo, valor, config)
                self.huecos += max(0, salto - 1)
                self.parcial |= incierto
                self.reinicios += int(valor < previo)
        elif previo is not None and config.significado == "contador":
            delta, incierto = incremento(previo, valor, config)
            self.parcial |= incierto
            self.reinicios += int(valor < previo)
        elif previo is not None and config.significado == "estado":
            self.parcial |= previo not in {0, 1} or valor not in {0, 1}
            delta = int(previo == 0 and valor == 1)
        self.total += delta
        self.lecturas += 1
        self.ultimo = valor
        self.ultima_lectura = fecha
        self.minimo = valor if self.minimo is None else min(self.minimo, valor)
        self.maximo = valor if self.maximo is None else max(self.maximo, valor)
        self.suma += valor
        self.previo = valor
        if self.deltas is not None:
            self.deltas.append((fecha, delta))
        return delta

    def resultado(self, duplicados=0):
        total = self.total
        config = self.config
        if config.significado in {"continuo", "desconocido"}:
            total = self.ultimo
        elif not self.lecturas or (
            not self.tiene_referencia
            and self.lecturas == 1
            and config.significado in {"contador", "estado"}
        ):
            total = None
        resultado = {
            "valor": total,
            "ultimo": self.ultimo,
            "lecturas": self.lecturas,
            "duplicados": duplicados,
            "parcial": self.parcial,
            "reinicios": self.reinicios,
            "saltos_secuencia": self.huecos,
            "ultima_lectura": self.ultima_lectura,
            "minimo": self.minimo,
            "maximo": self.maximo,
            "promedio": self.suma / self.lecturas if self.lecturas else None,
        }
        if self.deltas is not None:
            resultado["deltas"] = self.deltas
        return resultado


def resumir_serie(filas, anterior, config):
    """Una fuente en memoria; deduplica por instante y valor para los callers existentes."""
    unicas = sorted(set(filas))
    acumulado = ResumenSerieAcumulado(anterior, config, guardar_deltas=True)
    for fecha, valor in unicas:
        acumulado.agregar(fecha, valor)
    return acumulado.resultado(duplicados=len(filas) - len(unicas))
