"""
PP-97 (HU06): parseo genérico de archivos .dat tipo CSV.

No conoce nombres de columna específicos de ninguna marca de sensor -eso
es el mapeo de PP-96, todavía bloqueado-. Este módulo solo convierte texto
delimitado en filas {columna_original: valor_crudo}, respetando la
configuración de formato de la marca (delimitador, fila de header, fila de
inicio de datos, formato de fecha).
"""

import csv
import dataclasses
import datetime as dt
import io

DELIMITADORES = {
    ",": ",",
    ";": ";",
    "tab": "\t",
    "\t": "\t",
    "espacio": " ",
    " ": " ",
}


@dataclasses.dataclass
class ConfiguracionParseo:
    """Refleja los campos de mp_frmt (HU06) que afectan el parseo."""

    delimitador: str = ","
    fila_header: int = 1
    fila_inicio_datos: int = 1
    formato_fecha: str = "%Y-%m-%d %H:%M:%S"
    columna_fecha: str = "Fecha"


@dataclasses.dataclass
class FilaParseada:
    numero_fila: int
    fecha_hora: dt.datetime | None
    valores: dict  # columna_original -> valor crudo (str)
    error: str | None = None


@dataclasses.dataclass
class ResultadoParseo:
    columnas: list
    filas: list  # list[FilaParseada]


def _resolver_delimitador(delimitador: str) -> str:
    return DELIMITADORES.get(delimitador, delimitador)


def _parsear_fecha(valor: str, formato_fecha: str) -> dt.datetime:
    return dt.datetime.strptime(valor.strip(), formato_fecha)


def parsear_dat(contenido: str, config: ConfiguracionParseo = None) -> ResultadoParseo:
    """Parsea el contenido crudo (texto) de un archivo .dat.

    contenido: texto completo del archivo, ya decodificado.
    config: parámetros de formato de la marca (HU06 / mp_frmt). Si se
        omite, se usan los valores por defecto (coma, header en fila 1,
        datos desde fila 1 tras el header).

    Vacíos ("") y ceros se preservan tal cual vienen como valor crudo -no
    son errores de parseo, la validación semántica es responsabilidad de
    PP-99-. Solo se marca error en la fila cuando la columna de fecha no
    puede interpretarse con formato_fecha.

    Si una fila de datos trae más o menos valores que columnas de header,
    se conserva de forma tolerante: valores sobrantes se guardan bajo una
    clave posicional ("_col_N") y columnas sin valor quedan en None. Esto
    es real en tramas de campo donde el número de columnas de datos no
    siempre calza con el header declarado.
    """
    config = config or ConfiguracionParseo()
    delimitador = _resolver_delimitador(config.delimitador)

    lector = csv.reader(io.StringIO(contenido), delimiter=delimitador)
    lineas = [linea for linea in lector if linea]

    indice_header = config.fila_header - 1
    if indice_header < 0 or indice_header >= len(lineas):
        return ResultadoParseo(columnas=[], filas=[])

    columnas = [c.strip() for c in lineas[indice_header]]

    indice_inicio = indice_header + config.fila_inicio_datos
    filas = []
    for offset, valores_crudos in enumerate(lineas[indice_inicio:]):
        numero_fila = indice_inicio + offset + 1  # 1-based, incluye header

        fila = {}
        for i, nombre_col in enumerate(columnas):
            fila[nombre_col] = valores_crudos[i] if i < len(valores_crudos) else None
        for i in range(len(columnas), len(valores_crudos)):
            fila[f"_col_{i + 1}"] = valores_crudos[i]

        error = None
        fecha_hora = None
        valor_fecha = fila.get(config.columna_fecha)
        if valor_fecha is None or valor_fecha == "":
            error = f"columna de fecha '{config.columna_fecha}' vacía o ausente"
        else:
            try:
                fecha_hora = _parsear_fecha(valor_fecha, config.formato_fecha)
            except ValueError as exc:
                error = (
                    f"fecha '{valor_fecha}' no coincide con formato {config.formato_fecha}: {exc}"
                )

        filas.append(
            FilaParseada(
                numero_fila=numero_fila,
                fecha_hora=fecha_hora,
                valores=fila,
                error=error,
            )
        )

    return ResultadoParseo(columnas=columnas, filas=filas)


def parsear_archivo_dat(
    ruta: str, config: ConfiguracionParseo = None, encoding: str = "utf-8"
) -> ResultadoParseo:
    """Igual que parsear_dat pero leyendo el contenido desde disco."""
    with open(ruta, "r", encoding=encoding, newline="") as f:
        contenido = f.read()
    return parsear_dat(contenido, config)
