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


class ConexionFTPListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_cnxn: int
    nmbr: str
    hst: str
    prt: int
    usr_ftp: str | None
    rt_rmt: str | None
    frcnc_mnts: int
    estd: str


class ConexionFTPProbarRequest(BaseModel):
    hst: str
    prt: int = 21
    usr_ftp: str
    contrasena_ftp: str
    rt_rmt: str


class ConexionFTPCreate(BaseModel):
    nmbr: str
    hst: str
    prt: int = 21
    usr_ftp: str
    contrasena_ftp: str  # texto plano solo en el request; se cifra antes de guardar
    rt_rmt: str
    frcnc_mnts: int  # 1 = cada minuto, 60 = cada hora (CA HU05)
    id_sd: int | None = None  # requerido si el usuario tiene scope "global"


class ConexionFTPUpdate(BaseModel):
    nmbr: str | None = None
    hst: str | None = None
    prt: int | None = None
    usr_ftp: str | None = None
    contrasena_ftp: str | None = None  # si viene, se re-cifra; si no, se conserva la actual
    rt_rmt: str | None = None
    frcnc_mnts: int | None = None