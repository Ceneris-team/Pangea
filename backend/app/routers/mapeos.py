"""
HU 06 - Mapear formato de dispositivo (CRUD + vista previa)

El MOTOR de mapeo ya existía y está en uso por el pipeline de ingesta
(`app/services/ingesta/mapeo.py` y `parser.py`); lo que agrega este router
es la capa que permite crear y editar los mapeos desde la interfaz, en vez
de insertarlos a mano en la base de datos.

El mapeo cuelga del DISPOSITIVO (mp_frmt.id_dspstv), no de la marca: dos
dispositivos de la misma marca pueden traer sus columnas en distinto
orden en campo, así que un mapeo compartido por marca no representa eso.
El dispositivo se crea primero (HU11, sin requerir mapeo); su mapeo se
configura después, desde acá.

Cobertura de los CA:

  CA1  GET /parametros                -> pobla el selector de parámetro
                                         estándar de la tabla de asignación
  CA2  POST /mapeos/vista-previa      -> primeras 10 filas del .dat de
                                         muestra interpretadas con el mapeo
  CA3  POST /mapeos                   -> "Mapeo guardado correctamente"
  CA4  PUT  /mapeos/{id_mp}           -> "Mapeo actualizado correctamente"
  CA5  GET  /mapeos, GET /mapeos/{id} -> listado y detalle

Acceso: solo Técnico CENERIS y Administrador, vía require_permiso sobre el
módulo 'Ingesta' (es el módulo del CHECK constraint de prms_usr_sd que
corresponde a la configuración de la ingesta; no existe un módulo
'Mapeos'). Lectura para consultar, Edición para crear/actualizar.
"""

import csv
import ftplib
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.ingesta.ftp_receptor import descargar_archivo_dat, listar_archivos_dat
from app.models import (
    ConexionFTP, Dispositivo, MapeoColumna, MapeoFormato, Parametro, Sede, Ubicacion,
)
from app.security.permisos import (
    require_permiso, require_alguno_permiso, verificar_sede, LECTURA, EDICION,
)
from app.services.ingesta.parser import ConfiguracionParseo, parsear_dat
from app.tasks.ingesta import normalizar_contenido_dat
from app.schemas import (
    ArchivoFtpDisponible,
    ColumnaVistaPrevia,
    DispositivoParaMapeo,
    FilaVistaPrevia,
    ListadoParametros,
    MapeoColumnaDetalle,
    MapeoFormatoActualizar,
    MapeoFormatoCrear,
    MapeoFormatoDetalle,
    MapeoFormatoListItem,
    ParametroActualizar,
    ParametroCrear,
    ParametroListItem,
    SedeListItem,
    VistaPreviaResponse,
)
from app.security.permisos import (
    EDICION,
    LECTURA,
    require_alguno_permiso,
    require_permiso,
    verificar_sede,
)
from app.services.ingesta.parser import ConfiguracionParseo, parsear_dat
from app.tasks.ingesta import normalizar_contenido_dat

router = APIRouter(prefix="/mapeos", tags=["Mapeos de formato"])
router_parametros = APIRouter(prefix="/parametros", tags=["Mapeos de formato"])
router_sedes = APIRouter(prefix="/sedes", tags=["Mapeos de formato"])
router_dispositivos_mapeo = APIRouter(prefix="/mapeos/dispositivos", tags=["Mapeos de formato"])

# Regla de negocio HU06: "El delimitador acepta solo coma, punto y coma,
# tabulador o espacio". La clave es lo que manda el frontend; el valor es
# lo que se guarda en mp_frmt.dlmtdr y entiende el parser (ver
# parser.DELIMITADORES, que ya acepta estos mismos tokens).
DELIMITADORES_VALIDOS = {
    ",": ",",
    ";": ";",
    "tab": "tab",
    "\t": "tab",
    "espacio": "espacio",
    " ": "espacio",
}

# HU06/PP-96: el tipo de trama ya no es un catálogo cerrado (antes era un
# CHECK constraint de mp_frmt con {"H", "E", "P"}) -el equipo de
# telemetría define el prefijo de archivo de cada dataloger según el
# proyecto, y exigir una migración por cada letra nueva no escala. Se
# valida solo el FORMATO acá: una letra A-Z, que es lo que puede preceder
# a un "_" en un nombre de archivo (H_, E_, P_, X_...). Ver
# services/ingesta/mapeo.py: detectar_tipo_trama ya no usa un diccionario
# fijo, resuelve el prefijo contra los mp_frmt activos del dispositivo.
TIPO_TRAMA_PATRON = re.compile(r"^[A-Z]$")

# Separador decimal del dato numérico (DEC-09). Solo punto o coma: son los
# dos que produce un datalogger real, y el CHECK de mp_frmt exige lo mismo.
DELIMITADORES_DECIMALES_VALIDOS = {".", ","}

# HU06: "Formato de fecha/hora: acepta cadenas tipo YYYY-MM-DD HH:mm:ss".
# El motor (parser._parsear_fecha) usa strptime, así que lo que se guarda
# en mp_frmt.frmt_fch es el formato de strptime. Se traduce en la frontera
# para que la UI hable en el lenguaje de la HU y el motor no cambie.
_TOKENS_FECHA = [
    ("YYYY", "%Y"),
    ("YY", "%y"),
    ("MM", "%m"),
    ("DD", "%d"),
    ("HH", "%H"),
    ("mm", "%M"),
    ("ss", "%S"),
]

