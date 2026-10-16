from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.services.contratos import aplicar_programadas
from app.services.limites_plan import fecha_comercial


@celery_app.task
def activar_suscripciones_programadas():
    with SessionLocal() as db:
        total = aplicar_programadas(db, fecha_comercial())
        db.commit()
        return {"activadas": total}
