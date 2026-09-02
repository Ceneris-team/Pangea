"""
HU 10 - Listar dispositivos

CA: tabla con Nombre, Marca, Ubicación y Estado. Búsqueda por nombre o marca
(insensible a mayúsculas). Filtro por ubicación y por estado. Paginado de 10
por defecto. Mismo patrón de acceso que HU07 (routers/ubicaciones.py):
Administrador y Técnico CENERIS ven el listado completo (dentro de su sede);
Cliente Final solo ve dispositivos cuya ubicación esté en PermisoUbicacion.

Dispositivo no tiene id_sd propio (ver mapeo_dispositivo.py): el
aislamiento por sede (HT-09 CA3) se resuelve vía join con Ubicacion, mismo
criterio que mapeos.py e ingesta.py usan con su propio id_sd.

HU 11 - Añadir dispositivo

CA1: formulario con Nombre, Marca, Modelo (opcional), Ubicación y Conexión
FTP, más el punto GPS del dispositivo:

  lttd/lngtd (NOT NULL, punto GPS del dispositivo): DEC-28 los convierte
  en el punto PROPIO del dispositivo, no una copia del centro de su
  Ubicación. Son opcionales en el body: si no vienen, crear_dispositivo
  cae al centro de la Ubicación (comportamiento previo) para no romper a
  los clientes que todavía no los mandan. Son columnas independientes de
  las de Ubicacion (no hay FK).

  Todavía NO se valida que el punto caiga dentro del polígono de su
  Ubicación (plgn_gjsn): eso es tarea aparte (R-06 del RAID), y depende
  de que el punto sea real y editable, que es justo lo que hace DEC-28.

DEC-09: el dispositivo ya NO resuelve un mapeo de formato al crearse. El
mapeo pasó a colgar del dispositivo (mp_frmt.id_dspstv), así que primero
existe el dispositivo y después se le configura su mapeo en HU06; crear un
dispositivo sin mapeo es un estado válido (todavía no ingesta nada).

Además valida (no es un CA literal, pero lo exige la arquitectura de
ingesta ya existente): resolver_dispositivo() en
services/ingesta/persistencia.py asume EXACTAMENTE un dispositivo Activo
por conexión FTP para poder resolver a qué dispositivo pertenece un
archivo entrante. Un segundo dispositivo Activo en la misma conexión
rompería esa resolución en silencio, así que se rechaza con 409.
"""

import datetime as dt

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ConexionFTP, Dispositivo, PermisoUbicacion, Ubicacion
from app.models.archivo_ingesta import ArchivoIngesta
from app.models.mapeo_dispositivo import MapeoColumna, MapeoFormato
from app.models.telemetria import Telemetria
from app.schemas import (
    CargaManualRequest,
    DispositivoCreado,
    DispositivoCrear,
    DispositivoDetalle,
    DispositivoListItem,
    DispositivoParaMapa,
    DispositivoUpdate,
    LogIngestaListItem,
)
from app.security.auditoria import limpiar_contexto_auditoria, marcar_contexto_auditoria
from app.security.permisos import EDICION, LECTURA, require_permiso, verificar_sede
from app.services.cache.invalidacion import invalidar_por_lectura
from app.services.ingesta.mapeo import MapeoNoEncontradoError, resolver_formato
from app.services.ingesta.usuario_sistema import resolver_id_usuario_sistema
from app.services.particiones import (
    ParticionInexistenteError,
    es_error_de_particion_faltante,
)
from app.tasks.ingesta import ErrorDatosNoRecuperable, interpretar_y_guardar

router = APIRouter(prefix="/dispositivos", tags=["Dispositivos"])

ROLES_CON_ACCESO_TOTAL = {"Administrador", "Tecnico CENERIS", "Técnico CENERIS"}


