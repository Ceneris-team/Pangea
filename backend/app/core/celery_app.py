import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL", "redis://localhost:6379/2"
)
CELERY_RESULT_BACKEND = os.environ.get(
    "CELERY_RESULT_BACKEND", "redis://localhost:6379/3"
)

celery_app = Celery(
    "pangea",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["app.tasks.ping", "app.tasks.ingesta"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Bogota",
    enable_utc=True,
    task_track_started=True,
)

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
}
