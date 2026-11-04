"""
HU31 - Historial de reprocesos: tests de app/tasks/ingesta.py::procesar_archivo_dat
y su registro en intnt_prcsmnt (_registrar_intento).

La tabla intnt_prcsmnt ya estaba migrada (HT-13/HU31) pero nunca se
insertaba ni se leía -este archivo cubre justamente eso, ver el docstring
de reintentos_encolados en test_ingesta_cola.py, que ya anticipaba esta
cobertura.

Se ejercita procesar_archivo_dat llamándola DIRECTO (sin .delay()): fuera
de un worker, Celery ejecuta el cuerpo de la task de forma síncrona con
self.request.retries=0, que es exactamente lo que hace falta para probar
el pipeline sin levantar un broker real. Mismo patrón de
patch.object(tareas_ingesta, "SessionLocal", ...) que test_sondeo_ftp.py,
para que la task use la sesión transaccional del test.

El camino a 'Fallido' más simple y determinista es un
DispositivoNoResueltoError (la conexión no tiene ningún Dispositivo
Activo asociado): no requiere mockear FTP ni el parseo de un .dat, y cae
directo en ErrorDatosNoRecuperable -mismo resultado final que un archivo
con dispositivo/mapeo mal configurado en producción-.
"""

import dataclasses
import ftplib
import types
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from app.models import ConexionFTP, Dispositivo, IntentoProcesamiento, Ubicacion
from app.models.archivo_ingesta import ArchivoIngesta
from app.tasks import ingesta as tareas_ingesta

POLIGONO_DUMMY = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}


@pytest.fixture()
def conexion_sin_dispositivo(db_session, fabrica):
    """ConexionFTP activa sin ningún Dispositivo asociado: resolver_dispositivo
    (services/ingesta/persistencia.py) revienta con DispositivoNoResueltoError
    para cualquier archivo que llegue por acá, sin tocar FTP ni parsear nada."""
    sede = fabrica.sede()
    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr="Datalogger sin dispositivo",
        prtcl="FTP",
        hst="127.0.0.1",
        prt=21,
        usr_ftp="usr",
        crdncl_cfrd="cifrado-de-prueba",
        rt_rmt="/data",
        frcnc_mnts=1,
        estd="Activa",
    )
    db_session.add(conexion)
    db_session.flush()
    return conexion


def crear_archivo(db_session, conexion, nombre="H_ejemplo.dat", estd="Pendiente"):
    archivo = ArchivoIngesta(id_cnxn=conexion.id_cnxn, nmbr_archv=nombre, estd=estd)
    db_session.add(archivo)
    db_session.flush()
    return archivo


def procesar(db_session, **kwargs):
    """Corre procesar_archivo_dat contra la sesión transaccional del
    test, sin worker ni broker real (ver docstring del módulo)."""
    with (
        patch.object(tareas_ingesta, "SessionLocal", return_value=db_session),
        patch.object(db_session, "close"),
    ):
        return tareas_ingesta.procesar_archivo_dat(**kwargs)


def intentos_de(db_session, id_archv):
    return (
        db_session.query(IntentoProcesamiento)
        .filter(IntentoProcesamiento.id_archv == id_archv)
        .order_by(IntentoProcesamiento.fch_intnt.asc(), IntentoProcesamiento.id_intnt.asc())
        .all()
    )


