"""
Red de seguridad de HU09/HT-05: reencolar_pendientes_atascados.

sondear_conexiones_ftp solo encola procesar_archivo_dat en el instante en
que crea la fila de archv_ingst (ver app/tasks/ingesta.py); un archivo que
entra a 'Pendiente' por otra vía (carga de datos de prueba, worker caído
entre el INSERT y el .delay(), mensaje de Celery perdido) queda "En
espera" para siempre sin este job. Pasó de verdad el 2026-08-24 con 409
archivos atascados.
"""

import datetime as dt

import pytest

from app.models import ArchivoIngesta, ConexionFTP
from app.tasks.ingesta import MINUTOS_PENDIENTE_ATASCADO, reencolar_pendientes_atascados


def crear_conexion(db_session, sede, nombre="Datalogger de prueba"):
    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr=nombre,
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


def crear_archivo(db_session, conexion, nombre, estd="Pendiente", fch_dtccn=None):
    archivo = ArchivoIngesta(
        id_cnxn=conexion.id_cnxn,
        nmbr_archv=nombre,
        estd=estd,
        **({"fch_dtccn": fch_dtccn} if fch_dtccn else {}),
    )
    db_session.add(archivo)
    db_session.flush()
    return archivo


@pytest.fixture()
def sesion_de_prueba(monkeypatch, db_session):
    """La task abre su propia sesión con SessionLocal() y la cierra al
    terminar (db.close()); acá se inyecta la sesión transaccional del test
    y se neutraliza el close() para no cortar el rollback del fixture
    db_session (ver conftest.py)."""
    monkeypatch.setattr("app.tasks.ingesta.SessionLocal", lambda: db_session)
    cierre_original = db_session.close
    monkeypatch.setattr(db_session, "close", lambda: None)
    yield db_session
    monkeypatch.setattr(db_session, "close", cierre_original)


@pytest.fixture()
def encolados(monkeypatch):
    """Spy sobre procesar_archivo_dat.delay: lo que corresponde verificar
    acá es que la task identifica y reencola los ids correctos, no que el
    pipeline de ingesta corra de punta a punta (eso lo cubren otros
    tests)."""
    llamadas = []
    monkeypatch.setattr(
        "app.tasks.ingesta.procesar_archivo_dat.delay",
        lambda id_archv: llamadas.append(id_archv),
    )
    return llamadas


def test_reencola_pendiente_mas_viejo_que_el_umbral(
    sesion_de_prueba, encolados, fabrica
):
    sede = fabrica.sede()
    conexion = crear_conexion(sesion_de_prueba, sede)
    viejo = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        minutes=MINUTOS_PENDIENTE_ATASCADO + 5
    )
    archivo = crear_archivo(sesion_de_prueba, conexion, "H_atascado.dat", fch_dtccn=viejo)

    resultado = reencolar_pendientes_atascados()

    assert resultado == {"reencolados": 1}
    assert encolados == [archivo.id_archv]


def test_no_reencola_pendiente_reciente(sesion_de_prueba, encolados, fabrica):
    """Un archivo recién detectado por el sondeo normal también pasa un
    instante por 'Pendiente' antes de que el worker lo tome: sin el
    margen de MINUTOS_PENDIENTE_ATASCADO, este job competiría por
    re-encolar algo que ya tiene una tarea Celery en camino."""
    sede = fabrica.sede()
    conexion = crear_conexion(sesion_de_prueba, sede)
    crear_archivo(sesion_de_prueba, conexion, "H_recien_llegado.dat")

    resultado = reencolar_pendientes_atascados()

    assert resultado == {"reencolados": 0}
    assert encolados == []


def test_no_reencola_archivos_procesando_o_ya_resueltos(
    sesion_de_prueba, encolados, fabrica
):
    sede = fabrica.sede()
    conexion = crear_conexion(sesion_de_prueba, sede)
    viejo = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    crear_archivo(sesion_de_prueba, conexion, "H_procesando.dat", estd="Procesando", fch_dtccn=viejo)
    crear_archivo(sesion_de_prueba, conexion, "H_exitoso.dat", estd="Exitoso", fch_dtccn=viejo)
    crear_archivo(sesion_de_prueba, conexion, "H_fallido.dat", estd="Fallido", fch_dtccn=viejo)

    resultado = reencolar_pendientes_atascados()

    assert resultado == {"reencolados": 0}
    assert encolados == []


def test_reencola_varios_en_orden_de_deteccion(sesion_de_prueba, encolados, fabrica):
    sede = fabrica.sede()
    conexion = crear_conexion(sesion_de_prueba, sede)
    ahora = dt.datetime.now(dt.timezone.utc)
    margen = dt.timedelta(minutes=MINUTOS_PENDIENTE_ATASCADO + 5)

    mas_nuevo = crear_archivo(
        sesion_de_prueba, conexion, "H_b.dat", fch_dtccn=ahora - margen
    )
    mas_viejo = crear_archivo(
        sesion_de_prueba, conexion, "H_a.dat", fch_dtccn=ahora - margen - dt.timedelta(minutes=10)
    )

    resultado = reencolar_pendientes_atascados()

    assert resultado == {"reencolados": 2}
    assert encolados == [mas_viejo.id_archv, mas_nuevo.id_archv]
