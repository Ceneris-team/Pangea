"""Series independientes por datalogger, formato y parámetro."""

import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    ArchivoIngesta,
    Dispositivo,
    MapeoColumna,
    MapeoFormato,
    Parametro,
    Telemetria,
    Ubicacion,
)
from app.security.permisos import LECTURA, require_permiso
from app.security.ubicaciones_permitidas import ubicaciones_permitidas
from app.services.visualizacion import ResumenSerieAcumulado, configuracion_columna

router = APIRouter(prefix="/series")


def _series(db, usuario):
    return (
        db.query(MapeoColumna, MapeoFormato, Parametro, Dispositivo, Ubicacion)
        .join(MapeoFormato, MapeoFormato.id_mp == MapeoColumna.id_mp)
        .join(Parametro, Parametro.id_prmtr == MapeoColumna.id_prmtr)
        .join(Dispositivo, Dispositivo.id_dspstv == MapeoFormato.id_dspstv)
        .join(Ubicacion, Ubicacion.id_ubccn == Dispositivo.id_ubccn)
        .filter(
            Ubicacion.id_ubccn.in_(ubicaciones_permitidas(db, usuario)),
            MapeoFormato.estd == "Activo",
            Parametro.tipo_dato == "numerico",
        )
    )


@router.get("")
def listar_series(
    ubicacion_id: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", LECTURA)),
):
    filas = (
        _series(db, usuario)
        .filter(Ubicacion.id_ubccn == ubicacion_id)
        .order_by(Dispositivo.nmbr, MapeoFormato.tp_trm, Parametro.nmbr, MapeoColumna.indc_clmn)
        .all()
    )
    return {
        "items": [
            {
                "id_serie": c.id_mp_cl,
                "id_dspstv": d.id_dspstv,
                "dispositivo_nombre": d.nmbr,
                "id_prmtr": p.id_prmtr,
                "parametro_nombre": p.nmbr,
                "undd": p.undd,
                "id_ubccn": u.id_ubccn,
                "ubicacion_nombre": u.nmbr,
                "tp_trm": f.tp_trm,
                "indc_clmn": c.indc_clmn,
                "configuracion": configuracion_columna(c, p).model_dump(),
            }
            for c, f, p, d, u in filas
        ]
    }