class TestRegistroDeIntentoAutomatico:
    def test_procesamiento_automatico_genera_una_fila_con_id_usr_null(
        self, db_session, conexion_sin_dispositivo
    ):
        """El primer procesamiento -detectado por sondear_conexiones_ftp,
        SIN pasar por los endpoints de reintentar- también es un intento:
        se llama sin id_usr_reintento, igual que hace sondear_conexiones_ftp."""
        archivo = crear_archivo(db_session, conexion_sin_dispositivo)

        procesar(db_session, id_archv=archivo.id_archv)

        intentos = intentos_de(db_session, archivo.id_archv)
        assert len(intentos) == 1
        assert intentos[0].id_usr is None
        assert intentos[0].rsltd == "Fallido"
        assert intentos[0].mnsj_errr is not None
        assert intentos[0].fch_intnt is not None

    def test_procesamiento_automatico_exitoso_tambien_registra_el_intento(
        self, db_session, fabrica, monkeypatch
    ):
        """Mismo criterio para el camino de ÉXITO -no solo el de
        Fallido-: _registrar_intento se llama en los TRES puntos de
        resolución final de procesar_archivo_dat. Se mockea
        interpretar_y_guardar (el tramo de parseo/descarga real, ya
        cubierto por sus propios tests) para llegar al "Exitoso" sin
        depender de un .dat ni de FTP real."""
        sede = fabrica.sede()
        conexion = ConexionFTP(
            id_sd=sede.id_sd,
            nmbr="Datalogger de prueba",
            prtcl="FTP",
            hst="127.0.0.1",
            prt=21,
            usr_ftp="usr",
            crdncl_cfrd="cifrado-de-prueba",
            rt_rmt="/data",
            frcnc_mnts=1,
            estd="Activa",
        )
        db_session.add(conexion)
        db_session.flush()

        ubicacion = Ubicacion(
            id_sd=sede.id_sd, nmbr="Ubicacion de prueba", lttd=0, lngtd=0, plgn_gjsn=POLIGONO_DUMMY
        )
        db_session.add(ubicacion)
        db_session.flush()
        dispositivo = Dispositivo(
            id_ubccn=ubicacion.id_ubccn,
            id_cnxn=conexion.id_cnxn,
            nmbr="CR1000-01",
            mrc="Campbell",
            lttd=0,
            lngtd=0,
            estd="Activo",
        )
        db_session.add(dispositivo)
        db_session.flush()

        archivo = crear_archivo(db_session, conexion)

        ResultadoValidacionFalso = dataclasses.make_dataclass(
            "ResultadoValidacionFalso", [("validas", list), ("errores", list)]
        )
        ResultadoPersistenciaFalso = dataclasses.make_dataclass(
            "ResultadoPersistenciaFalso",
            [
                ("guardadas", int),
                ("omitidas_sin_valor", int),
                ("omitidas_parametro_desconocido", list),
                ("ultimos_por_parametro", dict),
                ("id_ubccn", int),
                ("id_sd", int),
            ],
        )

        formato_falso = type(
            "FormatoFalso",
            (),
            {"id_mp": 1, "tipo_trama": "H", "config": None, "delimitador_decimal": "."},
        )()
        monkeypatch.setattr(tareas_ingesta, "resolver_formato", lambda *a, **k: formato_falso)
        monkeypatch.setattr(tareas_ingesta, "descargar_archivo_dat", lambda *a, **k: "contenido")
        monkeypatch.setattr(
            tareas_ingesta,
            "interpretar_y_guardar",
            lambda *a, **k: (
                ResultadoValidacionFalso(validas=[], errores=[]),
                ResultadoPersistenciaFalso(
                    guardadas=3,
                    omitidas_sin_valor=0,
                    omitidas_parametro_desconocido=[],
                    ultimos_por_parametro={},
                    id_ubccn=ubicacion.id_ubccn,
                    id_sd=sede.id_sd,
                ),
            ),
        )

        procesar(db_session, id_archv=archivo.id_archv)

        db_session.refresh(archivo)
        assert archivo.estd == "Exitoso"
        intentos = intentos_de(db_session, archivo.id_archv)
        assert len(intentos) == 1
        assert intentos[0].id_usr is None
        assert intentos[0].rsltd == "Exitoso"
        assert intentos[0].mnsj_errr is None


