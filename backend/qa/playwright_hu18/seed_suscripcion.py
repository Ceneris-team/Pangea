"""Da suscripción Vigente a la empresa de la Sede Demo en la BD pangea_e2e (solo QA local)."""

import datetime as dt

from app.database import SessionLocal
from app.models import Sede
from app.models.suscripcion import LimitePlan, PlanSuscripcion, Suscripcion

db = SessionLocal()
sede = db.query(Sede).first()
plan = db.query(PlanSuscripcion).filter_by(nmbr="Plan QA HU18").first()
if plan is None:
    plan = PlanSuscripcion(nmbr="Plan QA HU18", prc_mnsl=100)
    db.add(plan)
    db.flush()
    db.add(LimitePlan(id_pln=plan.id_pln, mx_sds=1, mx_ubccns=50, mx_dspstvs=50, mx_usrs=50))
hoy = dt.date.today()
if not db.query(Suscripcion).filter_by(id_clnt=sede.id_clnt).first():
    db.add(
        Suscripcion(
            id_clnt=sede.id_clnt,
            id_pln=plan.id_pln,
            fch_inc=hoy - dt.timedelta(days=1),
            fch_vncmnt=hoy + dt.timedelta(days=60),
            estd="Activa",
        )
    )
db.commit()
print("Suscripción vigente para cliente", sede.id_clnt)
