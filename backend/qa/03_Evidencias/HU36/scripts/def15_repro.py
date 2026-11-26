"""DEF-15: reproduce el 500 con byte NUL en filtros de GET /dispositivos (API real).

Uso desde backend/: python def15_repro.py <salida.txt>
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.getcwd())
from app.scripts.seed_usuarios_prueba import PASSWORD_PRUEBA  # noqa: E402

API = "http://127.0.0.1:8000"


def llamar(metodo, ruta, cuerpo=None, cookie=None):
    h = {"Content-Type": "application/json", "X-Cliente-Id": "1"}
    if cookie:
        h["Cookie"] = cookie
    req = urllib.request.Request(API + ruta, method=metodo, headers=h,
                                 data=json.dumps(cuerpo).encode() if cuerpo else None)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.headers.get("Set-Cookie"), r.read()[:120]
    except urllib.error.HTTPError as e:
        return e.code, None, e.read()[:120]


st, sc, _ = llamar("POST", "/auth/login", {"correo": "tecnico@pangea-dev.com", "contrasena": PASSWORD_PRUEBA})
assert st == 200, st
cookie = sc.split(";", 1)[0]
lineas = ["DEF-15 · reproducción contra la API real (uvicorn 127.0.0.1:8000), sesión Técnico CENERIS"]
casos = [
    "/dispositivos?marca=Campbell",
    "/dispositivos?marca=Campbell%00",
    "/dispositivos?estado=Activo%00",
    "/dispositivos?busqueda=Campbell%00",
    "/dispositivos?marca=%00",
]
for ruta in casos:
    resultados = [llamar("GET", ruta, cookie=cookie)[0] for _ in range(3)]
    lineas.append(f"GET {ruta:40} -> {resultados}  (3/3)" if len(set(resultados)) == 1 else f"GET {ruta} -> {resultados}")
texto = "\n".join(lineas)
print(texto)
open(sys.argv[1], "w", encoding="utf-8").write(texto + "\n")
