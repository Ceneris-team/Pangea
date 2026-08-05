"""
HU 06 - Mapear formato de marca de sensor (CRUD + vista previa)

El MOTOR de mapeo ya existía y está en uso por el pipeline de ingesta
(`app/services/ingesta/mapeo.py` y `parser.py`); lo que faltaba -y es lo
que agrega este router- es la capa que permite al Técnico CENERIS crear y
editar los mapeos desde la interfaz, en vez de insertarlos a mano en la
base de datos.

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
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MapeoColumna, MapeoFormato, Parametro
from app.security.permisos import require_permiso, verificar_sede, LECTURA, EDICION
from app.services.ingesta.parser import ConfiguracionParseo, parsear_dat
from app.schemas import (
    ColumnaVistaPrevia,
    FilaVistaPrevia,
    MapeoColumnaDetalle,
    MapeoFormatoActualizar,
    MapeoFormatoCrear,
    MapeoFormatoDetalle,
    MapeoFormatoListItem,
    ParametroListItem,
    VistaPreviaResponse,
)

router = APIRouter(prefix="/mapeos", tags=["Mapeos de formato"])
router_parametros = APIRouter(prefix="/parametros", tags=["Mapeos de formato"])

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

TIPOS_TRAMA_VALIDOS = {"H", "E"}  # CHECK constraint de mp_frmt (PP-96)

# HU06: "Formato de fecha/hora: acepta cadenas tipo YYYY-MM-DD HH:mm:ss".
# El motor (parser._parsear_fecha) usa strptime, así que lo que se guarda
# en mp_frmt.frmt_fch es el formato de strptime. Se traduce en la frontera
# para que la UI hable en el lenguaje de la HU y el motor no cambie.
_TOKENS_FECHA = [
    ("YYYY", "%Y"), ("YY", "%y"),
    ("MM", "%m"), ("DD", "%d"),
    ("HH", "%H"), ("mm", "%M"), ("ss", "%S"),
]

FILAS_VISTA_PREVIA = 10  # CA2: "muestra las primeras 10 filas"


def a_formato_strptime(formato: str) -> str:
    """"YYYY-MM-DD HH:mm:ss" -> "%Y-%m-%d %H:%M:%S".

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


def _validar_tipo_trama(tp_trm: str) -> str:
    if tp_trm not in TIPOS_TRAMA_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail="El tipo de trama solo admite 'H' (datos periódicos) o 'E' (estados y eventos)",
        )
    return tp_trm


def _resolver_sede(usuario: dict, id_sd_body: int | None) -> int:
    """Mismo criterio que HU05 (routers/conexiones_ftp.py): un usuario con
    scope 'por_sede' siempre opera sobre su propia sede; uno 'global' debe
    indicar a qué sede pertenece el mapeo."""
    if usuario.get("scope") == "por_sede":
        return usuario["sede_id"]
    if id_sd_body is None:
        raise HTTPException(
            status_code=422,
            detail="Debe indicar id_sd: su usuario no está limitado a una sede única",
        )
    return id_sd_body


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


def _a_list_item(formato: MapeoFormato, total_columnas: int) -> MapeoFormatoListItem:
    return MapeoFormatoListItem(
        id_mp=formato.id_mp,
        id_sd=formato.id_sd,
        mrc=formato.mrc,
        tp_trm=formato.tp_trm,
        dlmtdr=formato.dlmtdr,
        fl_inc_dts=formato.fl_inc_dts,
        frmt_fch=a_formato_legible(formato.frmt_fch),
        estd=formato.estd,
        total_columnas=total_columnas,
    )


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


