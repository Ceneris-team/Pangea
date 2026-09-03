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


class UbicacionParaMapa(UbicacionListItem):
    """HU22: una ubicación tal como la necesita la vista de mapa.

    Trae de una sola vez lo que el mapa pinta y lo que el panel emergente
    muestra al hacer clic en un marcador (CA2): los campos del listado
    (nombre, descripción, estado y el punto lttd/lngtd) más el polígono y
    el conteo de dispositivos.

    Por qué un schema propio y no agregar los campos a UbicacionListItem:
    UbicacionDetalle HEREDA de UbicacionListItem, así que cualquier campo
    agregado al padre se filtraría también a GET /ubicaciones/{id}, que no
    lo necesita -y el conteo obligaría a ese endpoint a hacer un JOIN que
    hoy no hace-. Acá el costo se paga solo en el endpoint que lo usa.
    """

    plgn_gjsn: dict
    # CA2: "la cantidad de dispositivos asociados". Se calcula con un
    # LEFT JOIN + COUNT en el router; una ubicación sin dispositivos
    # cuenta 0, no se omite del mapa.
    dispositivos_count: int


# Los dos estados que maneja una Ubicación (mismos valores que ofrece el
# filtro del listado, HU07, y que pone el server_default 'Activa').
ESTADOS_UBICACION = ("Activa", "Inactiva")


def _validar_nombre_ubicacion(valor: str) -> str:
    """Un nombre de solo espacios pasa min_length=1 pero no es un nombre:
    se normaliza acá para que el UNIQUE por sede compare siempre el valor
    ya recortado.

    Vive fuera de la clase porque el alta (UbicacionCrear) y la edición
    (UbicacionActualizar) exigen exactamente la misma regla; duplicarla
    invitaría a que una de las dos se quede atrás al cambiarla.
    """
    recortado = valor.strip()
    if not recortado:
        raise ValueError("El nombre es obligatorio")
    return recortado


def _validar_poligono_geojson(valor: dict) -> dict:
    """Valida la forma mínima de un GeoJSON Polygon: un anillo exterior
    cerrado (primer vértice == último) de al menos 3 vértices distintos,
    con coordenadas en rango. Sin esto entraría a JSONB cualquier objeto
    -incluido `{}`- y el campo dejaría de significar "el contorno de la
    zona".

    Compartida entre el alta y la edición por el mismo motivo que
    _validar_nombre_ubicacion: es una sola regla de negocio.
    """
    if valor.get("type") != "Polygon":
        raise ValueError("El polígono debe ser un GeoJSON de tipo 'Polygon'")

    anillos = valor.get("coordinates")
    if not isinstance(anillos, list) or not anillos:
        raise ValueError("El polígono debe tener al menos un anillo de coordenadas")

    exterior = anillos[0]
    if not isinstance(exterior, list) or len(exterior) < 4:
        raise ValueError("El polígono debe tener al menos 3 vértices para delimitar la zona")

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
        return _validar_nombre_ubicacion(valor)

    @field_validator("plgn_gjsn")
    @classmethod
    def _poligono_valido(cls, valor: dict) -> dict:
        return _validar_poligono_geojson(valor)


