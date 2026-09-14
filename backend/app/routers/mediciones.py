"""
HU 13 - Seleccionar parámetros y ubicaciones
HU 12 - Seleccionar rango de fechas

CA: el Cliente Final filtra la vista de telemetría por uno o más
parámetros y/o ubicaciones (selección múltiple). Sin filtros, se muestran
todos los datos disponibles para la cuenta. Los parámetros y ubicaciones
ofrecidos dependen de lo asignado al usuario (prms_ubccn, HU 21) y del
catálogo de parámetros mapeados (mp_clmn/prmtr, HU 06).

HU 12: además, la vista se puede acotar a un rango de fechas (fecha_inicio/
fecha_fin, con hora incluida). La fecha de inicio no puede ser posterior a
la fecha de fin, y no se permiten fechas futuras. Sin fecha_inicio/
fecha_fin, no se aplica ningún filtro de fecha (DEC-11: "LIMPIAR FILTROS"
de HU13 sigue sin depender de ningún filtro de fecha).
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Dispositivo,
    EventoTexto,
    MapeoColumna,
    MapeoFormato,
    Parametro,
    Telemetria,
    Ubicacion,
)
from app.schemas import MedicionListItem, ParametroListItem
from app.security.permisos import LECTURA, require_permiso
from app.services.cache import consultas as cache
from app.services.cache.downsampling import (
    MAXIMO_PUNTOS_DEFECTO,
    muestrear,
    rango_es_amplio,
)

# HU 21: el filtro "qué ubicaciones ve este usuario" se movió a
# security/ubicaciones_permitidas.py para que HU 17 (mapa del Cliente
# Final) lo REUTILICE en vez de copiarlo. El comportamiento es idéntico
# al que tenía la función privada que vivía acá.
from app.security.ubicaciones_permitidas import (  # noqa: F401  (ROLES_... se reexporta)
    ROLES_CON_ACCESO_TOTAL,
    ubicaciones_permitidas as _ubicaciones_permitidas,
)

router = APIRouter(prefix="/mediciones", tags=["Mediciones"])


@router.get("/parametros")
def listar_parametros_disponibles(
    db: Session = Depends(get_db),
    # "Mediciones" no es un módulo válido en prms_usr_sd (HT-03: solo
    # Usuarios/Ubicaciones/Dispositivos/Ingesta/Tableros/Alarmas/Comercial).
    # La consulta de datos de telemetría cae dentro de "Tableros", que ya
    # tiene Lectura otorgada al Cliente Final en el seed.
    usuario: dict = Depends(require_permiso("Tableros", LECTURA)),
):
    """CA1: lista los parámetros disponibles asociados a las ubicaciones
    asignadas al usuario. Un parámetro solo aparece si está mapeado (HU 06)
    para algún dispositivo de esas ubicaciones."""
    ids_ubicaciones = _ubicaciones_permitidas(db, usuario)
    if not ids_ubicaciones:
        return {"items": []}

    # DEC-09: el mapeo ya no cuelga de dspstv.id_mp (columna eliminada),
    # sino al revés: mp_frmt.id_dspstv apunta al dispositivo. El join pasa
    # por mp_frmt para llegar del parámetro al dispositivo.
    parametros = (
        db.query(Parametro)
        .join(MapeoColumna, MapeoColumna.id_prmtr == Parametro.id_prmtr)
        .join(MapeoFormato, MapeoFormato.id_mp == MapeoColumna.id_mp)
        .join(Dispositivo, Dispositivo.id_dspstv == MapeoFormato.id_dspstv)
        .filter(Dispositivo.id_ubccn.in_(ids_ubicaciones))
        .distinct()
        .order_by(Parametro.nmbr)
        .all()
    )
    items = [ParametroListItem.model_validate(p) for p in parametros]
    return {"items": items}


@router.get("")
def listar_mediciones(
    parametro_ids: list[int] | None = Query(default=None),
    ubicacion_ids: list[int] | None = Query(default=None),
    fecha_inicio: dt.datetime | None = Query(default=None),
    fecha_fin: dt.datetime | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=50, ge=1, le=500),
    # HT-10 CA3: tope de puntos cuando el rango es amplio (>30 días).
    # Configurable por petición para que la gráfica pueda pedir menos
    # puntos que el default según su ancho real en pantalla.
    max_puntos: int = Query(default=MAXIMO_PUNTOS_DEFECTO, ge=1, le=50000),
    db: Session = Depends(get_db),
    # "Mediciones" no es un módulo válido en prms_usr_sd (HT-03: solo
    # Usuarios/Ubicaciones/Dispositivos/Ingesta/Tableros/Alarmas/Comercial).
    # La consulta de datos de telemetría cae dentro de "Tableros", que ya
    # tiene Lectura otorgada al Cliente Final en el seed.
    usuario: dict = Depends(require_permiso("Tableros", LECTURA)),
):
    """CA2-CA4: aplica los filtros de parámetros y/o ubicaciones sobre la
    vista de datos. Si no se selecciona ninguno, se muestran todos los
    datos disponibles para la cuenta (dentro de las ubicaciones permitidas).

    Combina tlmtr (parámetros 'numerico') y evnt_txt (parámetros 'texto',
    ej. "Puerta Abierta"): un parámetro de texto se ofrece en /parametros
    igual que uno numérico (ver listar_parametros_disponibles, que no
    filtra por tipo_dato), así que sin esto el filtro lo dejaba elegir
    pero la tabla nunca mostraba sus valores.

    HT-10: la respuesta se cachea en Redis con TTL corto, con la clave
    compuesta por el ÁMBITO DE VISIBILIDAD del usuario (sede + ubicaciones
    permitidas) más todos los parámetros de consulta, incluido el rango de
    fechas. Ver services/cache/consultas.py: la clave por ámbito es lo que
    impide que la respuesta de una sede se sirva a otra (CA4).
    """
    ids_ubicaciones_permitidas = set(_ubicaciones_permitidas(db, usuario))

    # HT-10 CA4: el ámbito entra en la clave, así que dos usuarios con
    # visibilidad distinta nunca comparten entrada aunque pidan la misma
    # URL. Se calcula con la lista YA resuelta de ubicaciones permitidas.
    ambito = cache.ambito_de_usuario(usuario, ids_ubicaciones_permitidas)
    clave_cache = cache.clave(
        "mediciones",
        ambito,
        parametro_ids=parametro_ids,
        ubicacion_ids=ubicacion_ids,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        pagina=pagina,
        por_pagina=por_pagina,
        max_puntos=max_puntos,
    )
    cacheado = cache.obtener(clave_cache)
    if cacheado is not None:
        return cacheado

    def _query_base(modelo):
        query = (
            db.query(modelo, Ubicacion, Parametro)
            .join(Dispositivo, Dispositivo.id_dspstv == modelo.id_dspstv)
            .join(Ubicacion, Ubicacion.id_ubccn == Dispositivo.id_ubccn)
            .join(Parametro, Parametro.id_prmtr == modelo.id_prmtr)
            .filter(Ubicacion.id_ubccn.in_(ids_ubicaciones_permitidas))
        )
        if ubicacion_ids:
            ids_solicitadas = set(ubicacion_ids) & ids_ubicaciones_permitidas
            query = query.filter(Ubicacion.id_ubccn.in_(ids_solicitadas))
        if parametro_ids:
            query = query.filter(Parametro.id_prmtr.in_(parametro_ids))
        # HT-10 punto 4: el rango de fechas se aplica EN SQL.
        #
        # HU12 documentaba estos dos parámetros y el endpoint los recibía,
        # pero no llegaban a la consulta: se traían TODAS las filas de las
        # ubicaciones permitidas y el rango no se aplicaba en ninguna
        # parte. Además de devolver datos fuera del rango pedido, hacía
        # imposible el partition pruning de HT-08 -sin predicado sobre
        # fch_hr, Postgres tiene que escanear todas las particiones de
        # tlmtr-. Filtrar acá es lo que hace que esta consulta use
        # idx_tlmtr_sd (id_sd, fch_hr) y el índice BRIN sobre fch_hr.
        if fecha_inicio is not None:
            query = query.filter(modelo.fch_hr >= fecha_inicio)
        if fecha_fin is not None:
            query = query.filter(modelo.fch_hr <= fecha_fin)
        # El ORDER BY se baja a SQL (antes se ordenaba en Python sobre la
        # lista completa) para que el planner pueda resolverlo por índice.
        return query.order_by(modelo.fch_hr.desc())

    mediciones = _query_base(Telemetria).all()
    eventos = _query_base(EventoTexto).all()

    items = [
        MedicionListItem(
            id_registro=t.id_lctr,
            fch_hr=t.fch_hr,
            id_ubccn=u.id_ubccn,
            ubicacion_nombre=u.nmbr,
            id_prmtr=p.id_prmtr,
            parametro_nombre=p.nmbr,
            undd=p.undd,
            vlr=float(t.vlr),
        )
        for t, u, p in mediciones
    ] + [
        MedicionListItem(
            id_registro=e.id_evnt,
            fch_hr=e.fch_hr,
            id_ubccn=u.id_ubccn,
            ubicacion_nombre=u.nmbr,
            id_prmtr=p.id_prmtr,
            parametro_nombre=p.nmbr,
            undd=p.undd,
            vlr=e.vlr,
        )
        for e, u, p in eventos
    ]
    # Las dos consultas ya vienen ordenadas de SQL, pero hay que
    # reordenar la UNION de ambas (tlmtr + evnt_txt son tablas distintas).
    items.sort(key=lambda item: item.fch_hr, reverse=True)

    # HT-10 CA3: rango amplio (>30 días) -> downsampling con tope
    # configurable. Se aplica ANTES de paginar: el criterio es "cuántos
    # puntos representan esta serie", no "cuántos caben en una página", y
    # muestrear después dejaría el total sin reducir.
    #
    # El muestreo es uniforme y determinista; el criterio y sus límites
    # están documentados en services/cache/downsampling.py.
    downsampling_aplicado = False
    total_sin_muestrear = len(items)
    if rango_es_amplio(fecha_inicio, fecha_fin) and total_sin_muestrear > max_puntos:
        items = muestrear(items, max_puntos)
        downsampling_aplicado = True

    total = len(items)
    items_pagina = items[(pagina - 1) * por_pagina : (pagina - 1) * por_pagina + por_pagina]

    respuesta = {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        # CA3: el frontend necesita poder decir "mostrando una muestra de
        # N puntos de M" en la gráfica; sin estos dos campos, una serie
        # muestreada es indistinguible de una con menos datos reales.
        "downsampling": downsampling_aplicado,
        "total_sin_muestrear": total_sin_muestrear,
        "items": items_pagina,
    }

    # HT-10: se cachea la respuesta ya serializable. Los índices de
    # invalidación son las SEDES presentes en la respuesta (punto 3): una
    # lectura nueva de cualquiera de ellas debe tirar esta entrada.
    #
    # Se indexa por sede y no por ubicación porque la clave se arma con el
    # ámbito completo del usuario -que puede abarcar varias ubicaciones de
    # una sede-, y una lectura nueva en cualquiera de ellas cambia esta
    # respuesta. invalidar_por_lectura() borra ambos índices, así que el
    # camino de escritura acierta igual.
    sedes_en_respuesta = {u.id_sd for _, u, _ in mediciones} | {u.id_sd for _, u, _ in eventos}
    if not sedes_en_respuesta:
        # Respuesta vacía: no hay ninguna sede en los resultados de la que
        # colgar el índice, pero la entrada IGUAL debe invalidarse cuando
        # llegue el primer dato -si no, el usuario seguiría viendo "sin
        # datos" durante todo el TTL después de que su primera lectura
        # entrara-. Se indexa por las ubicaciones que el usuario puede
        # ver, que es el ámbito exacto de esta respuesta vacía.
        indices = [cache.indice_de_ubicacion(i) for i in ids_ubicaciones_permitidas]
    else:
        indices = [cache.indice_de_sede(s) for s in sedes_en_respuesta]
    cache.guardar(
        clave_cache,
        jsonable_encoder(respuesta),
        ttl=cache.TTL_CORTO,
        indices=indices,
    )
    return respuesta
