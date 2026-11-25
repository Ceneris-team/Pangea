"""El mapa utiliza las mismas condiciones compartidas que las alarmas."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

# Los tres estados del semáforo (CA de HU 17: verde / amarillo / rojo).
from app.models import Dispositivo, EventoTexto, Parametro, Telemetria, Ubicacion
from app.models.alarma import Alarma, CondicionAlarma

VERDE = "verde"
ROJO = "rojo"
AMARILLO = "amarillo"
_GRAVEDAD = {VERDE: 0, AMARILLO: 1, ROJO: 2}

# Preaviso: a 10 % del umbral (en valor absoluto) o menos.
MARGEN_PREAVISO = Decimal("0.10")

Condicion = tuple[str, Decimal]


def condiciones_por_ubicacion(
    db: Session, ids_ubicaciones: list[int]
) -> dict[int, dict[int, list[Condicion]]]:
    """{id_ubccn: {id_prmtr: [(operador, umbral), ...]}} de las alarmas
    ACTIVAS de esas ubicaciones, en una sola consulta.

    Es una lista por parámetro porque puede haber varias alarmas (de uno o
    varios usuarios) sobre el mismo parámetro de la misma estación, y
    alarmas anteriores a PP-74 con más de una condición."""
    if not ids_ubicaciones:
        return {}
    filas = (
        db.query(Alarma.id_ubccn, Alarma.id_prmtr, CondicionAlarma.oprdr, CondicionAlarma.vlr_umbrl)
        .join(CondicionAlarma, CondicionAlarma.id_alrm == Alarma.id_alrm)
        .filter(Alarma.id_ubccn.in_(ids_ubicaciones), Alarma.estd == "Activa")
        .order_by(Alarma.id_alrm, CondicionAlarma.id_cndcn)
        .all()
    )
    resultado: dict[int, dict[int, list[Condicion]]] = {}
    for id_ubccn, id_prmtr, operador, umbral in filas:
        resultado.setdefault(id_ubccn, {}).setdefault(id_prmtr, []).append(
            (operador, Decimal(str(umbral)))
        )
    return resultado


def _cumple_condicion(valor: Decimal, operador: str, umbral: Decimal) -> bool:
    """Evalúa un valor contra una condición (operador, umbral).

    Los operadores son exactamente los que admite el CHECK de cndcn_alrm.
    Un operador fuera de esa lista devuelve False en vez de reventar: una
    fila corrupta no debe tumbar el mapa entero."""
    if operador == ">":
        return valor > umbral
    if operador == "<":
        return valor < umbral
    if operador == ">=":
        return valor >= umbral
    if operador == "<=":
        return valor <= umbral
    if operador == "=":
        return valor == umbral
    return False


def _en_preaviso(valor: Decimal, operador: str, umbral: Decimal) -> bool:
    """True si el valor, sin cumplir la condición, está a MARGEN_PREAVISO o
    menos del umbral del lado en que se dispararía.

    Sin preaviso para "=" (la condición es un punto, no un lado) ni para un
    umbral 0 (el 10 % de 0 es 0: no hay margen que medir)."""
    if _cumple_condicion(valor, operador, umbral) or umbral == 0:
        return False
    margen = abs(umbral) * MARGEN_PREAVISO
    if operador in (">", ">="):
        return umbral - margen <= valor <= umbral
    if operador in ("<", "<="):
        return umbral <= valor <= umbral + margen
    return False


def _como_decimal(valor) -> Decimal | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        # Parámetro de texto (evnt_txt): se muestra, no se semaforiza.
        return None
    return numero if numero.is_finite() else None


def evaluar_parametro(condiciones: list[Condicion], valor) -> str:
    """Color de UN parámetro según su último valor y las condiciones de las
    alarmas activas sobre él. Sin condiciones, o con un valor no numérico
    (evnt_txt), es VERDE."""
    numero = _como_decimal(valor)
    if numero is None or not condiciones:
        return VERDE
    # ROJO primero: si cumple una condición y está en preaviso de otra,
    # gana el más grave.
    if any(_cumple_condicion(numero, op, umbral) for op, umbral in condiciones):
        return ROJO
    if any(_en_preaviso(numero, op, umbral) for op, umbral in condiciones):
        return AMARILLO
    return VERDE


def evaluar_semaforo(
    valores_por_parametro: dict[int, object],
    condiciones_por_parametro: dict[int, list[Condicion]] | None = None,
) -> str:
    """Color de UNA ESTACIÓN: {id_prmtr: último valor} contra
    {id_prmtr: [(operador, umbral)]} (de condiciones_por_ubicacion).

    Gana el parámetro MÁS GRAVE: una estación con nueve parámetros en verde
    y uno en rojo se pinta roja (CA1/CA3 de HU 17). Una estación sin datos
    o sin alarmas queda VERDE."""
    condiciones_por_parametro = condiciones_por_parametro or {}
    peor = VERDE
    for id_prmtr, valor in valores_por_parametro.items():
        color = evaluar_parametro(condiciones_por_parametro.get(id_prmtr, []), valor)
        if _GRAVEDAD[color] > _GRAVEDAD[peor]:
            peor = color
    return peor


def semaforos_por_ubicacion(db, ids_ubicaciones, dispositivo_id=None):
    from app.services.monitoreo import umbral_sin_datos

    proyectos = db.query(Ubicacion).filter(Ubicacion.id_ubccn.in_(ids_ubicaciones)).all()
    resultado = {u.id_ubccn: "sin_datos" if u.monitoreo_activo else "detenido" for u in proyectos}
    reglas = (
        db.query(Alarma, CondicionAlarma)
        .join(CondicionAlarma, CondicionAlarma.id_alrm == Alarma.id_alrm)
        .join(Parametro, Parametro.id_prmtr == Alarma.id_prmtr)
        .filter(Alarma.id_ubccn.in_(ids_ubicaciones), Alarma.estd == "Activa")
        .all()
    )
    condiciones = {}
    for alarma, condicion in reglas:
        condiciones.setdefault(alarma.id_ubccn, {}).setdefault(alarma.id_prmtr, []).append(
            (condicion.oprdr, condicion.vlr_umbrl)
        )
    limite = datetime.now(timezone.utc) - umbral_sin_datos()
    consulta = (
        db.query(
            Dispositivo.id_ubccn,
            Telemetria.id_dspstv,
            Telemetria.id_prmtr,
            Parametro.nmbr,
            Telemetria.vlr,
            Telemetria.fch_hr,
        )
        .select_from(Telemetria)
        .join(Dispositivo, Dispositivo.id_dspstv == Telemetria.id_dspstv)
        .join(Parametro, Parametro.id_prmtr == Telemetria.id_prmtr)
        .filter(
            Dispositivo.id_ubccn.in_(ids_ubicaciones),
            Dispositivo.estd == "Activo",
            Telemetria.fch_hr >= limite,
        )
    )
    if dispositivo_id is not None:
        consulta = consulta.filter(Dispositivo.id_dspstv == dispositivo_id)
    ultimos = (
        consulta.distinct(Telemetria.id_dspstv, Telemetria.id_prmtr)
        .order_by(Telemetria.id_dspstv, Telemetria.id_prmtr, Telemetria.fch_hr.desc())
        .all()
    )
    recientes = {fila[0] for fila in ultimos}
    textos = (
        db.query(Dispositivo.id_ubccn)
        .join(EventoTexto, EventoTexto.id_dspstv == Dispositivo.id_dspstv)
        .filter(
            Dispositivo.id_ubccn.in_(ids_ubicaciones),
            Dispositivo.estd == "Activo",
            EventoTexto.fch_hr >= limite,
        )
    )
    if dispositivo_id is not None:
        textos = textos.filter(Dispositivo.id_dspstv == dispositivo_id)
    recientes.update(proyecto for (proyecto,) in textos.distinct().all())
    for proyecto in recientes:
        if proyecto not in condiciones and resultado.get(proyecto) != "detenido":
            resultado[proyecto] = "sin_reglas"
    colores = {}
    for proyecto, _equipo, _parametro, nombre, valor, fecha in ultimos:
        if fecha < limite:
            continue
        color = (
            evaluar_parametro(condiciones.get(proyecto, {}).get(_parametro, []), valor)
            if _parametro in condiciones.get(proyecto, {})
            else "sin_reglas"
        )
        if color in {ROJO, AMARILLO, VERDE}:
            colores.setdefault(proyecto, set()).add(color)
    for proyecto in condiciones:
        if resultado.get(proyecto) == "detenido":
            continue
        actuales = colores.get(proyecto, set())
        resultado[proyecto] = (
            ROJO
            if ROJO in actuales
            else AMARILLO if AMARILLO in actuales else VERDE if VERDE in actuales else "sin_datos"
        )
    return resultado
