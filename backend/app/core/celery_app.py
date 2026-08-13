import os

from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/2")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/3")

celery_app = Celery(
    "pangea",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.ping",
        "app.tasks.ingesta",
        "app.tasks.notificaciones",
        "app.tasks.particiones",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Bogota",
    enable_utc=True,
    task_track_started=True,
)

# HT-05 CA4 - Límite de concurrencia del worker
#
# Recomendado para DESARROLLO/PRUEBAS: --concurrency=4
#   celery -A app.core.celery_app worker --loglevel=info --concurrency=4
# (ya aplicado en el servicio `worker` de docker-compose.yml)
#
# Por qué 4, y no más ni menos:
#
# - Beat dispara sondear_conexiones_ftp cada 60s (beat_schedule, abajo).
#   Ese tick es el ritmo máximo al que entran archivos nuevos a la cola,
#   así que la ráfaga a absorber es "todo lo que se detectó en un tick".
# - Cada datalogger produce dos cadencias distintas de archivo: los
#   periódicos tipo H_ (uno cada ~15 min) y los irregulares por evento
#   tipo E_ (impredecibles, pueden llegar varios juntos). El peor caso no
#   es el promedio de H_, sino un tick donde coinciden varios H_ vencidos
#   con una ráfaga de E_.
# - procesar_archivo_dat es I/O-bound (descarga FTP + INSERTs), no
#   CPU-bound: los 4 procesos prefork pasan la mayor parte del tiempo
#   esperando red/BD, así que 4 en paralelo saturan poco CPU y cubren de
#   sobra 1 archivo/minuto/datalogger (CA4) para las pocas conexiones de
#   un entorno de pruebas.
# - No subirlo más en desarrollo: cada proceso prefork abre su propia
#   conexión a Postgres y su propia sesión FTP. Con --concurrency alto se
#   agota el pool de conexiones de la BD (o se satura el FTP del
#   datalogger, que suele aceptar pocas sesiones simultáneas) antes de
#   ganar throughput real.
#
# Para producción este número se debe recalcular con el número real de
# dataloggers y el max_connections de la RDS; la vía de crecimiento es
# escalar horizontalmente (más réplicas del worker), no subir sin límite
# la concurrencia de uno solo - ver backend/README.md.

# HT-05 CA1: sondeo de conexiones FTP cada minuto. La cadencia real por
# datalogger la controla cnxn_ftp.frcnc_mnts (ver
# app.tasks.ingesta.sondear_conexiones_ftp) - 1 minuto es el "tick" mínimo
# posible, así que ninguna frcnc_mnts configurada por debajo de eso puede
# cumplirse igual.
celery_app.conf.beat_schedule = {
    "sondear-conexiones-ftp-cada-minuto": {
        "task": "app.tasks.ingesta.sondear_conexiones_ftp",
        "schedule": 60.0,
    },
    # HT-08: mantiene el colchón de particiones de tlmtr. Corre a diario a
    # las 03:00 (hora baja de ingesta) y no una vez al mes a propósito: si
    # el job falla un día, al siguiente se recupera solo. Un job mensual
    # que falle deja un hueco que nadie nota hasta que la ingesta empieza
    # a rechazar lecturas. Como crea MESES_DE_COLCHON meses por delante,
    # la partición del mes siguiente existe siempre con semanas de
    # anticipación -HT-08 exige al menos una-.
    "asegurar-particiones-tlmtr-diario": {
        "task": "app.tasks.particiones.asegurar_particiones_futuras",
        "schedule": crontab(hour=3, minute=0),
    },
}
