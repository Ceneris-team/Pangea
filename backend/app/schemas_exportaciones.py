from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ExportacionCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formato: Literal["csv", "xlsx"] = "csv"
    fecha_inicio: AwareDatetime
    fecha_fin: AwareDatetime
    ubicacion_ids: list[int] = Field(default_factory=list, max_length=1000)
    dispositivo_ids: list[int] = Field(default_factory=list, max_length=1000)
    parametro_ids: list[int] = Field(default_factory=list, max_length=1000)
    valor_min: Decimal | None = None
    valor_max: Decimal | None = None
    frecuencia_muestreo: int | None = Field(default=None, ge=1, le=525600)

    @model_validator(mode="after")
    def validar(self):
        if self.fecha_fin <= self.fecha_inicio:
            raise ValueError("La fecha final debe ser posterior a la inicial")
        if (
            self.valor_min is not None
            and self.valor_max is not None
            and self.valor_min > self.valor_max
        ):
            raise ValueError("El valor mínimo no puede superar al máximo")
        if any(
            id_ <= 0
            for ids in (self.ubicacion_ids, self.dispositivo_ids, self.parametro_ids)
            for id_ in ids
        ):
            raise ValueError("Los identificadores deben ser positivos")
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
