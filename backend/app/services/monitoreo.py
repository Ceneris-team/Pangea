"""Continuidad de datos independiente de los derechos de envío de correos."""

import os
from datetime import datetime, timedelta, timezone

from app.models import Dispositivo, Sede, Suscripcion, Ubicacion
from app.models.alarma import Alarma, DestinatarioAlarma, EstadoAlarma, NotificacionEnviada
from app.services.contratos import estado_contrato, ultimo_contrato
from app.services.limites_plan import fecha_comercial


def umbral_sin_datos():
    return timedelta(minutes=max(1, int(os.getenv("MONITOREO_SIN_DATOS_MINUTOS", "60"))))


def correos_habilitados(db, id_sd):
    sede = db.get(Sede, id_sd)
    if sede is None:
        return False
    hoy = fecha_comercial()
    contrato = ultimo_contrato(db, sede.id_clnt, hoy)
    if contrato is None and os.getenv("PLAN_LIMITS_REQUIRE_SUBSCRIPTION", "true").lower() in {
        "false",
        "0",
        "no",
    }:
        return not db.query(Suscripcion).filter_by(id_clnt=sede.id_clnt).first()
    # El período de gracia conserva la ingesta, pero no extiende los correos.
    return estado_contrato(db, contrato, hoy) == "Vigente"


def motivo_no_enviar(db, notificacion):
    alarma = db.get(Alarma, notificacion.id_alrm) if notificacion.id_alrm else None
    proyecto_id = alarma.id_ubccn if alarma else notificacion.id_ubccn
    if proyecto_id is None:
        return None  # Bienvenida y avisos comerciales mantienen su política propia.
    proyecto = db.get(Ubicacion, proyecto_id)
    if proyecto is None or not proyecto.monitoreo_activo:
        return "Monitoreo detenido explícitamente"
    if alarma:
        if alarma.estd != "Activa":
            return "La regla de alarma está pausada"
        destinatario = (
            db.query(DestinatarioAlarma)
            .filter_by(id_alrm=alarma.id_alrm, cnl="email", crr=notificacion.dstn)
            .first()
        )
        if destinatario is None:
            return "El destinatario ya no pertenece a la alarma"
    if notificacion.tipo == "dispositivo_sin_datos":
        autorizado = (
            db.query(DestinatarioAlarma)
            .join(Alarma)
            .filter(
                Alarma.id_ubccn == proyecto_id,
                Alarma.estd == "Activa",
                DestinatarioAlarma.cnl == "email",
                DestinatarioAlarma.crr == notificacion.dstn,
            )
            .first()
        )
        if autorizado is None:
            return "El destinatario ya no recibe avisos del proyecto"
        equipo = db.get(Dispositivo, notificacion.contexto.get("id_dspstv"))
        if (
            equipo is None
            or equipo.estd != "Activo"
            or equipo.sin_datos_desde is None
            or equipo.sin_datos_desde.isoformat() != notificacion.contexto.get("desde")
        ):
            return "El equipo ya recibió datos o el incidente dejó de estar vigente"
    if not correos_habilitados(db, proyecto.id_sd):
        return "Correos pausados por vencimiento o suspensión de la suscripción"
    return None


def omitir_notificacion(db, notificacion, motivo):
    notificacion.estd = "Omitido"
    notificacion.ultimo_error = motivo
    notificacion.bloqueo_hasta = None
    if notificacion.tipo == "dispositivo_sin_datos":
        equipo = db.get(Dispositivo, notificacion.contexto.get("id_dspstv"))
        if equipo:
            equipo.aviso_sin_datos = None
    if notificacion.id_alrm:
        for estado in db.query(EstadoAlarma).filter_by(id_alrm=notificacion.id_alrm).all():
            if estado.en_alarma:
                estado.resumen_pendiente = True