@router.get("/{id_serie}")
def datos_serie(
    id_serie: int,
    fecha_inicio: dt.datetime,
    fecha_fin: dt.datetime,
    zona_horaria: str = "America/Lima",
    max_puntos: int = Query(1500, ge=2, le=5000),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Tableros", LECTURA)),
):
    fila = _series(db, usuario).filter(MapeoColumna.id_mp_cl == id_serie).first()
    if fila is None:
        raise HTTPException(404, "Serie no disponible")
    c, formato, parametro, dispositivo, ubicacion = fila
    inicio = (
        fecha_inicio.replace(tzinfo=dt.timezone.utc)
        if fecha_inicio.tzinfo is None
        else fecha_inicio
    )
    fin = fecha_fin.replace(tzinfo=dt.timezone.utc) if fecha_fin.tzinfo is None else fecha_fin
    if inicio > fin:
        raise HTTPException(422, "El inicio no puede ser posterior al fin")
    try:
        zona = ZoneInfo(zona_horaria)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(422, "Zona horaria no válida") from exc

    # La tabla histórica no guarda índice de columna. No inventar una
    # separación si dos columnas del mismo archivo usan el mismo parámetro.
    if (
        db.query(MapeoColumna)
        .filter(MapeoColumna.id_mp == formato.id_mp, MapeoColumna.id_prmtr == parametro.id_prmtr)
        .count()
        > 1
    ):
        raise HTTPException(
            409,
            "Este formato asigna varias columnas al mismo parámetro. Asigna parámetros distintos para distinguir sus datos.",
        )
    cantidad_formatos = (
        db.query(MapeoFormato.tp_trm)
        .join(MapeoColumna)
        .filter(
            MapeoFormato.id_dspstv == dispositivo.id_dspstv,
            MapeoColumna.id_prmtr == parametro.id_prmtr,
        )
        .distinct()
        .count()
    )
    nombre_base = func.regexp_replace(
        func.replace(ArchivoIngesta.nmbr_archv, "\\", "/"), "^.*/", ""
    )
    prefijo = func.upper(func.split_part(nombre_base, "_", 1))
    origen = prefijo == formato.tp_trm.upper()
    if cantidad_formatos == 1:
        origen = or_(origen, Telemetria.id_archv.is_(None))
    query = (
        db.query(Telemetria.fch_hr, Telemetria.vlr)
        .outerjoin(ArchivoIngesta, ArchivoIngesta.id_archv == Telemetria.id_archv)
        .filter(
            Telemetria.id_dspstv == dispositivo.id_dspstv,
            Telemetria.id_prmtr == parametro.id_prmtr,
            origen,
        )
    )
    anterior = (
        query.filter(Telemetria.fch_hr < inicio)
        .order_by(Telemetria.fch_hr.desc(), Telemetria.id_lctr.desc())
        .first()
    )
    rango = query.filter(Telemetria.fch_hr >= inicio, Telemetria.fch_hr <= fin)
    # DISTINCT conserva la identidad histórica disponible (fecha y valor).
    # El cursor entrega lotes al acumulador; nunca materializamos todo el rango.
    unicas = rango.distinct()
    total = unicas.count()
    total_bruto = rango.count()
    indices_muestra = (
        {round(i * (total - 1) / (max_puntos - 1)) for i in range(max_puntos)}
        if total > max_puntos
        else None
    )
    config = configuracion_columna(c, parametro)
    acumulado = ResumenSerieAcumulado(
        (anterior[0], float(anterior[1])) if anterior else None, config
    )
    # Agregar ANTES de reducir los puntos: ningún reinicio queda oculto al KPI.
    segundos = (fin - inicio).total_seconds()
    intervalo = "hora" if segundos <= 172800 else "dia" if segundos <= 3888000 else "mes"
    buckets = {}
    puntos = []
    for indice, (fecha, valor) in enumerate(
        unicas.order_by(Telemetria.fch_hr, Telemetria.vlr).yield_per(1000)
    ):
        valor = float(valor)
        delta = acumulado.agregar(fecha, valor)
        if indices_muestra is None or indice in indices_muestra:
            puntos.append((fecha, valor))
        local = fecha.astimezone(zona)
        bucket = local.replace(minute=0, second=0, microsecond=0)
        if intervalo != "hora":
            bucket = bucket.replace(hour=0)
        if intervalo == "mes":
            bucket = bucket.replace(day=1)
        buckets[bucket] = buckets.get(bucket, 0) + delta
    resumen = acumulado.resultado(duplicados=total_bruto - total)
    barras = []
    for f, v in sorted(buckets.items()):
        if intervalo == "hora":
            fin_bucket = f.timestamp() + 3600
        elif intervalo == "dia":
            fin_bucket = (f + dt.timedelta(days=1)).timestamp()
        else:
            fin_bucket = f.replace(
                year=f.year + (f.month == 12), month=f.month % 12 + 1
            ).timestamp()
        barras.append({"t": f.timestamp() * 1000, "t_fin": fin_bucket * 1000, "delta": v})
    resumen["barras"] = barras
    resumen["intervalo"] = intervalo
    resumen["sin_origen"] = (
        cantidad_formatos > 1
        and query.session.query(Telemetria)
        .filter(
            Telemetria.id_dspstv == dispositivo.id_dspstv,
            Telemetria.id_prmtr == parametro.id_prmtr,
            Telemetria.id_archv.is_(None),
            Telemetria.fch_hr >= inicio,
            Telemetria.fch_hr <= fin,
        )
        .count()
        > 0
    )
    return {
        "resumen": resumen,
        "muestreado": total > max_puntos,
        "items": [
            {
                "id_registro": i,
                "fch_hr": f,
                "vlr": v,
                "id_prmtr": parametro.id_prmtr,
                "parametro_nombre": parametro.nmbr,
                "undd": parametro.undd,
                "id_dspstv": dispositivo.id_dspstv,
                "dispositivo_nombre": dispositivo.nmbr,
                "id_ubccn": ubicacion.id_ubccn,
                "ubicacion_nombre": ubicacion.nmbr,
            }
            for i, (f, v) in enumerate(puntos)
        ],
    }
