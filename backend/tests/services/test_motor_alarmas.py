"""
HU 29 CA3/CA4 - Motor de evaluación de condiciones de alarma.

  CA3  la alarma Activa cuyo valor cumple la condición pasa a Disparada y
       se registra la notificación (HU30)
  CA4  la alarma Disparada cuyo valor vuelve a estar dentro del rango
       normal regresa a Activa

Llama directamente a evaluar_alarmas() con la misma forma de
ultimos_por_parametro que guardar_lecturas() ya calcula, sin pasar por el
pipeline de ingesta completo (parseo/FTP/Celery): eso ya lo cubren los
tests de tests/services/test_ingesta_*.py y tests/routers/test_alarmas.py
cubre la creación/edición de la alarma y su condición.
"""

import datetime as dt

from app.models.alarma import Alarma, CondicionAlarma, DestinatarioAlarma, NotificacionEnviada
from app.models.mapeo_dispositivo import Parametro
from app.models.ubicacion_conexion import Ubicacion
from app.services.alarmas.motor import evaluar_alarmas

POLIGONO_DUMMY = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}


def _crear_ubicacion(db_session, sede, nombre="Estación motor de alarmas"):
    ubicacion = Ubicacion(id_sd=sede.id_sd, nmbr=nombre, lttd=0, lngtd=0, plgn_gjsn=POLIGONO_DUMMY)
    db_session.add(ubicacion)
    db_session.flush()
    return ubicacion


def _crear_alarma(db_session, usuario, ubicacion, parametro, oprdr=">", umbral=30, estd="Activa"):
    alarma = Alarma(
        id_usr=usuario.id_usr,
        id_sd=ubicacion.id_sd,
        nmbr="Alarma de prueba",
        id_prmtr=parametro.id_prmtr,
        id_ubccn=ubicacion.id_ubccn,
        estd=estd,
    )
    db_session.add(alarma)
    db_session.flush()
    db_session.add(CondicionAlarma(id_alrm=alarma.id_alrm, oprdr=oprdr, vlr_umbrl=umbral))
    db_session.flush()
    return alarma


def _activar_notificacion_por_correo(db_session, alarma, correo):
    db_session.add(DestinatarioAlarma(id_alrm=alarma.id_alrm, cnl="email", crr=correo))
    db_session.flush()


def test_ca3_alarma_activa_que_cumple_la_condicion_pasa_a_disparada(db_session, fabrica):
    sede = fabrica.sede()
    usuario = fabrica.usuario()
    ubicacion = _crear_ubicacion(db_session, sede)
    parametro = Parametro(nmbr="nivel_motor_ca3", undd="m", tipo_dato="numerico")
    db_session.add(parametro)
    db_session.flush()

    alarma = _crear_alarma(db_session, usuario, ubicacion, parametro, oprdr=">", umbral=30)
    _activar_notificacion_por_correo(db_session, alarma, usuario.crr)

    ahora = dt.datetime.now(dt.timezone.utc)
    evaluar_alarmas(db_session, ubicacion.id_ubccn, {"nivel_motor_ca3": (35.0, ahora)})

    db_session.refresh(alarma)
    assert alarma.estd == "Disparada"

    notificaciones = (
        db_session.query(NotificacionEnviada)
        .filter(NotificacionEnviada.id_alrm == alarma.id_alrm)
        .all()
    )
    assert len(notificaciones) == 1
    assert notificaciones[0].dstn == usuario.crr
    assert notificaciones[0].estd == "Enviado"


def test_alarma_activa_que_no_cumple_la_condicion_no_cambia(db_session, fabrica):
    sede = fabrica.sede()
    usuario = fabrica.usuario()
    ubicacion = _crear_ubicacion(db_session, sede)
    parametro = Parametro(nmbr="nivel_motor_sin_cambio", undd="m", tipo_dato="numerico")
    db_session.add(parametro)
    db_session.flush()

    alarma = _crear_alarma(db_session, usuario, ubicacion, parametro, oprdr=">", umbral=30)

    evaluar_alarmas(
        db_session,
        ubicacion.id_ubccn,
        {"nivel_motor_sin_cambio": (10.0, dt.datetime.now(dt.timezone.utc))},
    )

    db_session.refresh(alarma)
    assert alarma.estd == "Activa"
    assert (
        db_session.query(NotificacionEnviada)
        .filter(NotificacionEnviada.id_alrm == alarma.id_alrm)
        .count()
        == 0
    )


def test_ca4_alarma_disparada_que_vuelve_al_rango_normal_regresa_a_activa(db_session, fabrica):
    sede = fabrica.sede()
    usuario = fabrica.usuario()
    ubicacion = _crear_ubicacion(db_session, sede)
    parametro = Parametro(nmbr="nivel_motor_ca4", undd="m", tipo_dato="numerico")
    db_session.add(parametro)
    db_session.flush()

    alarma = _crear_alarma(
        db_session, usuario, ubicacion, parametro, oprdr=">", umbral=30, estd="Disparada"
    )

    evaluar_alarmas(
        db_session,
        ubicacion.id_ubccn,
        {"nivel_motor_ca4": (10.0, dt.datetime.now(dt.timezone.utc))},
    )

    db_session.refresh(alarma)
    assert alarma.estd == "Activa"