@router.get("")
def listar_dispositivos(
    busqueda: str | None = Query(
        default=None, description="Nombre o marca del dispositivo, parcial"
    ),
    id_ubccn: int | None = Query(default=None, description="Filtrar por ubicación"),
    estado: str | None = Query(default=None, description="Activo / Inactivo"),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=10, ge=1, le=100),  # CA: 10 por defecto
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Dispositivos", LECTURA)),
):
    query = db.query(Dispositivo, Ubicacion.nmbr).join(
        Ubicacion, Ubicacion.id_ubccn == Dispositivo.id_ubccn
    )

    # Aislamiento por sede (HT-09 CA3): un usuario 'por_sede' solo ve los
    # dispositivos de ubicaciones de su sede, aunque pida otra explícitamente.
    if usuario.get("scope") == "por_sede":
        query = query.filter(Ubicacion.id_sd == usuario["sede_id"])

    # CA: Administrador/Tecnico CENERIS ven todo; Cliente solo lo asignado.
    if usuario.get("rol") not in ROLES_CON_ACCESO_TOTAL:
        id_usr = int(usuario["sub"])
        query = query.join(
            PermisoUbicacion, PermisoUbicacion.id_ubccn == Dispositivo.id_ubccn
        ).filter(PermisoUbicacion.id_usr == id_usr)

    if busqueda:
        patron = f"%{busqueda.lower()}%"
        query = query.filter(
            func.lower(Dispositivo.nmbr).like(patron) | func.lower(Dispositivo.mrc).like(patron)
        )
    if id_ubccn is not None:
        query = query.filter(Dispositivo.id_ubccn == id_ubccn)
    if estado:
        query = query.filter(Dispositivo.estd == estado)

    total = query.count()
    filas = (
        query.order_by(Dispositivo.nmbr).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    )

    items = [
        DispositivoListItem(
            id_dspstv=dispositivo.id_dspstv,
            nmbr=dispositivo.nmbr,
            mrc=dispositivo.mrc,
            ubicacion_nombre=ubicacion_nombre,
            estd=dispositivo.estd,
        )
        for dispositivo, ubicacion_nombre in filas
    ]

    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": items}


@router.get("/mapa", response_model=list[DispositivoParaMapa])
def dispositivos_para_mapa(
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Dispositivos", LECTURA)),
):
    """I-17: los dispositivos que pinta la vista de mapa (HU22), con su
    punto GPS propio (DEC-28), en una sola llamada.

    Se declara ANTES de GET /{id_dspstv}: si fuera después, esa ruta
    capturaría "mapa" como si fuera un id y respondería 422.

    Endpoint propio y no un campo anidado dentro de GET /ubicaciones/mapa
    porque "Ubicaciones" y "Dispositivos" son módulos de permiso
    SEPARADOS (HT-03): anidarlos entregaría datos de dispositivos a quien
    solo tiene Lectura sobre Ubicaciones. Así cada recurso sigue
    exigiendo el suyo, y el frontend hace dos llamadas en paralelo -no
    N+1: una por recurso, no una por ubicación-.

    Sin paginar ni filtrar por estado, igual que /ubicaciones/mapa: se
    muestran todos y el color los distingue. Los filtros de visibilidad
    (sede y PermisoUbicacion) sí se mantienen, replicando exactamente los
    de listar_dispositivos, porque son reglas de acceso.
    """
    query = db.query(Dispositivo).join(Ubicacion, Ubicacion.id_ubccn == Dispositivo.id_ubccn)

    # Aislamiento por sede (HT-09 CA3). Dispositivo no tiene id_sd propio:
    # se resuelve por su ubicación, igual que en listar_dispositivos.
    if usuario.get("scope") == "por_sede":
        query = query.filter(Ubicacion.id_sd == usuario["sede_id"])

    if usuario.get("rol") not in ROLES_CON_ACCESO_TOTAL:
        id_usr = int(usuario["sub"])
        query = query.join(
            PermisoUbicacion, PermisoUbicacion.id_ubccn == Dispositivo.id_ubccn
        ).filter(PermisoUbicacion.id_usr == id_usr)

    return [
        DispositivoParaMapa.model_validate(dispositivo)
        for dispositivo in query.order_by(Dispositivo.nmbr).all()
    ]