FILAS_VISTA_PREVIA = 10  # CA2: "muestra las primeras 10 filas"


def a_formato_strptime(formato: str) -> str:
    """ "YYYY-MM-DD HH:mm:ss" -> "%Y-%m-%d %H:%M:%S".

    Si ya viene en formato strptime (contiene '%') se deja pasar tal cual:
    los mapeos sembrados a mano antes de HU06 ya están guardados así.
    """
    if "%" in formato:
        return formato
    resultado = formato
    for token, directiva in _TOKENS_FECHA:
        resultado = resultado.replace(token, directiva)
    return resultado


def a_formato_legible(formato: str) -> str:
    """Inverso de a_formato_strptime, para que el formulario de edición
    (CA4) muestre lo mismo que el usuario escribió al crear."""
    resultado = formato
    for token, directiva in _TOKENS_FECHA:
        resultado = resultado.replace(directiva, token)
    return resultado


def _validar_delimitador(dlmtdr: str) -> str:
    if dlmtdr not in DELIMITADORES_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail="El delimitador solo admite coma (,), punto y coma (;), tabulador (tab) o espacio",
        )
    return DELIMITADORES_VALIDOS[dlmtdr]


def _validar_delimitador_decimal(dlmtdr_dcml: str) -> str:
    if dlmtdr_dcml not in DELIMITADORES_DECIMALES_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail="El delimitador decimal solo admite punto (.) o coma (,)",
        )
    return dlmtdr_dcml


ESTADOS_MAPEO_VALIDOS = {"Activo", "Inactivo"}


def _validar_estado_mapeo(estd: str) -> str:
    if estd not in ESTADOS_MAPEO_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail="El estado del mapeo solo admite 'Activo' o 'Inactivo'",
        )
    return estd


def _validar_tipo_trama(tp_trm: str) -> str:
    """Letra libre (A-Z): define el prefijo de archivo que este mapeo
    interpreta (p. ej. 'X' -> X_*.dat). Se normaliza a mayúscula porque
    detectar_tipo_trama compara sobre el nombre de archivo en mayúsculas
    (los dataloggers no son consistentes con el case)."""
    tp_trm = tp_trm.strip().upper()
    if not TIPO_TRAMA_PATRON.match(tp_trm):
        raise HTTPException(
            status_code=422,
            detail="El tipo de trama debe ser una sola letra (A-Z), p. ej. 'H', 'E' o 'P'",
        )
    return tp_trm


def _resolver_dispositivo(db: Session, id_dspstv: int) -> tuple[Dispositivo, Ubicacion]:
    """DEC-09: el mapeo cuelga de un dispositivo. Devuelve el dispositivo y
    su ubicación (de donde sale la sede para verificar_sede, mismo patrón
    que POST /dispositivos en HU11)."""
    dispositivo = db.query(Dispositivo).filter(Dispositivo.id_dspstv == id_dspstv).first()
    if dispositivo is None:
        raise HTTPException(status_code=422, detail=f"El dispositivo {id_dspstv} no existe")

    ubicacion = db.query(Ubicacion).filter(Ubicacion.id_ubccn == dispositivo.id_ubccn).first()
    if ubicacion is None:
        # El FK lo impide en la práctica; si pasara, es un dato roto y no
        # se puede decidir la sede a la que pertenece el mapeo.
        raise HTTPException(
            status_code=422,
            detail=f"El dispositivo {id_dspstv} apunta a una ubicación inexistente",
        )
    return dispositivo, ubicacion


def _validar_delimitadores_compatibles(dlmtdr: str, dlmtdr_dcml: str) -> None:
    """Coma para separar columnas Y coma decimal es indecidible: "23,5"
    en una línea separada por comas son dos campos, no un número. Se
    rechaza en el formulario en vez de dejar que produzca lecturas
    partidas en silencio, que es la clase de fallo mudo que DEC-09 busca
    eliminar."""
    if dlmtdr == "," and dlmtdr_dcml == ",":
        raise HTTPException(
            status_code=422,
            detail=(
                "El delimitador de columna y el decimal no pueden ser ambos coma: "
                "elige punto y coma (;) como delimitador de columna, o punto (.) "
                "como decimal"
            ),
        )


def _validar_parametros_existen(db: Session, columnas) -> None:
    """Un id_prmtr inexistente reventaría como IntegrityError de FK al
    hacer commit, que se traduciría a un 409 confuso ("ya existe un
    mapeo"). Se valida antes para devolver un 422 con la causa real."""
    ids_pedidos = {c.id_prmtr for c in columnas}
    if not ids_pedidos:
        return
    ids_existentes = {
        fila.id_prmtr
        for fila in db.query(Parametro.id_prmtr).filter(Parametro.id_prmtr.in_(ids_pedidos)).all()
    }
    faltantes = sorted(ids_pedidos - ids_existentes)
    if faltantes:
        raise HTTPException(
            status_code=422,
            detail=f"Los parámetros estándar {faltantes} no existen",
        )


