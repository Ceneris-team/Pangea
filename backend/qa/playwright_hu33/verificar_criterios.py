"""PP-408 ronda 2: verificación de los criterios nuevos de HU-15 contra procesos reales.

Requiere en marcha (ver entorno_local.py): API, worker (colas exportaciones y celery) y Beat. Este script levanta
y detiene el servidor SMTP local con STARTTLS (smtp_local.py); el correo lo envía el código real del producto por SMTP.
El bucket sigue simulado en una carpeta (no hay Object Storage real en este equipo).

    venv/Scripts/python.exe qa/playwright_hu33/verificar_criterios.py <cert.pem> <key.pem>
"""
import csv
import email
import io
import json
import re
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import entorno_local as e

e.parchar()
from openpyxl import load_workbook  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402

API = "http://127.0.0.1:8000"
CARPETA = e.RAIZ / "ronda2"
CORREOS = CARPETA / "correos_smtp"
SALIDA = CARPETA / "verificacion_criterios_ronda2.txt"
CERT, CLAVE = sys.argv[1:3]
CARPETA.mkdir(exist_ok=True)
lineas, resultados = [], {}


def log(msg=""):
    print(msg, flush=True)
    lineas.append(msg)


def api(ruta, metodo="GET", cuerpo=None, token=None):
    req = urllib.request.Request(API + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}"), time.perf_counter() - inicio
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}"), time.perf_counter() - inicio


def login(correo):
    return api("/auth/login", "POST", {"correo": correo, "contrasena": "Pangea2026"})[1]["access_token"]


def sql(consulta, **params):
    with SessionLocal() as db:
        return db.execute(text(consulta), params).all()


def esperar(id_, token, estado="Lista", tope=90):
    for _ in range(tope):
        _, item, _ = api(f"/exportaciones/{id_}", token=token)
        if item["estd"] == estado:
            return item
        time.sleep(1)
    raise TimeoutError(f"#{id_} no llegó a {estado}: {item}")


def veredicto(clave, ok, detalle):
    resultados[clave] = ok
    log(f"  -> {'CUMPLE' if ok else 'NO CUMPLE'}: {detalle}")


