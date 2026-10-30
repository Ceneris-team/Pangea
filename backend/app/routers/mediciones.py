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

import base64
import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func
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
from app.routers.series_mediciones import router as series_router
from app.schemas import MedicionListItem, ParametroListItem
from app.security.permisos import LECTURA, require_permiso

# HU 21: el filtro "qué ubicaciones ve este usuario" se movió a
# security/ubicaciones_permitidas.py para que HU 17 (mapa del Cliente
# Final) lo REUTILICE en vez de copiarlo. El comportamiento es idéntico
# al que tenía la función privada que vivía acá.
from app.security.ubicaciones_permitidas import (  # noqa: F401  (ROLES_... se reexporta)
    ROLES_CON_ACCESO_TOTAL,
)
from app.security.ubicaciones_permitidas import (
    ubicaciones_permitidas as _ubicaciones_permitidas,
)
from app.services.cache import consultas as cache
from app.services.cache.downsampling import (
    MAXIMO_PUNTOS_DEFECTO,
    muestrear,
    rango_es_amplio,
)

router = APIRouter(prefix="/mediciones", tags=["Mediciones"])


router.include_router(series_router)

# HT-16 CA3: paginación por cursor keyset sobre (fch_hr, origen, id_registro).
# "origen" desempata entre Telemetria y EventoTexto -dos tablas distintas
# unidas en Python (ver más abajo)-, cuyas filas pueden compartir el mismo
# fch_hr exacto; id_registro desempata dentro de la misma tabla y el mismo
# fch_hr. El orden total (fch_hr, origen, id) es lo que hace al cursor
# estable ante inserciones concurrentes: una fila nueva se inserta en su
# posición según ESTA clave, nunca antes del cursor ya entregado, así que
# nunca duplica ni salta una fila de una página ya servida (a diferencia de
# OFFSET, que se corre si algo se inserta/borra antes de la página pedida).
_ORIGEN_TELEMETRIA = "t"
_ORIGEN_EVENTO = "e"


def _codificar_cursor(fch_hr: dt.datetime, origen: str, id_registro: int) -> str:
    crudo = f"{fch_hr.isoformat()}|{origen}|{id_registro}"
    return base64.urlsafe_b64encode(crudo.encode()).decode()


def _decodificar_cursor(cursor: str) -> tuple[dt.datetime, str, int]:
    try:
        crudo = base64.urlsafe_b64decode(cursor.encode()).decode()
        fch_hr_str, origen, id_registro_str = crudo.rsplit("|", 2)
        fch_hr = dt.datetime.fromisoformat(fch_hr_str)
        if origen not in (_ORIGEN_TELEMETRIA, _ORIGEN_EVENTO):
            raise ValueError
        return fch_hr, origen, int(id_registro_str)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail="El cursor no es válido") from exc


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


def _enriquecer_items(db: Session, candidatos: list[tuple]) -> list[MedicionListItem]:
    """Resuelve Ubicacion/Parametro/Dispositivo para un conjunto YA
    ACOTADO de filas de tlmtr/evnt_txt (la página final, no todo el
    resultado filtrado).

    HT-16 punto 1: antes este JOIN vivía dentro de _query_base y corría
    ANTES del ORDER BY+LIMIT, lo que le impedía al planner usar un top-N
    heapsort (ver el comentario sobre ids_dispositivos_query). Resolverlo
    acá, sobre como mucho 2*(por_pagina+1) filas o el total ya muestreado,
    cambia el costo de "un JOIN sobre potencialmente cientos de miles de
    filas" a "tres SELECT ... WHERE id IN (<=cientos de ids)", que golpean
    la PK de cada tabla.
    """
    if not candidatos:
        return []

    ids_dispositivo = {fila.id_dspstv for _, _, _, _, fila in candidatos}
    ids_parametro = {fila.id_prmtr for _, _, _, _, fila in candidatos}

    dispositivos = {
        d.id_dspstv: d
        for d in db.query(Dispositivo).filter(Dispositivo.id_dspstv.in_(ids_dispositivo)).all()
    }
    ubicaciones = {
        u.id_ubccn: u
        for u in db.query(Ubicacion)
        .filter(Ubicacion.id_ubccn.in_({d.id_ubccn for d in dispositivos.values()}))
        .all()
    }
    parametros = {
        p.id_prmtr: p
        for p in db.query(Parametro).filter(Parametro.id_prmtr.in_(ids_parametro)).all()
    }

    items = []
    for _fch_hr, _origen, _id, tipo, fila in candidatos:
        dispositivo = dispositivos[fila.id_dspstv]
        ubicacion = ubicaciones[dispositivo.id_ubccn]
        parametro = parametros[fila.id_prmtr]
        items.append(
            MedicionListItem(
                id_registro=fila.id_lctr if tipo == "t" else fila.id_evnt,
                fch_hr=fila.fch_hr,
                id_ubccn=ubicacion.id_ubccn,
                ubicacion_nombre=ubicacion.nmbr,
                id_sd=ubicacion.id_sd,
                id_dspstv=dispositivo.id_dspstv,
                dispositivo_nombre=dispositivo.nmbr,
                id_prmtr=parametro.id_prmtr,
                parametro_nombre=parametro.nmbr,
                undd=parametro.undd,
                vlr=float(fila.vlr) if tipo == "t" else fila.vlr,
            )
        )
    return items