def _validar_indices_unicos(columnas) -> None:
    """mp_clmn tiene UNIQUE (id_mp, indc_clmn). Igual que arriba: se
    detecta antes para no confundir el 409 de "mapeo duplicado"."""
    indices = [c.indc_clmn for c in columnas]
    if len(indices) != len(set(indices)):
        raise HTTPException(
            status_code=422,
            detail="No se puede asignar dos parámetros al mismo índice de columna",
        )


def _contar_columnas(db: Session, id_mp: int) -> int:
    return db.query(MapeoColumna).filter(MapeoColumna.id_mp == id_mp).count()


def _a_list_item(
    formato: MapeoFormato,
    dispositivo: Dispositivo,
    ubicacion: Ubicacion,
    total_columnas: int,
) -> MapeoFormatoListItem:
    """DEC-09: la marca y la sede ya no viven en mp_frmt; se derivan del
    dispositivo y de su ubicación, y se siguen exponiendo igual para no
    romper la tabla del frontend."""
    return MapeoFormatoListItem(
        id_mp=formato.id_mp,
        id_dspstv=dispositivo.id_dspstv,
        dispositivo_nombre=dispositivo.nmbr,
        id_sd=ubicacion.id_sd,
        mrc=dispositivo.mrc,
        tp_trm=formato.tp_trm,
        dscrpcn=formato.dscrpcn,
        dlmtdr=formato.dlmtdr,
        dlmtdr_dcml=formato.dlmtdr_dcml,
        fl_inc_dts=formato.fl_inc_dts,
        frmt_fch=a_formato_legible(formato.frmt_fch),
        estd=formato.estd,
        total_columnas=total_columnas,
    )


def _cargar_contexto(db: Session, formato: MapeoFormato) -> tuple[Dispositivo, Ubicacion]:
    """Dispositivo + Ubicación de un mapeo ya cargado, para poder armar su
    list item (marca, sede) y verificar la sede."""
    dispositivo = db.query(Dispositivo).filter(Dispositivo.id_dspstv == formato.id_dspstv).first()
    ubicacion = (
        db.query(Ubicacion).filter(Ubicacion.id_ubccn == dispositivo.id_ubccn).first()
        if dispositivo is not None
        else None
    )
    if dispositivo is None or ubicacion is None:
        raise HTTPException(
            status_code=422,
            detail=f"El mapeo {formato.id_mp} apunta a un dispositivo/ubicación inexistente",
        )
    return dispositivo, ubicacion


def _columnas_detalle(db: Session, id_mp: int) -> list[MapeoColumnaDetalle]:
    filas = (
        db.query(MapeoColumna, Parametro)
        .join(Parametro, Parametro.id_prmtr == MapeoColumna.id_prmtr)
        .filter(MapeoColumna.id_mp == id_mp)
        .order_by(MapeoColumna.indc_clmn)
        .all()
    )
    return [
        MapeoColumnaDetalle(
            indc_clmn=columna.indc_clmn,
            id_prmtr=columna.id_prmtr,
            parametro_nombre=parametro.nmbr,
            parametro_unidad=parametro.undd,
        )
        for columna, parametro in filas
    ]


@router_parametros.get("", response_model=list[ParametroListItem] | ListadoParametros)
def listar_parametros(
    pagina: int | None = Query(default=None, ge=1),
    por_pagina: int | None = Query(default=None, ge=1, le=100),
    q: str | None = Query(default=None, description="Filtro por nombre, insensible a mayúsculas"),
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    """CA1: pobla el selector de parámetro estándar del formulario.

    Sin pagina/por_pagina devuelve la lista COMPLETA (comportamiento
    original): los selectores de "parámetro estándar" en ConfigurarMapeo y
    en la ficha de Dispositivo necesitan ver todo el catálogo para poder
    elegir cualquiera, no solo una página. Con esos params, pagina -lo usa
    la pantalla de catálogo (Parámetros), que sí puede crecer bastante. `q`
    filtra por nombre en el SERVIDOR (no solo en la página cargada): así
    una búsqueda encuentra un parámetro aunque esté en otra página."""
    query = db.query(Parametro).order_by(Parametro.nmbr)
    if q:
        query = query.filter(Parametro.nmbr.ilike(f"%{q}%"))

    if pagina is None and por_pagina is None:
        return [ParametroListItem.model_validate(p) for p in query.all()]

    pagina = pagina or 1
    por_pagina = por_pagina or 25
    total = query.count()
    parametros = query.offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    return ListadoParametros(
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        items=[ParametroListItem.model_validate(p) for p in parametros],
    )


@router_parametros.post("", response_model=ParametroListItem, status_code=201)
def crear_parametro(
    body: ParametroCrear,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("Ingesta", EDICION)),
):
    """Alta de un parámetro estándar en el catálogo (prmtr). No es parte de
    los CA de HU06 -que solo lista lo ya existente- sino del hueco que
    dejaba: antes de esto un parámetro nuevo solo se podía insertar a mano
    en la BD, lo mismo que HU06 resolvió para los mapeos."""
    ya_existe = db.query(Parametro).filter(Parametro.nmbr == body.nmbr).first()
    if ya_existe is not None:
        raise HTTPException(status_code=409, detail=f"Ya existe un parámetro llamado '{body.nmbr}'")

    parametro = Parametro(
        nmbr=body.nmbr, undd=body.undd, dscrpcn=body.dscrpcn, tipo_dato=body.tipo_dato
    )
    db.add(parametro)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Ya existe un parámetro llamado '{body.nmbr}'")
    db.refresh(parametro)
    return ParametroListItem.model_validate(parametro)