def iniciar_smtp():
    return subprocess.Popen([sys.executable, str(Path(__file__).with_name("smtp_local.py")), str(CORREOS), CERT, CLAVE],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


CUERPO = {"formato": "csv", "fecha_inicio": "2026-10-29T00:00:00Z", "fecha_fin": "2026-10-31T00:00:00Z", "ubicacion_ids": [], "parametro_ids": []}
cliente, admin = login("cliente@pangea-dev.com"), login("admin@pangea-dev.com")
log(f"Verificación de criterios de HU-15 · ronda 2 · {time.strftime('%d/%m/%Y %H:%M:%S')} · API, worker, Beat y SMTP local con STARTTLS")
smtp = iniciar_smtp()
time.sleep(3)

# 1. Solicitud asíncrona: percentil 95 de aceptación
log("\n1. Solicitud asíncrona: 30 solicitudes seguidas (cada una espera a Lista antes de la siguiente)")
tiempos, ids = [], []
for _ in range(30):
    estado, resp, seg = api("/exportaciones", "POST", CUERPO, cliente)
    assert estado == 202, (estado, resp)
    tiempos.append(seg)
    ids.append(resp["exportacion"]["id_exprtcn"])
    esperar(ids[-1], cliente)
p95 = sorted(tiempos)[int(len(tiempos) * 0.95) - 1]
log(f"   202 en las 30; mediana {statistics.median(tiempos) * 1000:.0f} ms; p95 {p95 * 1000:.0f} ms; máximo {max(tiempos) * 1000:.0f} ms")
veredicto("p95", p95 <= 2, "p95 <= 2 s")

# 2. Contenido completo (CSV y XLSX)
log("\n2. Contenido completo: columnas, filas, zona horaria y decimales")
filtros = sql("select fltrs_aplcds from exprtcn where id_exprtcn=:i", i=ids[-1])[0][0]
esperadas = sql("""
    select (select count(*) from tlmtr t join dspstv d on d.id_dspstv=t.id_dspstv where d.id_ubccn = any(:u) and t.fch_hr between :a and :b)
         + (select count(*) from evnt_txt t join dspstv d on d.id_dspstv=t.id_dspstv where d.id_ubccn = any(:u) and t.fch_hr between :a and :b)
""", u=filtros["ubicacion_ids"], a=filtros["fecha_inicio"], b=filtros["fecha_fin"])[0][0]
clave_csv = sql("select objeto_clave from exprtcn where id_exprtcn=:i", i=ids[-1])[0][0]
filas = list(csv.reader(io.StringIO((e.BUCKET / clave_csv).read_bytes().decode("utf-8-sig"))))
cabecera, datos = filas[0], filas[1:]
log(f"   CSV: {len(datos)} filas; consulta directa a la BD: {esperadas}; cabecera: {cabecera}")
con_zona = all(re.search(r"[+-]\d\d:\d\d$", f[8]) for f in datos)
log(f"   Fecha con zona horaria en todas las filas: {con_zona}; ejemplo: {datos[0][8] if datos else '—'}; valor: {datos[0][9] if datos else '—'}")
estado, resp, _ = api("/exportaciones", "POST", {**CUERPO, "formato": "xlsx"}, cliente)
id_x = resp["exportacion"]["id_exprtcn"]
esperar(id_x, cliente)
clave_x = sql("select objeto_clave from exprtcn where id_exprtcn=:i", i=id_x)[0][0]
libro = load_workbook(e.BUCKET / clave_x, read_only=True)
filas_x = list(libro.active.values)
libro.close()
log(f"   XLSX: {len(filas_x) - 1} filas; cabecera igual a la del CSV: {list(filas_x[0]) == cabecera}")
veredicto("contenido", len(datos) == esperadas == len(filas_x) - 1 and con_zona and list(filas_x[0]) == cabecera and len(cabecera) == 11,
          "todas las filas coinciden con la BD, 11 columnas y fecha con zona horaria")

# 3. Filtros reproducibles
log("\n3. Filtros conservados con el trabajo")
log(f"   fltrs_aplcds de #{ids[-1]}: rango {filtros['fecha_inicio']} a {filtros['fecha_fin']}, proyectos {filtros['ubicacion_ids']}, dispositivos {filtros['dispositivo_ids']}, parámetros {filtros['parametro_ids']}")
veredicto("filtros", filtros["fecha_inicio"].startswith("2026-10-29") and bool(filtros["ubicacion_ids"]), "los filtros quedan persistidos con el trabajo")

# 4. Aislamiento con otro administrador y con identificadores manipulados
log("\n4. Aislamiento: otro administrador y un identificador inexistente")
a = api(f"/exportaciones/{ids[-1]}", token=admin)[0]
b = api(f"/exportaciones/{ids[-1]}/descarga", "POST", token=admin)[0]
c = api("/exportaciones/99999999", token=cliente)[0]
listado = api("/exportaciones", token=admin)[1]["items"]
log(f"   admin consulta #{ids[-1]} -> {a}; admin descarga -> {b}; cliente consulta id inexistente -> {c}; el listado del admin incluye el trabajo del cliente: {any(i['id_exprtcn'] == ids[-1] for i in listado)}")
veredicto("aislamiento", a == 404 and b == 404 and c == 404 and not any(i["id_exprtcn"] == ids[-1] for i in listado), "404 para otro administrador y para un id inexistente")

# 5. Vigencia: misma fecha límite tras recargar y descargar de nuevo
log("\n5. Vigencia y descarga")
antes = api(f"/exportaciones/{ids[-1]}", token=cliente)[1]["fch_exprcn"]
firmas_antes = len(e.FIRMAS.read_text().splitlines()) if e.FIRMAS.exists() else 0
urls = [api(f"/exportaciones/{ids[-1]}/descarga", "POST", token=cliente)[1]["url"] for _ in range(3)]
despues = api(f"/exportaciones/{ids[-1]}", token=cliente)[1]["fch_exprcn"]
firmas = [json.loads(x) for x in e.FIRMAS.read_text().splitlines()[firmas_antes:]]
log(f"   fecha límite antes {antes}; después de 3 descargas {despues}; segundos de cada firma: {[f['segundos'] for f in firmas]}")
fin = sql("select fch_exprcn - fch_fin, fch_fin from exprtcn where id_exprtcn=:i", i=ids[-1])[0]
log(f"   fecha límite - fin de la generación = {fin[0]} (24 h exactas desde que quedó lista)")
veredicto("vigencia", antes == despues and all(f["segundos"] <= 60 for f in firmas) and str(fin[0]).startswith("1 day, 0:00:00"), "misma fecha, firmas de 60 s o menos y 24 h desde el fin")

# 6. Notificación por SMTP real y reintento sin regenerar
log("\n6. Notificación por SMTP (servidor local con STARTTLS)")
recibidos = sorted(CORREOS.glob("*.eml"))
ultimo = email.message_from_bytes(recibidos[-1].read_bytes()) if recibidos else None
if ultimo:
    cuerpo = ultimo.get_payload(decode=True).decode()
    log(f"   {len(recibidos)} correos recibidos; último para {ultimo['To']}, asunto «{ultimo['Subject']}», adjuntos: {ultimo.is_multipart()}")
    log("   cuerpo: " + cuerpo.replace("\n", " | ")[:260])
    veredicto("correo", "consulta-datos?exportacion=" in cuerpo and "Disponible hasta" in cuerpo and not ultimo.is_multipart(), "enlace a la aplicación y fecha de caducidad, sin adjuntos")
else:
    veredicto("correo", False, "no llegó ningún correo")
log("   Se detiene el SMTP, se solicita una exportación y se vuelve a levantar el SMTP")
smtp.terminate()
smtp.wait()
estado, resp, _ = api("/exportaciones", "POST", CUERPO, cliente)
id_r = resp["exportacion"]["id_exprtcn"]
item = esperar(id_r, cliente)
time.sleep(5)
item = api(f"/exportaciones/{id_r}", token=cliente)[1]
clave_r = sql("select objeto_clave, intentos from exprtcn where id_exprtcn=:i", i=id_r)[0]
log(f"   con SMTP caído: estado={item['estd']}, notificación={item['notificacion_estado']}, archivo disponible hasta {item['fch_exprcn']}")
descarga_sin_correo = api(f"/exportaciones/{id_r}/descarga", "POST", token=cliente)[0]
log(f"   descarga mientras el correo falla -> {descarga_sin_correo}")
smtp = iniciar_smtp()
inicio = time.time()
for _ in range(100):
    item = api(f"/exportaciones/{id_r}", token=cliente)[1]
    if item["notificacion_estado"] == "Enviada":
        break
    time.sleep(3)
clave_r2 = sql("select objeto_clave, intentos from exprtcn where id_exprtcn=:i", i=id_r)[0]
log(f"   tras volver el SMTP: notificación={item['notificacion_estado']} en {time.time() - inicio:.0f} s; misma clave de archivo: {clave_r == clave_r2}; intentos de generación: {clave_r2[1]}")
veredicto("reintento_correo", item["notificacion_estado"] == "Enviada" and clave_r == clave_r2 and descarga_sin_correo == 200 and clave_r2[1] == 1,
          "el archivo siguió disponible y el correo se reintentó sin regenerarlo")

# 7. Limpieza con Beat real
log("\n7. Limpieza con Beat y worker reales")
sql_obj = sql("select objeto_clave from exprtcn where id_exprtcn=:i", i=ids[0])[0][0]
with SessionLocal() as db:
    db.execute(text("update exprtcn set fch_exprcn = now() - interval '1 second' where id_exprtcn=:i"), {"i": ids[0]})
    db.commit()
t0 = time.time()
borrado = False
for _ in range(120):
    estado_bd = sql("select estd, objeto_clave from exprtcn where id_exprtcn=:i", i=ids[0])[0]
    if estado_bd[0] == "Expirada" and not (e.BUCKET / sql_obj).exists():
        borrado = True
        break
    time.sleep(3)
seg = time.time() - t0
log(f"   vencimiento forzado; Beat/worker lo limpiaron en {seg:.0f} s; estado {estado_bd[0]}; objeto en el almacén: {(e.BUCKET / sql_obj).exists()}")
log(f"   descarga posterior -> {api(f'/exportaciones/{ids[0]}/descarga', 'POST', token=cliente)[0]}")
veredicto("limpieza", borrado and seg <= 300, "objeto vencido eliminado en menos de 5 minutos")

smtp.terminate()
log("\nRESUMEN: " + "; ".join(f"{k}={'ok' if v else 'FALLA'}" for k, v in resultados.items()))
SALIDA.write_text("\n".join(lineas) + "\n", encoding="utf-8")
