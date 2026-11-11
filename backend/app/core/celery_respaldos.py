"""Worker/Beat de respaldos para despliegues con una version anterior de la API.

Comparte Redis y la tarea de respaldo. No programa ni consume ingesta o correos
de otras versiones de la aplicacion. Desplegar una sola instancia con --beat.
"""

from app.core.celery_app import celery_app

entrada = celery_app.conf.beat_schedule["respaldo-extendido-semanal"]
celery_app.conf.update(
    include=["app.tasks.respaldos"],
    task_default_queue="respaldos",
    task_routes={"app.tasks.respaldos.respaldo_semanal": {"queue": "respaldos"}},
    beat_schedule={"respaldo-extendido-semanal": entrada},
)