@router_parametros.put("/{id_prmtr}", response_model=ParametroListItem)
def actualizar_parametro(
    id_prmtr: int,
    body: ParametroActualizar,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("Ingesta", EDICION)),
):
    """Edita un parámetro del catálogo. No afecta los mapeos que ya lo
    usan (mp_clmn referencia id_prmtr, no el nombre): renombrar o cambiar
    la unidad de un parámetro se ve reflejado en todos los mapeos que lo
    tienen asignado, que es el comportamiento esperado de un catálogo
    compartido."""
    parametro = db.query(Parametro).filter(Parametro.id_prmtr == id_prmtr).first()
    if parametro is None:
        raise HTTPException(status_code=404, detail="Parámetro no encontrado")

    if body.nmbr is not None and body.nmbr != parametro.nmbr:
        ya_existe = db.query(Parametro).filter(Parametro.nmbr == body.nmbr).first()
        if ya_existe is not None:
            raise HTTPException(
                status_code=409, detail=f"Ya existe un parámetro llamado '{body.nmbr}'"
            )
        parametro.nmbr = body.nmbr
    if body.undd is not None:
        parametro.undd = body.undd
    if body.dscrpcn is not None:
        parametro.dscrpcn = body.dscrpcn.strip() or None

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f"Ya existe un parámetro llamado '{body.nmbr}'"
        )
    db.refresh(parametro)
    return ParametroListItem.model_validate(parametro)


@router_parametros.delete("/{id_prmtr}")
def eliminar_parametro(
    id_prmtr: int,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("Ingesta", EDICION)),
):
    """Borra un parámetro del catálogo -a diferencia del borrado de mapeo
    (ver eliminar_mapeo más abajo), acá SÍ es un borrado físico: un
    parámetro sin ningún mapeo que lo use no tiene historial que proteger,
    a diferencia de mp_frmt (los archivos ya procesados dependen de que su
    mp_clmn siga existiendo).

    Si algún mp_clmn ya lo usa, se bloquea con 409 en vez de dejar que la
    FK reviente con un IntegrityError crudo: borrarlo rompería la
    asignación de columnas de esos mapeos en silencio."""
    parametro = db.query(Parametro).filter(Parametro.id_prmtr == id_prmtr).first()
    if parametro is None:
        raise HTTPException(status_code=404, detail="Parámetro no encontrado")

    en_uso = db.query(MapeoColumna).filter(MapeoColumna.id_prmtr == id_prmtr).first()
    if en_uso is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"El parámetro '{parametro.nmbr}' está en uso por al menos un mapeo "
                f"y no se puede eliminar. Quita la asignación de esa columna primero."
            ),
        )

    db.delete(parametro)
    db.commit()
    return {"mensaje": "Parámetro eliminado correctamente"}


@router_sedes.get("", response_model=list[SedeListItem])
def listar_sedes(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(
        require_alguno_permiso(("Ingesta", LECTURA), ("Ubicaciones", LECTURA))
    ),
):
    """Pobla el selector de sede de formularios que un usuario 'global'
    debe llenar explícitamente (Agregar Ubicación, Conexiones FTP): no
    existe otro endpoint que liste sedes -GET /ubicaciones es una tabla
    distinta (ubicaciones dentro de una sede, no sedes).

    Ya no lo usa el formulario de mapeos (HU06): la sede del mapeo sale
    ahora del dispositivo elegido, no se pide aparte.

    HU08 reusa este selector para registrar una ubicación, así que el
    permiso admite también Ubicaciones/lectura: el endpoint solo expone id
    y nombre de sede, y negárselo a quien administra ubicaciones no
    respondería a ninguna regla de negocio."""
    sedes = db.query(Sede).order_by(Sede.nmbr).all()
    return [SedeListItem.model_validate(s) for s in sedes]


