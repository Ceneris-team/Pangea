"""QA PP-27 (PP-439): datos para el E2E en la app real (pangea_qa36, Cliente Demo).

Crea dos dataloggers QA27 en «[DEMO] Río Rímac» con mapeo activo y 14 archivos Fallido
con su original conservado y un intento automático previo:
- H_QA27_F_00..11.dat (datalogger A): original válido → el reproceso debe dejarlos Procesado.
- H_QA27_MALO.dat (datalogger A): original alterado (huella distinta) → debe volver a Fallido.
- H_QA27_B_00.dat (datalogger B): para comprobar el alcance por datalogger.
Idempotente: borra antes lo que empiece por QA27.
Uso (desde backend/ de dev 78edb10, DATABASE_URL=pangea_qa36):
    python seed_pp27.py
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ["OBJECT_STORAGE_BUCKET"] = ""

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    ArchivoIngesta,
    ConexionFTP,
    Dispositivo,
    IntentoProcesamiento,
    Sede,
    Ubicacion,
)
from app.services.ingesta.originales import conservar_original  # noqa: E402
from tests.routers.test_mediciones import (  # noqa: E402
    crear_conexion,
    crear_dispositivo,
    crear_parametro,
    mapear_parametro,
)

MOTIVO = "No hay un formato activo (mp_frmt) para el dispositivo y el tipo de trama"


def limpiar(db):
    for sql in (
        "DELETE FROM tlmtr WHERE id_archv IN (SELECT id_archv FROM archv_ingst WHERE nmbr_archv LIKE '%QA27%')",
        "DELETE FROM intnt_prcsmnt WHERE id_archv IN (SELECT id_archv FROM archv_ingst WHERE nmbr_archv LIKE '%QA27%')",
        "DELETE FROM archv_ingst WHERE nmbr_archv LIKE '%QA27%'",
    ):
        db.execute(text(sql))
    db.commit()


def main():
    db = SessionLocal()
    limpiar(db)
    sede = db.get(Sede, 1)
    proyecto = db.get(Ubicacion, 1)
    equipos = []
    for letra in ("A", "B"):
        nombre = f"QA27 Datalogger {letra}"
        cnxn = db.query(ConexionFTP).filter_by(nmbr=nombre).first() or crear_conexion(db, sede, nombre)
        eq = db.query(Dispositivo).filter_by(nmbr=f"QA27 CR1000 {letra}").first()
        if eq is None:
            eq = crear_dispositivo(db, proyecto, cnxn, f"QA27 CR1000 {letra}")
            mapear_parametro(db, eq, crear_parametro(db, f"QA27 Nivel {letra}", "m"))
        equipos.append((cnxn, eq))
    base = dt.datetime(2026, 11, 20, 8, 0)
    archivos = [(f"H_QA27_F_{i:02}.dat", 0, i) for i in range(12)]
    archivos += [("H_QA27_MALO.dat", 0, 12), ("H_QA27_B_00.dat", 1, 13)]
    for nombre, cual, i in archivos:
        cnxn, eq = equipos[cual]
        recibido = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=60 - i)
        a = ArchivoIngesta(
            id_cnxn=cnxn.id_cnxn, id_dspstv=eq.id_dspstv, nmbr_archv=nombre,
            estd="Fallido", mnsj_errr=MOTIVO, fch_dtccn=recibido, fch_prcsd=recibido,
        )
        db.add(a)
        db.flush()
        fecha = base + dt.timedelta(hours=i)
        conservar_original(a, f"Fecha,Nivel\n{fecha:%Y-%m-%d %H:%M:%S},{10 + i}.5\n".encode())
        if nombre == "H_QA27_MALO.dat":
            a.contenido_original = b"Fecha,Nivel\n2026-11-20 20:00:00,999\n"  # alterado tras la recepción
        db.add(IntentoProcesamiento(
            id_archv=a.id_archv, rsltd="Fallido", mnsj_errr=MOTIVO,
            fch_intnt=recibido, fch_inicio=recibido, fch_fin=recibido,
        ))
    db.commit()
    print("Sembrados:", db.query(ArchivoIngesta).filter(ArchivoIngesta.nmbr_archv.like("%QA27%")).count())
    db.close()


if __name__ == "__main__":
    main()