class TestHistorialEntreReintentosMultiples:
    def test_reprocesar_dos_veces_deja_dos_filas_no_una_pisando_a_la_otra(
        self, db_session, conexion_sin_dispositivo, fabrica
    ):
        """El caso central de HU31: reprocesar un archivo Fallido dos
        veces seguidas -mismo id_archv ambas veces, como hacen
        reintentar_archivo_ingesta/reintentar_fallidos_ingesta al volver
        a encolar el mismo id- tiene que dejar DOS filas en
        intnt_prcsmnt, cada una con su propio id_usr, no una fila
        actualizada/sobrescrita."""
        archivo = crear_archivo(db_session, conexion_sin_dispositivo, estd="Fallido")
        usuario_1 = fabrica.usuario()
        usuario_2 = fabrica.usuario()

        procesar(db_session, id_archv=archivo.id_archv, id_usr_reintento=usuario_1.id_usr)
        procesar(db_session, id_archv=archivo.id_archv, id_usr_reintento=usuario_2.id_usr)

        intentos = intentos_de(db_session, archivo.id_archv)
        assert len(intentos) == 2
        assert [i.id_usr for i in intentos] == [usuario_1.id_usr, usuario_2.id_usr]
        assert all(i.rsltd == "Fallido" for i in intentos)
        # Cada intento con su propio timestamp -no es la misma fila
        # reescrita, son dos filas distintas con id_intnt distinto-.
        assert intentos[0].id_intnt != intentos[1].id_intnt

    def test_reprocesar_tres_veces_incluyendo_el_automatico_deja_tres_filas(
        self, db_session, conexion_sin_dispositivo, fabrica
    ):
        """Mezcla el caso automático (id_usr=None) con dos manuales, en
        el orden real: detección automática primero, reintentos manuales
        después."""
        archivo = crear_archivo(db_session, conexion_sin_dispositivo)
        usuario = fabrica.usuario()

        procesar(db_session, id_archv=archivo.id_archv)  # automático
        procesar(db_session, id_archv=archivo.id_archv, id_usr_reintento=usuario.id_usr)  # manual
        procesar(db_session, id_archv=archivo.id_archv, id_usr_reintento=usuario.id_usr)  # manual

        intentos = intentos_de(db_session, archivo.id_archv)
        assert len(intentos) == 3
        assert [i.id_usr for i in intentos] == [None, usuario.id_usr, usuario.id_usr]

    def test_intentos_de_archivos_distintos_no_se_mezclan(
        self, db_session, conexion_sin_dispositivo, fabrica
    ):
        archivo_a = crear_archivo(db_session, conexion_sin_dispositivo, nombre="H_a.dat")
        archivo_b = crear_archivo(db_session, conexion_sin_dispositivo, nombre="H_b.dat")
        usuario_1 = fabrica.usuario()
        usuario_2 = fabrica.usuario()
        usuario_3 = fabrica.usuario()

        procesar(db_session, id_archv=archivo_a.id_archv, id_usr_reintento=usuario_1.id_usr)
        procesar(db_session, id_archv=archivo_b.id_archv, id_usr_reintento=usuario_2.id_usr)
        procesar(db_session, id_archv=archivo_a.id_archv, id_usr_reintento=usuario_3.id_usr)

        intentos_a = intentos_de(db_session, archivo_a.id_archv)
        intentos_b = intentos_de(db_session, archivo_b.id_archv)
        assert [i.id_usr for i in intentos_a] == [usuario_1.id_usr, usuario_3.id_usr]
        assert [i.id_usr for i in intentos_b] == [usuario_2.id_usr]


