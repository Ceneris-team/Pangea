"""
HU 09 - Monitorear cola de procesamiento

HT-05, CA3: "El sistema expone métricas en tiempo real de jobs pendientes,
en proceso y fallidos, consumibles por el módulo de monitoreo." Se cuenta
directamente sobre archv_ingst (agrupado por estd, usa idx_archvingst_estd)
en vez de consultar celery.control.inspect(): así el conteo refleja también
los jobs que un receptor FTP ya registró como 'Pendiente' pero que ningún
worker ha tomado todavía, que es justo el caso que se quiere monitorear.

CA1-CA3 (listado, filtro y detalle de la cola) se agregan más abajo en
este mismo router: comparten módulo de permisos ('Ingesta') y tabla base
(archv_ingst) con /metricas, que no se toca.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.ingesta.ftp_receptor import descargar_archivo_dat
from app.models import ArchivoIngesta, ConexionFTP, Dispositivo
from app.schemas import (
    ArchivoIngestaDetalle,
    ArchivoIngestaListItem,
    FilaCrudaIngesta,
    MetricasColaIngesta,
    RegistrosIngestaResponse,
)
from app.security.permisos import EDICION, LECTURA, require_permiso, verificar_sede
from app.services.ingesta.mapeo import MapeoNoEncontradoError, resolver_formato
from app.services.ingesta.parser import parsear_dat
from app.services.ingesta.persistencia import DispositivoNoResueltoError, resolver_dispositivo
from app.tasks.ingesta import normalizar_contenido_dat, procesar_archivo_dat

router = APIRouter(prefix="/ingesta", tags=["Ingesta"])

ESTADOS = ("Pendiente", "Procesando", "Exitoso", "Fallido")

# HU09: la HU habla de "En espera / Procesando / Procesado / Fallido", pero
# el CHECK constraint de archv_ingst.estd (y por tanto todo el motor de
# ingesta de HT-05, ver app/tasks/ingesta.py) usa Pendiente/Procesando/
# Exitoso/Fallido. La traducción se hace en la frontera del router -mismo
# criterio que a_formato_legible/DELIMITADORES_VALIDOS en routers/mapeos.py
# para HU06- así el motor no cambia y la API habla el lenguaje de negocio.
ESTADO_BD_A_NEGOCIO = {
    "Pendiente": "En espera",
    "Procesando": "Procesando",
    "Exitoso": "Procesado",
    "Fallido": "Fallido",
}
ESTADO_NEGOCIO_A_BD = {negocio: bd for bd, negocio in ESTADO_BD_A_NEGOCIO.items()}

POR_PAGINA_DEFAULT = 10  # CA1: "pagina de 10 registros por defecto"


def _validar_estado_negocio(estado: str) -> str:
    if estado not in ESTADO_NEGOCIO_A_BD:
        raise HTTPException(
            status_code=422,
            detail=f"Estado inválido: debe ser uno de {sorted(ESTADO_NEGOCIO_A_BD)}",
        )
    return ESTADO_NEGOCIO_A_BD[estado]


def _mapa_dataloggers(db: Session, ids_cnxn: set[int]) -> dict[int, str]:
    """ "Datalogger de origen" de cada archivo. cnxn_ftp.nmbr (HU05: "Nombre
    del datalogger") ya es un nombre de negocio válido y sirve de fallback,
    pero el dueño real del nombre del datalogger es dspstv.nmbr (HU10-11):
    se prefiere ese cuando existe exactamente un dispositivo activo
    resuelto para la conexión (mismo criterio que resolver_dispositivo en
    services/ingesta/persistencia.py)."""
    if not ids_cnxn:
        return {}

    nombres = {
        c.id_cnxn: c.nmbr
        for c in db.query(ConexionFTP).filter(ConexionFTP.id_cnxn.in_(ids_cnxn)).all()
    }

    dispositivos_por_cnxn: dict[int, list[str]] = {}
    for id_cnxn, nombre in (
        db.query(Dispositivo.id_cnxn, Dispositivo.nmbr)
        .filter(Dispositivo.id_cnxn.in_(ids_cnxn), Dispositivo.estd == "Activo")
        .all()
    ):
        dispositivos_por_cnxn.setdefault(id_cnxn, []).append(nombre)

    for id_cnxn, activos in dispositivos_por_cnxn.items():
        if len(activos) == 1:
            nombres[id_cnxn] = activos[0]

    return nombres


@router.get("/metricas", response_model=MetricasColaIngesta)
def metricas_cola_ingesta(
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    conteos = dict(
        db.query(ArchivoIngesta.estd, func.count(ArchivoIngesta.id_archv))
        .filter(ArchivoIngesta.estd.in_(ESTADOS))
        .group_by(ArchivoIngesta.estd)
        .all()
    )

    pendientes = conteos.get("Pendiente", 0)
    procesando = conteos.get("Procesando", 0)
    exitosos = conteos.get("Exitoso", 0)
    fallidos = conteos.get("Fallido", 0)

    return MetricasColaIngesta(
        pendientes=pendientes,
        procesando=procesando,
        exitosos=exitosos,
        fallidos=fallidos,
        total=pendientes + procesando + exitosos + fallidos,
    )


@router.get("/dataloggers")
def listar_dataloggers_cola(
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    """Dataloggers de origen con archivos en la cola, para el filtro de
    HU09 CA2: evita mezclar en la misma vista los archivos de estaciones
    distintas. Mismo aislamiento por sede que /cola."""
    query = db.query(ArchivoIngesta.id_cnxn).join(
        ConexionFTP, ConexionFTP.id_cnxn == ArchivoIngesta.id_cnxn
    )
    if usuario.get("scope") == "por_sede":
        query = query.filter(ConexionFTP.id_sd == usuario["sede_id"])

    ids_cnxn = {id_cnxn for (id_cnxn,) in query.distinct().all()}
    dataloggers = _mapa_dataloggers(db, ids_cnxn)

    items = sorted(
        ({"id_cnxn": id_cnxn, "nombre": dataloggers.get(id_cnxn, "Desconocido")} for id_cnxn in ids_cnxn),
        key=lambda d: d["nombre"],
    )
    return {"items": items}


@router.get("/cola")
def listar_cola_ingesta(
    estado: str | None = Query(
        default=None, description="En espera | Procesando | Procesado | Fallido"
    ),
    id_cnxn: int | None = Query(
        default=None, description="Filtra por datalogger de origen (conexión FTP)"
    ),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=POR_PAGINA_DEFAULT, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    """CA1: listado paginado de la cola, orden fch_dtccn descendente.
    CA2: filtro opcional por estado (lenguaje de negocio de la HU) y por
    datalogger de origen, para no mezclar en la misma vista archivos de
    estaciones distintas."""
    query = db.query(ArchivoIngesta).join(
        ConexionFTP, ConexionFTP.id_cnxn == ArchivoIngesta.id_cnxn
    )

    # Aislamiento por sede (mismo criterio que el resto del módulo Ingesta,
    # ver routers/mapeos.py y HT-09 CA3): un usuario 'por_sede' solo ve los
    # archivos de conexiones FTP de su propia sede.
    if usuario.get("scope") == "por_sede":
        query = query.filter(ConexionFTP.id_sd == usuario["sede_id"])

    if estado is not None:
        query = query.filter(ArchivoIngesta.estd == _validar_estado_negocio(estado))

    if id_cnxn is not None:
        query = query.filter(ArchivoIngesta.id_cnxn == id_cnxn)

    total = query.count()
    archivos = (
        query.order_by(ArchivoIngesta.fch_dtccn.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    dataloggers = _mapa_dataloggers(db, {a.id_cnxn for a in archivos})
    items = [
        ArchivoIngestaListItem(
            id_archv=a.id_archv,
            nmbr_archv=a.nmbr_archv,
            datalogger_nombre=dataloggers.get(a.id_cnxn, "Desconocido"),
            fch_dtccn=a.fch_dtccn,
            estado=ESTADO_BD_A_NEGOCIO.get(a.estd, a.estd),
        )
        for a in archivos
    ]
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": items}


@router.get("/cola/{id_archv}", response_model=ArchivoIngestaDetalle)
def detalle_archivo_ingesta(
    id_archv: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    """CA3: fecha de recepción, fecha de procesamiento, registros
    procesados y mensaje de resultado (mnsj_errr solo se llena si Fallido,
    ver app/tasks/ingesta.py)."""
    archivo = db.query(ArchivoIngesta).filter(ArchivoIngesta.id_archv == id_archv).first()
    if archivo is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    conexion = db.get(ConexionFTP, archivo.id_cnxn)
    verificar_sede(usuario, conexion.id_sd, db, modulo="Ingesta", accion=LECTURA)

    datalogger_nombre = _mapa_dataloggers(db, {archivo.id_cnxn}).get(archivo.id_cnxn, "Desconocido")

    return ArchivoIngestaDetalle(
        id_archv=archivo.id_archv,
        nmbr_archv=archivo.nmbr_archv,
        datalogger_nombre=datalogger_nombre,
        estado=ESTADO_BD_A_NEGOCIO.get(archivo.estd, archivo.estd),
        fch_dtccn=archivo.fch_dtccn,
        fch_prcsd=archivo.fch_prcsd,
        rgstrs_prcsds=archivo.rgstrs_prcsds,
        mnsj_errr=archivo.mnsj_errr,
    )


FILAS_MOSTRADAS_REGISTROS_INGESTA = 50


@router.get("/cola/{id_archv}/registros", response_model=RegistrosIngestaResponse)
def registros_archivo_ingesta(
    id_archv: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    """Vista cruda del .dat, tal como lo mandó el datalogger, ANTES del
    mapeo columna->parámetro: permite ver si una fila vino vacía/en cero o
    con datos reales -algo que ya no se distingue en tlmtr/evnt_txt, donde
    una columna sin mapeo activo ni siquiera llega a guardarse-.

    El archivo no se persiste en archv_ingst (HU09 solo guarda el nombre y
    el resultado), así que se vuelve a descargar del mismo FTP de origen
    -que conserva el .dat tras procesarlo, ver app/ingesta/ftp_receptor.py-,
    igual que hace app.tasks.ingesta.procesar_archivo_dat. Si el archivo ya
    no está en el FTP (limpieza externa, rotación), se informa con 404 en
    vez de un error crudo de conexión.
    """
    archivo = db.query(ArchivoIngesta).filter(ArchivoIngesta.id_archv == id_archv).first()
    if archivo is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    conexion = db.get(ConexionFTP, archivo.id_cnxn)
    verificar_sede(usuario, conexion.id_sd, db, modulo="Ingesta", accion=LECTURA)

    try:
        dispositivo = resolver_dispositivo(db, archivo.id_cnxn)
        formato = resolver_formato(db, dispositivo.id_dspstv, archivo.nmbr_archv)
    except (DispositivoNoResueltoError, MapeoNoEncontradoError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        contenido = descargar_archivo_dat(conexion, archivo.nmbr_archv)
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=f"No se pudo volver a leer '{archivo.nmbr_archv}' del FTP de origen: {exc}",
        ) from exc

    resultado = parsear_dat(normalizar_contenido_dat(contenido), formato.config)

    filas = [
        FilaCrudaIngesta(
            numero_fila=fila.numero_fila,
            fecha_hora=fila.fecha_hora.isoformat() if fila.fecha_hora else None,
            error=fila.error,
            valores=fila.valores,
        )
        for fila in resultado.filas[:FILAS_MOSTRADAS_REGISTROS_INGESTA]
    ]

    return RegistrosIngestaResponse(
        columnas=resultado.columnas,
        total_filas_archivo=len(resultado.filas),
        filas_mostradas=len(filas),
        filas=filas,
    )


@router.post("/cola/{id_archv}/reintentar", response_model=ArchivoIngestaDetalle)
def reintentar_archivo_ingesta(
    id_archv: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", EDICION)),
):
    """HU31: reprocesamiento manual de un archivo Fallido.

    Cubre el caso que autoretry_for de procesar_archivo_dat deja afuera a
    propósito (ver app/tasks/ingesta.py): errores de datos/configuración
    (ErrorDatosNoRecuperable) no se reintentan solos porque reintentar no
    los arregla -alguien tiene que corregir la causa primero (ej. cargar
    el mapeo que faltaba, resolver el dispositivo)-. Este endpoint es esa
    acción manual: solo tiene sentido sobre un archivo en estado Fallido,
    y vuelve a dejarlo Pendiente para que un worker lo tome de nuevo desde
    cero.
    """
    archivo = db.query(ArchivoIngesta).filter(ArchivoIngesta.id_archv == id_archv).first()
    if archivo is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    conexion = db.get(ConexionFTP, archivo.id_cnxn)
    verificar_sede(usuario, conexion.id_sd, db, modulo="Ingesta", accion=EDICION)

    if archivo.estd != "Fallido":
        raise HTTPException(
            status_code=409,
            detail="Solo se pueden reintentar archivos en estado Fallido",
        )

    archivo.estd = "Pendiente"
    archivo.mnsj_errr = None
    archivo.fch_prcsd = None
    archivo.rgstrs_prcsds = None
    db.commit()

    procesar_archivo_dat.delay(id_archv=archivo.id_archv)

    datalogger_nombre = _mapa_dataloggers(db, {archivo.id_cnxn}).get(archivo.id_cnxn, "Desconocido")
    return ArchivoIngestaDetalle(
        id_archv=archivo.id_archv,
        nmbr_archv=archivo.nmbr_archv,
        datalogger_nombre=datalogger_nombre,
        estado=ESTADO_BD_A_NEGOCIO.get(archivo.estd, archivo.estd),
        fch_dtccn=archivo.fch_dtccn,
        fch_prcsd=archivo.fch_prcsd,
        rgstrs_prcsds=archivo.rgstrs_prcsds,
        mnsj_errr=archivo.mnsj_errr,
    )