@router.post("", status_code=201)
def crear_dispositivo(
    body: DispositivoCrear,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Dispositivos", EDICION)),
):
    """CA2: 'GUARDAR' registra el dispositivo con estado 'Activo' y
    devuelve 201 con 'Dispositivo añadido correctamente', mismo formato de
    respuesta que crear_ubicacion (HU08)."""
    ubicacion = db.query(Ubicacion).filter(Ubicacion.id_ubccn == body.id_ubccn).first()
    if ubicacion is None:
        raise HTTPException(status_code=422, detail=f"La ubicación {body.id_ubccn} no existe")
    if ubicacion.estd != "Activa":
        raise HTTPException(status_code=422, detail="La ubicación elegida no está Activa")

    conexion = db.query(ConexionFTP).filter(ConexionFTP.id_cnxn == body.id_cnxn).first()
    if conexion is None:
        raise HTTPException(status_code=422, detail=f"La conexión FTP {body.id_cnxn} no existe")

    # Un usuario 'por_sede' no puede crear un dispositivo en una ubicación
    # de otra sede aunque conozca su id_ubccn (HT-09 CA3).
    verificar_sede(usuario, ubicacion.id_sd, db, modulo="Dispositivos", accion=EDICION)

    # resolver_dispositivo() en services/ingesta/persistencia.py asume
    # exactamente 1 dispositivo Activo por conexión FTP; un segundo
    # rompería en silencio la resolución de archivos entrantes.
    ya_tiene_activo = (
        db.query(Dispositivo)
        .filter(Dispositivo.id_cnxn == body.id_cnxn, Dispositivo.estd == "Activo")
        .first()
    )
    if ya_tiene_activo is not None:
        raise HTTPException(
            status_code=409,
            detail="Esta conexión FTP ya tiene un dispositivo activo asociado",
        )

    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn,
        id_cnxn=conexion.id_cnxn,
        nmbr=body.nmbr,
        mrc=body.mrc,
        mdl=body.mdl,
        # DEC-28: el punto GPS propio del dispositivo. Si el formulario no
        # lo manda, se cae al centro de la Ubicación -el comportamiento de
        # siempre- para no romper a quien todavía crea sin coordenadas.
        lttd=body.lttd if body.lttd is not None else ubicacion.lttd,
        lngtd=body.lngtd if body.lngtd is not None else ubicacion.lngtd,
        # estd lo pone el server_default 'Activo' del modelo.
    )
    db.add(dispositivo)
    db.commit()
    db.refresh(dispositivo)

    return {
        "mensaje": "Dispositivo añadido correctamente",
        "dispositivo": DispositivoCreado.model_validate(dispositivo),
    }