class UbicacionActualizar(BaseModel):
    """HU08 (ampliación): edición de una ubicación existente.

    Todos los campos son opcionales -solo se actualiza lo que venga, mismo
    patrón que ConexionFTPUpdate y DispositivoUpdate-, y reusan las mismas
    validaciones del alta vía _validar_nombre_ubicacion /
    _validar_poligono_geojson.

    id_sd NO está y no debe estarlo: mover una ubicación de sede es un
    cambio de jerarquía administrativa (Cliente -> Sede), no una edición
    de la zona. Además arrastraría a sus dispositivos y a los permisos por
    sede ya concedidos sobre ella. Al no declararse acá, Pydantic lo
    descarta del body en vez de aplicarlo en silencio.

    Ojo con el None: significa "no lo mandes, no lo toques"
    (exclude_unset lo filtra en el router), NO "ponlo en NULL" -salvo
    dscrpcn, la única columna que sí admite NULL-.
    """

    nmbr: str | None = Field(default=None, min_length=1, max_length=150)
    dscrpcn: str | None = Field(default=None, max_length=300)
    lttd: float | None = Field(default=None, ge=-90, le=90)
    lngtd: float | None = Field(default=None, ge=-180, le=180)
    plgn_gjsn: dict | None = None
    estd: str | None = None

    @field_validator("nmbr")
    @classmethod
    def _nombre_no_vacio(cls, valor: str | None) -> str | None:
        if valor is None:
            return valor
        return _validar_nombre_ubicacion(valor)

    @field_validator("plgn_gjsn")
    @classmethod
    def _poligono_valido(cls, valor: dict | None) -> dict | None:
        if valor is None:
            return valor
        return _validar_poligono_geojson(valor)

    @field_validator("estd")
    @classmethod
    def _estado_valido(cls, valor: str | None) -> str | None:
        """Los mismos dos estados que ofrece el filtro del listado (HU07).
        La columna es un String(20) sin CHECK, así que sin esto entraría
        cualquier texto y el filtro dejaría de encontrar el registro."""
        if valor is None:
            return valor
        if valor not in ESTADOS_UBICACION:
            raise ValueError(f"El estado debe ser uno de: {', '.join(ESTADOS_UBICACION)}")
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


class DispositivoParaMapa(BaseModel):
    """I-17: un dispositivo tal como lo necesita la vista de mapa (HU22).

    Trae su punto GPS propio (DEC-28) para pintarlo dentro del polígono de
    su ubicación, más lo que muestra el panel al hacer clic: nombre, marca
    y estado.

    Schema propio y no una extensión de DispositivoListItem porque ese es
    el del listado de HU10, que no necesita coordenadas -y agregárselas lo
    obligaría a cargar columnas que su tabla no muestra-. Mismo criterio
    que se usó con UbicacionParaMapa.

    id_ubccn viaja para que el frontend pueda relacionar cada punto con su
    zona sin una segunda consulta.
    """

    model_config = ConfigDict(from_attributes=True)

    id_dspstv: int
    id_ubccn: int
    nmbr: str
    mrc: str
    estd: str
    lttd: float
    lngtd: float


# HU11 - Añadir dispositivo


class DispositivoCrear(BaseModel):
    """HU11 CA1: campos del formulario (Nombre, Marca, Modelo opcional,
    Ubicación, Conexión FTP).

    DEC-28: lttd/lngtd son el punto GPS PROPIO del dispositivo, no una
    copia del centro de su Ubicación. Van opcionales y no obligatorios
    porque las columnas ya existían llenándose por copia: exigirlos ahora
    rompería todo cliente y test que hoy crea dispositivos sin
    coordenadas. Si no se envían, crear_dispositivo cae al centro de la
    Ubicación (mismo comportamiento previo) y el equipo migra gradual.

    Los rangos ya los garantizan los CheckConstraint dspstv_lttd_check /
    dspstv_lngtd_check, pero se repiten en Pydantic para responder 422 con
    la causa real antes de tocar la BD -mismo criterio que UbicacionCrear-.

    DEC-09: el dispositivo ya no necesita un mapeo de formato previo para
    crearse; el mapeo se configura después, apuntando a este dispositivo."""

    nmbr: str = Field(min_length=1, max_length=150)
    mrc: str = Field(min_length=1, max_length=100)
    mdl: str | None = None
    id_ubccn: int
    id_cnxn: int
    lttd: float | None = Field(default=None, ge=-90, le=90)
    lngtd: float | None = Field(default=None, ge=-180, le=180)


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