@router.get("", response_model=dict)
def listar_mapeos(
    marca: str | None = Query(
        default=None, description="Filtrar por marca del dispositivo, exacto"
    ),
    id_sd: int | None = Query(default=None, description="Filtrar por sede"),
    id_dspstv: int | None = Query(default=None, description="Filtrar por dispositivo"),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    """CA5: 'VER MAPEOS' muestra el listado, donde el registro nuevo
    aparece asociado a su dispositivo.

    DEC-09: la marca y la sede salen del JOIN mp_frmt -> dspstv -> ubccn,
    mismo patrón que GET /dispositivos usa para aislar por sede."""
    query = (
        db.query(MapeoFormato, Dispositivo, Ubicacion)
        .join(Dispositivo, Dispositivo.id_dspstv == MapeoFormato.id_dspstv)
        .join(Ubicacion, Ubicacion.id_ubccn == Dispositivo.id_ubccn)
    )

    # Aislamiento por sede (HT-09 CA3): un usuario 'por_sede' solo ve los
    # mapeos de dispositivos de su sede, aunque pida otra explícitamente.
    # La sede sale de la ubicación del dispositivo (ver _sede_de_dispositivo).
    if usuario.get("scope") == "por_sede":
        query = query.filter(Ubicacion.id_sd == usuario["sede_id"])
    elif id_sd is not None:
        query = query.filter(Ubicacion.id_sd == id_sd)

    if marca:
        query = query.filter(Dispositivo.mrc == marca)
    if id_dspstv is not None:
        query = query.filter(MapeoFormato.id_dspstv == id_dspstv)

    filas = query.order_by(Dispositivo.nmbr, MapeoFormato.tp_trm).all()
    items = [
        _a_list_item(formato, dispositivo, ubicacion, _contar_columnas(db, formato.id_mp))
        for formato, dispositivo, ubicacion in filas
    ]
    return {"total": len(items), "items": items}


@router.get("/{id_mp}", response_model=MapeoFormatoDetalle)
def obtener_mapeo(
    id_mp: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    """CA4: al acceder a un mapeo existente se cargan sus datos y su tabla
    de asignación para poder modificarlos."""
    formato = db.query(MapeoFormato).filter(MapeoFormato.id_mp == id_mp).first()
    if formato is None:
        raise HTTPException(status_code=404, detail="Mapeo no encontrado")

    dispositivo, ubicacion = _cargar_contexto(db, formato)
    verificar_sede(usuario, ubicacion.id_sd, modulo="Ingesta", accion=LECTURA)

    base = _a_list_item(formato, dispositivo, ubicacion, _contar_columnas(db, formato.id_mp))
    return MapeoFormatoDetalle(
        **base.model_dump(),
        columnas=_columnas_detalle(db, formato.id_mp),
    )


@router.post("", status_code=201)
def crear_mapeo(
    body: MapeoFormatoCrear,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", EDICION)),
):
    """CA3: 'GUARDAR' registra el mapeo, lo asocia al dispositivo y
    devuelve 'Mapeo guardado correctamente'."""
    delimitador = _validar_delimitador(body.dlmtdr)
    delimitador_decimal = _validar_delimitador_decimal(body.dlmtdr_dcml)
    _validar_delimitadores_compatibles(delimitador, delimitador_decimal)
    tipo_trama = _validar_tipo_trama(body.tp_trm)

    # DEC-09: la sede sale del dispositivo (dspstv -> ubccn), mismo patrón
    # que POST /dispositivos (HU11): un usuario 'por_sede' no puede colgar
    # un mapeo de un dispositivo de otra sede aunque conozca su id.
    dispositivo, ubicacion = _resolver_dispositivo(db, body.id_dspstv)
    verificar_sede(usuario, ubicacion.id_sd, modulo="Ingesta", accion=EDICION)

    _validar_indices_unicos(body.columnas)
    _validar_parametros_existen(db, body.columnas)

    # El índice único parcial (id_dspstv, tp_trm) WHERE estd='Activo' ya lo
    # garantiza; se chequea antes para devolver el 409 con el mensaje de
    # negocio en vez de un IntegrityError crudo (mismo criterio que el 409
    # de nombre duplicado en HU08 y el de conexión ocupada en HU11).
    duplicado = (
        db.query(MapeoFormato)
        .filter(
            MapeoFormato.id_dspstv == dispositivo.id_dspstv,
            MapeoFormato.tp_trm == tipo_trama,
            MapeoFormato.estd == "Activo",
        )
        .first()
    )
    if duplicado is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"El dispositivo '{dispositivo.nmbr}' ya tiene un mapeo activo "
                f"para el tipo de trama '{tipo_trama}'"
            ),
        )

    formato = MapeoFormato(
        id_dspstv=dispositivo.id_dspstv,
        tp_trm=tipo_trama,
        dscrpcn=body.dscrpcn.strip() if body.dscrpcn else None,
        dlmtdr=delimitador,
        dlmtdr_dcml=delimitador_decimal,
        fl_inc_dts=body.fl_inc_dts,
        frmt_fch=a_formato_strptime(body.frmt_fch),
        estd="Activo",
    )
    db.add(formato)

    try:
        db.flush()  # asigna id_mp sin cerrar la transacción todavía
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                f"El dispositivo '{dispositivo.nmbr}' ya tiene un mapeo activo "
                f"para el tipo de trama '{tipo_trama}'"
            ),
        )

    for columna in body.columnas:
        db.add(
            MapeoColumna(
                id_mp=formato.id_mp,
                indc_clmn=columna.indc_clmn,
                id_prmtr=columna.id_prmtr,
            )
        )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                f"El dispositivo '{dispositivo.nmbr}' ya tiene un mapeo activo "
                f"para el tipo de trama '{tipo_trama}'"
            ),
        )
    db.refresh(formato)

    return {
        "mensaje": "Mapeo guardado correctamente",
        "mapeo": _a_list_item(formato, dispositivo, ubicacion, _contar_columnas(db, formato.id_mp)),
    }