def test_no_reenvia_notificacion_mientras_sigue_disparada(db_session, fabrica):
    """Edge-triggered: si la alarma ya está Disparada y el valor sigue
    cumpliendo la condición, no se genera una notificación nueva en cada
    lote -solo al cruzar de Activa a Disparada-."""
    sede = fabrica.sede()
    usuario = fabrica.usuario()
    ubicacion = _crear_ubicacion(db_session, sede)
    parametro = Parametro(nmbr="nivel_motor_sin_reenvio", undd="m", tipo_dato="numerico")
    db_session.add(parametro)
    db_session.flush()

    alarma = _crear_alarma(
        db_session, usuario, ubicacion, parametro, oprdr=">", umbral=30, estd="Disparada"
    )
    _activar_notificacion_por_correo(db_session, alarma, usuario.crr)

    evaluar_alarmas(
        db_session,
        ubicacion.id_ubccn,
        {"nivel_motor_sin_reenvio": (35.0, dt.datetime.now(dt.timezone.utc))},
    )

    db_session.refresh(alarma)
    assert alarma.estd == "Disparada"
    assert (
        db_session.query(NotificacionEnviada)
        .filter(NotificacionEnviada.id_alrm == alarma.id_alrm)
        .count()
        == 0
    )


def test_sin_destinatario_activo_no_notifica_pero_igual_dispara(db_session, fabrica):
    """HU30 CA4: canal de correo desactivado -> la alarma igual pasa a
    Disparada (CA3 sigue cumpliéndose), pero no hay a quién notificar."""
    sede = fabrica.sede()
    usuario = fabrica.usuario()
    ubicacion = _crear_ubicacion(db_session, sede)
    parametro = Parametro(nmbr="nivel_motor_sin_destinatario", undd="m", tipo_dato="numerico")
    db_session.add(parametro)
    db_session.flush()

    alarma = _crear_alarma(db_session, usuario, ubicacion, parametro, oprdr=">", umbral=30)

    evaluar_alarmas(
        db_session,
        ubicacion.id_ubccn,
        {"nivel_motor_sin_destinatario": (35.0, dt.datetime.now(dt.timezone.utc))},
    )

    db_session.refresh(alarma)
    assert alarma.estd == "Disparada"
    assert (
        db_session.query(NotificacionEnviada)
        .filter(NotificacionEnviada.id_alrm == alarma.id_alrm)
        .count()
        == 0
    )


def test_alarma_sin_condicion_configurada_se_omite(db_session, fabrica):
    sede = fabrica.sede()
    usuario = fabrica.usuario()
    ubicacion = _crear_ubicacion(db_session, sede)
    parametro = Parametro(nmbr="nivel_motor_sin_condicion", undd="m", tipo_dato="numerico")
    db_session.add(parametro)
    db_session.flush()

    alarma = Alarma(
        id_usr=usuario.id_usr,
        id_sd=ubicacion.id_sd,
        nmbr="Alarma sin condición",
        id_prmtr=parametro.id_prmtr,
        id_ubccn=ubicacion.id_ubccn,
    )
    db_session.add(alarma)
    db_session.flush()

    # No debe lanzar ni tocar el estado de una alarma sin fila en
    # cndcn_alrm todavía (HU29 CA1 pendiente para esa alarma).
    evaluar_alarmas(
        db_session,
        ubicacion.id_ubccn,
        {"nivel_motor_sin_condicion": (999.0, dt.datetime.now(dt.timezone.utc))},
    )

    db_session.refresh(alarma)
    assert alarma.estd == "Activa"


def test_alarma_de_otra_ubicacion_no_se_evalua(db_session, fabrica):
    sede = fabrica.sede()
    usuario = fabrica.usuario()
    ubicacion = _crear_ubicacion(db_session, sede, nombre="Ubicación evaluada")
    ubicacion_ajena = _crear_ubicacion(db_session, sede, nombre="Ubicación ajena")
    parametro = Parametro(nmbr="nivel_motor_otra_ubicacion", undd="m", tipo_dato="numerico")
    db_session.add(parametro)
    db_session.flush()

    alarma_ajena = _crear_alarma(
        db_session, usuario, ubicacion_ajena, parametro, oprdr=">", umbral=30
    )

    evaluar_alarmas(
        db_session,
        ubicacion.id_ubccn,
        {"nivel_motor_otra_ubicacion": (999.0, dt.datetime.now(dt.timezone.utc))},
    )

    db_session.refresh(alarma_ajena)
    assert alarma_ajena.estd == "Activa"
