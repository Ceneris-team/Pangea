"""DEF-18: byte NUL en la búsqueda de GET /parametros-calculados provoca 500 (API real).

Uso desde backend/: python def18_repro.py <salida.txt>
Creado por Elliot_QA | Aseguramiento de Calidad.
"""
import json, os, sys, urllib.error, urllib.request
sys.path.insert(0, os.getcwd())
from app.scripts.seed_usuarios_prueba import PASSWORD_PRUEBA  # noqa: E402

API = "http://127.0.0.1:8000"
def llamar(metodo, ruta, cuerpo=None, cookie=None):
    h = {"Content-Type": "application/json", "X-Cliente-Id": "1"}
    if cookie: h["Cookie"] = cookie
    req = urllib.request.Request(API + ruta, method=metodo, headers=h, data=json.dumps(cuerpo).encode() if cuerpo else None)
    try:
        with urllib.request.urlopen(req) as r: return r.status, r.headers.get("Set-Cookie"), r.read()[:100]
    except urllib.error.HTTPError as e: return e.code, None, e.read()[:100]

st, sc, _ = llamar("POST", "/auth/login", {"correo": "tecnico@pangea-dev.com", "contrasena": PASSWORD_PRUEBA})
assert st == 200, st
cookie = sc.split(";", 1)[0]
lineas = ["DEF-18 · reproducción contra la API real (uvicorn 127.0.0.1:8000, dev 78edb10), sesión Técnico CENERIS, X-Cliente-Id=1"]
for ruta in ["/parametros-calculados?q=caudal", "/parametros-calculados?q=caudal%00", "/parametros-calculados?q=%00&estado=Activo"]:
    st, _, cuerpo = llamar("GET", ruta, cookie=cookie)
    lineas.append(f"GET {ruta} -> {st} {cuerpo.decode(errors='replace')[:80]}")
open(sys.argv[1], "w", encoding="utf-8").write("\n".join(lineas) + "\n")
print("\n".join(lineas))