class DispositivoUpdate(BaseModel):
    """Edición desde la ficha del dispositivo: nombre, marca, modelo,
    punto GPS y reasignación de Conexión FTP. Todos opcionales (solo se
    actualiza lo que venga, mismo patrón que ConexionFTPUpdate).

    DEC-28: lttd/lngtd pasan a ser editables -antes estaban bloqueados
    porque el punto se heredaba de la Ubicación y editarlo no tenía
    sentido-. id_ubccn sigue sin ser editable acá: cambiar de ubicación
    implicaría revalidar el punto contra el polígono de la nueva zona,
    fuera de este alcance.

    Ojo con el None: para estos dos campos significa "no lo mandes, no lo
    toques" (exclude_unset lo filtra en el router), NO "ponlo en NULL" -las
    columnas son NOT NULL-."""

    nmbr: str | None = Field(default=None, min_length=1, max_length=150)
    mrc: str | None = Field(default=None, min_length=1, max_length=100)
    mdl: str | None = None
    id_cnxn: int | None = None
    lttd: float | None = Field(default=None, ge=-90, le=90)
    lngtd: float | None = Field(default=None, ge=-180, le=180)


# DEC-09 / IMP-06 - Ficha del dispositivo (pestañas Formato, Datos,
# Carga de datos, Carga manual y Logs)


class DispositivoDetalle(BaseModel):
    """Cabecera de la ficha del dispositivo: los datos propios más el
    contexto (ubicación, sede, conexión) que las pestañas muestran como
    referencia de solo lectura.

    frcnc_mnts viene de la Conexión FTP (HU05) y se expone SOLO para
    lectura: el intervalo de polling se edita en la conexión, y
    duplicarlo acá crearía una segunda fuente de verdad."""

    model_config = ConfigDict(from_attributes=True)

    id_dspstv: int
    nmbr: str
    mrc: str
    mdl: str | None
    estd: str
    # DEC-28: el punto GPS propio del dispositivo. Va en la ficha para que
    # el formulario de edición pueda precargarlo -sin esto no habría con
    # qué llenar los campos antes de editarlos-.
    lttd: float
    lngtd: float
    id_ubccn: int
    ubicacion_nombre: str
    id_sd: int
    id_cnxn: int
    conexion_nombre: str
    conexion_frcnc_mnts: int


class CargaManualItem(BaseModel):
    """Un valor de un parámetro para el punto de carga manual."""

    id_prmtr: int
    vlr: float


class CargaManualRequest(BaseModel):
    """IMP-06: alta de UN punto de telemetría capturado a mano, sin
    archivo de por medio.

    Solo aplica a la trama 'H' (datos periódicos): un evento 'E' no es una
    medición puntual de parámetros, así que la ficha no ofrece carga
    manual para ese tipo de trama.

    fch_hr la escribe el usuario -es el momento de la MEDICIÓN, no el de
    la captura-, así que no se puede derivar del reloj del servidor."""

    fch_hr: datetime
    valores: list[CargaManualItem] = Field(min_length=1)


class LogIngestaListItem(BaseModel):
    """Una fila de archv_ingst (HU09) vista desde la ficha del
    dispositivo, filtrada por su conexión FTP."""

    model_config = ConfigDict(from_attributes=True)

    id_archv: int
    nmbr_archv: str
    estd: str
    fch_dtccn: datetime
    fch_prcsd: datetime | None
    mnsj_errr: str | None
    rgstrs_prcsds: int | None


class DispositivoEstadisticas(BaseModel):
    """HU19: panel de estadísticas de un dispositivo, calculado sobre
    archv_ingst (HU09) dentro del rango de fechas pedido. Los cuatro
    indicadores son enteros (CA: 'se muestran como valores numéricos
    enteros').

    id_cnxn/id_ubccn viajan en la respuesta para que el frontend arme los
    dos botones de redirección (CA3/CA4: 'VER COLA DE PROCESAMIENTO' hacia
    /cola-ingesta filtrado por conexión, 'VER HISTORIAL DE DATOS' hacia
    /consulta-datos filtrado por ubicación) sin una segunda llamada a la
    ficha del dispositivo."""

    total_recibidos: int
    total_procesados: int
    total_fallidos: int
    ultima_fecha_recepcion: datetime | None
    fecha_inicio: datetime
    fecha_fin: datetime
    id_cnxn: int
    id_ubccn: int


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