@router.put("/{id_mp}")
def actualizar_mapeo(
    id_mp: int,
    body: MapeoFormatoActualizar,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", EDICION)),
):
    """CA4: 'ACTUALIZAR' guarda los cambios y devuelve 'Mapeo actualizado
    correctamente'."""
    formato = db.query(MapeoFormato).filter(MapeoFormato.id_mp == id_mp).first()
    if formato is None:
        raise HTTPException(status_code=404, detail="Mapeo no encontrado")

    dispositivo, ubicacion = _cargar_contexto(db, formato)
    verificar_sede(usuario, ubicacion.id_sd, modulo="Ingesta", accion=EDICION)

    if body.dlmtdr is not None:
        formato.dlmtdr = _validar_delimitador(body.dlmtdr)
    if body.dlmtdr_dcml is not None:
        formato.dlmtdr_dcml = _validar_delimitador_decimal(body.dlmtdr_dcml)
    # Se comprueba sobre los valores YA aplicados, no sobre el body: el
    # conflicto puede surgir de cambiar solo uno de los dos contra el que
    # ya estaba guardado.
    _validar_delimitadores_compatibles(formato.dlmtdr, formato.dlmtdr_dcml)
    if body.tp_trm is not None:
        formato.tp_trm = _validar_tipo_trama(body.tp_trm)
    if body.dscrpcn is not None:
        formato.dscrpcn = body.dscrpcn.strip() or None
    if body.fl_inc_dts is not None:
        formato.fl_inc_dts = body.fl_inc_dts
    if body.frmt_fch is not None:
        formato.frmt_fch = a_formato_strptime(body.frmt_fch)
    if body.estd is not None:
        formato.estd = _validar_estado_mapeo(body.estd)

    # `columnas` omitido = no se toca la tabla de asignación; `columnas`
    # presente = reemplaza la asignación completa. Se distingue con None,
    # no con lista vacía: una lista vacía es "borra todas las columnas",
    # que es una operación legítima.
    if body.columnas is not None:
        _validar_indices_unicos(body.columnas)
        _validar_parametros_existen(db, body.columnas)
        db.query(MapeoColumna).filter(MapeoColumna.id_mp == formato.id_mp).delete()
        for columna in body.columnas:
            db.add(
                MapeoColumna(
                    id_mp=formato.id_mp,
                    indc_clmn=columna.indc_clmn,
                    id_prmtr=columna.id_prmtr,
                )
            )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                f"El dispositivo '{dispositivo.nmbr}' ya tiene un mapeo activo "
                f"para ese tipo de trama"
            ),
        )
    db.refresh(formato)

    return {
        "mensaje": "Mapeo actualizado correctamente",
        "mapeo": _a_list_item(formato, dispositivo, ubicacion, _contar_columnas(db, formato.id_mp)),
    }


@router.delete("/{id_mp}")
def eliminar_mapeo(
    id_mp: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", EDICION)),
):
    """Elimina (lógicamente) un mapeo: lo marca 'Inactivo' en vez de
    borrar la fila.

    Un borrado físico rompería la trazabilidad: archv_ingst no guarda
    id_mp, pero los archivos ya interpretados con este mapeo dependen de
    que mp_clmn siga existiendo si alguna vez hay que auditar por qué una
    lectura vieja se guardó bajo tal parámetro. Desactivar además libera
    el índice único parcial (id_dspstv, tp_trm) WHERE estd='Activo', así
    que la misma letra se puede volver a usar con un mapeo nuevo -que es
    justo el caso de uso: el técnico se equivocó de configuración y quiere
    "borrar y volver a crear" esa trama."""
    formato = db.query(MapeoFormato).filter(MapeoFormato.id_mp == id_mp).first()
    if formato is None:
        raise HTTPException(status_code=404, detail="Mapeo no encontrado")

    dispositivo, ubicacion = _cargar_contexto(db, formato)
    verificar_sede(usuario, ubicacion.id_sd, modulo="Ingesta", accion=EDICION)

    if formato.estd == "Inactivo":
        raise HTTPException(status_code=409, detail="Este mapeo ya está inactivo")

    formato.estd = "Inactivo"
    db.commit()

    return {"mensaje": "Mapeo eliminado correctamente"}


def _decodificar_dat(contenido_bytes: bytes) -> str:
    try:
        contenido = contenido_bytes.decode("utf-8")
    except UnicodeDecodeError:
        # Los .dat de campo a veces vienen en latin-1 (grados, ñ).
        contenido = contenido_bytes.decode("latin-1")
    # Los .dat reales traen CRLF y a veces un NUL de relleno, que rompen el
    # csv.reader del parser. La normalización vive en tasks.ingesta y la
    # comparten la vista previa y el pipeline real (automático y carga
    # manual), para que un mismo archivo se lea igual por las tres vías.
    return normalizar_contenido_dat(contenido)