class TestNoRegistraIntentosTransitoriosSinTerminar:
    def test_error_transitorio_con_reintentos_disponibles_no_registra_intento(
        self, db_session, conexion_sin_dispositivo, monkeypatch
    ):
        """Un error de red (ERRORES_TRANSITORIOS) con reintentos
        disponibles NO es un intento terminado -Celery lo va a reintentar
        solo (autoretry_for)-, así que no debe dejar fila en
        intnt_prcsmnt. Se fuerza sondeando una excepción transitoria
        DESPUÉS de resolver el dispositivo -por eso esta vez la conexión
        SÍ necesita un Dispositivo, y se fuerza el fallo en
        descargar_archivo_dat, que es donde de verdad puede ocurrir un
        error de FTP transitorio en producción."""
        ubicacion = Ubicacion(
            id_sd=conexion_sin_dispositivo.id_sd,
            nmbr="Ubicacion de prueba",
            lttd=0,
            lngtd=0,
            plgn_gjsn=POLIGONO_DUMMY,
        )
        db_session.add(ubicacion)
        db_session.flush()
        dispositivo = Dispositivo(
            id_ubccn=ubicacion.id_ubccn,
            id_cnxn=conexion_sin_dispositivo.id_cnxn,
            nmbr="CR1000-01",
            mrc="Campbell",
            lttd=0,
            lngtd=0,
            estd="Activo",
        )
        db_session.add(dispositivo)
        db_session.flush()

        archivo = crear_archivo(db_session, conexion_sin_dispositivo)

        # resolver_formato también reventaría (no hay mp_frmt cargado)
        # antes de llegar a la descarga; se lo deja pasar devolviendo un
        # objeto mínimo para que el flujo llegue hasta
        # descargar_archivo_dat, que es la pieza bajo prueba acá.
        formato_falso = type(
            "FormatoFalso",
            (),
            {"id_mp": 1, "tipo_trama": "H", "config": None, "delimitador_decimal": "."},
        )()
        monkeypatch.setattr(tareas_ingesta, "resolver_formato", lambda *a, **k: formato_falso)
        monkeypatch.setattr(
            tareas_ingesta,
            "descargar_archivo_dat",
            lambda *a, **k: (_ for _ in ()).throw(ftplib.error_temp("425 timeout")),
        )

        # self.request.retries=0 y max_retries=5 (default de la task):
        # todavía quedan reintentos, así que NO se marca Fallido ni se
        # registra el intento -Celery reintentaría solo en producción.
        with pytest.raises(ftplib.error_temp):
            procesar(db_session, id_archv=archivo.id_archv)

        assert intentos_de(db_session, archivo.id_archv) == []


CONTENIDO_DAT = "TOA5,CR1000,datos\n2026-01-01 00:00:00,1,2.5\n"


@pytest.fixture()
def entorno_exitoso(db_session, fabrica, monkeypatch):
    """Conexión con dispositivo y pipeline (formato/descarga/persistencia)
    mockeado para que procesar_archivo_dat llegue a 'Exitoso' sin FTP ni un
    .dat real. Aísla el archivado del .dat crudo (HT-06 CA3)."""
    sede = fabrica.sede()
    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr="Datalogger con dispositivo",
        prtcl="FTP",
        hst="127.0.0.1",
        prt=21,
        usr_ftp="usr",
        crdncl_cfrd="cifrado-de-prueba",
        rt_rmt="/data",
        frcnc_mnts=1,
        estd="Activa",
    )
    db_session.add(conexion)
    db_session.flush()
    ubicacion = Ubicacion(
        id_sd=sede.id_sd, nmbr="Ubicacion de prueba", lttd=0, lngtd=0, plgn_gjsn=POLIGONO_DUMMY
    )
    db_session.add(ubicacion)
    db_session.flush()
    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn,
        id_cnxn=conexion.id_cnxn,
        nmbr="CR1000-01",
        mrc="Campbell",
        lttd=0,
        lngtd=0,
        estd="Activo",
    )
    db_session.add(dispositivo)
    db_session.flush()

    formato_falso = type(
        "FormatoFalso",
        (),
        {"id_mp": 1, "tipo_trama": "H", "config": None, "delimitador_decimal": "."},
    )()
    monkeypatch.setattr(tareas_ingesta, "resolver_formato", lambda *a, **k: formato_falso)
    monkeypatch.setattr(tareas_ingesta, "descargar_archivo_dat", lambda *a, **k: CONTENIDO_DAT)

    ResultadoValidacionFalso = dataclasses.make_dataclass(
        "ResultadoValidacionFalso", [("validas", list), ("errores", list)]
    )
    ResultadoPersistenciaFalso = dataclasses.make_dataclass(
        "ResultadoPersistenciaFalso",
        [
            ("guardadas", int),
            ("omitidas_sin_valor", int),
            ("omitidas_parametro_desconocido", list),
            ("ultimos_por_parametro", dict),
            ("id_ubccn", int),
            ("id_sd", int),
        ],
    )
    monkeypatch.setattr(
        tareas_ingesta,
        "interpretar_y_guardar",
        lambda *a, **k: (
            ResultadoValidacionFalso(validas=[], errores=[]),
            ResultadoPersistenciaFalso(
                guardadas=3,
                omitidas_sin_valor=0,
                omitidas_parametro_desconocido=[],
                ultimos_por_parametro={},
                id_ubccn=ubicacion.id_ubccn,
                id_sd=sede.id_sd,
            ),
        ),
    )
    return types.SimpleNamespace(conexion=conexion, ubicacion=ubicacion, sede=sede)


