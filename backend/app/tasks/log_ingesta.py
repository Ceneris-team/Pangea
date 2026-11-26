from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.models import LogIngesta
from app.services.ingesta.log import limite_conservacion


@celery_app.task(name="app.tasks.log_ingesta.depurar")
def depurar():
    """Elimina solo eventos del log. Preserva originales, telemetría y reprocesos."""
    with SessionLocal() as db:
        eliminados = (
            db.query(LogIngesta)
            .filter(LogIngesta.fecha < limite_conservacion())
            .delete(synchronize_session=False)
        )
        db.commit()
        return {"eliminados": eliminados}
