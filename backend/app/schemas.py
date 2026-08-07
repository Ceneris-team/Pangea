from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UsuarioListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_usr: int
    nmbr_cmplt: str
    crr: str
    rol_nombre: str
    estd: str


class UsuarioCrear(BaseModel):
    """HU04 CA1: campos del formulario de alta. Teléfono es opcional."""

    nmbr_cmplt: str = Field(min_length=1, max_length=150)
    crr: EmailStr
    rol_nombre: str
    tlfn: str | None = Field(default=None, max_length=20)


class UsuarioCreado(BaseModel):
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


class ArchivoIngestaListItem(BaseModel):
    """HU09 CA1: una fila de la cola de ingesta. estado ya viene traducido
    al lenguaje de negocio de la HU (ver ESTADO_BD_A_NEGOCIO en
    routers/ingesta.py); en BD (archv_ingst.estd) se sigue guardando
    Pendiente/Procesando/Exitoso/Fallido."""

    id_archv: int
    nmbr_archv: str
    datalogger_nombre: str
    fch_dtccn: datetime
    estado: str


class ArchivoIngestaDetalle(BaseModel):
    """HU09 CA3: detalle de un archivo de la cola."""

    id_archv: int
    nmbr_archv: str
    datalogger_nombre: str
    estado: str
    fch_dtccn: datetime
    fch_prcsd: datetime | None
    rgstrs_prcsds: int | None
    mnsj_errr: str | None


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


class MedicionListItem(BaseModel):
    """HU 13: registro de telemetría filtrado por parámetros/ubicaciones."""

    id_lctr: int
    fch_hr: datetime
    id_ubccn: int
    ubicacion_nombre: str
    id_prmtr: int
    parametro_nombre: str
    undd: str
    vlr: float


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


# ---------------------------------------------------------------------------
# HU06 - Mapear formato de marca de sensor
# ---------------------------------------------------------------------------


class ParametroListItem(BaseModel):
    """HU06 CA1: pobla el selector de "parámetro estándar" de la tabla de
    asignación columna -> parámetro."""

    model_config = ConfigDict(from_attributes=True)

    id_prmtr: int
    nmbr: str
    undd: str
    dscrpcn: str | None


class SedeListItem(BaseModel):
    """Pobla el selector de sede del formulario de mapeos (HU06) para
    usuarios con scope 'global', que deben indicar id_sd explícitamente
    (ver _resolver_sede en routers/mapeos.py)."""

    model_config = ConfigDict(from_attributes=True)

    id_sd: int
    nmbr: str


class MapeoColumnaItem(BaseModel):
    """Una fila de la tabla de asignación (mp_clmn).

    indc_clmn es el índice 0-based de la columna sobre el header del
    archivo, no su nombre: los .dat de campo traen headers inconsistentes
    o repetidos y el índice es estable frente a eso (ver mapeo.py).
    """

    model_config = ConfigDict(from_attributes=True)

    indc_clmn: int = Field(ge=0)
    id_prmtr: int


class MapeoColumnaDetalle(MapeoColumnaItem):
    """Igual que MapeoColumnaItem pero con el parámetro ya resuelto, para
    que el frontend no tenga que cruzar contra GET /parametros."""

    parametro_nombre: str
    parametro_unidad: str


class MapeoFormatoBase(BaseModel):
    mrc: str = Field(min_length=1, max_length=100)  # obligatorio: nombre de marca
    tp_trm: str = Field(default="H")  # 'H' datos periódicos / 'E' eventos
    dlmtdr: str  # obligatorio: coma, punto y coma, tabulador o espacio
    fl_inc_dts: int = Field(default=1, ge=1)  # entero, default 1
    frmt_fch: str = Field(min_length=1, max_length=50)  # "YYYY-MM-DD HH:mm:ss"


class MapeoFormatoCrear(MapeoFormatoBase):
    id_sd: int | None = None  # requerido solo si el usuario tiene scope "global"
    columnas: list[MapeoColumnaItem] = Field(default_factory=list)


class MapeoFormatoActualizar(BaseModel):
    """Todos los campos opcionales: CA4 pide "modifica un campo" y
    actualiza. Si `columnas` viene, reemplaza la tabla de asignación
    completa; si se omite, las mp_clmn actuales se conservan."""

    mrc: str | None = Field(default=None, min_length=1, max_length=100)
    tp_trm: str | None = None
    dlmtdr: str | None = None
    fl_inc_dts: int | None = Field(default=None, ge=1)
    frmt_fch: str | None = Field(default=None, min_length=1, max_length=50)
    estd: str | None = None
    columnas: list[MapeoColumnaItem] | None = None


class MapeoFormatoListItem(BaseModel):
    """CA5: el listado muestra el mapeo asociado a su marca."""

    model_config = ConfigDict(from_attributes=True)

    id_mp: int
    id_sd: int
    mrc: str
    tp_trm: str
    dlmtdr: str
    fl_inc_dts: int
    frmt_fch: str
    estd: str
    total_columnas: int


class MapeoFormatoDetalle(MapeoFormatoListItem):
    """CA4: al abrir un mapeo existente se necesita también su tabla de
    asignación para poder editarla."""

    columnas: list[MapeoColumnaDetalle]


class FilaVistaPrevia(BaseModel):
    numero_fila: int
    fecha_hora: str | None
    error: str | None
    # nombre de columna del header -> valor crudo de esa fila
    valores: dict[str, str | None]


class ColumnaVistaPrevia(BaseModel):
    """Una columna del header del archivo de muestra, con el parámetro
    estándar que el mapeo en edición le asigna (o None si no tiene)."""

    indc_clmn: int
    nombre_columna: str
    parametro_nombre: str | None
    parametro_unidad: str | None


class VistaPreviaResponse(BaseModel):
    """CA2: primeras 10 filas interpretadas según el mapeo, con el
    parámetro estándar asignado a cada columna. El archivo de muestra NO
    se persiste (regla explícita de la HU)."""

    columnas: list[ColumnaVistaPrevia]
    filas: list[FilaVistaPrevia]
    total_filas_archivo: int
    filas_mostradas: int
