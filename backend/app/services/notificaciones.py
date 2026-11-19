"""Bandeja transaccional: no contacta Redis ni AWS durante la ingesta."""

import hashlib
import uuid
from datetime import timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.dialects.postgresql import insert

from app.models.alarma import (
    Alarma,
    CondicionAlarma,
    DestinatarioAlarma,
    EstadoAlarma,
    NotificacionEnviada,
)
from app.models.mapeo_dispositivo import Parametro
from app.models.rol_usuario import Usuario
from app.models.ubicacion_conexion import Ubicacion

PLANTILLAS = {"alarma_activada", "generica", "bienvenida"}

# ── HU30 CA3 (PP-75 / PP-233): contenido del correo de disparo ──────────────
#
# El aviso dice qué alarma, dónde, qué valor y contra qué condición, con la
# fecha en la zona horaria del dueño de la alarma (usr.zn_hrr) y los números
# sin los ceros de relleno de Numeric(14,4) ("30", no "30.0000").

ZONA_POR_DEFECTO = "America/Lima"
TEXTO_OPERADOR = {
    ">": "mayor que",
    ">=": "mayor o igual que",
    "<": "menor que",
    "<=": "menor o igual que",
    "=": "igual a",
}


def formatear_numero(valor) -> str:
    """35.0000 -> '35'; 7.0010 -> '7.001'; -0.5 -> '-0.5'. Sin notación
    científica (1E+1 -> '10')."""
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return str(valor)
    if not numero.is_finite():
        return str(valor)
    texto = format(numero.normalize(), "f")
    return "0" if texto in ("-0", "") else texto


def _con_unidad(texto: str, unidad: str) -> str:
    return f"{texto} {unidad}".strip() if unidad else texto


def texto_condicion(condiciones, unidad: str) -> str:
    """'mayor que 30 °C' (o varias unidas con ' o ', en alarmas antiguas)."""
    return " o ".join(
        _con_unidad(
            f"{TEXTO_OPERADOR.get(c.oprdr, c.oprdr)} {formatear_numero(c.vlr_umbrl)}", unidad
        )
        for c in condiciones
    )


def simbolo_condicion(condiciones, unidad: str) -> str:
    """'> 30 °C' (forma corta, la misma del listado de alarmas)."""
    return " o ".join(
        _con_unidad(f"{c.oprdr} {formatear_numero(c.vlr_umbrl)}", unidad) for c in condiciones
    )


def zona_valida(nombre: str | None) -> str:
    try:
        ZoneInfo(nombre or ZONA_POR_DEFECTO)
        return nombre or ZONA_POR_DEFECTO
    except (ZoneInfoNotFoundError, ValueError):
        return ZONA_POR_DEFECTO


def fecha_en_zona(fecha_utc, zona: str) -> str:
    """'19/11/2026 15:40:12' en la zona indicada."""
    return fecha_utc.astimezone(ZoneInfo(zona)).strftime("%d/%m/%Y %H:%M:%S")


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
    # HU30 CA4 (PP-232): con el canal de correo apagado la alarma se sigue
    # evaluando -su estado por dispositivo se actualiza-, pero no envía avisos.
    con_correo = [a.id_alrm for a in alarmas if a.cnl_crr_actv]
    destinatarios = {}
    for d in (
        db.query(DestinatarioAlarma)
        .filter(
            DestinatarioAlarma.id_alrm.in_(con_correo),
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
    # PP-233: la fecha del aviso va en la zona horaria del dueño de la alarma.
    zonas = {
        u.id_usr: zona_valida(u.zn_hrr)
        for u in db.query(Usuario.id_usr, Usuario.zn_hrr)
        .filter(Usuario.id_usr.in_({a.id_usr for a in alarmas}))
        .all()
    }
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
                unidad = parametro.undd or ""
                zona = zonas.get(alarma.id_usr, ZONA_POR_DEFECTO)
                contexto = {
                    "alarma": alarma.nmbr,
                    "ubicacion": ubicacion.nmbr,
                    "dispositivo": dispositivo.nmbr,
                    "parametro": parametro.nmbr,
                    "unidad": unidad,
                    "valor": formatear_numero(lectura.valor),
                    # UTC ISO para trazabilidad (historial); la fecha legible
                    # va en la zona del dueño de la alarma.
                    "fecha": fecha.isoformat(),
                    "fecha_local": fecha_en_zona(fecha, zona),
                    "zona_horaria": zona,
                    "condicion": simbolo_condicion(reglas, unidad),
                    "condicion_texto": texto_condicion(reglas, unidad),
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
