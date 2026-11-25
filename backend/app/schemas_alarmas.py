"""Esquemas de HU27 (listar alarmas), HU28 (crear alarma) y HU29
(condiciones de la alarma, PP-74).

Traídos de la rama `fabio` (commit ca9e795, 04/09/2026) a dev para PP-73.
Viven en su propio módulo, como schemas_exportaciones.py, para no seguir
creciendo schemas.py.

HU29 / PP-74: "una condición por alarma en v1.0, modelo flexible (HT-13)"
(Diccionario de Datos Pangea 4.0, CONDICION_ALARMA). La tabla cndcn_alrm
admite varias filas por alarma para crecer después, pero la regla de esta
versión es UNA: el alta y la edición la exigen y la evaluación (servicio
de notificaciones) sigue leyendo una lista, así que las alarmas antiguas
con varias condiciones no se rompen.
"""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictBool, field_validator


class EstadoDispositivoAlarma(BaseModel):
    id_dspstv: int
    nombre: str
    en_alarma: bool
    desde: datetime | None
    ultima_evaluacion: datetime | None
    pendiente_evaluacion: bool


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
    correos_habilitados: bool = True
    dispositivos: list[EstadoDispositivoAlarma] = Field(default_factory=list)


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


# cndcn_alrm.vlr_umbrl es Numeric(14,4): 10 dígitos enteros y 4 decimales.
# Postgres redondearía en silencio un quinto decimal; se rechaza antes.
UMBRAL_MAXIMO = Decimal("9999999999.9999")
DECIMALES_UMBRAL = 4
MENSAJE_UNA_CONDICION = "La alarma debe tener exactamente una condición (operador y valor umbral)"


def _exigir_una_condicion(condiciones):
    """HU29 v1.0: una condición por alarma. Mensaje en español en vez del
    'List should have at most 1 item' de Pydantic."""
    if condiciones is not None and len(condiciones) != 1:
        raise ValueError(MENSAJE_UNA_CONDICION)
    return condiciones


class CondicionAlarmaCrear(BaseModel):
    """La condición umbral de la alarma (HU29, PP-229): operador + valor.

    Llega en el paso 2 del alta (el registro recién se persiste al GUARDAR,
    HU28 CA3), en la edición desde el listado (PUT /alarmas/{id}/condicion,
    el "ACTUALIZAR" de la HU) y en el PATCH general."""

    oprdr: str
    vlr_umbrl: float

    @field_validator("oprdr", mode="before")
    @classmethod
    def _operador_valido(cls, valor) -> str:
        valor = valor.strip() if isinstance(valor, str) else valor
        if valor not in OPERADORES_ALARMA:
            raise ValueError(f"El operador debe ser uno de: {', '.join(OPERADORES_ALARMA)}")
        return valor

    @field_validator("vlr_umbrl", mode="before")
    @classmethod
    def _umbral_valido(cls, valor) -> float:
        # bool es subclase de int: true no es un umbral.
        if (
            valor is None
            or isinstance(valor, bool)
            or (isinstance(valor, str) and not valor.strip())
        ):
            raise ValueError("El valor umbral es obligatorio")
        if not isinstance(valor, (int, float, str)):
            raise ValueError("El valor umbral debe ser un número")
        try:
            numero = Decimal(str(valor).strip())
        except InvalidOperation:
            raise ValueError("El valor umbral debe ser un número") from None
        if not numero.is_finite():
            raise ValueError("El valor umbral debe ser un número finito")
        if abs(numero) > UMBRAL_MAXIMO:
            raise ValueError("El valor umbral debe estar entre -9999999999.9999 y 9999999999.9999")
        exponente = numero.as_tuple().exponent
        if isinstance(exponente, int) and exponente < -DECIMALES_UMBRAL:
            raise ValueError(f"El valor umbral admite hasta {DECIMALES_UMBRAL} decimales")
        return float(numero)


class CondicionAlarmaDetalle(BaseModel):
    """GET/PUT /alarmas/{id}/condicion: la condición vigente con lo que la
    pantalla necesita para mostrarla ("Se activará cuando Temperatura >
    30 °C"). `condiciones_guardadas` > 1 solo ocurre en alarmas creadas
    antes de PP-74; al actualizar quedan con una."""

    id_alrm: int
    alarma: str
    parametro: str
    unidad: str
    oprdr: str | None
    vlr_umbrl: float | None
    condicion: str | None
    condiciones_guardadas: int


class AlarmaDetalle(BaseModel):
    id_alrm: int
    nmbr: str
    estd: str
    correos_habilitados: bool = True
    parametro_nombre: str
    unidad: str | None
    condiciones: list[CondicionAlarmaCrear]
    dispositivos: list[EstadoDispositivoAlarma]


class AlarmaCrear(BaseModel):
    """HU28 CA1: los tres campos obligatorios del formulario (Nombre de la
    alarma, Parámetro a monitorear y Ubicación asociada), más las
    condiciones del paso 2 (HU29) que llegan en el mismo POST."""

    nmbr: str = Field(..., min_length=1, max_length=100)
    id_prmtr: int
    id_ubccn: int
    # HU29 v1.0: exactamente una (se valida también el valor por defecto,
    # para que omitir el campo dé el mismo 422 en español).
    condiciones: list[CondicionAlarmaCrear] = Field(default_factory=list, validate_default=True)
    destinatarios: list[EmailStr] = Field(default_factory=list, max_length=100)

    @field_validator("condiciones")
    @classmethod
    def _una_condicion(cls, valores):
        return _exigir_una_condicion(valores)

    @field_validator("destinatarios")
    @classmethod
    def _correos_unicos(cls, valores):
        correos = [str(c).lower() for c in valores]
        if len(correos) != len(set(correos)) or any(len(c) > 150 for c in correos):
            raise ValueError("Los destinatarios deben ser distintos y tener hasta 150 caracteres")
        return correos

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


class DestinatarioCrear(BaseModel):
    correo: EmailStr = Field(max_length=150)


class AlarmaActualizar(BaseModel):
    estado: str | None = Field(default=None, pattern="^(Activa|Inactiva)$")
    # HU29 v1.0: si llega, exactamente una (reemplaza a las anteriores).
    condiciones: list[CondicionAlarmaCrear] | None = None

    @field_validator("condiciones")
    @classmethod
    def _una_condicion(cls, valores):
        return _exigir_una_condicion(valores)


# ── HU30 (PP-75): configurar notificaciones ─────────────────────────────────
#
# CA1: el panel muestra los canales disponibles y los destinatarios actuales.
# En v1.0 el único canal disponible es el correo (Diccionario de Datos,
# DESTINATARIO_ALARMA: "correos destinatarios"); Telegram existe en el
# modelo pero no tiene HU que lo habilite, así que se muestra como no
# disponible.


class CanalNotificacion(BaseModel):
    canal: str
    nombre: str
    disponible: bool
    activo: bool


class DestinatarioDetalle(BaseModel):
    id: int
    correo: str


class NotificacionesAlarma(BaseModel):
    id_alrm: int
    alarma: str
    canal_email_activo: bool
    canales: list[CanalNotificacion]
    destinatarios: list[DestinatarioDetalle]
    # Se agrega al activar el canal si la alarma no tiene destinatarios.
    correo_cuenta: str


class NotificacionesGuardar(BaseModel):
    """CA2/CA4: activar o desactivar el canal de correo y GUARDAR.
    StrictBool: "si" o 1 no se aceptan como verdadero."""

    canal_email_activo: StrictBool