def mantener_monitoreo(db, ahora=None):
    from app.services.notificaciones import crear_notificacion

    ahora = ahora or datetime.now(timezone.utc)
    alarmas = (
        db.query(Alarma).filter_by(estd="Activa").order_by(Alarma.id_alrm).with_for_update().all()
    )
    resumenes = 0
    for alarma in alarmas:
        proyecto = db.get(Ubicacion, alarma.id_ubccn)
        estados = (
            db.query(EstadoAlarma)
            .join(Dispositivo, Dispositivo.id_dspstv == EstadoAlarma.id_dspstv)
            .filter(
                EstadoAlarma.id_alrm == alarma.id_alrm,
                Dispositivo.estd == "Activo",
                Dispositivo.id_ubccn == alarma.id_ubccn,
            )
            .all()
        )
        habilitado = proyecto.monitoreo_activo and correos_habilitados(db, proyecto.id_sd)
        if not habilitado:
            for estado in estados:
                estado.resumen_pendiente = estado.en_alarma
            continue
        pendientes = [e for e in estados if e.resumen_pendiente and e.en_alarma]
        if not pendientes:
            continue
        # Un resumen sustituye los avisos que quedaron pendientes antes de la pausa.
        anteriores = (
            db.query(NotificacionEnviada)
            .filter(
                NotificacionEnviada.id_alrm == alarma.id_alrm,
                NotificacionEnviada.estd.in_(["Pendiente", "Encolado", "Reintentando"]),
            )
            .with_for_update(skip_locked=True)
            .all()
        )
        for anterior in anteriores:
            anterior.estd = "Omitido"
            anterior.ultimo_error = "Sustituido por el resumen al reanudar los avisos"
            anterior.bloqueo_hasta = None
        activas = [e for e in estados if e.en_alarma]
        detalles = []
        for estado in activas:
            equipo = db.get(Dispositivo, estado.id_dspstv)
            detalles.append(
                f"{equipo.nmbr}: último valor {estado.ultimo_valor}; "
                f"última lectura {estado.ultima_fecha.isoformat()}"
            )
        destinatarios = (
            db.query(DestinatarioAlarma).filter_by(id_alrm=alarma.id_alrm, cnl="email").all()
        )
        for destinatario in destinatarios:
            crear_notificacion(
                db,
                destinatario=destinatario.crr,
                tipo="resumen_alarma_reanudada",
                plantilla="generica",
                id_usr=alarma.id_usr,
                id_sd=alarma.id_sd,
                id_alrm=alarma.id_alrm,
                id_ubccn=alarma.id_ubccn,
                contexto={
                    "titulo": f"Resumen de alarma: {alarma.nmbr}",
                    "mensaje": "Se reanudan los avisos. Últimos estados conocidos; "
                    "revisa las fechas de lectura. " + "; ".join(detalles),
                },
                clave=f"resumen:{alarma.id_alrm}:{ahora.isoformat()}:{destinatario.crr}",
            )
            resumenes += 1
        if destinatarios:
            for estado in estados:
                estado.resumen_pendiente = False

    # Revisar también mensajes que se crearon antes de vencer la suscripción.
    db.flush()
    pendientes = (
        db.query(NotificacionEnviada)
        .filter(
            NotificacionEnviada.estd.in_(["Pendiente", "Encolado", "Reintentando"]),
            NotificacionEnviada.id_ubccn.is_not(None) | NotificacionEnviada.id_alrm.is_not(None),
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    for notificacion in pendientes:
        motivo = motivo_no_enviar(db, notificacion)
        if motivo:
            omitir_notificacion(db, notificacion, motivo)

    incidentes = 0
    equipos = (
        db.query(Dispositivo)
        .join(Ubicacion)
        .filter(Dispositivo.estd == "Activo", Ubicacion.monitoreo_activo.is_(True))
        .order_by(Dispositivo.id_dspstv)
        .with_for_update(of=Dispositivo)
        .all()
    )
    for equipo in equipos:
        referencia = equipo.ultima_recepcion or equipo.fch_rgstr
        desde = referencia + umbral_sin_datos()
        if desde > ahora:
            equipo.sin_datos_desde = None
            equipo.aviso_sin_datos = None
            continue
        equipo.sin_datos_desde = desde
        if equipo.aviso_sin_datos == desde:
            continue
        proyecto = db.get(Ubicacion, equipo.id_ubccn)
        if not correos_habilitados(db, proyecto.id_sd):
            continue
        correos = (
            db.query(DestinatarioAlarma.crr)
            .join(Alarma)
            .filter(
                Alarma.id_ubccn == equipo.id_ubccn,
                Alarma.estd == "Activa",
                DestinatarioAlarma.cnl == "email",
            )
            .distinct()
            .all()
        )
        for (correo,) in correos:
            crear_notificacion(
                db,
                destinatario=correo,
                tipo="dispositivo_sin_datos",
                id_usr=None,
                id_sd=proyecto.id_sd,
                id_ubccn=proyecto.id_ubccn,
                contexto={
                    "titulo": f"Sin datos: {equipo.nmbr}",
                    "id_dspstv": equipo.id_dspstv,
                    "desde": desde.isoformat(),
                    "mensaje": f"{proyecto.nmbr}: no se reciben nuevas lecturas válidas "
                    f"desde {referencia.isoformat()}. Umbral de prueba: "
                    f"{int(umbral_sin_datos().total_seconds() / 60)} minutos.",
                },
                clave=f"sin-datos:{equipo.id_dspstv}:{desde.isoformat()}:{ahora.isoformat()}:{correo}",
            )
        if correos:
            equipo.aviso_sin_datos = desde
        incidentes += 1
    return {"resumenes": resumenes, "incidentes_sin_datos": incidentes}