@router.get("")
def listar_mediciones(
    parametro_ids: list[int] | None = Query(default=None),
    ubicacion_ids: list[int] | None = Query(default=None),
    # Una Ubicación puede tener más de un Dispositivo (dos dataloggers
    # midiendo el mismo parámetro en la misma estación es un caso real).
    # Sin este filtro, HU15 no podía aislar la serie de un solo datalogger
    # cuando el otro tenía lecturas con fallas mezcladas en el mismo
    # gráfico.
    dispositivo_ids: list[int] | None = Query(default=None),
    fecha_inicio: dt.datetime | None = Query(default=None),
    fecha_fin: dt.datetime | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    # El tope era 500, pensado para la TABLA de HU12 (una página que se
    # lee de a poco). La vista de gráficos (HU15) consume este mismo
    # endpoint pero necesita la serie entera de una vez, y como la
    # paginación es sobre la UNIÓN de todos los parámetros, 500 filas
    # repartidas entre 10 gráficos dejaban ~3 puntos por serie. El default
    # sigue en 50 para no cambiar el comportamiento de quien no lo pide;
    # el tamaño real de la respuesta lo sigue acotando max_puntos, que
    # aplica el downsampling antes de paginar.
    por_pagina: int = Query(default=50, ge=1, le=5000),
    # HT-16 CA3: cursor opaco (ver _codificar_cursor/_decodificar_cursor)
    # para pedir "la página siguiente" sin OFFSET. Coexiste con pagina/
    # por_pagina en vez de reemplazarlos: el MODO CURSOR solo se activa
    # cuando el rango pedido NO es amplio (o la tabla pide sin_muestreo)
    # y no hay frecuencia_muestreo activo (ver más abajo, "modo_cursor") -son los casos donde HT-16
    # midió el problema real (miles de filas sin LIMIT en SQL). Cuando el
    # rango es amplio o hay downsampling, la respuesta ya pasa por
    # muestrear() sobre la serie completa (HT-10), que por diseño necesita
    # conocer el conjunto entero para poder tomar 1 de cada N puntos; cortar
    # ese conjunto con LIMIT antes de muestrear rompería el criterio
    # "conserva la forma de la serie completa". pagina/por_pagina se
    # conservan intactos para ese caso (HU15, Graficos.tsx), que es el
    # único consumidor real de este endpoint hoy -ver el reporte de HT-16
    # sobre por qué el resto del alcance de cursor no aplicaba-.
    cursor: str | None = Query(default=None),
    # HT-10 CA3: tope de puntos cuando el rango es amplio (>30 días).
    # Configurable por petición para que la gráfica pueda pedir menos
    # puntos que el default según su ancho real en pantalla.
    max_puntos: int = Query(default=MAXIMO_PUNTOS_DEFECTO, ge=1, le=50000),
    # La tabla de consulta necesita acceder a cada registro del rango.
    # Las gráficas conservan el muestreo automático por defecto.
    sin_muestreo: bool = Query(default=False),
    # HU32: filtros avanzados. valor_min/valor_max son comparaciones
    # numéricas -solo tienen sentido sobre Telemetria.vlr (decimal); un
    # EventoTexto.vlr es texto ("Puerta Abierta") y no se filtra por
    # rango, ver _query_base.
    valor_min: Decimal | None = Query(default=None),
    valor_max: Decimal | None = Query(default=None),
    # HU32: NO es el downsampling de HT-10 (services/cache/downsampling.py,
    # automático por cantidad de puntos cuando el rango supera 30 días).
    # Es un filtro explícito que pide el usuario ("una lectura cada N
    # minutos"), independiente del ancho del rango. Se resuelve en SQL con
    # date_bin, mismo criterio que fecha_inicio/fecha_fin (ver comentario
    # en _query_base): así el planner lo resuelve sin traer filas de más.
    frecuencia_muestreo: int | None = Query(default=None, ge=1),
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
        dispositivo_ids=dispositivo_ids,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        pagina=pagina,
        por_pagina=por_pagina,
        max_puntos=max_puntos,
        sin_muestreo=sin_muestreo,
        valor_min=valor_min,
        valor_max=valor_max,
        frecuencia_muestreo=frecuencia_muestreo,
        cursor=cursor,
    )
    cacheado = cache.obtener(clave_cache)
    if cacheado is not None:
        return cacheado

    # HT-16 punto 1 (EXPLAIN ANALYZE): con el dataset de benchmark de 5
    # clientes, un JOIN directo tlmtr-dspstv-ubccn ANTES del ORDER BY+LIMIT
    # fuerza un Hash Join que arrastra Ubicacion/Parametro por delante del
    # corte, y Postgres no puede aplicar un top-N heapsort barato (tenía que
    # materializar y ordenar la unión completa: ~150ms). Resolviendo el
    # filtro de ubicación/dispositivo como subquery sobre id_dspstv -en vez
    # de JOIN- y sumando Ubicacion/Parametro/Dispositivo DESPUÉS del LIMIT
    # (ver _enriquecer más abajo), el planner sí llega a un top-N heapsort
    # sobre cada partición relevante (~60ms para el mismo dataset). Ver
    # backend/docs/ht16-rendimiento-consultas.md para el EXPLAIN completo.
    ids_dispositivos_query = (
        db.query(Dispositivo.id_dspstv)
        .join(Ubicacion, Ubicacion.id_ubccn == Dispositivo.id_ubccn)
        .filter(Ubicacion.id_ubccn.in_(ids_ubicaciones_permitidas))
    )
    if ubicacion_ids:
        ids_solicitadas = set(ubicacion_ids) & ids_ubicaciones_permitidas
        ids_dispositivos_query = ids_dispositivos_query.filter(
            Ubicacion.id_ubccn.in_(ids_solicitadas)
        )
    if dispositivo_ids:
        # No hace falta resolver "qué dispositivos son válidos" contra una
        # lista separada: el filtro por Ubicacion.id_ubccn (arriba, siempre
        # activo) ya acota la consulta a las ubicaciones permitidas, así
        # que un id_dspstv de una ubicación ajena simplemente no matchea
        # ninguna fila -no hace falta validarlo aparte para que el
        # aislamiento por ubicación se sostenga-.
        ids_dispositivos_query = ids_dispositivos_query.filter(
            Dispositivo.id_dspstv.in_(dispositivo_ids)
        )

    def _query_base(modelo):
        query = db.query(modelo).filter(modelo.id_dspstv.in_(ids_dispositivos_query))
        if parametro_ids:
            query = query.filter(modelo.id_prmtr.in_(parametro_ids))
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
        # HU32 CA1/CA2: valor mínimo/máximo (acumulativo = rango). Solo
        # aplica a Telemetria.vlr (Numeric): EventoTexto.vlr es String
        # ("Puerta Abierta") y una comparación >=/<= ahí sería una
        # comparación lexicográfica sin sentido de negocio, no un filtro
        # de rango. _query_base se llama una vez por modelo (ver abajo),
        # así que alcanza con mirar cuál es antes de aplicar el filtro.
        if modelo is Telemetria:
            if valor_min is not None:
                query = query.filter(modelo.vlr >= valor_min)
            if valor_max is not None:
                query = query.filter(modelo.vlr <= valor_max)
        if frecuencia_muestreo is not None:
            # HU32: "una lectura cada N minutos", no el downsampling de
            # HT-10 (services/cache/downsampling.py) -ver docstring del
            # parámetro en el endpoint-. date_bin trunca fch_hr a
            # intervalos fijos de N minutos anclados a las 00:00 de una
            # fecha de referencia (epoch), y DISTINCT ON se queda con UNA
            # fila por combinación (dispositivo, parámetro, bucket): sin
            # id_dspstv/id_prmtr en el DISTINCT ON, dos series distintas
            # que comparten el mismo bucket temporal se pisarían entre sí
            # y una perdería puntos que la otra no.
            #
            # Se resuelve en SQL, no con muestrear() en Python, por el
            # mismo motivo que fecha_inicio/fecha_fin: reduce las filas
            # que hay que traer de Postgres en vez de traerlas todas y
            # descartar después, y es el punto de la consulta donde ya se
            # decide qué filas pertenecen a la respuesta.
            bucket = func.date_bin(
                dt.timedelta(minutes=frecuencia_muestreo),
                modelo.fch_hr,
                dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc),
            )
            query = query.distinct(modelo.id_dspstv, modelo.id_prmtr, bucket)
            return query.order_by(modelo.id_dspstv, modelo.id_prmtr, bucket, modelo.fch_hr.desc())
        # El ORDER BY se baja a SQL (antes se ordenaba en Python sobre la
        # lista completa) para que el planner pueda resolverlo por índice.
        # Desempate por id_lctr/id_evnt (ver el otro order_by con el mismo
        # criterio en modo cursor): sin un segundo criterio, dos filas con
        # EXACTAMENTE el mismo fch_hr (real en telemetría de alta frecuencia,
        # más de un dispositivo/parámetro puede compartir timestamp) quedan
        # en un orden no determinista entre ejecuciones.
        columna_id = modelo.id_lctr if modelo is Telemetria else modelo.id_evnt
        return query.order_by(modelo.fch_hr.desc(), columna_id.desc())

    # HT-16 CA3: el modo cursor aplica cuando no habrá downsampling
    # automático. La tabla puede pedir sin_muestreo incluso para rangos
    # amplios; las gráficas conservan el muestreo de HT-10. Con frecuencia_muestreo
    # activo tampoco aplica: ese camino ya usa DISTINCT ON+bucket, que no
    # tiene una columna de desempate (id) estable para un cursor keyset.
    modo_cursor = (
        sin_muestreo or not rango_es_amplio(fecha_inicio, fecha_fin)
    ) and frecuencia_muestreo is None

    if modo_cursor:
        cursor_fch_hr = cursor_origen = cursor_id = None
        if cursor is not None:
            cursor_fch_hr, cursor_origen, cursor_id = _decodificar_cursor(cursor)

        def _con_cursor(modelo, origen, columna_id):
            query = _query_base(modelo)
            if cursor_fch_hr is None:
                return query
            # Keyset sobre el orden total (fch_hr DESC, origen DESC, id
            # DESC) que usa el merge de más abajo: "todo lo estrictamente
            # posterior al cursor en ESE orden". `origen` es una constante
            # de Python acá (_con_cursor se llama una vez por modelo, nunca
            # mezclando tablas en la misma query), así que la comparación
            # contra cursor_origen se resuelve en Python y solo queda una
            # de las tres ramas del orden total activa en SQL:
            #
            #   - origen == cursor_origen: misma tabla que generó el
            #     cursor. Empata en fch_hr y desempata por id (la rama que
            #     hace al cursor estable ante una inserción concurrente con
            #     el MISMO fch_hr: una fila nueva con id mayor cae después
            #     del cursor, nunca se repite ni se salta una ya servida).
            #   - origen < cursor_origen ("e" < "t", Telemetria antes que
            #     EventoTexto en el orden DESC): un empate exacto en fch_hr
            #     ya quedó resuelto a favor de Telemetria en la página del
            #     cursor, así que EventoTexto con ESE MISMO fch_hr también
            #     ya se sirvió -se excluye con <=, no <-.
            #   - origen > cursor_origen: el empate exacto en fch_hr
            #     todavía no se sirvió para esta tabla -se incluye con <=-.
            if origen == cursor_origen:
                return query.filter(
                    (modelo.fch_hr < cursor_fch_hr)
                    | ((modelo.fch_hr == cursor_fch_hr) & (columna_id < cursor_id))
                )
            if origen < cursor_origen:
                return query.filter(modelo.fch_hr < cursor_fch_hr)
            return query.filter(modelo.fch_hr <= cursor_fch_hr)

        # HT-16 punto 3: LIMIT real en SQL, no .all() completo. Se pide
        # por_pagina+1 de CADA modelo (no se sabe de antemano cuántas de
        # cada uno van a entrar en la página fusionada) y el merge de abajo
        # corta al tamaño real, sin traer más que 2*(por_pagina+1) filas
        # jamás -acotado, a diferencia del .all() de antes que traía TODO
        # el resultado filtrado sin importar la página pedida-.
        mediciones = (
            _con_cursor(Telemetria, _ORIGEN_TELEMETRIA, Telemetria.id_lctr)
            .limit(por_pagina + 1)
            .all()
        )
        eventos = (
            _con_cursor(EventoTexto, _ORIGEN_EVENTO, EventoTexto.id_evnt)
            .limit(por_pagina + 1)
            .all()
        )

        candidatos = [(t.fch_hr, _ORIGEN_TELEMETRIA, t.id_lctr, "t", t) for t in mediciones] + [
            (e.fch_hr, _ORIGEN_EVENTO, e.id_evnt, "e", e) for e in eventos
        ]
        candidatos.sort(key=lambda c: (c[0], c[1], c[2]), reverse=True)

        hay_mas = len(candidatos) > por_pagina
        pagina_candidatos = candidatos[:por_pagina]

        total = _query_base(Telemetria).count() + _query_base(EventoTexto).count()
        downsampling_aplicado = False
        total_sin_muestrear = total

        next_cursor = None
        if hay_mas and pagina_candidatos:
            ultima_fch_hr, ultimo_origen, ultimo_id, _tipo, _fila = pagina_candidatos[-1]
            next_cursor = _codificar_cursor(ultima_fch_hr, ultimo_origen, ultimo_id)

        items_enriquecidos = _enriquecer_items(db, pagina_candidatos)
        items_pagina = items_enriquecidos
    else:
        mediciones = _query_base(Telemetria).all()
        eventos = _query_base(EventoTexto).all()

        candidatos = [(t.fch_hr, _ORIGEN_TELEMETRIA, t.id_lctr, "t", t) for t in mediciones] + [
            (e.fch_hr, _ORIGEN_EVENTO, e.id_evnt, "e", e) for e in eventos
        ]
        # Las dos consultas ya vienen ordenadas de SQL, pero hay que
        # reordenar la UNION de ambas (tlmtr + evnt_txt son tablas distintas).
        candidatos.sort(key=lambda c: (c[0], c[1], c[2]), reverse=True)

        items = _enriquecer_items(db, candidatos)

        # HT-10 CA3: rango amplio (>30 días) -> downsampling con tope
        # configurable. Se aplica ANTES de paginar: el criterio es "cuántos
        # puntos representan esta serie", no "cuántos caben en una página",
        # y muestrear después dejaría el total sin reducir.
        #
        # El muestreo es uniforme y determinista; el criterio y sus
        # límites están documentados en services/cache/downsampling.py.
        downsampling_aplicado = False
        total_sin_muestrear = len(items)
        if (
            not sin_muestreo
            and rango_es_amplio(fecha_inicio, fecha_fin)
            and total_sin_muestrear > max_puntos
        ):
            items = muestrear(items, max_puntos)
            downsampling_aplicado = True

        total = len(items)
        items_pagina = items[(pagina - 1) * por_pagina : (pagina - 1) * por_pagina + por_pagina]
        next_cursor = None

    respuesta = {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        # HT-16 CA3: siguiente cursor opaco, solo en modo_cursor. None
        # cuando no hay más filas o cuando la consulta usa
        # pagina/por_pagina en lugar de cursor.
        "next_cursor": next_cursor,
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
    #
    # Antes se derivaba de las filas de Ubicacion que el JOIN de
    # _query_base traía junto con cada medición; ahora que ese JOIN se
    # resolvió aparte (ver _enriquecer_items, HT-16 punto 1), se toma
    # directo del id_ubccn ya resuelto en items_pagina -mismo resultado,
    # sin repetir la consulta de sedes.
    sedes_en_respuesta = {item.id_sd for item in items_pagina}
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