def _cargar_ficha(db: Session, id_dspstv: int, usuario: dict, accion: str):
    """Dispositivo + ubicación + conexión, con la sede ya verificada.

    Lo comparten los cuatro endpoints de la ficha (DEC-09 / IMP-06): todos
    necesitan el mismo contexto y el mismo aislamiento por sede, que se
    resuelve vía Ubicacion igual que en el listado."""
    fila = (
        db.query(Dispositivo, Ubicacion, ConexionFTP)
        .join(Ubicacion, Ubicacion.id_ubccn == Dispositivo.id_ubccn)
        .join(ConexionFTP, ConexionFTP.id_cnxn == Dispositivo.id_cnxn)
        .filter(Dispositivo.id_dspstv == id_dspstv)
        .first()
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    dispositivo, ubicacion, conexion = fila
    verificar_sede(usuario, ubicacion.id_sd, db, modulo="Dispositivos", accion=accion)

    # Un Cliente Final solo ve dispositivos de ubicaciones que tenga
    # asignadas, mismo criterio que el listado de HU10.
    if usuario.get("rol") not in ROLES_CON_ACCESO_TOTAL:
        tiene_permiso = (
            db.query(PermisoUbicacion)
            .filter(
                PermisoUbicacion.id_ubccn == dispositivo.id_ubccn,
                PermisoUbicacion.id_usr == int(usuario["sub"]),
            )
            .first()
        )
        if tiene_permiso is None:
            raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    return dispositivo, ubicacion, conexion


@router.get("/{id_dspstv}", response_model=DispositivoDetalle)
def obtener_dispositivo(
    id_dspstv: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Dispositivos", LECTURA)),
):
    """Cabecera de la ficha del dispositivo (DEC-09).

    Las pestañas Formato y Datos leen y escriben sus mapeos vía
    /mapeos?id_dspstv=... (HU06), que ya trabaja por dispositivo; acá solo
    va el contexto común que la ficha muestra arriba."""
    dispositivo, ubicacion, conexion = _cargar_ficha(db, id_dspstv, usuario, LECTURA)
    return DispositivoDetalle(
        id_dspstv=dispositivo.id_dspstv,
        nmbr=dispositivo.nmbr,
        mrc=dispositivo.mrc,
        mdl=dispositivo.mdl,
        estd=dispositivo.estd,
        lttd=dispositivo.lttd,
        lngtd=dispositivo.lngtd,
        id_ubccn=ubicacion.id_ubccn,
        ubicacion_nombre=ubicacion.nmbr,
        id_sd=ubicacion.id_sd,
        id_cnxn=conexion.id_cnxn,
        conexion_nombre=conexion.nmbr,
        # Solo lectura: el intervalo de polling se edita en la Conexión
        # FTP (HU05). Ver la nota de DispositivoDetalle.
        conexion_frcnc_mnts=conexion.frcnc_mnts,
    )


@router.put("/{id_dspstv}")
def actualizar_dispositivo(
    id_dspstv: int,
    body: DispositivoUpdate,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Dispositivos", EDICION)),
):
    """Edición de nombre/marca/modelo y reasignación de Conexión FTP.

    Caso real que motiva esto: un dispositivo quedó creado apuntando a
    la ConexionFTP equivocada (los archivos entrantes nunca calzan con
    ese id_cnxn) y hace falta corregirlo sin recrear el dispositivo -eso
    perdería su historial de mapeos (mp_frmt) y de ArchivoIngesta ya
    asociados a este id_dspstv.
    """
    dispositivo, ubicacion, _conexion_actual = _cargar_ficha(db, id_dspstv, usuario, EDICION)

    if body.id_cnxn is not None and body.id_cnxn != dispositivo.id_cnxn:
        conexion_nueva = db.query(ConexionFTP).filter(ConexionFTP.id_cnxn == body.id_cnxn).first()
        if conexion_nueva is None:
            raise HTTPException(
                status_code=422, detail=f"La conexión FTP {body.id_cnxn} no existe"
            )

        # Mismo criterio que crear_dispositivo (línea 151-163): un solo
        # dispositivo Activo por conexión. Se excluye el propio
        # dispositivo de la búsqueda -si ya era el dueño de otra
        # conexión, reasignarlo no debe chocar consigo mismo-.
        ya_tiene_activo = (
            db.query(Dispositivo)
            .filter(
                Dispositivo.id_cnxn == body.id_cnxn,
                Dispositivo.estd == "Activo",
                Dispositivo.id_dspstv != id_dspstv,
            )
            .first()
        )
        if ya_tiene_activo is not None:
            raise HTTPException(
                status_code=409,
                detail="Esta conexión FTP ya tiene un dispositivo activo asociado",
            )

    datos = body.model_dump(exclude_unset=True)
    # lttd/lngtd son NOT NULL en el modelo: un null EXPLÍCITO en el body
    # pasa el filtro de exclude_unset (se envió, solo que vacío) y
    # reventaría como IntegrityError en el commit. Para estos dos campos
    # "null" significa "no lo toques", igual que omitirlos.
    for campo in ("lttd", "lngtd"):
        if campo in datos and datos[campo] is None:
            del datos[campo]

    for campo, valor in datos.items():
        setattr(dispositivo, campo, valor)

    db.commit()
    db.refresh(dispositivo)

    conexion = db.query(ConexionFTP).filter(ConexionFTP.id_cnxn == dispositivo.id_cnxn).first()
    return {
        "mensaje": "Dispositivo actualizado correctamente",
        "dispositivo": DispositivoDetalle(
            id_dspstv=dispositivo.id_dspstv,
            nmbr=dispositivo.nmbr,
            mrc=dispositivo.mrc,
            mdl=dispositivo.mdl,
            estd=dispositivo.estd,
            lttd=dispositivo.lttd,
            lngtd=dispositivo.lngtd,
            id_ubccn=ubicacion.id_ubccn,
            ubicacion_nombre=ubicacion.nmbr,
            id_sd=ubicacion.id_sd,
            id_cnxn=conexion.id_cnxn,
            conexion_nombre=conexion.nmbr,
            conexion_frcnc_mnts=conexion.frcnc_mnts,
        ),
    }


@router.get("/{id_dspstv}/logs", response_model=list[LogIngestaListItem])
def listar_logs_dispositivo(
    id_dspstv: int,
    limite: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Dispositivos", LECTURA)),
):
    """Pestaña LOGS: los archivos procesados de ESTE dispositivo.

    Reusa archv_ingst (el modelo de cola/log de HU09, ya presente en esta
    rama), sin tabla nueva. archv_ingst referencia la CONEXIÓN, no el
    dispositivo, así que el filtro va por id_cnxn: la equivalencia se
    sostiene porque HU11 garantiza un solo dispositivo activo por conexión
    (el 409 de crear_dispositivo), que es el mismo supuesto con el que
    resolver_dispositivo() decide a qué dispositivo pertenece un archivo
    entrante."""
    dispositivo, _ubicacion, _conexion = _cargar_ficha(db, id_dspstv, usuario, LECTURA)

    filas = (
        db.query(ArchivoIngesta)
        .filter(ArchivoIngesta.id_cnxn == dispositivo.id_cnxn)
        .order_by(ArchivoIngesta.fch_dtccn.desc())
        .limit(limite)
        .all()
    )
    return [LogIngestaListItem.model_validate(f) for f in filas]


@router.post("/{id_dspstv}/carga-archivo", status_code=201)
async def cargar_archivo_dat(
    id_dspstv: int,
    archivo: UploadFile = File(..., description="Archivo .dat de este dispositivo"),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Dispositivos", EDICION)),
):
    """Pestaña CARGA DE DATOS (IMP-06): sube un .dat de este dispositivo y
    lo procesa por el MISMO pipeline que la ingesta automática.

    El tipo de trama se sigue deduciendo del prefijo del nombre del
    archivo (detectar_tipo_trama, vía resolver_formato) contra los mp_frmt
    activos de ESTE dispositivo -letra libre, no un catálogo fijo H_/E_-,
    igual que para un archivo que llega por FTP: lo único que cambia es el
    origen del contenido. El parseo/estandarización/validación/persistencia son
    literalmente la misma función que usa la tarea Celery
    (tasks.ingesta.interpretar_y_guardar), para que un archivo dé el mismo
    resultado por las dos vías.

    Queda registrado en archv_ingst para que aparezca en la pestaña Logs
    junto a los de FTP.
    """
    dispositivo, _ubicacion, _conexion = _cargar_ficha(db, id_dspstv, usuario, EDICION)

    nombre = archivo.filename or ""
    contenido_bytes = await archivo.read()
    if not contenido_bytes:
        raise HTTPException(status_code=422, detail="El archivo está vacío")
    try:
        contenido = contenido_bytes.decode("utf-8")
    except UnicodeDecodeError:
        # Los .dat de campo a veces vienen en latin-1 (grados, ñ).
        contenido = contenido_bytes.decode("latin-1")

    # HU49 CA5: esta carga manual (IMP-06) comparte con la ingesta
    # automática por FTP el mismo resolver_formato -así que también puede
    # disparar la creación automática de una trama nueva, y esa creación
    # tiene que auditarse igual, sin importar el canal de entrada. Se
    # marca con el usuario Sistema (no con el usuario HTTP que subió el
    # archivo): quien "crea" la trama es el algoritmo de HU49, no el
    # técnico que casualmente disparó la corrida -mismo criterio que
    # tasks/ingesta.py-.
    id_usr_sistema = resolver_id_usuario_sistema(db)
    marcar_contexto_auditoria(db, id_usr_sistema)
    try:
        formato = resolver_formato(db, dispositivo.id_dspstv, nombre)
    except MapeoNoEncontradoError as exc:
        # Mismo criterio que el pipeline automático: sin mapeo no se puede
        # interpretar el archivo y adivinar produciría lecturas erróneas
        # en silencio. Acá se responde 422 en vez de marcar Fallido porque
        # hay un usuario esperando la respuesta.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        limpiar_contexto_auditoria(db)

    registro = ArchivoIngesta(
        id_cnxn=dispositivo.id_cnxn,
        nmbr_archv=nombre,
        estd="Procesando",
    )
    db.add(registro)
    db.flush()  # necesitamos id_archv para las filas de tlmtr

    try:
        resultado_validacion, resultado_persistencia = interpretar_y_guardar(
            db,
            contenido=contenido,
            formato=formato,
            dispositivo=dispositivo,
            id_cnxn=dispositivo.id_cnxn,
            id_archv=registro.id_archv,
            nombre_archivo=nombre,
        )
    except (ErrorDatosNoRecuperable, ParticionInexistenteError) as exc:
        # La transacción se descarta entera (incluida la fila de
        # archv_ingst): no queda un log 'Procesando' colgado de una carga
        # que el usuario ya sabe que falló.
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    registro.estd = "Exitoso"
    registro.fch_prcsd = dt.datetime.now(dt.timezone.utc)
    registro.rgstrs_prcsds = resultado_persistencia.guardadas
    if resultado_validacion.errores:
        resumen = "; ".join(
            f"fila {e.numero_fila}: {e.motivo}" for e in resultado_validacion.errores[:5]
        )
        registro.mnsj_errr = resumen[:500]
    db.commit()

    return {
        "mensaje": "Archivo procesado correctamente",
        "id_archv": registro.id_archv,
        "tipo_trama": formato.tipo_trama,
        "guardadas": resultado_persistencia.guardadas,
        "omitidas_sin_valor": resultado_persistencia.omitidas_sin_valor,
        "errores_validacion": len(resultado_validacion.errores),
    }


@router.post("/{id_dspstv}/carga-manual", status_code=201)
def cargar_punto_manual(
    id_dspstv: int,
    body: CargaManualRequest,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Dispositivos", EDICION)),
):
    """Pestaña CARGA MANUAL (IMP-06): un punto de telemetría capturado a
    mano, sin archivo.

    No pasa por el parser -no hay archivo que parsear-, pero sí escribe en
    la misma tlmtr que la ingesta automática. Los parámetros admitidos son
    los que el dispositivo tenga mapeados para la trama 'H': la carga
    manual es de datos periódicos, y aceptar un parámetro no mapeado
    guardaría una lectura que el dispositivo nunca produce.
    """
    dispositivo, ubicacion, _conexion = _cargar_ficha(db, id_dspstv, usuario, EDICION)

    # Los parámetros mapeados en la pestaña Datos para la trama 'H'.
    formato_h = (
        db.query(MapeoFormato)
        .filter(
            MapeoFormato.id_dspstv == dispositivo.id_dspstv,
            MapeoFormato.tp_trm == "H",
            MapeoFormato.estd == "Activo",
        )
        .first()
    )
    if formato_h is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Este dispositivo no tiene un mapeo activo de datos periódicos (H): "
                "configúralo en la pestaña Datos antes de cargar mediciones a mano"
            ),
        )

    ids_mapeados = {
        fila.id_prmtr
        for fila in db.query(MapeoColumna.id_prmtr)
        .filter(MapeoColumna.id_mp == formato_h.id_mp)
        .all()
    }
    pedidos = [item.id_prmtr for item in body.valores]
    no_mapeados = sorted(set(pedidos) - ids_mapeados)
    if no_mapeados:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Los parámetros {no_mapeados} no están mapeados para la trama 'H' "
                f"de este dispositivo"
            ),
        )
    if len(pedidos) != len(set(pedidos)):
        raise HTTPException(
            status_code=422,
            detail="Hay un parámetro repetido en la carga",
        )

    fecha_hora = body.fch_hr
    if fecha_hora.tzinfo is None:
        # Igual que el validador del pipeline: un timestamp sin zona se
        # interpreta como UTC, no como hora local del servidor.
        fecha_hora = fecha_hora.replace(tzinfo=dt.timezone.utc)
    if fecha_hora > dt.datetime.now(dt.timezone.utc):
        raise HTTPException(
            status_code=422,
            detail="La fecha y hora de la medición no puede ser futura",
        )

    for item in body.valores:
        db.add(
            Telemetria(
                fch_hr=fecha_hora,
                id_dspstv=dispositivo.id_dspstv,
                id_prmtr=item.id_prmtr,
                id_sd=ubicacion.id_sd,
                vlr=item.vlr,
                id_archv=None,  # no hay archivo de origen: es captura manual
            )
        )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if es_error_de_particion_faltante(exc):
            # HT-08 CA4: mismo caso que en la ingesta automática, pero acá
            # hay un usuario esperando, así que se responde en vez de
            # dejarlo para reprocesamiento.
            raise HTTPException(
                status_code=422,
                detail=(
                    f"No existe partición de tlmtr para {fecha_hora:%Y-%m-%d}. "
                    f"Revisa la fecha de la medición."
                ),
            ) from exc
        raise

    # HT-10 CA2: la carga manual escribe DIRECTO en tlmtr sin pasar por
    # services/ingesta/persistencia.py, así que la invalidación del
    # pipeline no la cubre: hay que dispararla también acá. Sin esto, un
    # punto cargado a mano no aparecía en la gráfica ni en el mapa hasta
    # que caducara la entrada cacheada.
    #
    # Después del commit de arriba, nunca antes (mismo criterio que
    # tasks/ingesta.py) y filtrada por la sede y la ubicación de ESTE
    # dispositivo, no global.
    invalidar_por_lectura(id_sd=ubicacion.id_sd, id_ubccn=dispositivo.id_ubccn)

    return {
        "mensaje": "Medición registrada correctamente",
        "fch_hr": fecha_hora.isoformat(),
        "guardadas": len(body.valores),
    }
