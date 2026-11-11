"""Beat -> Redis -> worker -> pg_dump -> S3 -> restauracion local reales.

Opt-in: RUN_BACKUP_INTEGRATION=1. Solo origen local y prefijo temporal propio.
"""

import datetime as dt
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from celery import Celery
from celery.beat import ScheduleEntry, Scheduler
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BACKUP_INTEGRATION") != "1", reason="Requiere PostgreSQL, Redis y S3 reales"
)


def test_programacion_worker_reintento_s3_y_restauracion(tmp_path, monkeypatch):
    from app.services import almacen_respaldos as almacen
    from app.services import respaldos
    from app.services.restauracion_respaldos import restaurar_local
    from scripts.verificar_restauracion_local import verificar

    fuente = make_url(respaldos.database_url())
    assert fuente.host in {"localhost", "127.0.0.1", "db"}
    identificador = uuid.uuid4().hex[:12]
    entorno = "local-qa-" + identificador
    cola, nodo = "respaldos-qa-" + identificador, "respaldos-qa-" + identificador + "@local"
    broker = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/2")
    backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/3")
    monkeypatch.setenv("BACKUP_ENVIRONMENT", entorno)
    monkeypatch.setenv("BACKUP_ENABLED", "true")
    monkeypatch.setenv("BACKUP_RETRY_BASE_SECONDS", "1")
    monkeypatch.setenv("BACKUP_DATABASE_URL", fuente.render_as_string(hide_password=False))
    app = Celery("prueba_respaldos", broker=broker, backend=backend)
    app.conf.timezone = "America/Lima"
    from app.core.celery_app import celery_app

    original = celery_app.conf.beat_schedule["respaldo-extendido-semanal"]
    cron = original["schedule"]
    assert cron.hour == {2} and cron.minute == {0} and cron.day_of_week == {0}
    domingo = dt.datetime(2026, 11, 15, 2, tzinfo=ZoneInfo("America/Lima"))
    monkeypatch.setattr(cron, "nowfun", lambda: domingo)
    entrada = ScheduleEntry(
        name="respaldo-extendido-semanal",
        task=original["task"],
        schedule=cron,
        last_run_at=domingo - dt.timedelta(days=7),
        options={"queue": cola},
        app=app,
    )
    scheduler = Scheduler(app=app, lazy=True)
    scheduler.schedule = {entrada.name: entrada}
    recibidos = []
    aplicar = scheduler.apply_async

    def registrar(*args, **kwargs):
        resultado = aplicar(*args, **kwargs)
        recibidos.append(resultado)
        return resultado

    monkeypatch.setattr(scheduler, "apply_async", registrar)
    destino = fuente.set(database="pangea_restore_qa_" + identificador)
    url_destino = destino.render_as_string(hide_password=False)
    runtime = None
    contador = tmp_path / "intentos.txt"
    alerta = tmp_path / "alerta.txt"
    (tmp_path / "worker_respaldo_qa.py").write_text(
        "from pathlib import Path\n"
        "from app.core.celery_app import celery_app\n"
        "from app.tasks import respaldos as tarea\n"
        "original = tarea.ejecutar_respaldo\n"
        "intentos = 0\n"
        "def ejecutar():\n"
        "    global intentos\n"
        "    intentos += 1\n"
        f"    Path({str(contador)!r}).write_text(str(intentos))\n"
        "    if intentos == 1: raise ConnectionError('fallo controlado de prueba')\n"
        "    return original()\n"
        "def avisar(*args):\n"
        f"    Path({str(alerta)!r}).write_text('alerta intentada')\n"
        "tarea.ejecutar_respaldo = ejecutar\n"
        "tarea.emitir_alerta = avisar\n",
        encoding="utf-8",
    )
    entorno_worker = {
        **os.environ,
        "PYTHONPATH": str(tmp_path) + os.pathsep + str(Path(__file__).resolve().parents[2]),
    }
    with (tmp_path / "worker.log").open("w") as log:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "worker_respaldo_qa:celery_app",
                "worker",
                "--pool=solo",
                "--concurrency=1",
                "--loglevel=WARNING",
                "--without-gossip",
                "--without-mingle",
                "--without-heartbeat",
                "--queues",
                cola,
                "--hostname",
                nodo,
            ],
            cwd=Path(__file__).resolve().parents[2],
            env=entorno_worker,
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(30):
                if proc.poll() is not None:
                    pytest.fail("El worker de prueba no pudo iniciar")
                if app.control.ping(destination=[nodo], timeout=0.3):
                    break
                time.sleep(0.3)
            else:
                pytest.fail("El worker no respondio")
            scheduler.tick()
            assert len(recibidos) == 1
            resultado = recibidos[0].get(timeout=120)
            assert resultado["estado"] == "Exitoso" and resultado["tipo"] == "semanal"
            assert contador.read_text() == "2" and alerta.exists()
            assert resultado["clave"].startswith(almacen.prefijo())
            restaurado = restaurar_local(resultado["clave"], url_destino)
            assert restaurado["tablas_verificadas"] == len(resultado["tablas"])
            assert restaurado["filas_verificadas"] == sum(resultado["tablas"].values())
            validacion = verificar(url_destino)
            runtime = validacion.pop("cuenta_prueba")
            assert all(validacion.values())
            with pytest.raises(ValueError, match="ya existe"):
                restaurar_local(resultado["clave"], url_destino)
            print(
                json.dumps(
                    {
                        "beat_worker_s3": True,
                        "reintento_automatico": True,
                        "restauracion": restaurado,
                        "aplicacion": validacion,
                    }
                )
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            app.close()
            claves = [obj["Key"] for obj in almacen.listar()]
            almacen.eliminar(claves)
            admin = create_engine(
                fuente.set(database="postgres"), isolation_level="AUTOCOMMIT", hide_parameters=True
            )
            try:
                with admin.connect() as conn:
                    conn.exec_driver_sql(
                        'DROP DATABASE IF EXISTS "' + destino.database + '" WITH (FORCE)'
                    )
                    if runtime:
                        conn.exec_driver_sql('DROP ROLE "' + runtime + '"')
            finally:
                admin.dispose()


def test_retencion_real_s3_limite_y_antiguedad(monkeypatch):
    from app.services import almacen_respaldos as almacen
    from app.services import respaldos
    from app.services.object_storage import cliente_s3

    monkeypatch.setenv("BACKUP_ENVIRONMENT", "local-qa-retencion-" + uuid.uuid4().hex[:10])
    monkeypatch.setenv("BACKUP_MAX_COPIES", "8")
    monkeypatch.setenv("BACKUP_RETENTION_DAYS", "56")
    cliente = cliente_s3()
    hoy = dt.datetime.now(dt.timezone.utc).replace(hour=12)
    try:
        # Objetos de prueba pequenos, sin datos de negocio. Ningun objeto fuera de este prefijo.
        for semana in range(10):
            fecha = hoy - dt.timedelta(weeks=semana)
            clave = almacen.prefijo() + str(semana) + ".dump.enc"
            cliente.put_object(
                Bucket=almacen.bucket(),
                Key=clave,
                Body=b"fixture-retencion",
                ServerSideEncryption="AES256",
            )
            almacen.guardar_json(
                clave + ".json",
                {
                    "estado": "Exitoso",
                    "tipo": "semanal",
                    "clave": clave,
                    "semana": fecha.strftime("%G-W%V"),
                    "finalizado": fecha.isoformat(),
                },
            )
        eliminadas = respaldos.aplicar_retencion(hoy.date())
        assert set(eliminadas) == {
            almacen.prefijo() + "8.dump.enc",
            almacen.prefijo() + "9.dump.enc",
        }
        assert len([obj for obj in almacen.listar() if obj["Key"].endswith(".dump.enc")]) == 8
    finally:
        almacen.eliminar([obj["Key"] for obj in almacen.listar()])
