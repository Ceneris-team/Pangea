"""
HU 17 - Semáforo de estado de una estación en el mapa, con las condiciones
reales de las alarmas (HU 29, PP-74 / PP-230).

Hasta PP-74 los colores salían de UMBRALES_TEMPORALES, un dict fijo en
memoria que el propio módulo pedía reemplazar al implementar las
condiciones de alarma. Ahora salen de cndcn_alrm:

  ROJO      alguna alarma ACTIVA de la ubicación, sobre ese parámetro,
            cumple su condición con el último valor.
  AMARILLO  preaviso: el valor todavía no la cumple pero está a
            MARGEN_PREAVISO (10 %) o menos del umbral, del lado en que se
            dispararía (">"/">=": por debajo; "<"/"<=": por encima).
  VERDE     el resto, incluidos los parámetros sin alarma configurada:
            "sin condición definida" no es lo mismo que "en alarma".

Decisión de Gean (PP-230, 19/11/2026) al pasar de umbrales de dos niveles
a una condición binaria por alarma (v1.0: una condición por alarma).

Qué alarmas cuentan: todas las ACTIVAS de la ubicación, de cualquier
usuario. El color describe el estado de la ESTACIÓN (no revela qué alarma
ni de quién) y la carga inicial del mapa se cachea por ámbito de
ubicaciones, no por usuario (mapa_cliente.py): un color por usuario
contaminaría esa caché. Las pausadas (Inactiva) no pintan.

El vínculo es por id_prmtr y no por nombre: así lo guarda la alarma, y se
elimina el problema de grafías ('Temperatura' vs 'temperatura') que el
dict temporal tenía que normalizar.
"""

from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.models.alarma import Alarma, CondicionAlarma

# Los tres estados del semáforo (CA de HU 17: verde / amarillo / rojo).
VERDE = "verde"
AMARILLO = "amarillo"
ROJO = "rojo"

# El orden de gravedad ES la precedencia al combinar los parámetros de una
# estación: gana el más grave (ver evaluar_semaforo).
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
