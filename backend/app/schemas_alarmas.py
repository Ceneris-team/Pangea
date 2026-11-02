"""Esquemas de HU27 (listar alarmas) y HU28 (crear alarma).

Traídos de la rama `fabio` (commit ca9e795, 04/09/2026) a dev para PP-73.
Viven en su propio módulo, como schemas_exportaciones.py, para no seguir
creciendo schemas.py.
"""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AlarmaListItem(BaseModel):
    """Una fila del listado de HU27: 'nombre de la alarma, parámetro
    asociado, condición, estado y acciones'. 'acciones' no viaja como dato
    -son los botones que arma el frontend a partir de id_alrm/estd-.

    condicion es None cuando la alarma todavía no tiene una condición
    configurada: el modelo lo permite -una alrm puede existir sin fila en
    cndcn_alrm-, así que el frontend lo muestra como 'Sin condición
    configurada' en vez de reventar."""

    model_config = ConfigDict(from_attributes=True)

    id_alrm: int
    nmbr: str
    parametro_nombre: str
    condicion: str | None
    estd: str


# Mismos operadores que admite el CHECK de cndcn_alrm
# (cndcnalrm_oprdr_check, ver app/models/alarma.py). Se declaran acá para
# que el 422 con el detalle del campo salga de Pydantic y no como un
# IntegrityError opaco al hacer commit.
OPERADORES_ALARMA = (">", "<", ">=", "<=", "=")

# HU28 "detalles de la conversación": "El nombre de la alarma acepta texto
# alfanumérico con un máximo de 100 caracteres". Se lee como "texto", no
# como "solo [A-Za-z0-9]": un nombre real es "Nivel río Rímac - crecida",
# con espacios, tilde y guion. Lo que la regla sí descarta es un nombre
# puramente simbólico ("###"): la cadena tiene que empezar por un carácter
# alfanumérico y no puede traer símbolos fuera de la puntuación de abajo.
_CARACTERES_NOMBRE_ALARMA = r"0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ"
_RE_NOMBRE_ALARMA = re.compile(
    rf"^[{_CARACTERES_NOMBRE_ALARMA}][{_CARACTERES_NOMBRE_ALARMA} .,;:_()\-/]*$"
)


class UbicacionParaAlarma(BaseModel):
    """HU28 CA1: pobla el selector "Ubicación asociada". Proyección mínima
    de ubccn: el selector solo necesita id y nombre."""

    model_config = ConfigDict(from_attributes=True)

    id_ubccn: int
    nmbr: str


class CondicionAlarmaCrear(BaseModel):
    """Una condición umbral del paso 2 del alta (HU29).

    HU28 la recibe pero no define sus reglas de negocio: el flujo es de dos
    pasos ("datos generales en HU 28 y condiciones en HU 29") y el registro
    recién se persiste al GUARDAR del paso 2 (CA3), así que el POST tiene
    que poder traerlas. HU28 solo valida lo que ya exige el modelo: el
    operador dentro del CHECK."""

    oprdr: str
    vlr_umbrl: float

    @field_validator("oprdr")
    @classmethod
    def _operador_valido(cls, valor: str) -> str:
        valor = valor.strip()
        if valor not in OPERADORES_ALARMA:
            raise ValueError(f"El operador debe ser uno de: {', '.join(OPERADORES_ALARMA)}")
        return valor


class AlarmaCrear(BaseModel):
    """HU28 CA1: los tres campos obligatorios del formulario (Nombre de la
    alarma, Parámetro a monitorear y Ubicación asociada), más las
    condiciones del paso 2 (HU29) que llegan en el mismo POST."""

    nmbr: str = Field(..., min_length=1, max_length=100)
    id_prmtr: int
    id_ubccn: int
    condiciones: list[CondicionAlarmaCrear] = Field(default_factory=list)

    @field_validator("nmbr")
    @classmethod
    def _nombre_valido(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("El nombre de la alarma es obligatorio")
        if not _RE_NOMBRE_ALARMA.match(valor):
            raise ValueError(
                "El nombre de la alarma debe ser texto alfanumérico "
                "(se admiten espacios y los signos . , ; : _ ( ) - /)"
            )
        return valor


class AlarmaCreada(BaseModel):
    """HU28 CA3: "crea la alarma con estado Activa (...) y muestra el MSG
    'Alarma creada correctamente'". La alarma viaja con la misma forma que
    en el listado (AlarmaListItem): el frontend vuelve al listado tras
    guardar."""

    mensaje: str = "Alarma creada correctamente"
    alarma: AlarmaListItem
