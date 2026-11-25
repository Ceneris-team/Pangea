from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.services.filtros_mediciones import Condiciones, LimiteNumerico, validar_unicas


class ExportacionCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formato: Literal["csv", "xlsx"] = "csv"
    fecha_inicio: AwareDatetime
    fecha_fin: AwareDatetime
    ubicacion_ids: list[int] = Field(default_factory=list, max_length=1000)
    dispositivo_ids: list[int] = Field(default_factory=list, max_length=1000)
    parametro_ids: list[int] = Field(default_factory=list, max_length=1000)
    valor_min: LimiteNumerico | None = None
    valor_max: LimiteNumerico | None = None
    frecuencia_muestreo: int | None = Field(default=None, ge=1, le=525600)
    condiciones: Condiciones = Field(default_factory=list)

    @model_validator(mode="after")
    def validar(self):
        validar_unicas(self.condiciones)
        if self.condiciones and any(
            v is not None for v in (self.valor_min, self.valor_max, self.frecuencia_muestreo)
        ):
            raise ValueError("Usa condiciones por parámetro sin límites globales ni muestreo")
        if self.fecha_fin <= self.fecha_inicio:
            raise ValueError("La fecha final debe ser posterior a la inicial")
        if (
            self.valor_min is not None
            and self.valor_max is not None
            and self.valor_min > self.valor_max
        ):
            raise ValueError("El valor mínimo no puede superar al máximo")
        if any(id_ <= 0 for id_ in self.ubicacion_ids) or any(
            id_ == 0 for ids in (self.dispositivo_ids, self.parametro_ids) for id_ in ids
        ):
            raise ValueError(
                "Los identificadores no pueden ser cero y las ubicaciones deben ser positivas"
            )
        return self


class ExportacionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_exprtcn: int
    frmt: str
    estd: str
    fch_slctd: datetime
    fch_exprcn: datetime | None
    filas: int | None
    bytes_archivo: int | None
    error: str | None
    notificacion_estado: str
