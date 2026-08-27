"""
HU 17 CA1/CA2 - Carga inicial del mapa del Cliente Final.

CA1: marcadores en las coordenadas de las ubicaciones ASIGNADAS al
Cliente Final. CA2: al hacer clic, el panel muestra el nombre de la
estación, el ÚLTIMO VALOR de cada parámetro y la fecha/hora de la última
lectura.

Este módulo resuelve la parte pesada: "el último valor de cada parámetro
de cada ubicación permitida", en una sola pasada por tabla en vez de una
consulta por (ubicación, parámetro).

Nota sobre tlmtr y evnt_txt: son dos tablas con la misma forma
(dispositivo + parámetro + fecha + valor), una para mediciones numéricas
y otra para eventos de texto (ver el docstring de EventoTexto). El panel
de CA2 muestra ambas -un "Puerta Abierta" es tan "último valor de un
parámetro" como un 23.4-, así que se consultan las dos y se combinan.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Dispositivo, EventoTexto, Parametro, Telemetria, Ubicacion


def _ultimos_por_modelo(db: Session, modelo, ids_ubicaciones: list) -> dict:
    """Último valor de cada (ubicación, parámetro) para UN modelo de
    lectura (Telemetria o EventoTexto).

    Estrategia: subconsulta con GROUP BY que saca el MAX(fch_hr) por
    (dispositivo, parámetro), y luego un JOIN contra la tabla real para
    recuperar el valor de esa fila. Es el patrón clásico de "greatest-
    n-per-group"; se prefiere a DISTINCT ON porque no ata el código a
    Postgres más de lo que ya está, y a una ventana ROW_NUMBER() porque
    con el índice idx_tlmtr_dspstv_prmtr (id_dspstv, id_prmtr, fch_hr) el
    MAX se resuelve por índice.

    Se agrupa por DISPOSITIVO y no por ubicación en la subconsulta porque
    ese es el índice que existe; la agregación a nivel ubicación se hace
    después, en Python, sobre un conjunto ya pequeño (una fila por
    dispositivo+parámetro, no por lectura).
    """
    if not ids_ubicaciones:
        return {}

    ultimas = (
        db.query(
            modelo.id_dspstv.label("id_dspstv"),
            modelo.id_prmtr.label("id_prmtr"),
            func.max(modelo.fch_hr).label("max_fch_hr"),
        )
        .join(Dispositivo, Dispositivo.id_dspstv == modelo.id_dspstv)
        .filter(Dispositivo.id_ubccn.in_(ids_ubicaciones))
        .group_by(modelo.id_dspstv, modelo.id_prmtr)
        .subquery()
    )

    filas = (
        db.query(
            Dispositivo.id_ubccn,
            Parametro.nmbr,
            Parametro.undd,
            modelo.vlr,
            modelo.fch_hr,
        )
        .join(
            ultimas,
            (modelo.id_dspstv == ultimas.c.id_dspstv)
            & (modelo.id_prmtr == ultimas.c.id_prmtr)
            & (modelo.fch_hr == ultimas.c.max_fch_hr),
        )
        .join(Dispositivo, Dispositivo.id_dspstv == modelo.id_dspstv)
        .join(Parametro, Parametro.id_prmtr == modelo.id_prmtr)
        .all()
    )

    # Una ubicación puede tener VARIOS dispositivos midiendo el mismo
    # parámetro (ej. dos sensores de temperatura). El panel muestra un
    # valor por parámetro, así que gana el más reciente entre ellos.
    resultado: dict = {}
    for id_ubccn, nombre_parametro, unidad, valor, fch_hr in filas:
        por_ubicacion = resultado.setdefault(id_ubccn, {})
        anterior = por_ubicacion.get(nombre_parametro)
        if anterior is None or fch_hr > anterior["fch_hr"]:
            por_ubicacion[nombre_parametro] = {
                "parametro": nombre_parametro,
                "unidad": unidad,
                "valor": valor,
                "fch_hr": fch_hr,
            }
    return resultado


def ultimos_valores_por_ubicacion(db: Session, ids_ubicaciones: list) -> dict:
    """{id_ubccn: {nombre_parametro: {parametro, unidad, valor, fch_hr}}}
    combinando mediciones numéricas (tlmtr) y eventos de texto (evnt_txt).

    Si el mismo nombre de parámetro apareciera en ambas tablas -no debería,
    prmtr.tipo_dato lo determina y es único por parámetro- gana el más
    reciente, mismo criterio que entre dispositivos.
    """
    numericos = _ultimos_por_modelo(db, Telemetria, ids_ubicaciones)
    textos = _ultimos_por_modelo(db, EventoTexto, ids_ubicaciones)

    combinado: dict = {}
    for parcial in (numericos, textos):
        for id_ubccn, por_parametro in parcial.items():
            destino = combinado.setdefault(id_ubccn, {})
            for nombre_parametro, dato in por_parametro.items():
                anterior = destino.get(nombre_parametro)
                if anterior is None or dato["fch_hr"] > anterior["fch_hr"]:
                    destino[nombre_parametro] = dato
    return combinado


def ubicaciones_con_coordenadas(db: Session, ids_ubicaciones: list) -> list:
    """Las ubicaciones permitidas que el mapa puede pintar.

    Filtra las que no tienen coordenadas utilizables. En el esquema actual
    lttd/lngtd son NOT NULL, así que esto es defensa en profundidad más
    que un caso real; se deja porque un marcador en (0, 0) -"Null Island",
    en el Atlántico- es peor que no pintar el marcador: parece un dato
    válido y descuadra el encuadre automático del mapa.
    """
    if not ids_ubicaciones:
        return []
    return (
        db.query(Ubicacion)
        .filter(
            Ubicacion.id_ubccn.in_(ids_ubicaciones),
            Ubicacion.lttd.isnot(None),
            Ubicacion.lngtd.isnot(None),
        )
        .order_by(Ubicacion.nmbr)
        .all()
    )
