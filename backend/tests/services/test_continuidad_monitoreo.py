"""Reglas acordadas: captura continua, alarmas del proyecto y calidad de origen."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.ingesta.ftp_receptor import ArchivoRemoto
from app.models import Suscripcion, Telemetria
from app.models.alarma import (
    Alarma,
    CondicionAlarma,
    DestinatarioAlarma,
    EstadoAlarma,
    NotificacionEnviada,
)
from app.models.archivo_ingesta import ArchivoIngesta
from app.services.ingesta.originales import (
    conservar_original,
    dispositivo_del_archivo,
    leer_original,
)
from app.services.ingesta.persistencia import DispositivoNoResueltoError, guardar_lecturas
from app.services.ingesta.validador import LecturaValidada, _parsear_numero
from app.services.mapa.semaforo import semaforos_por_ubicacion
from app.services.monitoreo import correos_habilitados, mantener_monitoreo
from app.services.notificaciones import evaluar_alarmas
from app.tasks import ingesta
from app.tasks import notificaciones as tareas_correo
from tests.routers.test_alarmas import (
    crear_conexion,
    crear_dispositivo,
    crear_parametro,
    crear_ubicacion,
    dar_suscripcion_vigente,
)


@pytest.fixture()
def caso(db_session, fabrica, monkeypatch):
    monkeypatch.setenv("PLAN_LIMITS_REQUIRE_SUBSCRIPTION", "true")
    monkeypatch.setenv("MONITOREO_SIN_DATOS_MINUTOS", "60")
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "")
    sede = fabrica.sede()
    dar_suscripcion_vigente(db_session, sede)
    usuario = fabrica.usuario()
    proyecto = crear_ubicacion(db_session, sede)
    conexion = crear_conexion(db_session, sede)
    equipo = crear_dispositivo(db_session, proyecto, conexion)
    parametro = crear_parametro(db_session, "temperatura", "°C")
    alarma = Alarma(
        id_usr=usuario.id_usr,
        id_sd=sede.id_sd,
        id_ubccn=proyecto.id_ubccn,
        id_prmtr=parametro.id_prmtr,
        nmbr="Temperatura del proyecto",
    )
    db_session.add(alarma)
    db_session.flush()
    db_session.add_all(
        [
            CondicionAlarma(id_alrm=alarma.id_alrm, oprdr=">", vlr_umbrl=20),
            DestinatarioAlarma(id_alrm=alarma.id_alrm, cnl="email", crr="operador@example.com"),
        ]
    )
    db_session.flush()
    contrato = db_session.query(Suscripcion).filter_by(id_clnt=sede.id_clnt).one()
    contrato.fch_inc -= timedelta(days=30)
    db_session.flush()
    return dict(
        sede=sede,
        proyecto=proyecto,
        conexion=conexion,
        equipo=equipo,
        parametro=parametro,
        alarma=alarma,
        contrato=contrato,
    )


def medir(db, caso, valor=25, fecha=None):
    lectura = LecturaValidada(
        fecha or datetime.now(timezone.utc),
        caso["conexion"].id_cnxn,
        caso["parametro"].nmbr,
        valor,
        1,
    )
    evaluar_alarmas(db, lecturas=[lectura], dispositivo=caso["equipo"], id_sd=caso["sede"].id_sd)
    db.flush()
    return lectura


def test_vencimiento_pausa_correos_sin_perder_estado(db_session, caso):
    caso["contrato"].fch_vncmnt = datetime.now(timezone.utc).date() - timedelta(days=1)
    db_session.flush()
    medir(db_session, caso)
    assert not correos_habilitados(db_session, caso["sede"].id_sd)
    estado = db_session.query(EstadoAlarma).one()
    assert estado.en_alarma and estado.resumen_pendiente
    assert db_session.query(NotificacionEnviada).count() == 0


def test_reanudar_envia_un_resumen_y_no_repite_por_cada_lectura(db_session, caso):
    caso["contrato"].estd = "Suspendida"
    db_session.flush()
    for i in range(3):
        medir(db_session, caso, fecha=datetime.now(timezone.utc) + timedelta(seconds=i))
    caso["contrato"].estd = "Activa"
    db_session.flush()
    mantener_monitoreo(db_session)
    db_session.flush()
    mantener_monitoreo(db_session)
    db_session.flush()
    avisos = db_session.query(NotificacionEnviada).all()
    assert len(avisos) == 1
    assert avisos[0].tipo == "resumen_alarma_reanudada"


def test_si_se_normalizo_durante_la_pausa_no_envia_alarma_antigua(db_session, caso):
    caso["contrato"].estd = "Suspendida"
    db_session.flush()
    ahora = datetime.now(timezone.utc)
    medir(db_session, caso, 25, ahora)
    medir(db_session, caso, 10, ahora + timedelta(seconds=1))
    caso["contrato"].estd = "Activa"
    db_session.flush()
    mantener_monitoreo(db_session)
    assert db_session.query(NotificacionEnviada).count() == 0


def test_revalida_vigencia_de_un_correo_que_ya_estaba_encolado(db_session, caso, monkeypatch):
    medir(db_session, caso)
    aviso = db_session.query(NotificacionEnviada).one()
    caso["contrato"].estd = "Suspendida"
    db_session.flush()
    from contextlib import contextmanager

    @contextmanager
    def sesion():
        yield db_session

    monkeypatch.setattr(tareas_correo, "SessionLocal", sesion)
    with patch.object(tareas_correo, "enviar_ses") as enviar:
        resultado = tareas_correo.enviar_notificacion(aviso.id_ntfccn)
    assert resultado["estado"] == "Omitido"
    enviar.assert_not_called()


def test_una_hora_sin_datos_genera_un_solo_aviso_hasta_recuperar(db_session, caso):
    ahora = datetime.now(timezone.utc)
    caso["equipo"].ultima_recepcion = ahora - timedelta(minutes=59)
    db_session.flush()
    mantener_monitoreo(db_session, ahora)
    db_session.flush()
    assert caso["equipo"].sin_datos_desde is None
    mantener_monitoreo(db_session, ahora + timedelta(minutes=1))
    db_session.flush()
    mantener_monitoreo(db_session, ahora + timedelta(minutes=2))
    db_session.flush()
    assert (
        db_session.query(NotificacionEnviada).filter_by(tipo="dispositivo_sin_datos").count() == 1
    )
    caso["equipo"].ultima_recepcion = ahora + timedelta(minutes=3)
    db_session.flush()
    mantener_monitoreo(db_session, ahora + timedelta(minutes=3))
    assert caso["equipo"].sin_datos_desde is None


def test_monitor_detenido_no_genera_aviso_de_falta_de_datos(db_session, caso):
    caso["proyecto"].monitoreo_activo = False
    caso["equipo"].ultima_recepcion = datetime.now(timezone.utc) - timedelta(hours=3)
    db_session.flush()
    mantener_monitoreo(db_session)
    assert db_session.query(NotificacionEnviada).count() == 0


def test_archivado_y_sin_suscripcion_sigue_recogiendo_pero_detener_lo_frena(db_session, caso):
    caso["proyecto"].estd = "Inactiva"
    caso["contrato"].estd = "Suspendida"
    db_session.flush()
    with (
        patch.object(ingesta, "SessionLocal", return_value=db_session),
        patch.object(db_session, "close"),
        patch.object(ingesta, "listar_archivos_dat", return_value=["H_automatico.dat"]),
        patch.object(ingesta.procesar_archivo_dat, "delay"),
    ):
        assert ingesta.sondear_conexiones_ftp()["encolados"] == 1
        archivo = db_session.query(ArchivoIngesta).one()
        assert archivo.id_dspstv == caso["equipo"].id_dspstv
        caso["proyecto"].monitoreo_activo = False
        caso["conexion"].ultm_snd = None
        db_session.flush()
        assert ingesta.sondear_conexiones_ftp()["conexiones_revisadas"] == 0


def test_reemplazo_no_reasigna_archivos_pendientes_al_equipo_nuevo(db_session, caso):
    original = ArchivoIngesta(
        id_cnxn=caso["conexion"].id_cnxn,
        id_dspstv=caso["equipo"].id_dspstv,
        nmbr_archv="H_viejo.dat",
    )
    db_session.add(original)
    caso["equipo"].estd = "Inactivo"
    db_session.flush()
    crear_dispositivo(db_session, caso["proyecto"], caso["conexion"], "Reemplazo")
    assert dispositivo_del_archivo(db_session, original).id_dspstv == caso["equipo"].id_dspstv
    ambiguo = ArchivoIngesta(id_cnxn=caso["conexion"].id_cnxn, nmbr_archv="H_ambiguo.dat")
    with pytest.raises(DispositivoNoResueltoError):
        dispositivo_del_archivo(db_session, ambiguo)


def test_bd_impide_dos_equipos_activos_por_ftp(db_session, caso):
    with pytest.raises(IntegrityError), db_session.begin_nested():
        crear_dispositivo(db_session, caso["proyecto"], caso["conexion"], "Duplicado")


def test_original_se_conserva_sin_cambios_incluso_si_esta_corrupto(db_session, caso):
    archivo = ArchivoIngesta(id_cnxn=caso["conexion"].id_cnxn, nmbr_archv="H_corrupto.dat")
    db_session.add(archivo)
    db_session.flush()
    datos = b"\xff\x00archivo corrupto\r\n"
    conservar_original(archivo, datos)
    db_session.flush()
    conservar_original(archivo, b"otra version")
    assert leer_original(archivo) == datos


@pytest.mark.parametrize("valor", ["NaN", "Inf", "-Infinity", "error"])
def test_datos_invalidos_no_se_convierten_en_promedios(valor):
    numero, error = _parsear_numero(valor)
    assert numero is None and error


def test_mapa_utiliza_umbral_del_proyecto_y_no_un_valor_fijo(db_session, caso):
    archivo = ArchivoIngesta(id_cnxn=caso["conexion"].id_cnxn, nmbr_archv="H_mapa.dat")
    db_session.add(archivo)
    db_session.flush()
    db_session.add(
        Telemetria(
            id_dspstv=caso["equipo"].id_dspstv,
            id_prmtr=caso["parametro"].id_prmtr,
            id_sd=caso["sede"].id_sd,
            id_archv=archivo.id_archv,
            fch_hr=datetime.now(timezone.utc),
            vlr=Decimal("25"),
        )
    )
    db_session.flush()
    assert (
        semaforos_por_ubicacion(db_session, [caso["proyecto"].id_ubccn])[caso["proyecto"].id_ubccn]
        == "rojo"
    )
    regla = db_session.query(CondicionAlarma).one()
    regla.vlr_umbrl = 30
    db_session.flush()
    assert (
        semaforos_por_ubicacion(db_session, [caso["proyecto"].id_ubccn])[caso["proyecto"].id_ubccn]
        == "verde"
    )


def test_archivo_acumulativo_no_duplica_mediciones_anteriores(db_session, caso):
    archivo = ArchivoIngesta(id_cnxn=caso["conexion"].id_cnxn, nmbr_archv="H_acumulado.dat")
    db_session.add(archivo)
    db_session.flush()
    fecha = datetime.now(timezone.utc)
    anterior = LecturaValidada(fecha, caso["conexion"].id_cnxn, caso["parametro"].nmbr, 15, 1)
    nueva = LecturaValidada(
        fecha + timedelta(seconds=1), caso["conexion"].id_cnxn, caso["parametro"].nmbr, 16, 2
    )
    guardar_lecturas(db_session, [anterior], caso["equipo"], archivo.id_archv)
    resultado = guardar_lecturas(db_session, [anterior, nueva], caso["equipo"], archivo.id_archv)
    assert resultado.guardadas == 1
    assert db_session.query(Telemetria).filter_by(id_dspstv=caso["equipo"].id_dspstv).count() == 2


def test_detecta_version_nueva_con_el_mismo_nombre(db_session, caso):
    with (
        patch.object(ingesta, "SessionLocal", return_value=db_session),
        patch.object(db_session, "close"),
        patch.object(ingesta, "listar_archivos_dat") as listar,
        patch.object(ingesta.procesar_archivo_dat, "delay"),
    ):
        listar.return_value = [ArchivoRemoto("H_acumulado.dat", "version-1")]
        assert ingesta.sondear_conexiones_ftp()["encolados"] == 1
        caso["conexion"].ultm_snd = None
        db_session.commit()
        listar.return_value = [ArchivoRemoto("H_acumulado.dat", "version-2")]
        assert ingesta.sondear_conexiones_ftp()["encolados"] == 1
        assert db_session.query(ArchivoIngesta).filter_by(nmbr_archv="H_acumulado.dat").count() == 2


def test_ftp_sin_metadatos_compara_contenido_y_reutiliza_el_original(db_session, caso):
    with (
        patch.object(ingesta, "SessionLocal", return_value=db_session),
        patch.object(db_session, "close"),
        patch.object(
            ingesta, "listar_archivos_dat", return_value=[ArchivoRemoto("H_acumulado.dat")]
        ),
        patch.object(ingesta, "descargar_bytes_dat", return_value=b"original") as descargar,
        patch.object(ingesta.procesar_archivo_dat, "delay"),
    ):
        assert ingesta.sondear_conexiones_ftp()["encolados"] == 1
        caso["conexion"].ultm_snd = None
        db_session.commit()
        assert ingesta.sondear_conexiones_ftp()["encolados"] == 0
        assert descargar.call_count == 2
        archivo = db_session.query(ArchivoIngesta).one()
        assert leer_original(archivo) == b"original"


def test_archivar_sin_detener_monitoreo_conserva_el_cupo_del_proyecto(db_session, caso):
    from app.services.limites_plan import consumo_cliente

    caso["proyecto"].estd = "Inactiva"
    db_session.flush()
    assert consumo_cliente(db_session, caso["sede"].id_clnt)["ubicaciones"] == 1
    caso["proyecto"].monitoreo_activo = False
    db_session.flush()
    assert consumo_cliente(db_session, caso["sede"].id_clnt)["ubicaciones"] == 0


def test_corrupcion_interna_no_se_repara_uniendo_digitos():
    contenido = ingesta.normalizar_contenido_dat("Fecha,Nivel\r\n2026-11-23,2\x001\r\n\x00\x00")
    assert "2\x001" in contenido
    assert not contenido.endswith("\x00")
    assert _parsear_numero("2\x001")[1]


def test_texto_corrupto_se_rechaza_sin_descartar_otras_lecturas():
    from app.services.ingesta.estandarizador import LecturaEstandar
    from app.services.ingesta.validador import validar_lecturas

    fecha = datetime.now(timezone.utc) - timedelta(seconds=1)
    lecturas = [
        LecturaEstandar(fecha, 1, "evento", "Puerta\x00abierta", 1),
        LecturaEstandar(fecha, 1, "nivel", "12.5", 2),
    ]
    resultado = validar_lecturas(lecturas, tipos_parametro={"evento": "texto"})
    assert [lectura.valor for lectura in resultado.validas] == [12.5]
    assert len(resultado.errores) == 1
