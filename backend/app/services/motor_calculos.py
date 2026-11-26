"""Cálculo por lotes reanudables, con cola transaccional y revisiones."""

import datetime as dt
from dataclasses import replace

from sqlalchemy import and_, or_, select, text, union
from sqlalchemy.dialects.postgresql import insert

from app.models import (
    ConfiguracionCalculo,
    DependenciaCalculo,
    Dispositivo,
    Parametro,
    ParametroCalculado,
    ResultadoCalculo,
    RevisionCalculo,
    SerieCalculada,
    Telemetria,
    TrabajoCalculo,
)
from app.services.cache.invalidacion import invalidar_por_lectura
from app.services.unidades_calculo import evaluar, unidad, validar_unidades

LOTE = 200


def ahora():
    return dt.datetime.now(dt.timezone.utc)


def configuracion(db, sede):
    c = db.get(ConfiguracionCalculo, sede)
    return {
        "tolerancia_segundos": c.tolerancia_segundos if c else 60,
        "espera_horas": c.espera_horas if c else 24,
    }


def encolar_historico(db, sede, definicion=None):
    trabajo = TrabajoCalculo(id_sd=sede, id_prm_clc=definicion, estado="Pendiente")
    db.add(trabajo)
    db.flush()
    return trabajo


def grafo(db, sede):
    definiciones = {
        p.id_prm_clc: p
        for p in db.query(ParametroCalculado).filter(
            ParametroCalculado.id_sd == sede, ParametroCalculado.validada.is_(True)
        )
    }
    deps = {id_: [] for id_ in definiciones}
    for d in db.query(DependenciaCalculo).filter(DependenciaCalculo.id_prm_clc.in_(definiciones)):
        deps[d.id_prm_clc].append(d)
    orden, visitados, camino = [], set(), set()

    def visitar(id_):
        if id_ in camino:
            raise ValueError("Dependencia circular en las definiciones calculadas")
        if id_ in visitados:
            return
        camino.add(id_)
        for d in deps.get(id_, []):
            if d.id_origen_calculado in definiciones:
                visitar(d.id_origen_calculado)
        camino.remove(id_)
        visitados.add(id_)
        orden.append(id_)

    for id_ in definiciones:
        visitar(id_)
    hojas = {}
    for id_ in orden:
        hojas[id_] = set()
        for d in deps[id_]:
            if d.id_prmtr:
                hojas[id_].add(d.id_prmtr)
            else:
                hojas[id_].update(hojas.get(d.id_origen_calculado, set()))
    return definiciones, deps, orden, hojas


def _candidatos(db, trabajo, parametros):
    crudos = (
        select(Dispositivo.id_ubccn.label("ubicacion"), Telemetria.fch_hr.label("fecha"))
        .join(Telemetria, Telemetria.id_dspstv == Dispositivo.id_dspstv)
        .where(Telemetria.id_sd == trabajo.id_sd, Telemetria.id_prmtr.in_(parametros))
    )
    # Incluye instantes cuyo único dato se borró: se invalida su resultado anterior.
    previos = select(
        ResultadoCalculo.id_ubccn.label("ubicacion"), ResultadoCalculo.fch_hr.label("fecha")
    ).where(ResultadoCalculo.id_sd == trabajo.id_sd, ResultadoCalculo.vigente)
    candidatos = union(crudos, previos).subquery()
    q = db.query(candidatos.c.ubicacion, candidatos.c.fecha)
    if trabajo.id_ubccn:
        q = q.filter(candidatos.c.ubicacion == trabajo.id_ubccn)
    if trabajo.inicio:
        q = q.filter(candidatos.c.fecha >= trabajo.inicio)
    if trabajo.fin:
        q = q.filter(candidatos.c.fecha <= trabajo.fin)
    if trabajo.cursor:
        ubicacion, fecha = trabajo.cursor["ubicacion"], dt.datetime.fromisoformat(
            trabajo.cursor["fecha"]
        )
        q = q.filter(
            or_(
                candidatos.c.ubicacion > ubicacion,
                and_(candidatos.c.ubicacion == ubicacion, candidatos.c.fecha > fecha),
            )
        )
    return q.order_by(candidatos.c.ubicacion, candidatos.c.fecha).limit(LOTE + 1).all()


