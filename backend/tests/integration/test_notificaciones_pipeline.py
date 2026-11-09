"""PostgreSQL + Redis + proceso Celery reales; SES HTTP local con fallo 429."""

import json
import os
import secrets
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from celery import Celery
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models import (
    Alarma,
    Cliente,
    CondicionAlarma,
    ConexionFTP,
    DestinatarioAlarma,
    Dispositivo,
    EstadoAlarma,
    IntentoNotificacion,
    NotificacionEnviada,
    Parametro,
    Sede,
    Telemetria,
    Ubicacion,
    Usuario,
)
from app.services.ingesta.persistencia import guardar_lecturas
from app.services.ingesta.validador import LecturaValidada
from scripts.aprovisionar_auditoria import aprovisionar
from tests.conftest import TEST_DATABASE_URL
from tests.routers.test_alarmas import (
    crear_conexion,
    crear_dispositivo,
    crear_parametro,
    crear_ubicacion,
)


def test_pipeline_real_con_reintento_y_dos_destinatarios(tmp_path, monkeypatch):
    identificador = uuid.uuid4().hex
    recibidos = []

    class SESLocal(BaseHTTPRequestHandler):
        def do_POST(self):
            contenido = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            recibidos.append(contenido)
            primero = len(recibidos) == 1
            self.send_response(429 if primero else 200)
            self.send_header("Content-Type", "application/json")
            if primero:
                self.send_header("x-amzn-errortype", "TooManyRequestsException")
            self.end_headers()
            respuesta = (
                {"message": "Temporary throttling"}
                if primero
                else {"MessageId": f"ses-local-{len(recibidos)}"}
            )
            self.wfile.write(json.dumps(respuesta).encode())

        def log_message(self, *_):
            pass

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), SESLocal)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    backend = Path(__file__).resolve().parents[2]
    cola = f"ht14-{identificador}"
    redis_url = urlsplit(os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/2"))
    broker = redis_url._replace(path="/14").geturl()
    resultado = redis_url._replace(path="/15").geturl()
    # Celery prioriza estas variables sobre los argumentos del constructor.
    monkeypatch.setenv("CELERY_BROKER_URL", broker)
    monkeypatch.setenv("CELERY_RESULT_BACKEND", resultado)
    modulo = tmp_path / "ht14_worker.py"
    modulo.write_text(
        "import sys, os\n"
        f"sys.path.insert(0, {str(backend)!r})\n"
        "from app.services import correo_ses\n"
        "from app.core.celery_app import celery_app\n"
        "original = correo_ses.boto3.client\n"
        "def cliente(servicio, **kwargs):\n"
        f"    if servicio == 'sesv2': kwargs['endpoint_url'] = 'http://127.0.0.1:{servidor.server_port}'\n"
        "    return original(servicio, **kwargs)\n"
        "correo_ses.boto3.client = cliente\n"
        f"celery_app.conf.update(task_default_queue={cola!r}, task_routes={{}})\n",
        encoding="utf-8",
    )
    runtime_url = (
        make_url(TEST_DATABASE_URL)
        .set(username="pangea_ht14_test_runtime", password=secrets.token_urlsafe(36))
        .render_as_string(hide_password=False)
    )
    aprovisionar(TEST_DATABASE_URL, runtime_url)
    entorno = {
        **os.environ,
        "DATABASE_URL": TEST_DATABASE_URL,
        "DATABASE_RUNTIME_URL": runtime_url,
        "CELERY_BROKER_URL": broker,
        "CELERY_RESULT_BACKEND": resultado,
        "SES_FROM_EMAIL": "alarmas@example.com",
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "SES_CONFIGURATION_SET": "",
        "SES_TEST_RECIPIENT": "",
        "PYTHONIOENCODING": "utf-8",
    }
    entorno.pop("AWS_PROFILE", None)
    motor = create_engine(TEST_DATABASE_URL, hide_parameters=True)
    worker = None
    log = (tmp_path / "worker.log").open("w", encoding="utf-8")
    id_alarma = None
    cliente_celery = Celery("ht14-prueba", broker=broker, backend=resultado)
    try:
        with Session(motor) as db:
            cliente = Cliente(
                rzn_scl=f"HT14 {identificador}",
                rc=str(int(identificador[:10], 16))[-11:].zfill(11),
                crr_cntct="qa@example.com",
            )
            db.add(cliente)
            db.flush()
            sede = Sede(id_clnt=cliente.id_clnt, nmbr=f"HT14 {identificador}")
            db.add(sede)
            db.flush()
            ubicacion = crear_ubicacion(db, sede)
            dispositivo = crear_dispositivo(db, ubicacion, crear_conexion(db, sede))
            parametro = crear_parametro(db, f"HT14 {identificador}", "°C")
            sistema = db.query(Usuario).filter_by(crr="sistema.ingesta@pangea.internal").one()
            alarma = Alarma(
                id_usr=sistema.id_usr,
                id_sd=sede.id_sd,
                id_ubccn=ubicacion.id_ubccn,
                id_prmtr=parametro.id_prmtr,
                nmbr=f"HT14 {identificador}",
            )
            db.add(alarma)
            db.flush()
            id_alarma = alarma.id_alrm
            db.add(CondicionAlarma(id_alrm=id_alarma, oprdr=">", vlr_umbrl=30))
            for correo in ("uno@example.com", "dos@example.com"):
                db.add(DestinatarioAlarma(id_alrm=id_alarma, cnl="email", crr=correo))
            db.flush()
            lectura = LecturaValidada(
                datetime.now(timezone.utc), dispositivo.id_cnxn, parametro.nmbr, 40, 1
            )
            guardar_lecturas(db, [lectura], dispositivo, None)
            db.commit()
            assert db.query(NotificacionEnviada).filter_by(id_alrm=id_alarma).count() == 2
        worker = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "ht14_worker:celery_app",
                "worker",
                "--pool=solo",
                "--concurrency=1",
                "--loglevel=INFO",
                "--without-gossip",
                "--without-mingle",
                "--without-heartbeat",
                "-Q",
                cola,
            ],
            cwd=tmp_path,
            env=entorno,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        listo_hasta = time.monotonic() + 15
        while time.monotonic() < listo_hasta:
            if cliente_celery.control.inspect(timeout=1).ping():
                break
        cliente_celery.send_task("app.tasks.notificaciones.despachar_pendientes", queue=cola)
        limite = time.monotonic() + 50
        while time.monotonic() < limite:
            assert worker.poll() is None, "El worker terminó antes de completar el envío"
            with Session(motor) as db:
                filas = db.query(NotificacionEnviada).filter_by(id_alrm=id_alarma).all()
                if all(n.estd == "Enviado" for n in filas):
                    ids = [n.id_ntfccn for n in filas]
                    assert sum(n.rntnts for n in filas) == 1
                    assert (
                        db.query(IntentoNotificacion)
                        .filter(IntentoNotificacion.id_ntfccn.in_(ids))
                        .count()
                        == 3
                    )
                    assert all(n.mensaje_id and n.fch_env for n in filas)
                    break
            time.sleep(0.2)
        else:
            with Session(motor) as db:
                estados = [
                    (n.estd, n.ultimo_error)
                    for n in db.query(NotificacionEnviada).filter_by(id_alrm=id_alarma)
                ]
            log.flush()
            raise AssertionError(
                f"No se completó el reintento SES: {estados}; llamadas HTTP: {len(recibidos)}; {log.name}"
            )
        assert len(recibidos) == 3
        assert {r["Destination"]["ToAddresses"][0] for r in recibidos} == {
            "uno@example.com",
            "dos@example.com",
        }
        assert all(
            "Alarma activada" in r["Content"]["Simple"]["Subject"]["Data"] for r in recibidos
        )
        # Una redelivery de Celery no vuelve a llamar al proveedor.
        for id_notificacion in ids:
            cliente_celery.send_task(
                "app.tasks.notificaciones.enviar_notificacion", args=[id_notificacion], queue=cola
            )
        barrera = cliente_celery.send_task("app.tasks.ping.ping", queue=cola)
        barrera.get(timeout=10)
        assert len(recibidos) == 3
    finally:
        if worker:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)
        log.close()
        cliente_celery.close()
        servidor.shutdown()
        servidor.server_close()
        if id_alarma is not None:
            with Session(motor) as db:
                ids = db.query(NotificacionEnviada.id_ntfccn).filter_by(id_alrm=id_alarma)
                db.query(IntentoNotificacion).filter(IntentoNotificacion.id_ntfccn.in_(ids)).delete(
                    synchronize_session=False
                )
                db.query(NotificacionEnviada).filter_by(id_alrm=id_alarma).delete()
                db.query(EstadoAlarma).filter_by(id_alrm=id_alarma).delete()
                db.query(DestinatarioAlarma).filter_by(id_alrm=id_alarma).delete()
                db.query(CondicionAlarma).filter_by(id_alrm=id_alarma).delete()
                db.query(Alarma).filter_by(id_alrm=id_alarma).delete()
                # La prueba confirma commits entre procesos; también debe retirar
                # el resto del escenario para no contaminar los tests de permisos.
                cliente = db.query(Cliente).filter_by(rzn_scl=f"HT14 {identificador}").one_or_none()
                if cliente is not None:
                    sedes = db.query(Sede.id_sd).filter_by(id_clnt=cliente.id_clnt)
                    ubicaciones = db.query(Ubicacion.id_ubccn).filter(Ubicacion.id_sd.in_(sedes))
                    dispositivos = db.query(Dispositivo.id_dspstv).filter(
                        Dispositivo.id_ubccn.in_(ubicaciones)
                    )
                    db.query(Telemetria).filter(Telemetria.id_dspstv.in_(dispositivos)).delete(
                        synchronize_session=False
                    )
                    db.query(Dispositivo).filter(Dispositivo.id_ubccn.in_(ubicaciones)).delete(
                        synchronize_session=False
                    )
                    db.query(ConexionFTP).filter(ConexionFTP.id_sd.in_(sedes)).delete(
                        synchronize_session=False
                    )
                    db.query(Ubicacion).filter(Ubicacion.id_sd.in_(sedes)).delete(
                        synchronize_session=False
                    )
                    db.query(Sede).filter_by(id_clnt=cliente.id_clnt).delete()
                    db.delete(cliente)
                db.query(Parametro).filter_by(nmbr=f"HT14 {identificador}").delete()
                db.commit()
        motor.dispose()
