"""Prepara el entorno QA HU36: suscripción activa para la empresa de la Sede Demo.

Replica lo que hace el fixture `entorno` (tests/routers/test_entorno_operativo.py).
Idempotente. Ejecutar desde backend/ con DATABASE_URL de la cuenta de migraciones.
"""

import os
import sys
from datetime import timedelta

sys.path.insert(0, os.getcwd())
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.models import LimitePlan, PlanSuscripcion, Sede, Suscripcion  # noqa: E402
from tests.routers.test_entorno_operativo import fecha_comercial  # noqa: E402

engine = create_engine(os.environ["DATABASE_URL"])
with Session(engine) as db:
    sede = db.query(Sede).filter(Sede.nmbr == "Sede Demo").one()
    id_clnt = sede.id_clnt
    if db.query(Suscripcion).filter(Suscripcion.id_clnt == id_clnt, Suscripcion.estd == "Activa").first():
        print("ya existe suscripción activa")
    else:
        plan = db.query(PlanSuscripcion).filter(PlanSuscripcion.nmbr == "Plan QA HU36").first()
        if not plan:
            plan = PlanSuscripcion(nmbr="Plan QA HU36", prc_mnsl=100, funcionalidades=["tableros"])
            db.add(plan)
            db.flush()
            db.add(LimitePlan(id_pln=plan.id_pln, mx_sds=0, mx_ubccns=50, mx_dspstvs=50, mx_usrs=10))
        db.add(
            Suscripcion(
                id_clnt=id_clnt,
                id_pln=plan.id_pln,
                fch_inc=fecha_comercial(),
                fch_vncmnt=fecha_comercial() + timedelta(days=30),
                estd="Activa",
            )
        )
        db.commit()
        print(f"suscripción activa creada para id_clnt={id_clnt}")
