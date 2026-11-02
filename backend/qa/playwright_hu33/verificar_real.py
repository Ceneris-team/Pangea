"""PP-408 ronda 2 · CP-220 y CP-221: flujo completo contra un servidor S3 (moto en modo servidor) y un buzón SMTP (Mailpit), ambos locales.

No se parchea nada del producto: la API, el worker y Beat corren con QA_REAL=1 (ver entorno_local.py y .env.qa).
El correo sale por SMTP con STARTTLS hacia Mailpit y se lee desde su API; el archivo se sube, se firma y se borra con boto3.

    QA_REAL=1 venv/Scripts/python.exe qa/playwright_hu33/verificar_real.py
"""
import json
import time
import urllib.error
import urllib.request

import boto3
import entorno_local as e

e.parchar()
from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402

API, MAIL = "http://127.0.0.1:8000", "http://127.0.0.1:8025"
SALIDA = e.RAIZ / "ronda2" / "verificacion_real_ronda2.txt"
BUCKET = "pangea-exportaciones-qa"
s3 = boto3.client("s3", endpoint_url="http://127.0.0.1:9000", region_name="us-east-1", aws_access_key_id="qa-local", aws_secret_access_key="qa-local-secret")
lineas, ok = [], {}


def log(m=""):
    print(m, flush=True)
    lineas.append(m)


def http(url, metodo="GET", cuerpo=None, token=None):
    req = urllib.request.Request(url, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as r:
            datos = r.read()
            return r.status, (json.loads(datos) if datos[:1] in (b"{", b"[") else datos)
    except urllib.error.HTTPError as err:
        datos = err.read()
        return err.code, (json.loads(datos) if datos[:1] in (b"{", b"[") else datos)


def sql(q, **p):
    with SessionLocal() as db:
        return db.execute(text(q), p).all()


def versiones(clave):
    r = s3.list_object_versions(Bucket=BUCKET, Prefix=clave)
    return [v["VersionId"] for v in r.get("Versions", []) if v["Key"] == clave], [m["VersionId"] for m in r.get("DeleteMarkers", []) if m["Key"] == clave]


token = http(API + "/auth/login", "POST", {"correo": "cliente@pangea-dev.com", "contrasena": "Pangea2026"})[1]["access_token"]
log(f"Verificación con S3 y SMTP reales en local (moto como servidor S3, Mailpit como buzón con STARTTLS) · {time.strftime('%d/%m/%Y %H:%M:%S')}")
http(MAIL + "/api/v1/messages", "DELETE")

log("\nCP-221 · Flujo completo contra el servidor S3")
estado, resp = http(API + "/exportaciones", "POST", {"formato": "csv", "fecha_inicio": "2026-10-29T00:00:00Z", "fecha_fin": "2026-10-31T00:00:00Z", "ubicacion_ids": [], "parametro_ids": []}, token)
idx = resp["exportacion"]["id_exprtcn"]
log(f"1. POST /exportaciones -> {estado}; exportación #{idx}")
for _ in range(90):
    item = http(f"{API}/exportaciones/{idx}", token=token)[1]
    if item["estd"] in ("Lista", "Fallida"):
        break
    time.sleep(1)
log(f"2. Estado: {item['estd']}; filas {item['filas']}; error: {item['error']}")
clave, version = sql("select objeto_clave, objeto_version from exprtcn where id_exprtcn=:i", i=idx)[0]
vs, ms = versiones(clave) if clave else ([], [])
log(f"3. Objeto en el bucket: {clave}; versiones {len(vs)}, marcadores {len(ms)}; versión guardada en la BD: {version is not None}")
estado_dl, resp_dl = http(f"{API}/exportaciones/{idx}/descarga", "POST", token=token)
url = resp_dl["url"] if estado_dl == 200 else ""
log(f"4. POST /descarga -> {estado_dl}; URL firmada con X-Amz-Expires: {'X-Amz-Expires=60' in url}")
descarga = http(url)[0] if url else None
contenido = urllib.request.urlopen(url).read() if url else b""
log(f"5. GET de la URL firmada -> {descarga}; {len(contenido)} bytes; cabecera: {contenido[:60]!r}")
anonimo = http(f"http://127.0.0.1:9000/{BUCKET}/{clave}")[0] if clave else None
log(f"6. GET del mismo objeto sin firma -> {anonimo} (S3 real debe responder 403; moto no siempre valida acceso anónimo)")
ok["flujo"] = item["estd"] == "Lista" and len(vs) == 1 and estado_dl == 200 and descarga == 200 and contenido.startswith(b"\xef\xbb\xbfEmpresa")
log(f"  -> {'CUMPLE' if ok['flujo'] else 'NO CUMPLE'}: se subió, se firmó y se descargó el archivo real")

log("\nCP-220 · Correo recibido en el buzón (Mailpit, SMTP con STARTTLS)")
mensaje = None
for _ in range(60):
    lista = http(MAIL + "/api/v1/messages")[1]["messages"]
    if lista:
        mensaje = http(f"{MAIL}/api/v1/message/{lista[0]['ID']}")[1]
        break
    time.sleep(2)
if mensaje:
    cuerpo = mensaje["Text"]
    log(f"7. Mensaje recibido: para {[d['Address'] for d in mensaje['To']]}; asunto «{mensaje['Subject']}»; adjuntos: {len(mensaje.get('Attachments') or [])}")
    log("   cuerpo: " + cuerpo.replace("\n", " | ")[:300])
    ok["correo"] = f"consulta-datos?exportacion={idx}" in cuerpo and "Disponible hasta" in cuerpo and not mensaje.get("Attachments") and "Empresa" not in cuerpo
    log(f"  -> {'CUMPLE' if ok['correo'] else 'NO CUMPLE'}: llegó al buzón con el enlace a la aplicación y la caducidad, sin adjuntos ni datos")
else:
    ok["correo"] = False
    log("7. No llegó ningún mensaje al buzón en 2 minutos")

log("\nLimpieza con Beat y varias versiones")
s3.put_object(Bucket=BUCKET, Key=clave, Body=b"version anterior de un reintento")
s3.delete_object(Bucket=BUCKET, Key=clave)
vs, ms = versiones(clave)
log(f"8. Antes de vencer: {len(vs)} versiones y {len(ms)} marcadores de borrado en la clave")
with SessionLocal() as db:
    db.execute(text("update exprtcn set fch_exprcn = now() - interval '1 second' where id_exprtcn=:i"), {"i": idx})
    db.commit()
t0, limpio = time.time(), False
for _ in range(120):
    vs, ms = versiones(clave)
    est = sql("select estd from exprtcn where id_exprtcn=:i", i=idx)[0][0]
    if est == "Expirada" and not vs and not ms:
        limpio = True
        break
    time.sleep(3)
dl = http(f"{API}/exportaciones/{idx}/descarga", "POST", token=token)[0]
log(f"9. Beat lo limpió en {time.time() - t0:.0f} s: estado {est}; versiones {len(vs)}; marcadores {len(ms)}; descarga posterior -> {dl}")
ok["limpieza"] = limpio and dl == 410 and time.time() - t0 <= 300
log(f"  -> {'CUMPLE' if ok['limpieza'] else 'NO CUMPLE'}: se eliminaron todas las versiones y marcadores en menos de 5 minutos")
log("\nRESUMEN: " + "; ".join(f"{k}={'ok' if v else 'FALLA'}" for k, v in ok.items()))
SALIDA.write_text("\n".join(lineas) + "\n", encoding="utf-8")
