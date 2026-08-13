from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _validar_ruta_remota(valor: str) -> str:
    """HU05: 'El directorio remoto es una cadena de texto tipo ruta,
    por ejemplo /datos/estacion01.'"""
    if not valor.startswith("/"):
        raise ValueError("El directorio remoto debe ser una ruta absoluta (ej. /datos/estacion01)")
    return valor


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
    """HU04 CA2: el usuario recién creado, con el mensaje de éxito que la
    interfaz muestra tras guardar. Mismo patrón de respuesta que usan
    HU05/HU06/HU08/HU11 al crear un recurso ({"mensaje": ..., ...})."""

    model_config = ConfigDict(from_attributes=True)

    mensaje: str = "Usuario creado exitosamente"
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


class UbicacionDetalle(UbicacionListItem):
    """Ficha de una ubicación: lo mismo que el listado (HU07) más el
    polígono, para poder mostrar el contorno en un mapa de detalle."""

    id_sd: int
    plgn_gjsn: dict


class UbicacionCrear(BaseModel):
    """HU08 CA1/CA2: campos del formulario de alta de ubicación.

    Geometría: un DISPOSITIVO se ubica con un punto GPS simple, pero una
    UBICACIÓN (zona/sede) se delimita con un polígono GeoJSON de varios
    vértices, para representar el contorno real e irregular del terreno.
    Por eso van los dos campos y los dos son obligatorios: lttd/lngtd es
    el punto de referencia (centro) y plgn_gjsn el contorno. El modelo
    Ubicacion declara plgn_gjsn NOT NULL, así que omitirlo reventaría
    como IntegrityError; se valida acá para dar el mensaje claro.

    Los rangos de lat/lng ya los garantizan los CheckConstraint
    ubccn_lttd_check / ubccn_lngtd_check, pero se repiten en Pydantic
    para responder 422 con la causa real antes de tocar la BD.
    """

    nmbr: str = Field(min_length=1, max_length=150)
    dscrpcn: str | None = Field(default=None, max_length=300)
    lttd: float = Field(ge=-90, le=90)
    lngtd: float = Field(ge=-180, le=180)
    plgn_gjsn: dict
    id_sd: int | None = None  # requerido solo si el usuario tiene scope "global"

    @field_validator("nmbr")
    @classmethod
    def _nombre_no_vacio(cls, valor: str) -> str:
        """Un nombre de solo espacios pasa min_length=1 pero no es un
        nombre: se normaliza acá para que el UNIQUE por sede compare
        siempre el valor ya recortado."""
        recortado = valor.strip()
        if not recortado:
            raise ValueError("El nombre es obligatorio")
        return recortado

    @field_validator("plgn_gjsn")
    @classmethod
    def _poligono_valido(cls, valor: dict) -> dict:
        """Valida la forma mínima de un GeoJSON Polygon: un anillo
        exterior cerrado (primer vértice == último) de al menos 3 vértices
        distintos, con coordenadas en rango. Sin esto entraría a JSONB
        cualquier objeto -incluido `{}`- y el campo dejaría de significar
        "el contorno de la zona"."""
        if valor.get("type") != "Polygon":
            raise ValueError("El polígono debe ser un GeoJSON de tipo 'Polygon'")

        anillos = valor.get("coordinates")
        if not isinstance(anillos, list) or not anillos:
            raise ValueError("El polígono debe tener al menos un anillo de coordenadas")

        exterior = anillos[0]
        if not isinstance(exterior, list) or len(exterior) < 4:
            raise ValueError(
                "El polígono debe tener al menos 3 vértices para delimitar la zona"
            )

        for vertice in exterior:
            if not isinstance(vertice, (list, tuple)) or len(vertice) < 2:
                raise ValueError("Cada vértice del polígono debe ser un par [lng, lat]")
            lng, lat = vertice[0], vertice[1]
            if not isinstance(lng, (int, float)) or not isinstance(lat, (int, float)):
                raise ValueError("Las coordenadas del polígono deben ser numéricas")
            # GeoJSON usa el orden [longitud, latitud], no [lat, lng].
            if not -180 <= lng <= 180:
                raise ValueError("La longitud de cada vértice debe estar entre -180 y 180")
            if not -90 <= lat <= 90:
                raise ValueError("La latitud de cada vértice debe estar entre -90 y 90")

        if list(exterior[0][:2]) != list(exterior[-1][:2]):
            raise ValueError(
                "El polígono debe estar cerrado: el último vértice debe coincidir con el primero"
            )

        return valor


class UbicacionCreada(BaseModel):
    """HU08 CA2: la ubicación recién registrada, con el estado 'Activa'
    que le puso el server_default del modelo."""

    model_config = ConfigDict(from_attributes=True)

    id_ubccn: int
    id_sd: int
    nmbr: str
    dscrpcn: str | None
    lttd: float
    lngtd: float
    plgn_gjsn: dict
    estd: str


