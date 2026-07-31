"""
PP-98 (HU06): estandariza la salida del parser (PP-97) a una estructura
interna común -formato .tsp- usando un diccionario de mapeo
columna_original -> nombre_parametro_estandar.

Ese diccionario lo debe producir PP-96 (mini-ETL por marca: mp_frmt +
mp_clmn + prmtr) resolviendo, para cada archivo, qué mapeo aplica y
traduciendo mp_clmn.indc_clmn -> prmtr.nmbr. PP-96 todavía está bloqueado
pendiente de definición de negocio sobre cómo distinguir tipos de trama
por archivo, así que esta etapa recibe el mapeo ya resuelto como
parámetro y no sabe nada de mp_frmt/mp_clmn.
"""
import dataclasses
import datetime as dt

from app.services.ingesta.parser import FilaParseada, ResultadoParseo


@dataclasses.dataclass
class LecturaEstandar:
    fecha_hora: dt.datetime | None
    id_cnxn: int
    parametro: str
    valor_crudo: object  # str | None, sin castear todavía -eso es PP-99-
    numero_fila: int
    error_parseo: str | None = None


def mapeo_prueba_temporal() -> dict:
    """Mapeo mock solo para probar el pipeline end-to-end mientras PP-96
    no existe. Cubre las columnas de los dos archivos de ejemplo de HU06
    (trama de estado de gabinete y trama de calidad de agua).

    # TODO(PP-96): reemplazar por el mapeo real (mp_frmt + mp_clmn + prmtr)
    # cuando la definición de negocio de "cómo distinguir tipos de trama
    # por archivo" esté cerrada. El punto de integración es el parámetro
    # `mapeo` de estandarizar_filas() más abajo: quien llame a esta función
    # debe resolver el mapeo real ahí en vez de usar este mock.
    """
    return {
        "Estado_Gabinete": "estado_gabinete",
        "Estado_Puerta": "estado_puerta",
        "Contador_Puerta": "contador_puerta",
        "Mensaje_Alarma": "mensaje_alarma",
        "BattV(V)": "bateria_v",
        "Temperatura(C°)": "temperatura",
        "Conductividad(uS/cm)": "conductividad",
        "pH(pH)": "ph",
        "ORP(mV)": "orp",
    }


def estandarizar_filas(resultado: ResultadoParseo, id_cnxn: int, mapeo: dict) -> list:
    """Convierte cada FilaParseada en 0..n LecturaEstandar (una por columna
    mapeada). Columnas del archivo que no están en `mapeo` se ignoran -no
    todas las columnas de un .dat corresponden a un parámetro estándar
    (ej. índices de calidad, timestamps de máximos, etc. de HU06)-.

    `mapeo` es columna_original -> nombre_parametro_estandar, resuelto por
    quien llama (normalmente PP-96; ver mapeo_prueba_temporal para el
    mock usado en pruebas del pipeline)."""
    lecturas = []
    for fila in resultado.filas:
        lecturas.extend(_estandarizar_fila(fila, id_cnxn, mapeo))
    return lecturas


def _estandarizar_fila(fila: FilaParseada, id_cnxn: int, mapeo: dict) -> list:
    if fila.error:
        return [LecturaEstandar(
            fecha_hora=fila.fecha_hora,
            id_cnxn=id_cnxn,
            parametro=None,
            valor_crudo=None,
            numero_fila=fila.numero_fila,
            error_parseo=fila.error,
        )]

    lecturas = []
    for columna_original, parametro in mapeo.items():
        if columna_original not in fila.valores:
            continue
        lecturas.append(LecturaEstandar(
            fecha_hora=fila.fecha_hora,
            id_cnxn=id_cnxn,
            parametro=parametro,
            valor_crudo=fila.valores[columna_original],
            numero_fila=fila.numero_fila,
        ))
    return lecturas
