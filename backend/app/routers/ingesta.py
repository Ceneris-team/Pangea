"""
HU 09 - Monitorear cola de procesamiento

HT-05, CA3: "El sistema expone métricas en tiempo real de jobs pendientes,
en proceso y fallidos, consumibles por el módulo de monitoreo." Se cuenta
directamente sobre archv_ingst (agrupado por estd, usa idx_archvingst_estd)
en vez de consultar celery.control.inspect(): así el conteo refleja también
los jobs que un receptor FTP ya registró como 'Pendiente' pero que ningún
worker ha tomado todavía, que es justo el caso que se quiere monitorear.

Listado, métricas, detalle y reprocesos comparten permisos y alcance por
empresa/proyecto. Las solicitudes de HU31 se guardan antes de su despacho.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ArchivoIngesta, ConexionFTP, Dispositivo, IntentoProcesamiento, Usuario
from app.schemas import (
    ArchivoIngestaDetalle,
    ArchivoIngestaListItem,
    FilaCrudaIngesta,
    IntentoProcesamientoListItem,
    MetricasColaIngesta,
    RegistrosIngestaResponse,
    ReintentoMasivoResponse,
)
from app.security.entorno import (
    ROLES_CENERIS,
    filtrar_proyectos,
    filtrar_sedes,
    permiso_del_entorno,
)
from app.security.permisos import EDICION, LECTURA, require_permiso, tiene_permiso, verificar_sede
from app.services.ingesta.mapeo import MapeoNoEncontradoError, resolver_formato
from app.services.ingesta.originales import dispositivo_del_archivo, leer_original
from app.services.ingesta.parser import parsear_dat
from app.services.ingesta.persistencia import DispositivoNoResueltoError
from app.services.ingesta.reprocesos import solicitar
from app.tasks.ingesta import normalizar_contenido_dat

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


def _filtrar_cola(query, db, usuario):
    query = filtrar_sedes(query, ConexionFTP.id_sd, db, usuario)
    if usuario.get("proyecto_id") is not None or usuario.get("scope") == "por_cliente":
        equipos = filtrar_proyectos(
            db.query(Dispositivo.id_dspstv), Dispositivo.id_ubccn, db, usuario
        )
        query = query.filter(ArchivoIngesta.id_dspstv.in_(equipos))
    return query


def _puede_reprocesar(db, usuario):
    if usuario.get("rol") not in ROLES_CENERIS:
        return False
    permiso = permiso_del_entorno(db, usuario, "Ingesta", EDICION)
    return (
        permiso
        if permiso is not None
        else tiene_permiso(db, int(usuario["sub"]), usuario.get("sede_id"), "Ingesta", EDICION)
    )


def _exigir_rol(usuario):
    if usuario.get("rol") not in ROLES_CENERIS:
        raise HTTPException(403, "Solo Técnico CENERIS y Administrador pueden reprocesar archivos")


def _confirmar_solicitudes(db):
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            503, "No se pudo guardar la solicitud de reproceso. Vuelve a intentarlo."
        ) from exc


def _verificar_archivo(db, usuario, archivo, accion=LECTURA):
    conexion = db.get(ConexionFTP, archivo.id_cnxn)
    verificar_sede(usuario, conexion.id_sd, db, modulo="Ingesta", accion=accion)
    if usuario.get("proyecto_id") is not None or usuario.get("scope") == "por_cliente":
        visible = (
            _filtrar_cola(db.query(ArchivoIngesta.id_archv).join(ConexionFTP), db, usuario)
            .filter(ArchivoIngesta.id_archv == archivo.id_archv)
            .first()
        )
        if visible is None:
            raise HTTPException(403, "El archivo no pertenece al proyecto autorizado")


def _validar_estado_negocio(estado: str) -> str:
    if estado not in ESTADO_NEGOCIO_A_BD:
        raise HTTPException(
            status_code=422,
            detail=f"Estado inválido: debe ser uno de {sorted(ESTADO_NEGOCIO_A_BD)}",
        )
    return ESTADO_NEGOCIO_A_BD[estado]


def _mapa_dataloggers(db: Session, archivos) -> dict[int, str]:
    """Nombre del equipo vinculado al recibir el archivo, nunca el reemplazo actual."""
    if not archivos:
        return {}
    ids_cnxn = {a.id_cnxn for a in archivos}
    nombres = {
        c.id_cnxn: c.nmbr
        for c in db.query(ConexionFTP).filter(ConexionFTP.id_cnxn.in_(ids_cnxn)).all()
    }

    equipos = dict(
        db.query(Dispositivo.id_dspstv, Dispositivo.nmbr)
        .filter(Dispositivo.id_dspstv.in_([a.id_dspstv for a in archivos if a.id_dspstv]))
        .all()
    )
    return {
        a.id_archv: equipos.get(
            a.id_dspstv, f"{nombres.get(a.id_cnxn, 'FTP')} · equipo sin identificar"
        )
        for a in archivos
    }


@router.get("/metricas", response_model=MetricasColaIngesta)
def metricas_cola_ingesta(
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    query = db.query(ArchivoIngesta.estd, func.count(ArchivoIngesta.id_archv)).join(
        ConexionFTP, ConexionFTP.id_cnxn == ArchivoIngesta.id_cnxn
    )
    conteos = dict(
        _filtrar_cola(query, db, usuario)
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
    query = _filtrar_cola(query, db, usuario)

    ids_cnxn = {id_cnxn for (id_cnxn,) in query.distinct().all()}
    dataloggers = dict(
        db.query(ConexionFTP.id_cnxn, ConexionFTP.nmbr)
        .filter(ConexionFTP.id_cnxn.in_(ids_cnxn))
        .all()
    )

    items = sorted(
        (
            {"id_cnxn": id_cnxn, "nombre": dataloggers.get(id_cnxn, "Desconocido")}
            for id_cnxn in ids_cnxn
        ),
        key=lambda d: d["nombre"],
    )
    return {"items": items}


@router.get("/cola")
def listar_cola_ingesta(
    id_dspstv: int | None = Query(default=None, gt=0),
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
    query = _filtrar_cola(query, db, usuario)

    if estado is not None:
        query = query.filter(ArchivoIngesta.estd == _validar_estado_negocio(estado))

    if id_cnxn is not None:
        query = query.filter(ArchivoIngesta.id_cnxn == id_cnxn)
    if id_dspstv is not None:
        query = query.filter(ArchivoIngesta.id_dspstv == id_dspstv)

    total = query.count()
    archivos = (
        query.order_by(ArchivoIngesta.fch_dtccn.desc(), ArchivoIngesta.id_archv.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    dataloggers = _mapa_dataloggers(db, archivos)
    items = [
        ArchivoIngestaListItem(
            id_archv=a.id_archv,
            nmbr_archv=a.nmbr_archv,
            datalogger_nombre=dataloggers.get(a.id_archv, "Desconocido"),
            fch_dtccn=a.fch_dtccn,
            estado=ESTADO_BD_A_NEGOCIO.get(a.estd, a.estd),
            mnsj_errr=a.mnsj_errr,
        )
        for a in archivos
    ]
    fallidos = query.filter(ArchivoIngesta.estd == "Fallido").count()
    return {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "items": items,
        "fallidos": fallidos,
        "puede_reprocesar": _puede_reprocesar(db, usuario),
    }


@router.post("/cola/reintentar-fallidos", response_model=ReintentoMasivoResponse)
def reintentar_fallidos_ingesta(
    id_cnxn: int | None = Query(default=None, gt=0),
    id_dspstv: int | None = Query(default=None, gt=0),
    estado: str | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", EDICION)),
):
    _exigir_rol(usuario)
    if estado is not None and _validar_estado_negocio(estado) != "Fallido":
        return ReintentoMasivoResponse(reencolados=0)
    query = _filtrar_cola(db.query(ArchivoIngesta).join(ConexionFTP), db, usuario)
    query = query.filter(ArchivoIngesta.estd == "Fallido")
    if id_cnxn is not None:
        query = query.filter(ArchivoIngesta.id_cnxn == id_cnxn)
    if id_dspstv is not None:
        query = query.filter(ArchivoIngesta.id_dspstv == id_dspstv)
    fallidos = (
        query.order_by(ArchivoIngesta.id_archv)
        .with_for_update(of=ArchivoIngesta, skip_locked=True)
        .all()
    )
    for archivo in fallidos:
        _verificar_archivo(db, usuario, archivo, EDICION)
        solicitar(db, archivo, int(usuario["sub"]))
    _confirmar_solicitudes(db)
    return ReintentoMasivoResponse(reencolados=len(fallidos))


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

    _verificar_archivo(db, usuario, archivo)

    datalogger_nombre = _mapa_dataloggers(db, [archivo])[archivo.id_archv]

    return ArchivoIngestaDetalle(
        id_archv=archivo.id_archv,
        nmbr_archv=archivo.nmbr_archv,
        datalogger_nombre=datalogger_nombre,
        estado=ESTADO_BD_A_NEGOCIO.get(archivo.estd, archivo.estd),
        fch_dtccn=archivo.fch_dtccn,
        fch_prcsd=archivo.fch_prcsd,
        rgstrs_prcsds=archivo.rgstrs_prcsds,
        mnsj_errr=archivo.mnsj_errr,
        puede_reprocesar=_puede_reprocesar(db, usuario),
    )


@router.get("/cola/{id_archv}/intentos", response_model=list[IntentoProcesamientoListItem])
def intentos_archivo_ingesta(
    id_archv: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    """Solicitudes pendientes, ejecuciones y resultados, más recientes primero.

    Conserva cada ejecución anterior, incluidas interrupciones y errores
    transitorios. Los registros antiguos no inventan una fecha de inicio.
    """
    archivo = db.query(ArchivoIngesta).filter(ArchivoIngesta.id_archv == id_archv).first()
    if archivo is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    _verificar_archivo(db, usuario, archivo)

    # id_usr es NULLABLE (intento automático), así que el nombre se trae
    # con un LEFT JOIN -un INNER perdería justo esas filas-, mismo patrón
    # que AuditoriaListItem en routers/auditoria.py.
    filas = (
        db.query(IntentoProcesamiento, Usuario.nmbr_cmplt)
        .outerjoin(Usuario, Usuario.id_usr == IntentoProcesamiento.id_usr)
        .filter(IntentoProcesamiento.id_archv == id_archv)
        .order_by(IntentoProcesamiento.fch_intnt.desc(), IntentoProcesamiento.id_intnt.desc())
        .all()
    )

    return [
        IntentoProcesamientoListItem(
            id_intnt=intento.id_intnt,
            fch_intnt=intento.fch_intnt,
            rsltd=intento.rsltd,
            mnsj_errr=intento.mnsj_errr,
            id_usr=intento.id_usr,
            usuario_nombre=nombre,
            fch_inicio=intento.fch_inicio,
            fch_fin=intento.fch_fin,
            reintentos=intento.reintentos,
            registros_guardados=intento.registros_guardados,
        )
        for intento, nombre in filas
    ]


FILAS_MOSTRADAS_REGISTROS_INGESTA = 50


@router.get("/cola/{id_archv}/original")
def descargar_original_ingesta(
    id_archv: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    archivo = db.get(ArchivoIngesta, id_archv)
    if archivo is None:
        raise HTTPException(404, "Archivo no encontrado")
    _verificar_archivo(db, usuario, archivo)
    try:
        original = leer_original(archivo)
    except ValueError as exc:
        raise HTTPException(409, "La copia original requiere revisión de integridad") from exc
    except Exception as exc:
        raise HTTPException(
            503, "No se pudo recuperar la copia original. Vuelve a intentarlo."
        ) from exc
    if original is None:
        raise HTTPException(409, "Este registro aún no tiene una copia original archivada")
    return Response(
        original,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="original-{id_archv}.dat"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


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

    Se consulta la copia archivada. Un archivo del FTP con el mismo nombre
    puede ser una versión diferente y nunca sustituye silenciosamente al original.
    """
    archivo = db.query(ArchivoIngesta).filter(ArchivoIngesta.id_archv == id_archv).first()
    if archivo is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    _verificar_archivo(db, usuario, archivo)

    try:
        dispositivo = dispositivo_del_archivo(db, archivo)
        # HU49: esta es una vista de SOLO LECTURA (vuelve a resolver el
        # formato de un archivo ya procesado nada más que para mostrar su
        # contenido crudo), así que no debe tener el efecto secundario de
        # crear un mp_frmt nuevo con su entrada de auditoría -eso queda
        # reservado al pipeline real de ingesta.
        formato = resolver_formato(
            db, dispositivo.id_dspstv, archivo.nmbr_archv, permitir_creacion_automatica=False
        )
    except (DispositivoNoResueltoError, MapeoNoEncontradoError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        original = leer_original(archivo)
        if original is None:
            raise HTTPException(
                409,
                "Este registro no tiene una copia original archivada. No se sustituirá por el archivo actual del FTP.",
            )
        contenido = original.decode("utf-8-sig")
    except HTTPException:
        raise
    except UnicodeDecodeError as exc:
        raise HTTPException(
            422, "El original no es texto UTF-8 válido; descárgalo para revisión"
        ) from exc
    except ValueError as exc:
        raise HTTPException(409, "La copia original requiere revisión de integridad") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo recuperar la copia original archivada. Vuelve a intentarlo.",
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
    _exigir_rol(usuario)
    archivo = db.query(ArchivoIngesta).filter_by(id_archv=id_archv).with_for_update().first()
    if archivo is None:
        raise HTTPException(404, "Archivo no encontrado")
    _verificar_archivo(db, usuario, archivo, EDICION)
    if archivo.estd != "Fallido":
        raise HTTPException(409, "Solo se pueden reprocesar archivos en estado Fallido")
    solicitar(db, archivo, int(usuario["sub"]))
    _confirmar_solicitudes(db)
    return detalle_archivo_ingesta(id_archv, db, usuario)
