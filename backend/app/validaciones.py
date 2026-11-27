"""Validaciones de texto compartidas por los filtros de la API."""

import unicodedata
from typing import Annotated

from pydantic import AfterValidator


def validar_texto_sin_control(valor: str) -> str:
    if any(unicodedata.category(caracter) == "Cc" for caracter in valor):
        raise ValueError("El valor no puede contener caracteres de control (incluido NUL)")
    return valor


TextoSinControl = Annotated[str, AfterValidator(validar_texto_sin_control)]