def _resolver(db, definicion, deps, punto, instante, config, definiciones):
    trazas, valores, unidades = {}, {}, {}
    espera = dt.timedelta(hours=config["espera_horas"])
    estado_faltante = "Incompleto" if ahora() >= instante + espera else "Pendiente de datos"
    traza = {
        "formula": definicion.frml,
        "unidad": definicion.undd,
        "configuracion": config,
        "origenes": trazas,
    }
    problemas, faltantes = [], []
    for d in deps:
        if d.id_prmtr:
            p = db.get(Parametro, d.id_prmtr)
            if p is None or p.estd != "Activo" or p.tipo_dato != "numerico":
                problemas.append(f"Origen {d.variable} no está activo o no es numérico")
                continue
            filas = (
                db.query(Telemetria)
                .join(Dispositivo, Dispositivo.id_dspstv == Telemetria.id_dspstv)
                .filter(
                    Dispositivo.id_ubccn == punto,
                    Telemetria.id_prmtr == d.id_prmtr,
                    Telemetria.fch_hr <= instante,
                    Telemetria.fch_hr
                    >= instante - dt.timedelta(seconds=config["tolerancia_segundos"]),
                )
                .order_by(Telemetria.id_dspstv, Telemetria.fch_hr.desc(), Telemetria.id_lctr.desc())
                .distinct(Telemetria.id_dspstv)
                .all()
            )
            if len(filas) > 1:
                problemas.append(
                    f"{p.nmbr}: hay varios dispositivos de origen; configura parámetros distintos para distinguirlos"
                )
                continue
            fila = filas[0] if filas else None
            if fila:
                trazas[d.variable] = {
                    "tipo": "telemetria",
                    "nombre": p.nmbr,
                    "id": fila.id_lctr,
                    "fecha": fila.fch_hr.isoformat(),
                    "dispositivo": fila.id_dspstv,
                    "valor": float(fila.vlr),
                    "unidad": p.undd,
                }
        else:
            p = definiciones.get(d.id_origen_calculado)
            if p is None or p.estd != "Activo":
                problemas.append(f"Dependencia {d.variable} no está activa o disponible")
                continue
            fila = (
                db.query(ResultadoCalculo)
                .filter(
                    ResultadoCalculo.id_prm_clc == d.id_origen_calculado,
                    ResultadoCalculo.id_ubccn == punto,
                    ResultadoCalculo.vigente,
                    ResultadoCalculo.fch_hr <= instante,
                    ResultadoCalculo.fch_hr
                    >= instante - dt.timedelta(seconds=config["tolerancia_segundos"]),
                )
                .order_by(ResultadoCalculo.fch_hr.desc())
                .first()
            )
            if fila:
                trazas[d.variable] = {
                    "tipo": "calculado",
                    "nombre": p.nmbr,
                    "id": fila.id_resultado,
                    "fecha": fila.fch_hr.isoformat(),
                    "revision": fila.revision,
                    "estado": fila.estado,
                    "valor": fila.vlr,
                    "unidad": p.undd,
                }
                if fila.estado == "Fallido":
                    problemas.append(f"La dependencia {p.nmbr} falló: {fila.causa}")
                    continue
                if fila.estado != "Calculado":
                    faltantes.append(p.nmbr)
                    continue
        if fila is None:
            faltantes.append(p.nmbr)
            continue
        if p.undd != d.unidad_origen:
            problemas.append(f"Cambió la unidad de {p.nmbr}; es necesario revalidar la definición")
            continue
        valores[d.variable] = float(fila.vlr)
        unidades[d.variable] = unidad(d.unidad_origen)
        if d.id_origen_calculado and fila.trazabilidad.get("temperatura_relativa"):
            unidades[d.variable] = replace(unidades[d.variable], desplazamiento=0, relativa=True)
    if problemas:
        return "Fallido", None, "; ".join(problemas)[:500], traza
    if faltantes:
        return estado_faltante, None, ("Faltan datos: " + ", ".join(faltantes))[:500], traza
    try:
        if not deps:
            raise ValueError("La definición no tiene dependencias verificadas")
        validar_unidades(definicion.frml, unidades, definicion.undd)
        valor, relativa = evaluar(
            definicion.frml, valores, unidades, definicion.undd, con_tipo=True
        )
        traza["temperatura_relativa"] = relativa
        return "Calculado", valor, None, traza
    except (ValueError, TypeError, KeyError, ArithmeticError, SyntaxError) as exc:
        return "Fallido", None, str(exc)[:500], traza


