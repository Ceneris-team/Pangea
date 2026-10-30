"""
QA - HU18 / PP-190: el polling FTP se detiene al desactivar un dispositivo,
probado contra un servidor FTP REAL local (pyftpdlib), sin simular
listar_archivos_dat: el sondeo de Celery se conecta, lista y descarga de verdad.

    TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/pangea_test \
    venv/Scripts/python.exe -m pytest qa/03_Evidencias/HU18/test_integracion_ftp_real.py \
        --html=qa/03_Evidencias/HU18/pytest_hu18_ftp_real.html --self-contained-html
"""

import secrets
import threading
from unittest.mock import patch

import pytest
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import ThreadedFTPServer

from app.models import ArchivoIngesta, ConexionFTP
from app.security.ftp_crypto import encrypt_credential
from app.tasks import ingesta as tareas_ingesta
from tests.conftest import _engine, db_session, fabrica  # noqa: F401
from tests.routers.test_dispositivos import (  # noqa: F401
    client,
    preparar_dispositivo,
    tecnico_editor,
)

from test_hu18_qa import con_suscripcion_vigente


@pytest.fixture()
def ftp_local(tmp_path):
    """Servidor FTP efímero con un usuario de prueba y credenciales aleatorias."""
    usuario, clave = "qa_hu18", secrets.token_hex(8)
    autorizador = DummyAuthorizer()
    autorizador.add_user(usuario, clave, str(tmp_path), perm="elradfmw")
    manejador = type("H", (FTPHandler,), {"authorizer": autorizador})
    servidor = ThreadedFTPServer(("127.0.0.1", 0), manejador)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        yield {"dir": tmp_path, "usuario": usuario, "clave": clave, "puerto": servidor.address[1]}
    finally:
        servidor.close_all()


def sondeo_real(db_session):
    """Sondeo de Celery real (conecta al FTP de verdad); solo se evita el
    broker encolando y se reinicia ultm_snd para no esperar frcnc_mnts."""
    with (
        patch.object(tareas_ingesta, "SessionLocal", return_value=db_session),
        patch.object(tareas_ingesta.procesar_archivo_dat, "delay"),
        patch.object(db_session, "close"),
    ):
        return tareas_ingesta.sondear_conexiones_ftp()


def test_cp_ftp_real_desactivar_detiene_el_polling(client, db_session, tecnico_editor, ftp_local):
    sede, _ = tecnico_editor
    con_suscripcion_vigente(db_session, sede)
    d = preparar_dispositivo(db_session, sede)

    conexion = db_session.get(ConexionFTP, d.id_cnxn)
    conexion.hst, conexion.prt = "127.0.0.1", ftp_local["puerto"]
    conexion.usr_ftp = ftp_local["usuario"]
    conexion.crdncl_cfrd = encrypt_credential(ftp_local["clave"])
    conexion.rt_rmt = "/"
    db_session.flush()

    # 1) Activo: el archivo nuevo se detecta (conexión FTP verdadera).
    (ftp_local["dir"] / "H_antes.dat").write_text("x")
    assert sondeo_real(db_session)["encolados"] == 1

    # 2) Se desactiva el dispositivo por la API.
    assert client.delete(f"/dispositivos/{d.id_dspstv}").status_code == 200

    # 3) Llega otro archivo y vence la frecuencia de sondeo.
    (ftp_local["dir"] / "H_despues.dat").write_text("x")
    conexion.ultm_snd = None
    db_session.flush()
    resultado = sondeo_real(db_session)

    nombres = {a.nmbr_archv for a in db_session.query(ArchivoIngesta).filter_by(id_cnxn=d.id_cnxn)}
    assert "H_despues.dat" not in nombres, "se siguió ingiriendo del dispositivo desactivado"
    assert resultado["encolados"] == 0
