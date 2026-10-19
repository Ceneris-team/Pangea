from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.services.contratos import aplicar_programadas, vencer_sin_cobro
from app.services.limites_plan import fecha_comercial
from app.tasks.notificaciones import notificar_suscripciones_vencidas


@celery_app.task
def activar_suscripciones_programadas():
    with SessionLocal() as db:
        total = aplicar_programadas(db, fecha_comercial())
        db.commit()
        return {"activadas": total}


@celery_app.task
def vencer_suscripciones_sin_cobro():
    """PP-320 + PP-321: vence los contratos sin cobro y avisa al comercial.

    El aviso se encola después del commit: si la tarea falla antes, no se
    anuncia un vencimiento que no quedó guardado.
    """
    with SessionLocal() as db:
        vencidas = vencer_sin_cobro(db, fecha_comercial())
        db.commit()
    if vencidas:
        notificar_suscripciones_vencidas.delay(vencidas)
    return {"vencidas": len(vencidas)}