class ListadoPaginado(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    items: list


# HU10 - Listar dispositivos


class DispositivoListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_dspstv: int
    nmbr: str
    mrc: str
    ubicacion_nombre: str
    estd: str


# HU11 - Añadir dispositivo


class DispositivoCrear(BaseModel):
    """HU11 CA1: campos del formulario (Nombre, Marca, Modelo opcional,
    Ubicación, Conexión FTP). id_mp (mapeo de formato) y lttd/lngtd NO son
    campos del formulario: el router los resuelve/copia automáticamente
    (ver docstring de crear_dispositivo en routers/dispositivos.py)."""

    nmbr: str = Field(min_length=1, max_length=150)
    mrc: str = Field(min_length=1, max_length=100)
    mdl: str | None = None
    id_ubccn: int
    id_cnxn: int


class DispositivoCreado(BaseModel):
    """HU11 CA2: el dispositivo recién registrado, con el estado 'Activo'
    que le puso el server_default del modelo. Misma forma que
    UbicacionCreada (HU08)."""

    model_config = ConfigDict(from_attributes=True)

    id_dspstv: int
    id_ubccn: int
    id_cnxn: int
    nmbr: str
    mrc: str
    mdl: str | None
    lttd: float
    lngtd: float
    estd: str


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

    _validar_rt_rmt = field_validator("rt_rmt")(_validar_ruta_remota)


class ConexionFTPCreate(BaseModel):
    nmbr: str
    hst: str
    prt: int = 21
    usr_ftp: str
    contrasena_ftp: str  # texto plano solo en el request; se cifra antes de guardar
    rt_rmt: str
    frcnc_mnts: int  # 1 = cada minuto, 60 = cada hora (CA HU05)
    id_sd: int | None = None  # requerido si el usuario tiene scope "global"

    _validar_rt_rmt = field_validator("rt_rmt")(_validar_ruta_remota)


class ConexionFTPUpdate(BaseModel):
    nmbr: str | None = None
    hst: str | None = None
    prt: int | None = None
    usr_ftp: str | None = None
    contrasena_ftp: str | None = None  # si viene, se re-cifra; si no, se conserva la actual
    rt_rmt: str | None = None
    frcnc_mnts: int | None = None

    @field_validator("rt_rmt")
    @classmethod
    def _validar_rt_rmt(cls, valor: str | None) -> str | None:
        if valor is None:
            return valor
        return _validar_ruta_remota(valor)


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


class ParametroCrear(BaseModel):
    """Alta de un parámetro estándar nuevo en el catálogo (prmtr), para que
    el Técnico CENERIS no dependa de un INSERT manual cuando un mapeo
    necesita un parámetro que todavía no existe."""

    nmbr: str = Field(..., min_length=1, max_length=100)
    undd: str = Field(..., min_length=1, max_length=30)
    dscrpcn: str | None = Field(default=None, max_length=200)

    @field_validator("nmbr", "undd")
    @classmethod
    def _no_vacio(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("No puede estar vacío")
        return valor


class SedeListItem(BaseModel):
    """Pobla el selector de sede de formularios donde un usuario con scope
    'global' debe indicar id_sd explícitamente (Agregar Ubicación,
    Conexiones FTP)."""

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
    tp_trm: str = Field(default="H")  # 'H' datos periódicos / 'E' eventos
    dlmtdr: str  # obligatorio: coma, punto y coma, tabulador o espacio
    fl_inc_dts: int = Field(default=1, ge=1)  # entero, default 1
    frmt_fch: str = Field(min_length=1, max_length=50)  # "YYYY-MM-DD HH:mm:ss"


class MapeoFormatoCrear(MapeoFormatoBase):
    id_dspstv: int  # el dispositivo al que pertenece este mapeo
    columnas: list[MapeoColumnaItem] = Field(default_factory=list)


class MapeoFormatoActualizar(BaseModel):
    """Todos los campos opcionales: CA4 pide "modifica un campo" y
    actualiza. Si `columnas` viene, reemplaza la tabla de asignación
    completa; si se omite, las mp_clmn actuales se conservan.

    id_dspstv NO es editable: un mapeo no cambia de dueño, se crea otro
    para el nuevo dispositivo."""

    tp_trm: str | None = None
    dlmtdr: str | None = None
    fl_inc_dts: int | None = Field(default=None, ge=1)
    frmt_fch: str | None = Field(default=None, min_length=1, max_length=50)
    estd: str | None = None
    columnas: list[MapeoColumnaItem] | None = None


class MapeoFormatoListItem(BaseModel):
    """CA5: el listado muestra el mapeo asociado a su dispositivo."""

    model_config = ConfigDict(from_attributes=True)

    id_mp: int
    id_dspstv: int
    dispositivo_nombre: str
    dispositivo_marca: str
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
    estándar que el mapeo en edición le asigna (o None si no tiene).

    parametro_nombre/parametro_unidad reflejan una asignación YA
    CONFIRMADA (viene en `asignaciones`, ver _parsear_asignaciones).
    id_prmtr_sugerido es distinto: una sugerencia automática por
    coincidencia de nombre de columna, para prellenar el selector en el
    frontend -nunca se guarda sola, el usuario debe confirmarla al
    guardar el mapeo (ver diseño en la conversación de HU06)."""

    indc_clmn: int
    nombre_columna: str
    parametro_nombre: str | None
    parametro_unidad: str | None
    id_prmtr_sugerido: int | None = None


class DispositivoParaMapeo(BaseModel):
    """Selector de dispositivo para traer un .dat ya recibido por FTP en
    vez de subirlo a mano (ver GET /mapeos/dispositivos)."""

    model_config = ConfigDict(from_attributes=True)

    id_dspstv: int
    nmbr: str
    mrc: str
    mdl: str | None


class ArchivoFtpDisponible(BaseModel):
    """Un .dat listado en la carpeta remota de la conexión FTP de un
    dispositivo (ver GET /mapeos/dispositivos/{id}/archivos-ftp)."""

    nombre_archivo: str


class VistaPreviaResponse(BaseModel):
    """CA2: primeras 10 filas interpretadas según el mapeo, con el
    parámetro estándar asignado a cada columna. El archivo de muestra NO
    se persiste (regla explícita de la HU)."""

    columnas: list[ColumnaVistaPrevia]
    filas: list[FilaVistaPrevia]
    total_filas_archivo: int
    filas_mostradas: int
