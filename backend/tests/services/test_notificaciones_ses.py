from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import boto3
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from botocore.stub import Stubber
from celery.exceptions import Retry
from sqlalchemy import text

from app.models import (
    Alarma,
    CondicionAlarma,
    DestinatarioAlarma,
    EstadoAlarma,
    IntentoNotificacion,
    NotificacionEnviada,
)
from app.services.correo_ses import enviar_ses, error_transitorio, renderizar
from app.services.ingesta.persistencia import guardar_lecturas
from app.services.ingesta.validador import LecturaValidada
from app.services.notificaciones import crear_notificacion, cumple_condicion, evaluar_alarmas
from app.tasks import notificaciones as tareas
from tests.routers.test_alarmas import (
    crear_conexion,
    crear_dispositivo,
    crear_parametro,
    crear_ubicacion,
)


@pytest.fixture(autouse=True)
def aislar_destinatario_pruebas(monkeypatch):
    monkeypatch.delenv("SES_TEST_RECIPIENT", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)


@pytest.fixture()
def caso(db_session, fabrica, monkeypatch):
    sede = fabrica.sede()
    usuario = fabrica.usuario()
    ubicacion = crear_ubicacion(db_session, sede)
    conexion = crear_conexion(db_session, sede)
    dispositivo = crear_dispositivo(db_session, ubicacion, conexion)
    parametro = crear_parametro(db_session, "HT14 temperatura", "°C")
    alarma = Alarma(
        id_usr=usuario.id_usr,
        id_sd=sede.id_sd,
        id_ubccn=ubicacion.id_ubccn,
        id_prmtr=parametro.id_prmtr,
        nmbr="Temperatura alta",
    )
    db_session.add(alarma)
    db_session.flush()
    db_session.add(CondicionAlarma(id_alrm=alarma.id_alrm, oprdr=">", vlr_umbrl=30))
    for c in ("uno@example.com", "dos@example.com"):
        db_session.add(DestinatarioAlarma(id_alrm=alarma.id_alrm, crr=c, cnl="email"))
    db_session.flush()

    @contextmanager
    def sesion_prueba():
        yield db_session

    monkeypatch.setattr(tareas, "SessionLocal", sesion_prueba)
    return {
        "sede": sede,
        "usuario": usuario,
        "alarma": alarma,
        "dispositivo": dispositivo,
        "parametro": parametro,
        "conexion": conexion,
        "fecha": datetime.now(timezone.utc),
    }


def lecturas(caso, valores, inicio=0):
    return [
        LecturaValidada(
            fecha_hora=caso["fecha"] + timedelta(seconds=inicio + i),
            id_cnxn=caso["conexion"].id_cnxn,
            parametro=caso["parametro"].nmbr,
            valor=v,
            numero_fila=i + 1,
        )
        for i, v in enumerate(valores)
    ]


def evaluar(db, caso, valores, inicio=0):
    evaluar_alarmas(
        db,
        lecturas=lecturas(caso, valores, inicio),
        dispositivo=caso["dispositivo"],
        id_sd=caso["sede"].id_sd,
    )
    db.flush()


def aviso(db, caso):
    n = crear_notificacion(
        db,
        destinatario="uno@example.com",
        tipo="vencimiento",
        contexto={"titulo": "Contrato por vencer", "mensaje": "Revisa tu contrato"},
        id_usr=caso["usuario"].id_usr,
        id_sd=caso["sede"].id_sd,
    )
    db.flush()
    return n


def test_evalua_todas_las_lecturas_y_rearma_sin_avisos_repetidos(db_session, caso):
    evaluar(db_session, caso, [20, 35, 36, 20, 40, 41, 42])
    filas = db_session.query(NotificacionEnviada).all()
    assert len(filas) == 4  # dos activaciones por dos destinatarios
    assert {f.contexto["valor"] for f in filas} == {"35", "40"}
    assert all(f.estd == "Pendiente" for f in filas)
    evaluar(db_session, caso, [20, 35, 36, 20, 40, 41, 42])
    assert db_session.query(NotificacionEnviada).count() == 4


