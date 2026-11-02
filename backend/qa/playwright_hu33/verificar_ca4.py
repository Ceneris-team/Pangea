"""PP-408 CA4: un archivo exportado se elimina del bucket al expirar su vigencia (entorno local, bucket simulado en carpeta).
Usa la API y el worker en marcha (entorno_local.py) y ejecuta la tarea de mantenimiento del producto."""
import json
import time
import urllib.request

import entorno_local as e

e.parchar()
from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.tasks.exportaciones import mantener_exportaciones  # noqa: E402

API = "http://127.0.0.1:8000"
SALIDA = e.RAIZ / "verificacion_ca4_eliminacion.txt"
lineas = []


def log(msg):
    print(msg)
    lineas.append(msg)


def api(ruta, metodo="GET", cuerpo=None, token=None):
    req = urllib.request.Request(API + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


_, login = api("/auth/login", "POST", {"correo": "cliente@pangea-dev.com", "contrasena": "Pangea2026"})
token = login["access_token"]
log(f"Verificación CA4 · {time.strftime('%d/%m/%Y %H:%M:%S')} · usuario cliente@pangea-dev.com")
estado, resp = api("/exportaciones", "POST", {"formato": "csv", "fecha_inicio": "2026-10-29T00:00:00Z", "fecha_fin": "2026-10-31T00:00:00Z", "ubicacion_ids": [], "parametro_ids": []}, token)
log(f"1. POST /exportaciones -> {estado} {resp.get('mensaje', resp)}")
idx = resp["exportacion"]["id_exprtcn"]
for _ in range(40):
    _, item = api(f"/exportaciones/{idx}", token=token)
    if item["estd"] == "Lista":
        break
    time.sleep(1)
log(f"2. Exportación #{idx}: estado={item['estd']}, filas={item['filas']}, disponible hasta {item['fch_exprcn']}")
archivos = [p for p in (e.BUCKET).rglob("*") if p.is_file()]
clave = None
with SessionLocal() as db:
    clave = db.execute(text("select objeto_clave from exprtcn where id_exprtcn=:i"), {"i": idx}).scalar()
    horas = db.execute(text("select extract(epoch from (fch_exprcn - fch_slctd))/3600 from exprtcn where id_exprtcn=:i"), {"i": idx}).scalar()
log(f"3. Vigencia = {horas:.2f} horas desde la solicitud. Objeto en bucket: {clave} -> existe={ (e.BUCKET / clave).exists() }")
with SessionLocal() as db:
    db.execute(text("update exprtcn set fch_exprcn = now() - interval '1 second' where id_exprtcn=:i"), {"i": idx})
    db.commit()
log("4. Se fuerza el vencimiento (fch_exprcn = hace 1 segundo) y se ejecuta la tarea mantener_exportaciones del producto")
log(f"   resultado de la tarea: {mantener_exportaciones()}")
with SessionLocal() as db:
    fila = db.execute(text("select estd, objeto_clave from exprtcn where id_exprtcn=:i"), {"i": idx}).one()
log(f"5. Estado en BD: {fila[0]}, objeto_clave={fila[1]}")
log(f"6. Objeto en bucket tras la limpieza: existe={(e.BUCKET / clave).exists()}")
estado, resp = api(f"/exportaciones/{idx}/descarga", "POST", token=token)
log(f"7. POST /exportaciones/{idx}/descarga -> {estado} {resp.get('detail')}")
ok = fila[0] == "Expirada" and not (e.BUCKET / clave).exists() and estado == 410
log("RESULTADO: " + ("CUMPLE CA4" if ok else "NO CUMPLE CA4"))
SALIDA.write_text("\n".join(lineas) + "\n", encoding="utf-8")
