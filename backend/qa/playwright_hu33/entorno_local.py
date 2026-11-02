"""Entorno local de QA para PP-408: API y worker Celery reales con el bucket simulado en una carpeta.

Solo parchea el borde externo (S3 y SMTP). La tarea, los lotes, la expiración y la limpieza son el código del producto.
Uso: [QA_REAL=1] python entorno_local.py api | worker | beat; con QA_REAL=1 no se parchea nada y se usan los servicios de .env.qa (SMTP real contra smtp_local.py; QA_CORREO_SIMULADO=1 vuelve al correo simulado)
"""
import json
import os
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] / "03_Evidencias" / "HU33-HT15"
BUCKET = RAIZ / "bucket_local"
CORREOS = RAIZ / "correos_enviados.jsonl"
FIRMAS = RAIZ / "firmas_generadas.jsonl"

REAL = os.environ.get("QA_REAL") == "1"  # servicios reales: bucket de Lightsail y SMTP reales, leídos de .env.qa (ignorado por git)
os.environ.update(
    DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5433/pangea_e2e",
    RATELIMIT_STORAGE_URL="redis://localhost:6379/5",
)
if REAL:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env.qa"), override=True)
else:
    os.environ.update(EXPORT_S3_BUCKET="bucket-local-qa", SMTP_HOST="127.0.0.1", SMTP_PORT="1025")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def parchar():
    if REAL:
        return
    from app.security import mailer
    from app.services.exportaciones_storage import AlmacenExportaciones

    def init(self, bucket=None):
        self.bucket = bucket or "bucket-local-qa"

    def subir(self, archivo, clave, formato):
        destino = BUCKET / clave
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(archivo, destino)
        return "version-local"

    def eliminar(self, clave, version=None):
        (BUCKET / clave).unlink(missing_ok=True)

    def firmar(self, clave, segundos, version=None):
        with open(FIRMAS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"clave": clave, "segundos": segundos}) + "\n")
        return f"http://127.0.0.1:8000/docs#bucket-local/{clave}?X-Expires={segundos}"

    def correo(destino, enlace, expira_en):
        with open(CORREOS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"para": destino, "enlace": enlace, "expira_en": expira_en.isoformat()}) + "\n")

    AlmacenExportaciones.__init__ = init
    AlmacenExportaciones.verificar_privado = lambda self: None
    AlmacenExportaciones.subir = subir
    AlmacenExportaciones.eliminar = eliminar
    AlmacenExportaciones.firmar = firmar
    if os.environ.get('QA_CORREO_SIMULADO'):
        mailer.enviar_correo_exportacion = correo


if __name__ == "__main__":
    parchar()
    if sys.argv[1] == "api":
        import uvicorn

        from app.main import app

        uvicorn.run(app, port=8000)
    elif sys.argv[1] == "beat":
        from app.core.celery_app import celery_app

        celery_app.start(["beat", "-l", "INFO", "-s", str(RAIZ / "celerybeat-schedule-qa")])
    else:
        from app.core.celery_app import celery_app

        celery_app.worker_main(["worker", "-P", "solo", "-Q", "exportaciones,celery", "-l", "INFO", "-n", "qa@%h"])