def _guardar(db, p, punto, fecha, calculo):
    estado, valor, causa, traza = calculo
    anterior = (
        db.query(ResultadoCalculo)
        .filter_by(id_prm_clc=p.id_prm_clc, id_ubccn=punto, fch_hr=fecha)
        .one_or_none()
    )
    if anterior:
        if (anterior.estado, anterior.vlr, anterior.causa, anterior.trazabilidad) == calculo:
            return
        db.add(
            RevisionCalculo(
                id_resultado=anterior.id_resultado,
                revision=anterior.revision,
                anterior={
                    "estado": anterior.estado,
                    "valor": anterior.vlr,
                    "causa": anterior.causa,
                    "trazabilidad": anterior.trazabilidad,
                    "actualizado_en": anterior.actualizado_en.isoformat(),
                },
            )
        )
        anterior.estado, anterior.vlr, anterior.causa, anterior.trazabilidad = calculo
        anterior.revision += 1
        anterior.actualizado_en = ahora()
    else:
        db.add(
            ResultadoCalculo(
                id_prm_clc=p.id_prm_clc,
                id_ubccn=punto,
                id_sd=p.id_sd,
                fch_hr=fecha,
                estado=estado,
                vlr=valor,
                causa=causa,
                trazabilidad=traza,
            )
        )
    db.flush()


def _mismas_lecturas(db, parcial, completo):
    """Solo agrupa si el resultado completo utilizó las mismas lecturas disponibles."""
    origenes = parcial.get("origenes", {})
    otros = completo.get("origenes", {})
    if not origenes:
        return False
    for nombre, origen in origenes.items():
        otro = otros.get(nombre)
        if otro is None or origen.get("tipo") != otro.get("tipo"):
            return False
        if origen.get("id") == otro.get("id"):
            continue
        if origen.get("tipo") != "calculado":
            return False
        anterior = db.get(ResultadoCalculo, origen["id"])
        siguiente = db.get(ResultadoCalculo, otro["id"])
        cubierto = anterior.trazabilidad.get("cubierto_por") if anterior else None
        if not cubierto or not siguiente or dt.datetime.fromisoformat(cubierto) != siguiente.fch_hr:
            return False
    return True


def _cubierto_despues(db, p, deps, punto, fecha, config, definiciones, hojas, calculo):
    if calculo[0] not in {"Pendiente de datos", "Incompleto"} or not calculo[3]["origenes"]:
        return False
    limite = fecha + dt.timedelta(seconds=config["tolerancia_segundos"])
    fechas = (
        db.query(Telemetria.fch_hr)
        .join(Dispositivo, Dispositivo.id_dspstv == Telemetria.id_dspstv)
        .filter(
            Dispositivo.id_ubccn == punto,
            Telemetria.id_prmtr.in_(hojas),
            Telemetria.fch_hr > fecha,
            Telemetria.fch_hr <= limite,
        )
        .distinct()
        .order_by(Telemetria.fch_hr)
    )
    for (siguiente,) in fechas:
        futuro = _resolver(db, p, deps, punto, siguiente, config, definiciones)
        if futuro[0] == "Calculado" and _mismas_lecturas(db, calculo[3], futuro[3]):
            return True
    return False


def _cubrir_pendientes(db, p, punto, fecha, config, traza):
    # Los pendientes de corridas anteriores se conservan con su revisión para
    # auditoría, pero ya no cuentan como resultados/incidencias independientes.
    anteriores = (
        db.query(ResultadoCalculo)
        .filter(
            ResultadoCalculo.id_prm_clc == p.id_prm_clc,
            ResultadoCalculo.id_ubccn == punto,
            ResultadoCalculo.vigente,
            ResultadoCalculo.estado.in_(["Pendiente de datos", "Incompleto"]),
            ResultadoCalculo.fch_hr < fecha,
            ResultadoCalculo.fch_hr >= fecha - dt.timedelta(seconds=config["tolerancia_segundos"]),
        )
        .all()
    )
    for anterior in anteriores:
        if _mismas_lecturas(db, anterior.trazabilidad, traza):
            _guardar(
                db,
                p,
                punto,
                anterior.fch_hr,
                (
                    anterior.estado,
                    None,
                    anterior.causa,
                    {**anterior.trazabilidad, "cubierto_por": fecha.isoformat()},
                ),
            )