class FilaCrudaIngesta(BaseModel):
    """Una línea del .dat tal como llegó, ANTES del mapeo columna->
    parámetro: permite ver si el datalogger mandó la fila vacía/en cero o
    con datos reales, algo que se pierde una vez interpretada (una
    columna sin mapeo ni siquiera llega a tlmtr/evnt_txt)."""

    numero_fila: int
    fecha_hora: str | None
    error: str | None
    valores: dict[str, str | None]


class RegistrosIngestaResponse(BaseModel):
    """Vista previa acotada (no pretende ser exhaustiva) del contenido
    crudo del .dat, re-descargado desde el FTP de origen -no se persiste
    en la cola, ver HU09-. `columnas` es el header en orden; cada fila de
    `filas` trae el mismo valor crudo que recibió el mapeo, sin castear."""

    columnas: list[str]
    total_filas_archivo: int
    filas_mostradas: int
    filas: list[FilaCrudaIngesta]


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
    """HU 13: registro de telemetría filtrado por parámetros/ubicaciones.

    Combina tlmtr (parámetros 'numerico', vlr float) y evnt_txt
    (parámetros 'texto', ej. "Puerta Abierta"): ambos son lecturas de un
    dispositivo mapeado, y antes de esto un parámetro de texto se podía
    seleccionar en el filtro pero nunca aparecía en la tabla (guardaba
    en evnt_txt, que este endpoint no consultaba). id_registro es
    id_lctr o id_evnt según origen -no se puede usar un solo id_lctr
    porque son secuencias distintas y podrían colisionar como key de
    React-."""

    id_registro: int
    fch_hr: datetime
    id_ubccn: int
    ubicacion_nombre: str
    id_prmtr: int
    parametro_nombre: str
    undd: str
    vlr: float | str


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
    tipo_dato: str


