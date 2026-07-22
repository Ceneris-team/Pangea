from pydantic import BaseModel, ConfigDict


class UsuarioListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_usr: int
    nmbr_cmplt: str
    crr: str
    rol_nombre: str
    estd: str


class UbicacionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_ubccn: int
    nmbr: str
    dscrpcn: str | None
    lttd: float
    lngtd: float
    estd: str


class ListadoPaginado(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    items: list


class MetricasColaIngesta(BaseModel):
    """HU 09: conteo de archv_ingst agrupado por estado, para el módulo
    de monitoreo de la cola de procesamiento (HT-05, CA3)."""
    pendientes: int
    procesando: int
    exitosos: int
    fallidos: int
    total: int