def test_lectura_antigua_no_rearma_una_alarma_activa(db_session, caso):
    evaluar(db_session, caso, [40], inicio=10)
    evaluar(db_session, caso, [10], inicio=1)
    evaluar(db_session, caso, [45], inicio=11)
    assert db_session.query(NotificacionEnviada).count() == 2
    assert db_session.query(EstadoAlarma).one().en_alarma


def test_alarma_inactiva_no_notifica(db_session, caso):
    caso["alarma"].estd = "Inactiva"
    db_session.flush()
    evaluar(db_session, caso, [40])
    assert db_session.query(NotificacionEnviada).count() == 0


def test_ingesta_solo_persiste_aviso_sin_contactar_broker_ni_ses(db_session, caso):
    with (
        patch.object(tareas.enviar_notificacion, "apply_async") as publicar,
        patch.object(tareas, "enviar_ses") as ses,
    ):
        guardar_lecturas(db_session, lecturas(caso, [40, 20]), caso["dispositivo"], None)
        db_session.flush()
        assert db_session.query(NotificacionEnviada).count() == 2
        publicar.assert_not_called()
        ses.assert_not_called()


def test_rol_restringido_puede_evaluar_y_enviar(db_session, caso, monkeypatch):
    db_session.execute(text("SET LOCAL ROLE pangea_app"))
    evaluar(db_session, caso, [40])
    filas = db_session.query(NotificacionEnviada).all()
    assert len(filas) == 2
    monkeypatch.setattr(tareas, "enviar_ses", Mock(return_value="ses-rol-restringido"))
    tareas.enviar_notificacion.run(filas[0].id_ntfccn)
    assert filas[0].estd == "Enviado"


def test_rollback_revierte_lectura_estado_y_aviso(db_session, caso):
    with db_session.begin_nested() as transaccion:
        guardar_lecturas(db_session, lecturas(caso, [40]), caso["dispositivo"], None)
        db_session.flush()
        assert db_session.query(NotificacionEnviada).count() == 2
        transaccion.rollback()
    assert db_session.query(NotificacionEnviada).count() == 0
    assert db_session.query(EstadoAlarma).count() == 0


def test_idempotencia_generica_y_tipo_sin_alarma(db_session, caso):
    args = dict(
        destinatario="Uno@example.com",
        tipo="vencimiento",
        contexto={"titulo": "Hola", "mensaje": "Texto"},
        id_usr=caso["usuario"].id_usr,
        clave="evento-47",
    )
    n = crear_notificacion(db_session, **args)
    assert crear_notificacion(db_session, **args).id_ntfccn == n.id_ntfccn
    assert n.id_alrm is None and n.dstn == "uno@example.com"


def test_envio_satisfactorio_guarda_referencia_e_intento_y_no_repite(db_session, caso, monkeypatch):
    n = aviso(db_session, caso)
    enviar = Mock(return_value="ses-message-14")
    monkeypatch.setattr(tareas, "enviar_ses", enviar)
    assert tareas.enviar_notificacion.run(n.id_ntfccn)["estado"] == "Enviado"
    assert n.fch_env and n.mensaje_id == "ses-message-14"
    assert db_session.query(IntentoNotificacion).one().resultado == "Enviado"
    tareas.enviar_notificacion.run(n.id_ntfccn)
    assert enviar.call_count == 1


def temporal():
    return ClientError(
        {
            "Error": {"Code": "TooManyRequestsException"},
            "ResponseMetadata": {"HTTPStatusCode": 429},
        },
        "SendEmail",
    )


def test_retry_persistido_con_backoff_y_exito_posterior(db_session, caso, monkeypatch):
    n = aviso(db_session, caso)
    monkeypatch.setattr(tareas, "enviar_ses", Mock(side_effect=temporal()))
    monkeypatch.setattr(tareas.enviar_notificacion, "retry", Mock(side_effect=Retry()))
    with pytest.raises(Retry):
        tareas.enviar_notificacion.run(n.id_ntfccn)
    assert n.estd == "Reintentando" and n.rntnts == 1 and n.fch_env is None
    assert 4 <= (n.prxm_intnt - tareas.ahora()).total_seconds() <= 10
    assert n.ultimo_error == "TooManyRequestsException"
    n.prxm_intnt = tareas.ahora() - timedelta(seconds=1)
    db_session.flush()
    monkeypatch.setattr(tareas, "enviar_ses", Mock(return_value="recuperado"))
    tareas.enviar_notificacion.run(n.id_ntfccn)
    assert n.estd == "Enviado" and n.ultimo_error is None
    assert db_session.query(IntentoNotificacion).count() == 2


