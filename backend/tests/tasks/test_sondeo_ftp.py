"""
Sondeo FTP (tasks/ingesta.py::sondear_conexiones_ftp).

Cubre la regresión de la carrera commit/encolado: la tarea Celery se
encolaba con .delay() justo después de un db.flush(), o sea ANTES del
commit. El worker toma el job en milisegundos, no encontraba la fila
("archv_ingst id=N no existe, se descarta el job") y el archivo quedaba
'Pendiente' para siempre, porque el sondeo siguiente ya lo ve como
existente y no lo reencola.
"""

from unittest.mock import patch

import pytest

from app.models import ConexionFTP
from app.models.archivo_ingesta import ArchivoIngesta
from app.tasks import ingesta as tareas_ingesta


@pytest.fixture()
def conexion_activa(db_session, fabrica):
    """Una ConexionFTP Activa que el sondeo deba revisar."""
    sede = fabrica.sede()

    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr="Datalogger Sondeo",
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


def test_encola_solo_despues_de_confirmar_la_fila(db_session, conexion_activa):
    """La regresión: al encolar, la fila TIENE que ser visible en la BD.

    Se simula al worker consultando el id justo en el momento del .delay()
    con una sesión NUEVA -que es lo que hace el worker real-. Si el
    encolado ocurriera antes del commit, esa consulta devolvería None,
    igual que en producción.
    """
    # Se registra el ORDEN de los dos eventos: es justo lo que el bug
    # invertía (encolaba y después confirmaba).
    orden: list[str] = []

    commit_real = db_session.commit

    def commit_espiado():
        commit_real()
        orden.append("commit")

    with (
        patch.object(tareas_ingesta, "SessionLocal", return_value=db_session),
        patch.object(
            tareas_ingesta, "listar_archivos_dat", return_value=["H_2026-01-01_00-00-00.dat"]
        ),
        patch.object(
            tareas_ingesta.procesar_archivo_dat,
            "delay",
            side_effect=lambda id_archv: orden.append("delay"),
        ),
        patch.object(db_session, "commit", side_effect=commit_espiado),
        # db_session no debe cerrarse: el fixture la administra.
        patch.object(db_session, "close"),
    ):
        resultado = tareas_ingesta.sondear_conexiones_ftp()

    assert resultado["encolados"] == 1
    assert "delay" in orden, "no se encoló el archivo nuevo"
    assert orden.index("commit") < orden.index("delay"), (
        f"se encoló ANTES del commit (orden={orden}): el worker consultaría una "
        "fila todavía invisible y el archivo quedaría 'Pendiente' para siempre"
    )


def test_no_reencola_un_archivo_ya_registrado(db_session, conexion_activa):
    """El sondeo salta los nombres ya vistos para esa conexión. Es la otra
    mitad de por qué la carrera era grave: un archivo perdido por ella
    NUNCA vuelve a encolarse."""
    db_session.add(
        ArchivoIngesta(id_cnxn=conexion_activa.id_cnxn, nmbr_archv="H_ya_visto.dat")
    )
    db_session.flush()

    with (
        patch.object(tareas_ingesta, "SessionLocal", return_value=db_session),
        patch.object(tareas_ingesta, "listar_archivos_dat", return_value=["H_ya_visto.dat"]),
        patch.object(tareas_ingesta.procesar_archivo_dat, "delay") as delay,
        patch.object(db_session, "close"),
    ):
        resultado = tareas_ingesta.sondear_conexiones_ftp()

    assert resultado["encolados"] == 0
    delay.assert_not_called()


def test_una_conexion_caida_no_frena_el_resto(db_session, conexion_activa):
    """Un datalogger inalcanzable se loguea y el sondeo sigue con los
    demás; el archivo de la conexión sana igual se encola."""
    otra = ConexionFTP(
        id_sd=conexion_activa.id_sd,
        nmbr="Datalogger Caido",
        prtcl="FTP",
        hst="127.0.0.1",
        prt=21,
        usr_ftp="usr",
        crdncl_cfrd="cifrado-de-prueba",
        rt_rmt="/data",
        frcnc_mnts=1,
        estd="Activa",
    )
    db_session.add(otra)
    db_session.flush()

    def listar(cnxn):
        if cnxn.id_cnxn == otra.id_cnxn:
            raise OSError("Connection refused")
        return ["H_de_la_sana.dat"]

    with (
        patch.object(tareas_ingesta, "SessionLocal", return_value=db_session),
        patch.object(tareas_ingesta, "listar_archivos_dat", side_effect=listar),
        patch.object(tareas_ingesta.procesar_archivo_dat, "delay") as delay,
        patch.object(db_session, "close"),
    ):
        resultado = tareas_ingesta.sondear_conexiones_ftp()

    assert resultado["encolados"] == 1
    assert delay.call_count == 1