class ParametroCrear(BaseModel):
    """Alta de un parámetro estándar nuevo en el catálogo (prmtr), para que
    el Técnico CENERIS no dependa de un INSERT manual cuando un mapeo
    necesita un parámetro que todavía no existe.

    tipo_dato: 'numerico' (default, va a tlmtr) o 'texto' (va a evnt_txt,
    ver app.models.evento_texto) -para eventos como "Puerta Abierta" que
    no son una medición y no admiten float()."""

    nmbr: str = Field(..., min_length=1, max_length=100)
    undd: str = Field(..., min_length=1, max_length=30)
    dscrpcn: str | None = Field(default=None, max_length=200)
    tipo_dato: str = Field(default="numerico")

    @field_validator("nmbr", "undd")
    @classmethod
    def _no_vacio(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("No puede estar vacío")
        return valor

    @field_validator("tipo_dato")
    @classmethod
    def _tipo_dato_valido(cls, valor: str) -> str:
        if valor not in ("numerico", "texto"):
            raise ValueError("tipo_dato debe ser 'numerico' o 'texto'")
        return valor


class ParametroActualizar(BaseModel):
    """Todos los campos opcionales: se edita solo lo que cambia, mismo
    criterio que MapeoFormatoActualizar.

    tipo_dato NO se puede editar acá a propósito: si el parámetro ya
    tiene lecturas guardadas, cambiarlo dejaría datos mezclados entre
    tlmtr y evnt_txt bajo el mismo id_prmtr. Se define una sola vez al
    crear (ParametroCrear); si se necesita el otro tipo, se crea un
    parámetro nuevo."""

    nmbr: str | None = Field(default=None, min_length=1, max_length=100)
    undd: str | None = Field(default=None, min_length=1, max_length=30)
    dscrpcn: str | None = Field(default=None, max_length=200)

    @field_validator("nmbr", "undd")
    @classmethod
    def _no_vacio(cls, valor: str | None) -> str | None:
        if valor is None:
            return valor
        valor = valor.strip()
        if not valor:
            raise ValueError("No puede estar vacío")
        return valor


class ListadoParametros(BaseModel):
    """Paginado: el catálogo puede crecer bastante (un parámetro por cada
    variable física que mide algún dataloger), y listarlo entero en cada
    carga de la pantalla no escala."""

    total: int
    pagina: int
    por_pagina: int
    items: list[ParametroListItem]


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
    tp_trm: str = Field(default="H")  # letra libre A-Z; 'H'/'E'/'P' son solo las frecuentes
    # Descripción corta y libre de qué es esta trama (p. ej. "Nivel de
    # napa"). Sin catálogo cerrado de tp_trm, es lo único que explica qué
    # significa una letra que no es H/E/P.
    dscrpcn: str | None = Field(default=None, max_length=200)
    dlmtdr: str  # obligatorio: coma, punto y coma, tabulador o espacio
    # Separador decimal del dato numérico, no de las columnas. Default '.'
    # = comportamiento previo a DEC-09, para los mapeos ya cargados.
    dlmtdr_dcml: str = Field(default=".")
    fl_inc_dts: int = Field(default=1, ge=1)  # entero, default 1
    frmt_fch: str = Field(min_length=1, max_length=50)  # "YYYY-MM-DD HH:mm:ss"


class MapeoFormatoCrear(MapeoFormatoBase):
    """DEC-09: el mapeo se cuelga de un DISPOSITIVO concreto, no de
    sede+marca. La marca y la sede se derivan del dispositivo elegido, así
    que ya no son campos del formulario."""

    id_dspstv: int
    columnas: list[MapeoColumnaItem] = Field(default_factory=list)


class MapeoFormatoActualizar(BaseModel):
    """Todos los campos opcionales: CA4 pide "modifica un campo" y
    actualiza. Si `columnas` viene, reemplaza la tabla de asignación
    completa; si se omite, las mp_clmn actuales se conservan.

    DEC-09: `mrc` ya no se edita acá (es del dispositivo). Mover un mapeo
    a otro dispositivo tampoco se permite: se crea uno nuevo en el
    dispositivo correcto."""

    tp_trm: str | None = None
    dscrpcn: str | None = Field(default=None, max_length=200)
    dlmtdr: str | None = None
    dlmtdr_dcml: str | None = None
    fl_inc_dts: int | None = Field(default=None, ge=1)
    frmt_fch: str | None = Field(default=None, min_length=1, max_length=50)
    estd: str | None = None
    columnas: list[MapeoColumnaItem] | None = None


class MapeoFormatoListItem(BaseModel):
    """CA5: el listado muestra el mapeo asociado a su dispositivo.

    DEC-09: id_sd y mrc ya no son columnas de mp_frmt; se derivan por JOIN
    (mp_frmt -> dspstv -> ubccn) y se exponen igual para que la tabla del
    frontend siga mostrando Marca y Sede."""

    model_config = ConfigDict(from_attributes=True)

    id_mp: int
    id_dspstv: int
    dispositivo_nombre: str
    id_sd: int
    mrc: str
    tp_trm: str
    dscrpcn: str | None
    dlmtdr: str
    dlmtdr_dcml: str
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
    # True si el parámetro asignado es 'numerico' pero al menos una fila
    # de la MUESTRA trae un valor no numérico en esta columna (ej. "Modo
    # Normal" contra un parámetro numérico): esas filas se perderían en
    # la ingesta real, igual que perdía MensajeP/MensajeA antes de que
    # existiera prmtr.tipo_dato. Se avisa acá, antes de guardar, en vez
    # de que el técnico lo descubra después con datos faltantes en la
    # cola de ingesta.
    tipo_dato_incompatible: bool = False


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


# HU27 - Listar alarmas


class AlarmaListItem(BaseModel):
    """Una fila del listado de HU27: 'nombre de la alarma, parámetro
    asociado, condición, estado y acciones'. 'acciones' no viaja como dato
    -son los botones que arma el frontend a partir de id_alrm/estd-.

    condicion es None cuando la alarma todavía no tiene una condición
    configurada (HU29 es un requerimiento aparte): el detalle de HU27 no
    contempla ese caso, pero el modelo sí lo permite -una alrm puede
    existir sin fila en cndcn_alrm todavía-, así que el frontend lo
    muestra como 'Sin condición configurada' en vez de reventar."""

    model_config = ConfigDict(from_attributes=True)

    id_alrm: int
    nmbr: str
    parametro_nombre: str
    condicion: str | None
    estd: str
    filas_mostradas: int