@router_parametros.get("", response_model=list[ParametroListItem])
def listar_parametros(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    """CA1: pobla el selector de parámetro estándar del formulario."""
    parametros = db.query(Parametro).order_by(Parametro.nmbr).all()
    return [ParametroListItem.model_validate(p) for p in parametros]


@router.get("", response_model=dict)
def listar_mapeos(
    marca: str | None = Query(default=None, description="Filtrar por marca, exacto"),
    id_sd: int | None = Query(default=None, description="Filtrar por sede"),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    """CA5: 'VER MAPEOS' muestra el listado, donde el registro nuevo
    aparece asociado a su marca."""
    query = db.query(MapeoFormato)

    # Aislamiento por sede (HT-09 CA3): un usuario 'por_sede' solo ve los
    # mapeos de su sede, aunque pida otra explícitamente.
    if usuario.get("scope") == "por_sede":
        query = query.filter(MapeoFormato.id_sd == usuario["sede_id"])
    elif id_sd is not None:
        query = query.filter(MapeoFormato.id_sd == id_sd)

    if marca:
        query = query.filter(MapeoFormato.mrc == marca)

    formatos = query.order_by(MapeoFormato.mrc, MapeoFormato.tp_trm).all()
    items = [_a_list_item(f, _contar_columnas(db, f.id_mp)) for f in formatos]
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

    verificar_sede(usuario, formato.id_sd, modulo="Ingesta", accion=LECTURA)

    base = _a_list_item(formato, _contar_columnas(db, formato.id_mp))
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
    """CA3: 'GUARDAR' registra el mapeo, lo asocia a la marca y devuelve
    'Mapeo guardado correctamente'."""
    delimitador = _validar_delimitador(body.dlmtdr)
    tipo_trama = _validar_tipo_trama(body.tp_trm)
    id_sd = _resolver_sede(usuario, body.id_sd)
    verificar_sede(usuario, id_sd, modulo="Ingesta", accion=EDICION)

    _validar_indices_unicos(body.columnas)
    _validar_parametros_existen(db, body.columnas)

    formato = MapeoFormato(
        id_sd=id_sd,
        mrc=body.mrc.strip(),
        tp_trm=tipo_trama,
        dlmtdr=delimitador,
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
            detail=f"Ya existe un mapeo para la marca '{body.mrc}' y el tipo de trama '{tipo_trama}' en esta sede",
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
            detail=f"Ya existe un mapeo para la marca '{body.mrc}' y el tipo de trama '{tipo_trama}' en esta sede",
        )
    db.refresh(formato)

    return {
        "mensaje": "Mapeo guardado correctamente",
        "mapeo": _a_list_item(formato, _contar_columnas(db, formato.id_mp)),
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

    verificar_sede(usuario, formato.id_sd, modulo="Ingesta", accion=EDICION)

    if body.dlmtdr is not None:
        formato.dlmtdr = _validar_delimitador(body.dlmtdr)
    if body.tp_trm is not None:
        formato.tp_trm = _validar_tipo_trama(body.tp_trm)
    if body.mrc is not None:
        formato.mrc = body.mrc.strip()
    if body.fl_inc_dts is not None:
        formato.fl_inc_dts = body.fl_inc_dts
    if body.frmt_fch is not None:
        formato.frmt_fch = a_formato_strptime(body.frmt_fch)
    if body.estd is not None:
        formato.estd = body.estd

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
            detail=f"Ya existe un mapeo para la marca '{formato.mrc}' y ese tipo de trama en esta sede",
        )
    db.refresh(formato)

    return {
        "mensaje": "Mapeo actualizado correctamente",
        "mapeo": _a_list_item(formato, _contar_columnas(db, formato.id_mp)),
    }


@router.post("/vista-previa", response_model=VistaPreviaResponse)
async def vista_previa(
    archivo: UploadFile = File(..., description="Archivo .dat de muestra"),
    dlmtdr: str = Form(default=","),
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
    estándar quedó asignado a cada columna.

    El archivo de muestra es TEMPORAL: se lee en memoria y NO se persiste
    en base de datos ni en disco (regla explícita de la HU). Por eso este
    endpoint solo requiere permiso de LECTURA: no escribe nada.
    """
    delimitador = _validar_delimitador(dlmtdr)

    contenido_bytes = await archivo.read()
    try:
        contenido = contenido_bytes.decode("utf-8")
    except UnicodeDecodeError:
        # Los .dat de campo a veces vienen en latin-1 (grados, ñ).
        contenido = contenido_bytes.decode("latin-1")

    config = ConfiguracionParseo(
        delimitador=delimitador,
        fila_inicio_datos=fl_inc_dts,
        formato_fecha=a_formato_strptime(frmt_fch),
        columna_fecha=columna_fecha,
    )
    resultado = parsear_dat(contenido, config)

    if not resultado.columnas:
        raise HTTPException(
            status_code=422,
            detail="No se pudo leer el header del archivo de muestra: revisa el delimitador y la fila de inicio de datos",
        )

    indice_a_parametro = _parsear_asignaciones(db, asignaciones, len(resultado.columnas))

    columnas = [
        ColumnaVistaPrevia(
            indc_clmn=indice,
            nombre_columna=nombre,
            parametro_nombre=indice_a_parametro.get(indice, (None, None))[0],
            parametro_unidad=indice_a_parametro.get(indice, (None, None))[1],
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


def _parsear_asignaciones(db: Session, asignaciones: str, total_columnas: int) -> dict:
    """"0:3,2:7" -> {0: ("Temperatura", "°C"), 2: ("pH", "pH")}.

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
