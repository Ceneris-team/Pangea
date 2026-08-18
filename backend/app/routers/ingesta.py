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
from app.models import ArchivoIngesta, ConexionFTP, Dispositivo
from app.schemas import ArchivoIngestaDetalle, ArchivoIngestaListItem, MetricasColaIngesta
from app.security.permisos import LECTURA, require_permiso, verificar_sede

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


@router.get("/cola")
def listar_cola_ingesta(
    estado: str | None = Query(
        default=None, description="En espera | Procesando | Procesado | Fallido"
    ),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=POR_PAGINA_DEFAULT, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Ingesta", LECTURA)),
):
    """CA1: listado paginado de la cola, orden fch_dtccn descendente.
    CA2: filtro opcional por estado (lenguaje de negocio de la HU)."""
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
    verificar_sede(usuario, conexion.id_sd, modulo="Ingesta", accion=LECTURA)

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
