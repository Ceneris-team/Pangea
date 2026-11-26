"""Adaptadores de lectura: fuentes calculadas sin inventar sensores físicos."""

from fastapi import HTTPException

from app.models import ParametroCalculado, ResultadoCalculo, SerieCalculada, Ubicacion
from app.services.visualizacion import ConfigVisualizacion, ResumenSerieAcumulado


def catalogo_calculados(db, puntos):
    items = {}
    for p, u in (
        db.query(ParametroCalculado, Ubicacion)
        .join(Ubicacion, Ubicacion.id_sd == ParametroCalculado.id_sd)
        .filter(Ubicacion.id_ubccn.in_(puntos), ParametroCalculado.validada.is_(True))
    ):
        item = items.setdefault(
            p.id_prm_clc,
            {
                "id_prmtr": -p.id_prm_clc,
                "nmbr": p.nmbr,
                "undd": p.undd,
                "dscrpcn": p.dscrpcn,
                "tipo_dato": "numerico",
                "tipo_visualizacion": "continuo",
                "estd": p.estd,
                "orgn_crcn": "Calculado",
                "fuentes": [],
            },
        )
        item["fuentes"].append(
            {"dispositivo_id": -u.id_ubccn, "ubicacion_id": u.id_ubccn, "admite_rango": True}
        )
    return list(items.values())


def series_calculadas(db, puntos):
    return (
        db.query(SerieCalculada, ParametroCalculado, Ubicacion)
        .join(ParametroCalculado, ParametroCalculado.id_prm_clc == SerieCalculada.id_prm_clc)
        .join(Ubicacion, Ubicacion.id_ubccn == SerieCalculada.id_ubccn)
        .filter(Ubicacion.id_ubccn.in_(puntos), ParametroCalculado.validada.is_(True))
    )


def item_serie(s, p, u):
    return {
        "id_serie": -s.id_serie,
        "id_dspstv": -u.id_ubccn,
        "dispositivo_nombre": "Cálculo del punto",
        "id_prmtr": -p.id_prm_clc,
        "parametro_nombre": p.nmbr,
        "undd": p.undd,
        "id_ubccn": u.id_ubccn,
        "ubicacion_nombre": u.nmbr,
        "tp_trm": "Calculado",
        "indc_clmn": 0,
        "configuracion": ConfigVisualizacion(significado="continuo", confirmada=True).model_dump(),
    }


def datos_calculados(db, id_serie, puntos, inicio, fin, max_puntos):
    fila = series_calculadas(db, puntos).filter(SerieCalculada.id_serie == -id_serie).first()
    if fila is None:
        raise HTTPException(404, "Serie no disponible")
    s, p, u = fila
    q = db.query(ResultadoCalculo).filter(
        ResultadoCalculo.vigente,
        ResultadoCalculo.id_prm_clc == p.id_prm_clc,
        ResultadoCalculo.id_ubccn == u.id_ubccn,
        ResultadoCalculo.fch_hr >= inicio,
        ResultadoCalculo.fch_hr <= fin,
    )
    incidencias = q.filter(ResultadoCalculo.estado != "Calculado").count()
    q = q.filter(ResultadoCalculo.estado == "Calculado")
    total = q.count()
    indices = (
        {round(i * (total - 1) / (max_puntos - 1)) for i in range(max_puntos)}
        if total > max_puntos
        else None
    )
    acumulado = ResumenSerieAcumulado(
        None, ConfigVisualizacion(significado="continuo", confirmada=True)
    )
    items = []
    for i, r in enumerate(q.order_by(ResultadoCalculo.fch_hr).yield_per(1000)):
        acumulado.agregar(r.fch_hr, r.vlr)
        if indices is None or i in indices:
            items.append(
                {
                    "id_registro": r.id_resultado,
                    "fch_hr": r.fch_hr,
                    "vlr": r.vlr,
                    "id_prmtr": -p.id_prm_clc,
                    "parametro_nombre": p.nmbr,
                    "undd": p.undd,
                    "id_dspstv": -u.id_ubccn,
                    "dispositivo_nombre": "Cálculo del punto",
                    "id_ubccn": u.id_ubccn,
                    "ubicacion_nombre": u.nmbr,
                    "origen": "calculado",
                    "id_calculado": p.id_prm_clc,
                }
            )
    resumen = acumulado.resultado()
    resumen.update(
        parcial=bool(incidencias),
        sin_origen=False,
        intervalo="dia",
        barras=[],
        incidencias=incidencias,
    )
    return {"resumen": resumen, "items": items, "muestreado": total > max_puntos}