class TestArchivadoDatCrudo:
    """HT-06 CA3 (PP-127): el .dat crudo se persiste en Object Storage."""

    def test_sube_el_dat_crudo_cuando_hay_bucket(self, db_session, entorno_exitoso, monkeypatch):
        subidos = []
        monkeypatch.setattr(tareas_ingesta.object_storage, "esta_configurado", lambda: True)
        monkeypatch.setattr(
            tareas_ingesta.object_storage,
            "subir_contenido",
            lambda datos, clave, content_type="application/octet-stream": subidos.append(
                (datos, clave, content_type)
            ),
        )
        archivo = crear_archivo(db_session, entorno_exitoso.conexion)

        procesar(db_session, id_archv=archivo.id_archv)

        db_session.refresh(archivo)
        assert archivo.estd == "Exitoso"
        assert len(subidos) == 1
        datos, clave, content_type = subidos[0]
        assert datos == CONTENIDO_DAT.encode("utf-8")
        assert clave.startswith(f"datos-crudos/cnxn-{entorno_exitoso.conexion.id_cnxn}/")
        assert clave.endswith("/H_ejemplo.dat")
        assert content_type == "text/plain; charset=utf-8"

    def test_no_sube_nada_si_no_hay_bucket(self, db_session, entorno_exitoso, monkeypatch):
        llamadas = []
        monkeypatch.setattr(tareas_ingesta.object_storage, "esta_configurado", lambda: False)
        monkeypatch.setattr(
            tareas_ingesta.object_storage, "subir_contenido", lambda *a, **k: llamadas.append(a)
        )
        archivo = crear_archivo(db_session, entorno_exitoso.conexion)

        procesar(db_session, id_archv=archivo.id_archv)

        db_session.refresh(archivo)
        assert archivo.estd == "Exitoso"
        assert llamadas == []

    def test_fallo_de_subida_es_transitorio_y_no_marca_fallido(
        self, db_session, entorno_exitoso, monkeypatch
    ):
        """Una caída de S3 al archivar el .dat se trata como transitoria: se
        propaga para que Celery reintente (retries<max), sin marcar Fallido ni
        registrar intento, y sin haber tocado telemetría (la subida va ANTES
        del parseo)."""
        monkeypatch.setattr(tareas_ingesta.object_storage, "esta_configurado", lambda: True)

        def falla(*a, **k):
            raise ClientError(
                {"Error": {"Code": "ServiceUnavailable", "Message": "down"}}, "PutObject"
            )

        monkeypatch.setattr(tareas_ingesta.object_storage, "subir_contenido", falla)
        archivo = crear_archivo(db_session, entorno_exitoso.conexion)

        with pytest.raises(ClientError):
            procesar(db_session, id_archv=archivo.id_archv)

        db_session.refresh(archivo)
        assert archivo.estd != "Fallido"
        assert intentos_de(db_session, archivo.id_archv) == []