def test_agota_reintentos_aunque_celery_cambie_identificador(db_session, caso, monkeypatch):
    n = aviso(db_session, caso)
    monkeypatch.setattr(tareas, "enviar_ses", Mock(side_effect=temporal()))
    monkeypatch.setattr(tareas.enviar_notificacion, "retry", Mock(side_effect=Retry()))
    for intento in range(6):
        n.prxm_intnt = tareas.ahora() - timedelta(seconds=1)
        db_session.flush()
        if intento < 5:
            with pytest.raises(Retry):
                tareas.enviar_notificacion.run(n.id_ntfccn)
        else:
            tareas.enviar_notificacion.run(n.id_ntfccn)
    assert n.estd == "Fallido" and n.rntnts == 5
    assert db_session.query(IntentoNotificacion).count() == 6


def test_error_permanente_no_reintenta(db_session, caso, monkeypatch):
    n = aviso(db_session, caso)
    error = ClientError(
        {"Error": {"Code": "MessageRejected", "Message": "dato sensible"}}, "SendEmail"
    )
    monkeypatch.setattr(tareas, "enviar_ses", Mock(side_effect=error))
    retry = Mock()
    monkeypatch.setattr(tareas.enviar_notificacion, "retry", retry)
    tareas.enviar_notificacion.run(n.id_ntfccn)
    assert n.estd == "Fallido" and n.ultimo_error == "MessageRejected"
    assert n.rntnts == 0
    retry.assert_not_called()


def test_no_envia_antes_de_fecha_programada(db_session, caso, monkeypatch):
    n = aviso(db_session, caso)
    n.prxm_intnt = tareas.ahora() + timedelta(minutes=1)
    db_session.flush()
    enviar = Mock()
    monkeypatch.setattr(tareas, "enviar_ses", enviar)
    tareas.enviar_notificacion.run(n.id_ntfccn)
    enviar.assert_not_called()


def test_reintento_manual_conserva_la_numeracion_del_historial(db_session, caso, monkeypatch):
    n = aviso(db_session, caso)
    error = ClientError({"Error": {"Code": "AccessDeniedException"}}, "SendEmail")
    monkeypatch.setattr(tareas, "enviar_ses", Mock(side_effect=error))
    tareas.enviar_notificacion.run(n.id_ntfccn)
    assert n.estd == "Fallido"
    n.estd, n.rntnts = "Pendiente", 0
    db_session.flush()
    monkeypatch.setattr(tareas, "enviar_ses", Mock(return_value="recuperado"))
    tareas.enviar_notificacion.run(n.id_ntfccn)
    intentos = db_session.query(IntentoNotificacion).order_by(IntentoNotificacion.numero).all()
    assert [i.numero for i in intentos] == [1, 2]


def test_broker_caido_conserva_aviso_y_despacho_posterior(db_session, caso, monkeypatch):
    n = aviso(db_session, caso)
    publicar = Mock(side_effect=ConnectionError("redis caído"))
    monkeypatch.setattr(tareas.enviar_notificacion, "apply_async", publicar)
    tareas.despachar_pendientes.run()
    assert n.estd == "Pendiente" and n.bloqueo_hasta is None
    publicar.side_effect = None
    tareas.despachar_pendientes.run()
    assert n.estd == "Encolado" and n.bloqueo_hasta > tareas.ahora()
    assert publicar.call_count == 2


def test_reserva_vencida_se_recupera_tras_caida_worker(db_session, caso, monkeypatch):
    n = aviso(db_session, caso)
    n.estd = "Encolado"
    n.bloqueo_hasta = tareas.ahora() - timedelta(seconds=1)
    db_session.flush()
    publicar = Mock()
    monkeypatch.setattr(tareas.enviar_notificacion, "apply_async", publicar)
    tareas.despachar_pendientes.run()
    publicar.assert_called_once()
    tareas.despachar_pendientes.run()
    publicar.assert_called_once()