def _sugerir_parametros(db: Session, nombres_columnas: list[str]) -> dict[int, int]:
    """Sugiere, por coincidencia EXACTA de nombre (insensible a mayúsculas
    y espacios), qué parámetro estándar corresponde a cada columna del
    header. Es solo una sugerencia para prellenar el formulario: nunca se
    persiste sola, el Técnico CENERIS confirma o corrige cada columna
    antes de guardar (ver Asignación de columnas). No se intenta fuzzy
    matching más allá de esto -un match aproximado incorrecto sería peor
    que no sugerir nada, porque entraría a producción sin que nadie lo
    note."""
    catalogo = {p.nmbr.strip().lower(): p.id_prmtr for p in db.query(Parametro).all()}
    sugerencias = {}
    for indice, nombre in enumerate(nombres_columnas):
        id_prmtr = catalogo.get(nombre.strip().lower())
        if id_prmtr is not None:
            sugerencias[indice] = id_prmtr
    return sugerencias


def _construir_vista_previa(
    db: Session,
    contenido: str,
    dlmtdr: str,
    fl_inc_dts: int,
    frmt_fch: str,
    columna_fecha: str,
    asignaciones: str,
) -> VistaPreviaResponse:
    delimitador = _validar_delimitador(dlmtdr)
    config = ConfiguracionParseo(
        delimitador=delimitador,
        fila_inicio_datos=fl_inc_dts,
        formato_fecha=a_formato_strptime(frmt_fch),
        columna_fecha=columna_fecha,
    )
    try:
        resultado = parsear_dat(contenido, config)
    except csv.Error as exc:
        raise HTTPException(
            status_code=422,
            detail=f"No se pudo interpretar el archivo de muestra con este delimitador/formato: {exc}",
        )

    if not resultado.columnas:
        raise HTTPException(
            status_code=422,
            detail="No se pudo leer el header del archivo de muestra: revisa el delimitador y la fila de inicio de datos",
        )

    indice_a_parametro = _parsear_asignaciones(db, asignaciones, len(resultado.columnas))
    sugerencias = _sugerir_parametros(db, resultado.columnas)

    columnas = [
        ColumnaVistaPrevia(
            indc_clmn=indice,
            nombre_columna=nombre,
            parametro_nombre=indice_a_parametro.get(indice, (None, None))[0],
            parametro_unidad=indice_a_parametro.get(indice, (None, None))[1],
            id_prmtr_sugerido=sugerencias.get(indice) if indice not in indice_a_parametro else None,
        )
        for indice, nombre in enumerate(resultado.columnas)
    ]

    filas = [
        FilaVistaPrevia(
            numero_fila=fila.numero_fila,
            fecha_hora=fila.fecha_hora.isoformat() if fila.fecha_hora else None,
            error=fila.error,
            valores=fila.valores,
        )
        for fila in resultado.filas[:FILAS_VISTA_PREVIA]
    ]

    return VistaPreviaResponse(
        columnas=columnas,
        filas=filas,
        total_filas_archivo=len(resultado.filas),
        filas_mostradas=len(filas),
    )


