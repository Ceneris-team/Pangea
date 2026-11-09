"""Bandeja transaccional: no contacta Redis ni AWS durante la ingesta."""

import hashlib
import uuid
from datetime import timezone
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert

from app.models.alarma import (
    Alarma,
    CondicionAlarma,
    DestinatarioAlarma,
    EstadoAlarma,
    NotificacionEnviada,
)
from app.models.mapeo_dispositivo import Parametro
from app.models.ubicacion_conexion import Ubicacion

PLANTILLAS = {"alarma_activada", "generica", "bienvenida"}


def crear_notificacion(
    db,
    *,
    destinatario,
    tipo,
    contexto,
    id_usr,
    id_sd=None,
    id_alrm=None,
    plantilla="generica",
    clave=None,
):
    """El llamador confirma la transacción. Clave estable permite idempotencia."""
    from pydantic import EmailStr, TypeAdapter

    destinatario = str(TypeAdapter(EmailStr).validate_python(destinatario)).lower()
    if plantilla not in PLANTILLAS:
        raise ValueError("Plantilla de notificación desconocida")
    if not tipo or len(tipo) > 50 or len(destinatario) > 150:
        raise ValueError("Tipo o destinatario de notificación inválido")
    clave = hashlib.sha256((clave or str(uuid.uuid4())).encode()).hexdigest()
    valores = dict(
        id_alrm=id_alrm,
        id_usr=id_usr,
        id_sd=id_sd,
        cnl="email",
        dstn=destinatario,
        tipo=tipo,
        plantilla=plantilla,
        contexto=contexto,
        clave=clave,
        estd="Pendiente",
    )
    # La unicidad se decide en PostgreSQL, incluso entre procesos o dos
    # llamadas con la misma clave antes del flush del llamador.
    notificacion = db.execute(
        insert(NotificacionEnviada)
        .values(**valores)
        .on_conflict_do_nothing(index_elements=["clave"])
        .returning(NotificacionEnviada)
    ).scalar_one_or_none()
    return (
        notificacion
        if notificacion is not None
        else db.query(NotificacionEnviada).filter_by(clave=clave).one()
    )


def cumple_condicion(valor, operador, umbral):
    valor, umbral = Decimal(str(valor)), Decimal(str(umbral))
    if not valor.is_finite() or not umbral.is_finite():
        return False
    return {
        ">": lambda: valor > umbral,
        "<": lambda: valor < umbral,
        ">=": lambda: valor >= umbral,
        "<=": lambda: valor <= umbral,
        "=": lambda: valor == umbral,
    }[operador]()


def evaluar_alarmas(db, *, lecturas, dispositivo, id_sd):
    """Evalúa TODAS las lecturas ordenadas, no solo la última del archivo.

    Una condición cumplida activa la alarma (OR). Se notifica la transición
    normal -> alarma por dispositivo. Lecturas antiguas/reprocesadas no
    cambian el estado más reciente. El bloqueo serializa ingestas concurrentes.
    """
    numericas = [
        lectura
        for lectura in lecturas
        if lectura.valor is not None and not isinstance(lectura.valor, str)
    ]
    if not numericas:
        return
    alarmas = (
        db.query(Alarma)
        .filter(
            Alarma.id_ubccn == dispositivo.id_ubccn,
            Alarma.estd == "Activa",
        )
        .order_by(Alarma.id_alrm)
        .with_for_update()
        .all()
    )
    if not alarmas:
        return
    ids = [a.id_alrm for a in alarmas]
    condiciones = {}
    for c in db.query(CondicionAlarma).filter(CondicionAlarma.id_alrm.in_(ids)).all():
        condiciones.setdefault(c.id_alrm, []).append(c)
    destinatarios = {}
    for d in (
        db.query(DestinatarioAlarma)
        .filter(
            DestinatarioAlarma.id_alrm.in_(ids),
            DestinatarioAlarma.cnl == "email",
        )
        .all()
    ):
        destinatarios.setdefault(d.id_alrm, []).append(d.crr)
    parametros = {
        p.id_prmtr: p
        for p in db.query(Parametro)
        .filter(Parametro.id_prmtr.in_([a.id_prmtr for a in alarmas]))
        .all()
    }
    ubicacion = db.get(Ubicacion, dispositivo.id_ubccn)
    for alarma in alarmas:
        reglas = condiciones.get(alarma.id_alrm, [])
        parametro = parametros[alarma.id_prmtr]
        estado = db.get(EstadoAlarma, (alarma.id_alrm, dispositivo.id_dspstv))
        for lectura in sorted(numericas, key=lambda item: item.fecha_hora):
            if lectura.parametro != parametro.nmbr or not reglas:
                continue
            fecha = lectura.fecha_hora
            if fecha.tzinfo is None:
                raise ValueError("La evaluación de alarmas requiere lecturas con zona horaria")
            fecha = fecha.astimezone(timezone.utc)
            if estado is not None and fecha <= estado.ultima_fecha:
                continue
            activa = any(cumple_condicion(lectura.valor, c.oprdr, c.vlr_umbrl) for c in reglas)
            if estado is None:
                estado = EstadoAlarma(
                    id_alrm=alarma.id_alrm,
                    id_dspstv=dispositivo.id_dspstv,
                    en_alarma=False,
                    ultima_fecha=fecha,
                )
                db.add(estado)
            if activa and not estado.en_alarma:
                contexto = {
                    "alarma": alarma.nmbr,
                    "ubicacion": ubicacion.nmbr,
                    "dispositivo": dispositivo.nmbr,
                    "parametro": parametro.nmbr,
                    "unidad": parametro.undd or "",
                    "valor": str(lectura.valor),
                    "fecha": fecha.isoformat(),
                    "condicion": " o ".join(f"{c.oprdr} {c.vlr_umbrl}" for c in reglas),
                }
                for correo in destinatarios.get(alarma.id_alrm, []):
                    crear_notificacion(
                        db,
                        destinatario=correo,
                        tipo="alarma_activada",
                        contexto=contexto,
                        id_usr=alarma.id_usr,
                        id_sd=id_sd,
                        id_alrm=alarma.id_alrm,
                        plantilla="alarma_activada",
                        clave=f"alarma:{alarma.id_alrm}:{dispositivo.id_dspstv}:{fecha.isoformat()}:{correo.lower()}",
                    )
            estado.en_alarma = activa
            estado.ultima_fecha = fecha
