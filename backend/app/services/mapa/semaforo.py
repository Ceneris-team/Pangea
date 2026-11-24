"""El mapa utiliza las mismas condiciones compartidas que las alarmas."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from app.models import Dispositivo, EventoTexto, Parametro, Telemetria, Ubicacion
from app.models.alarma import Alarma, CondicionAlarma
from app.services.notificaciones import cumple_condicion

VERDE = "verde"
ROJO = "rojo"
AMARILLO = "amarillo"


def evaluar_parametro(nombre_parametro, valor, condiciones=None):
    reglas = (condiciones or {}).get(nombre_parametro, [])
    if not reglas:
        return "sin_reglas"
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return "sin_datos"
    if not numero.is_finite():
        return "sin_datos"
    return ROJO if any(cumple_condicion(numero, op, umbral) for op, umbral in reglas) else VERDE


def evaluar_semaforo(valores_por_parametro, condiciones=None):
    colores = {evaluar_parametro(n, v, condiciones) for n, v in valores_por_parametro.items()}
    if ROJO in colores:
        return ROJO
    if VERDE in colores:
        return VERDE
    return "sin_datos" if condiciones else "sin_reglas"


def semaforos_por_ubicacion(db, ids_ubicaciones, dispositivo_id=None):
    from app.services.monitoreo import umbral_sin_datos

    proyectos = db.query(Ubicacion).filter(Ubicacion.id_ubccn.in_(ids_ubicaciones)).all()
    resultado = {u.id_ubccn: "sin_datos" if u.monitoreo_activo else "detenido" for u in proyectos}
    reglas = (
        db.query(Alarma, CondicionAlarma, Parametro.nmbr)
        .join(CondicionAlarma, CondicionAlarma.id_alrm == Alarma.id_alrm)
        .join(Parametro, Parametro.id_prmtr == Alarma.id_prmtr)
        .filter(Alarma.id_ubccn.in_(ids_ubicaciones), Alarma.estd == "Activa")
        .all()
    )
    condiciones = {}
    for alarma, condicion, nombre in reglas:
        condiciones.setdefault(alarma.id_ubccn, {}).setdefault(nombre, []).append(
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
        color = evaluar_parametro(nombre, valor, condiciones.get(proyecto))
        if color in {ROJO, VERDE}:
            colores.setdefault(proyecto, set()).add(color)
    for proyecto in condiciones:
        if resultado.get(proyecto) == "detenido":
            continue
        actuales = colores.get(proyecto, set())
        resultado[proyecto] = (
            ROJO if ROJO in actuales else VERDE if VERDE in actuales else "sin_datos"
        )
    return resultado