@router.post("/vista-previa", response_model=VistaPreviaResponse)
async def vista_previa(
    archivo: UploadFile = File(..., description="Archivo .dat de muestra"),
    dlmtdr: str = Form(default=","),
    dlmtdr_dcml: str = Form(default="."),
    fl_inc_dts: int = Form(default=1),
    frmt_fch: str = Form(default="YYYY-MM-DD HH:mm:ss"),
    columna_fecha: str = Form(default="Fecha"),
    asignaciones: str = Form(
        default="",
        description='Asignación columna->parámetro como "indice:id_prmtr" separadas por coma, p. ej. "0:3,2:7"',
    ),
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    """CA2: interpreta el archivo de muestra con la configuración en
    edición y devuelve las primeras 10 filas, indicando qué parámetro
    estándar quedó asignado a cada columna (y, para las que no tienen
    asignación confirmada todavía, una sugerencia por nombre -ver
    id_prmtr_sugerido en ColumnaVistaPrevia-).

    El archivo de muestra es TEMPORAL: se lee en memoria y NO se persiste
    en base de datos ni en disco (regla explícita de la HU). Por eso este
    endpoint solo requiere permiso de LECTURA: no escribe nada.
    """
    # La vista previa muestra el valor CRUDO (sin castear a float), así que
    # el decimal no cambia lo que se ve; se valida igual para que el
    # formulario avise del conflicto coma/coma acá y no recién al guardar.
    _validar_delimitadores_compatibles(_validar_delimitador(dlmtdr), _validar_delimitador_decimal(dlmtdr_dcml))
    contenido = _decodificar_dat(await archivo.read())
    return _construir_vista_previa(db, contenido, dlmtdr, fl_inc_dts, frmt_fch, columna_fecha, asignaciones)


@router_dispositivos_mapeo.get("", response_model=list[DispositivoParaMapeo])
def listar_dispositivos_para_mapeo(
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    """Pobla el selector 'Dispositivo' de la vista previa: elegir uno para
    traer un .dat que ya llegó por FTP, en vez de subirlo a mano. Solo
    dispositivos con conexión FTP (prtcl='FTP'): es el único protocolo que
    se puede listar/descargar por polling (ver ftp_receptor.py)."""
    query = (
        db.query(Dispositivo)
        .join(ConexionFTP, ConexionFTP.id_cnxn == Dispositivo.id_cnxn)
        .filter(ConexionFTP.prtcl == "FTP")
    )
    if usuario.get("scope") == "por_sede":
        query = query.filter(ConexionFTP.id_sd == usuario["sede_id"])

    dispositivos = query.order_by(Dispositivo.nmbr).all()
    return [DispositivoParaMapeo.model_validate(d) for d in dispositivos]


def _conexion_del_dispositivo(db: Session, usuario: dict, id_dspstv: int) -> ConexionFTP:
    dispositivo = db.query(Dispositivo).filter(Dispositivo.id_dspstv == id_dspstv).first()
    if dispositivo is None:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    cnxn = db.query(ConexionFTP).filter(ConexionFTP.id_cnxn == dispositivo.id_cnxn).first()
    if cnxn is None or cnxn.prtcl != "FTP":
        raise HTTPException(
            status_code=422, detail="Este dispositivo no tiene una conexión FTP configurada"
        )

    verificar_sede(usuario, cnxn.id_sd, modulo="Ingesta", accion=LECTURA)
    return cnxn


@router_dispositivos_mapeo.get("/{id_dspstv}/archivos-ftp", response_model=list[ArchivoFtpDisponible])
def listar_archivos_ftp_dispositivo(
    id_dspstv: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    """Lista los .dat presentes ahora mismo en la carpeta remota del
    dispositivo, para elegir uno como muestra sin bajarlo/subirlo a
    mano."""
    cnxn = _conexion_del_dispositivo(db, usuario, id_dspstv)
    try:
        nombres = listar_archivos_dat(cnxn)
    except ftplib.all_errors as exc:
        raise HTTPException(
            status_code=502, detail=f"No se pudo listar los archivos del servidor FTP: {exc}"
        )
    return [ArchivoFtpDisponible(nombre_archivo=n) for n in sorted(nombres, reverse=True)]


@router.post("/vista-previa-ftp", response_model=VistaPreviaResponse)
def vista_previa_ftp(
    id_dspstv: int = Form(...),
    nombre_archivo: str = Form(...),
    dlmtdr: str = Form(default=","),
    dlmtdr_dcml: str = Form(default="."),
    fl_inc_dts: int = Form(default=1),
    frmt_fch: str = Form(default="YYYY-MM-DD HH:mm:ss"),
    columna_fecha: str = Form(default="Fecha"),
    asignaciones: str = Form(default=""),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    """Misma vista previa de CA2, pero con la muestra tomada directo de un
    .dat ya recibido por FTP (ver listar_archivos_ftp_dispositivo) en vez
    de subida a mano. Tampoco se persiste: se descarga a memoria, se
    interpreta y se descarta."""
    _validar_delimitadores_compatibles(_validar_delimitador(dlmtdr), _validar_delimitador_decimal(dlmtdr_dcml))
    cnxn = _conexion_del_dispositivo(db, usuario, id_dspstv)
    try:
        if nombre_archivo not in listar_archivos_dat(cnxn):
            raise HTTPException(
                status_code=404,
                detail=f"'{nombre_archivo}' ya no está en la carpeta remota de este dispositivo",
            )
        # latin-1 decodifica cualquier secuencia de bytes sin levantar
        # UnicodeDecodeError (es una tabla de 256 puntos, uno por byte), así
        # que sirve como intento único acá -no hace falta el fallback de
        # _decodificar_dat, pensado para bytes ya en memoria de un upload.
        contenido = descargar_archivo_dat(cnxn, nombre_archivo, encoding="latin-1")
    except ftplib.all_errors as exc:
        raise HTTPException(
            status_code=502, detail=f"No se pudo descargar el archivo del servidor FTP: {exc}"
        )

    contenido = normalizar_contenido_dat(contenido)
    return _construir_vista_previa(db, contenido, dlmtdr, fl_inc_dts, frmt_fch, columna_fecha, asignaciones)


def _parsear_asignaciones(db: Session, asignaciones: str, total_columnas: int) -> dict:
    """ "0:3,2:7" -> {0: ("Temperatura", "°C"), 2: ("pH", "pH")}.

    Se manda como string y no como JSON porque el resto del request es
    multipart/form-data (lleva el archivo de muestra), donde un campo
    anidado obligaría a serializar igual.
    """
    if not asignaciones.strip():
        return {}

    pares = {}
    for fragmento in asignaciones.split(","):
        fragmento = fragmento.strip()
        if not fragmento:
            continue
        try:
            indice_txt, id_prmtr_txt = fragmento.split(":")
            indice, id_prmtr = int(indice_txt), int(id_prmtr_txt)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Asignación inválida '{fragmento}': se esperaba el formato 'indice:id_prmtr'",
            )
        if 0 <= indice < total_columnas:
            pares[indice] = id_prmtr

    if not pares:
        return {}

    parametros = {
        p.id_prmtr: p
        for p in db.query(Parametro).filter(Parametro.id_prmtr.in_(set(pares.values()))).all()
    }
    return {
        indice: (parametros[id_prmtr].nmbr, parametros[id_prmtr].undd)
        for indice, id_prmtr in pares.items()
        if id_prmtr in parametros
    }