def procesar_lote(db, trabajo):
    # Un worker por sede; ingesta solo escribe el outbox, nunca espera al motor.
    db.execute(text("SELECT pg_advisory_xact_lock(38001, :sede)"), {"sede": trabajo.id_sd})
    definiciones, deps, orden, hojas = grafo(db, trabajo.id_sd)
    if trabajo.id_prm_clc is not None:
        seleccion = {trabajo.id_prm_clc}
        while True:
            anteriores = set(seleccion)
            for id_, referencias in deps.items():
                padres = {d.id_origen_calculado for d in referencias if d.id_origen_calculado}
                if id_ in seleccion:
                    seleccion.update(padres)
                if padres & seleccion:
                    seleccion.add(id_)
            if seleccion == anteriores:
                break
        orden = [id_ for id_ in orden if id_ in seleccion]
    # El histórico incluye ancestros y descendientes para que los reintentos
    # y las correcciones propaguen resultados consistentes.
    config = configuracion(db, trabajo.id_sd)
    parametros = set().union(*(hojas[id_] for id_ in orden)) if orden else set()
    candidatos = _candidatos(db, trabajo, parametros) if parametros else []
    trabajo.estado, trabajo.error = "En curso", None
    for punto, fecha in candidatos[:LOTE]:
        presentes = {
            id_
            for (id_,) in db.query(Telemetria.id_prmtr)
            .join(Dispositivo, Dispositivo.id_dspstv == Telemetria.id_dspstv)
            .filter(Dispositivo.id_ubccn == punto, Telemetria.fch_hr == fecha)
        }
        previos = {
            id_
            for (id_,) in db.query(ResultadoCalculo.id_prm_clc)
            .filter(ResultadoCalculo.vigente)
            .filter_by(id_ubccn=punto, fch_hr=fecha)
        }
        for id_ in orden:
            p = definiciones[id_]
            activado = any(
                d.id_prmtr in presentes or d.id_origen_calculado in previos for d in deps[id_]
            )
            if p.estd != "Activo" or not (activado or id_ in previos):
                continue
            db.execute(
                insert(SerieCalculada)
                .values(id_prm_clc=id_, id_ubccn=punto)
                .on_conflict_do_nothing()
            )
            calculo = _resolver(db, p, deps[id_], punto, fecha, config, definiciones)
            if _cubierto_despues(
                db, p, deps[id_], punto, fecha, config, definiciones, hojas[id_], calculo
            ):
                continue
            _guardar(db, p, punto, fecha, calculo)
            previos.add(id_)
            if calculo[0] == "Calculado":
                _cubrir_pendientes(db, p, punto, fecha, config, calculo[3])
            trabajo.incidencias += int(calculo[0] != "Calculado")
            trabajo.procesados += 1
        trabajo.cursor = {"ubicacion": punto, "fecha": fecha.isoformat()}
    if len(candidatos) <= LOTE:
        resultados = db.query(ResultadoCalculo).filter(
            ResultadoCalculo.id_sd == trabajo.id_sd,
            ResultadoCalculo.id_prm_clc.in_(orden),
            ResultadoCalculo.vigente,
        )
        if trabajo.id_ubccn:
            resultados = resultados.filter(ResultadoCalculo.id_ubccn == trabajo.id_ubccn)
        if trabajo.inicio:
            resultados = resultados.filter(ResultadoCalculo.fch_hr >= trabajo.inicio)
        if trabajo.fin:
            resultados = resultados.filter(ResultadoCalculo.fch_hr <= trabajo.fin)
        trabajo.procesados = resultados.count()
        trabajo.incidencias = resultados.filter(ResultadoCalculo.estado != "Calculado").count()
        trabajo.estado = "Completado con incidencias" if trabajo.incidencias else "Completado"
    trabajo.actualizado_en = ahora()
    db.flush()
    return len(candidatos[:LOTE])


def mantener_pendientes(db):
    """Vencimiento independiente del arribo de nuevos archivos."""
    sedes = [
        id_
        for (id_,) in db.query(ResultadoCalculo.id_sd)
        .filter(ResultadoCalculo.estado == "Pendiente de datos")
        .distinct()
    ]
    for sede in sedes:
        config = configuracion(db, sede)
        vencidos = (
            db.query(ResultadoCalculo)
            .filter(
                ResultadoCalculo.id_sd == sede,
                ResultadoCalculo.estado == "Pendiente de datos",
                ResultadoCalculo.vigente,
                ResultadoCalculo.fch_hr <= ahora() - dt.timedelta(hours=config["espera_horas"]),
            )
            .with_for_update(skip_locked=True)
            .limit(LOTE)
            .all()
        )
        for r in vencidos:
            _guardar(
                db,
                db.get(ParametroCalculado, r.id_prm_clc),
                r.id_ubccn,
                r.fch_hr,
                ("Incompleto", None, r.causa, r.trazabilidad),
            )


def invalidar_resultados(sede, puntos):
    for punto in puntos:
        invalidar_por_lectura(id_sd=sede, id_ubccn=punto)
