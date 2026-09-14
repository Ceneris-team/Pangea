"""
HU 29 - Establecer condiciones de la alarma (CA3/CA4: evaluación en la
ingesta).

CA3: "el sistema recibe telemetría del parámetro monitoreado, CUANDO el
valor recibido cumple la condición configurada, ENTONCES el sistema
activa la alarma, la marca como disparada en el listado y envía la
notificación según la configuración de HU 30."
CA4: "una alarma ha sido disparada y el valor del parámetro vuelve a
estar dentro del rango normal, CUANDO el sistema recibe el nuevo valor,
ENTONCES la alarma regresa al estado Activa".

Se llama desde app/tasks/ingesta.py, DESPUÉS del commit de
guardar_lecturas -mismo criterio que _publicar_eventos_mapa (HU17):
nunca debe hacer fallar el job de ingesta ni revertir datos de
telemetría ya persistidos, así que evaluar_alarmas() nunca lanza.

No toca app/services/mapa/semaforo.py: ese módulo pinta los colores del
mapa (HU17) con umbrales todavía temporales y es un consumidor
DISTINTO de cndcn_alrm, con su propio reemplazo pendiente. Esta HU
evalúa las alarmas reales del usuario, no el semáforo.

Transición de estados (edge-triggered, para no reenviar la misma
notificación en cada archivo mientras la condición sigue cumplida):
  Activa    + cumple     -> Disparada (+ notifica)
  Disparada + no cumple  -> Activa
  cualquier otro caso    -> sin cambios

Solo se evalúan alarmas con id_prmtr entre los parámetros de este lote y
que ya tengan una condición configurada (HU29 CA1 pendiente para esa
alarma en particular no debe reventar el lote de otras).
"""

import logging
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.models.alarma import Alarma, CondicionAlarma, DestinatarioAlarma, NotificacionEnviada
from app.models.mapeo_dispositivo import Parametro
from app.models.rol_usuario import Usuario
from app.models.ubicacion_conexion import Ubicacion
from app.security.mailer import enviar_correo_alarma

logger = logging.getLogger(__name__)

ESTADOS_EVALUABLES = ("Activa", "Disparada")


def _cumple_condicion(valor: Decimal, operador: str, umbral: Decimal) -> bool:
    """Misma semántica que el CHECK de cndcn_alrm (> < >= <= =)."""
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


def evaluar_alarmas(db: Session, id_ubccn: int, ultimos_por_parametro: dict) -> None:
    """ultimos_por_parametro: {nombre_parametro: (valor, fecha_hora)}, la
    misma forma que ya usa _publicar_eventos_mapa (HU17) -el resumen que
    guardar_lecturas ya calculó, no una consulta nueva a tlmtr."""
    if not ultimos_por_parametro or id_ubccn is None:
        return

    try:
        _evaluar_alarmas(db, id_ubccn, ultimos_por_parametro)
    except Exception:
        logger.exception(
            "HU29: fallo evaluando alarmas de ubicacion=%s, se omite este lote", id_ubccn
        )
        db.rollback()


def _evaluar_alarmas(db: Session, id_ubccn: int, ultimos_por_parametro: dict) -> None:
    ids_por_nombre = {
        p.nmbr: p.id_prmtr
        for p in db.query(Parametro).filter(Parametro.nmbr.in_(list(ultimos_por_parametro.keys())))
    }
    if not ids_por_nombre:
        return
    nombre_por_id_prmtr = {v: k for k, v in ids_por_nombre.items()}

    alarmas = (
        db.query(Alarma)
        .filter(
            Alarma.id_ubccn == id_ubccn,
            Alarma.id_prmtr.in_(ids_por_nombre.values()),
            Alarma.estd.in_(ESTADOS_EVALUABLES),
        )
        .all()
    )
    if not alarmas:
        return

    condiciones_por_alarma: dict[int, CondicionAlarma] = {}
    for condicion in (
        db.query(CondicionAlarma)
        .filter(CondicionAlarma.id_alrm.in_([a.id_alrm for a in alarmas]))
        .order_by(CondicionAlarma.id_cndcn)
    ):
        # Una alarma admite -en teoría- más de una fila en cndcn_alrm,
        # pero HU29 fija "únicamente una condición de disparo en v1.0":
        # se evalúa la primera, igual criterio que el listado de HU27
        # (_formatear_condicion en routers/alarmas.py).
        condiciones_por_alarma.setdefault(condicion.id_alrm, condicion)

    hubo_cambios = False
    for alarma in alarmas:
        condicion = condiciones_por_alarma.get(alarma.id_alrm)
        if condicion is None:
            continue

        nombre_parametro = nombre_por_id_prmtr.get(alarma.id_prmtr)
        valor, fecha_hora = ultimos_por_parametro.get(nombre_parametro, (None, None))
        if valor is None:
            continue

        try:
            valor_decimal = Decimal(str(valor))
        except (InvalidOperation, ValueError, TypeError):
            continue

        cumple = _cumple_condicion(valor_decimal, condicion.oprdr, condicion.vlr_umbrl)
        hubo_cambios = True

        if cumple and alarma.estd == "Activa":
            alarma.estd = "Disparada"
            db.flush()
            _notificar_disparo(db, alarma, condicion, valor_decimal, fecha_hora)
        elif not cumple and alarma.estd == "Disparada":
            alarma.estd = "Activa"

    if hubo_cambios:
        db.commit()


def _notificar_disparo(
    db: Session,
    alarma: Alarma,
    condicion: CondicionAlarma,
    valor: Decimal,
    fecha_hora,
) -> None:
    """HU30: notifica a los destinatarios con el canal de correo activo
    para esta alarma. Sin destinatarios configurados, no hay nada que
    enviar -HU30 CA4, canal desactivado-."""
    destinatarios = (
        db.query(DestinatarioAlarma)
        .filter(DestinatarioAlarma.id_alrm == alarma.id_alrm, DestinatarioAlarma.cnl == "email")
        .all()
    )
    if not destinatarios:
        return

    ubicacion = db.get(Ubicacion, alarma.id_ubccn)
    parametro = db.get(Parametro, alarma.id_prmtr)
    usuario = db.get(Usuario, alarma.id_usr)
    unidad = parametro.undd if parametro else ""

    for destinatario in destinatarios:
        estado_envio = "Enviado"
        try:
            enviar_correo_alarma(
                destinatario.crr,
                nombre_alarma=alarma.nmbr,
                nombre_parametro=parametro.nmbr if parametro else "",
                valor=valor,
                umbral=condicion.vlr_umbrl,
                unidad=unidad,
                nombre_ubicacion=ubicacion.nmbr if ubicacion else "",
                fecha_hora=fecha_hora,
                zona_horaria=usuario.zn_hrr if usuario else None,
            )
        except Exception:
            logger.exception(
                "HU29/HU30: fallo enviando notificación de alarma id_alrm=%s a %s",
                alarma.id_alrm,
                destinatario.crr,
            )
            estado_envio = "Fallido"

        db.add(
            NotificacionEnviada(
                id_alrm=alarma.id_alrm,
                cnl="email",
                dstn=destinatario.crr,
                estd=estado_envio,
            )
        )
