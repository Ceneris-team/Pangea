"""
PP-96 (HU06): resuelve, para un archivo .dat concreto, qué formato aplica
y cómo se traduce cada columna a un parámetro estándar.

Es la pieza que reemplaza el mapeo mock de estandarizador.py. Dos
decisiones de negocio la definen:

1. El TIPO DE TRAMA sale del prefijo del nombre del archivo:
     H_*.dat -> datos periódicos (la lectura en tiempo real)
     E_*.dat -> estados y eventos que genera el equipo
   Un mismo datalogger manda ambos, con distinto número de columnas.

2. El MAPEO columna->parámetro sale de mp_clmn, que referencia la columna
   por su ÍNDICE (indc_clmn), no por su nombre. Es a propósito: los
   archivos de campo traen headers con nombres inconsistentes o
   repetidos, y el índice es estable frente a eso.
"""
import dataclasses
import logging
import os

from sqlalchemy.orm import Session

from app.models.mapeo_dispositivo import MapeoColumna, MapeoFormato, Parametro
from app.services.ingesta.parser import ConfiguracionParseo

logger = logging.getLogger(__name__)

# Prefijo del nombre de archivo -> tipo de trama (mp_frmt.tp_trm).
PREFIJOS_TIPO_TRAMA = {
    "H_": "H",
    "E_": "E",
}


class MapeoNoEncontradoError(Exception):
    """No hay un mp_frmt activo para ese dispositivo + tipo de trama.

    Es un error de configuración, no transitorio: reintentar no lo
    resuelve. El llamador debe tratarlo como error de datos (ver
    app.tasks.ingesta)."""


@dataclasses.dataclass
class FormatoResuelto:
    """El formato aplicable a un archivo, resuelto ANTES de parsearlo.

    El mapeo columna->parámetro no va aquí: mp_clmn referencia columnas
    por índice, así que hace falta el header ya leído para traducirlo a
    nombres. Se obtiene después con construir_mapeo()."""
    id_mp: int
    tipo_trama: str
    config: ConfiguracionParseo


def detectar_tipo_trama(nombre_archivo: str) -> str | None:
    """Devuelve 'H', 'E' o None si el nombre no lleva prefijo conocido.

    Se compara sobre el nombre base y en mayúsculas: los dataloggers no
    son consistentes con el case ni con la ruta que antecede al archivo.
    """
    base = os.path.basename(nombre_archivo).upper()
    for prefijo, tipo in PREFIJOS_TIPO_TRAMA.items():
        if base.startswith(prefijo):
            return tipo
    return None


def resolver_formato(
    db: Session,
    id_dspstv: int,
    nombre_archivo: str,
) -> FormatoResuelto:
    """Resuelve el formato y el mapeo real para un archivo dado.

    DEC-09: el formato se busca por DISPOSITIVO + tipo de trama, no por
    sede + marca. Dos dataloggers de la misma marca en la misma sede
    pueden tener sensores distintos conectados; con el criterio anterior
    compartían mapeo y las lecturas del segundo se guardaban bajo el
    parámetro equivocado sin ningún error visible. El dispositivo ya viene
    resuelto por resolver_dispositivo() a partir de la conexión FTP
    entrante, que es exclusiva de un solo datalogger físico.

    Levanta MapeoNoEncontradoError si el archivo no tiene un prefijo
    reconocible o si no hay un mp_frmt activo para ese dispositivo: sin
    mapeo no se puede interpretar el archivo, y adivinar produciría
    lecturas incorrectas en silencio.
    """
    tipo_trama = detectar_tipo_trama(nombre_archivo)
    if tipo_trama is None:
        raise MapeoNoEncontradoError(
            f"El archivo '{nombre_archivo}' no empieza por un prefijo de tipo de "
            f"trama conocido ({', '.join(sorted(PREFIJOS_TIPO_TRAMA))}); no se "
            f"puede determinar qué formato aplica."
        )

    formato = (
        db.query(MapeoFormato)
        .filter(
            MapeoFormato.id_dspstv == id_dspstv,
            MapeoFormato.tp_trm == tipo_trama,
            MapeoFormato.estd == "Activo",
        )
        .first()
    )
    if formato is None:
        raise MapeoNoEncontradoError(
            f"No hay un formato activo (mp_frmt) para el dispositivo "
            f"id={id_dspstv} y el tipo de trama='{tipo_trama}'. Cárgalo antes "
            f"de procesar archivos de este datalogger."
        )

    config = ConfiguracionParseo(
        delimitador=formato.dlmtdr,
        fila_inicio_datos=formato.fl_inc_dts,
        formato_fecha=formato.frmt_fch,
    )

    return FormatoResuelto(
        id_mp=formato.id_mp,
        tipo_trama=tipo_trama,
        config=config,
    )


def construir_mapeo(db: Session, id_mp: int, columnas: list) -> dict:
    """columna_original -> nombre de parámetro, a partir de mp_clmn.

    mp_clmn referencia la columna por índice; `columnas` son los nombres
    leídos del header del archivo, en orden. El índice se interpreta
    como 0-based sobre ese header.
    """
    filas = (
        db.query(MapeoColumna, Parametro)
        .join(Parametro, Parametro.id_prmtr == MapeoColumna.id_prmtr)
        .filter(MapeoColumna.id_mp == id_mp)
        .all()
    )

    mapeo = {}
    fuera_de_rango = []
    for mp_columna, parametro in filas:
        indice = mp_columna.indc_clmn
        if indice < 0 or indice >= len(columnas):
            fuera_de_rango.append(indice)
            continue
        mapeo[columnas[indice]] = parametro.nmbr

    if fuera_de_rango:
        logger.warning(
            "mp_frmt id=%s: los índices %s de mp_clmn quedan fuera del header "
            "del archivo (%s columnas); esas columnas se ignoran.",
            id_mp, sorted(fuera_de_rango), len(columnas),
        )

    return mapeo