@pytest.mark.parametrize(
    "operador,valor,esperado",
    [
        (">", 31, True),
        ("<", 29, True),
        (">=", 30, True),
        ("<=", 30, True),
        ("=", 30, True),
        ("=", 31, False),
        (">", float("nan"), False),
    ],
)
def test_operadores(operador, valor, esperado):
    assert cumple_condicion(valor, operador, 30) == esperado


def test_plantilla_html_escapa_contenido_y_texto_se_conserva():
    asunto, texto, html = renderizar(
        "generica", {"titulo": "A&B", "mensaje": '<script>alert("x")</script>'}
    )
    assert asunto == "A&B" and "<script>" in texto
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_renderizado_no_depende_del_directorio_de_trabajo(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert "Hola" in renderizar("generica", {"titulo": "Hola", "mensaje": "Texto"})[0]


def test_bienvenida_cifra_credencial_y_la_elimina_tras_el_envio(db_session, caso, monkeypatch):
    from app.services.correo_ses import cifrar_password_temporal

    temporal = "TemporalDePrueba2026"
    cifrada = cifrar_password_temporal(temporal)
    assert temporal not in cifrada
    assert (
        temporal in renderizar("bienvenida", {"nombre": "Usuario", "password_cifrada": cifrada})[1]
    )
    tareas.enviar_correo_bienvenida.run(caso["usuario"].crr, "Usuario", temporal)
    n = db_session.query(NotificacionEnviada).one()
    assert temporal not in str(n.contexto)
    monkeypatch.setattr(tareas, "enviar_ses", Mock(return_value="bienvenida-14"))
    tareas.enviar_notificacion.run(n.id_ntfccn)
    assert n.contexto == {"nombre": "Usuario"}


def test_ses_sin_remitente_falla_explicito(monkeypatch):
    monkeypatch.delenv("SES_FROM_EMAIL", raising=False)
    with pytest.raises(ValueError, match="SES_FROM_EMAIL"):
        enviar_ses("generica", {}, "uno@example.com", 14)


def test_entorno_local_rechaza_cualquier_destinatario_distinto(monkeypatch):
    from app.services.correo_ses import DestinatarioPruebaNoPermitido

    monkeypatch.setenv("SES_TEST_RECIPIENT", "desarrollo@ceneris.com")
    with patch("app.services.correo_ses.boto3.client") as cliente:
        with pytest.raises(DestinatarioPruebaNoPermitido):
            enviar_ses("generica", {}, "otro@example.com", 14)
        cliente.assert_not_called()


def test_ses_v2_contenido_destinatario_y_correlacion(monkeypatch):
    monkeypatch.setenv("SES_FROM_EMAIL", "alarmas@example.com")
    monkeypatch.setenv("SES_TEST_RECIPIENT", "uno@example.com")
    monkeypatch.setenv("SES_CONFIGURATION_SET", "pangea")
    ses = boto3.client(
        "sesv2",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    stub = Stubber(ses)
    with patch("app.services.correo_ses.boto3.client", return_value=ses):

        def comprobar(params, **kwargs):
            assert params["Destination"]["ToAddresses"] == ["uno@example.com"]
            assert params["Content"]["Simple"]["Body"]["Html"]["Charset"] == "UTF-8"
            assert params["ConfigurationSetName"] == "pangea"
            assert params["EmailTags"] == [{"Name": "pangea_notificacion", "Value": "14"}]

        ses.meta.events.register("before-parameter-build.sesv2.SendEmail", comprobar)
        stub.add_response("send_email", {"MessageId": "ses-14"})
        with stub:
            assert (
                enviar_ses(
                    "generica", {"titulo": "Alerta", "mensaje": "Texto"}, "uno@example.com", 14
                )
                == "ses-14"
            )


@pytest.mark.parametrize(
    "error,esperado",
    [
        (temporal(), True),
        (EndpointConnectionError(endpoint_url="https://email.us-east-1.amazonaws.com"), True),
        (ClientError({"Error": {"Code": "AccessDeniedException"}}, "SendEmail"), False),
        (ValueError("configuración"), False),
    ],
)
def test_clasificacion_errores(error, esperado):
    assert error_transitorio(error) == esperado
