"""QA HU36 (PP-436): E2E contra la app REAL (backend + frontend de qa-elliot).

Sin respuestas simuladas: login real del Técnico CENERIS sembrado por
app.scripts.seed_usuarios_prueba y datos de app.scripts.seed_dispositivos_demo.
Cubre CP-505 a CP-512 en pantalla. Cada corrida usa una etiqueta propia para
la ubicación vacía y la marca nueva, así puede repetirse sin limpiar la base.

Uso (desde backend/, con API en 127.0.0.1:8000 y Vite en 127.0.0.1:5180):
    python qa_hu36_e2e_real.py <dir_evidencias> [ancho]
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

from playwright.sync_api import expect, sync_playwright

API = os.environ.get("HU36_API", "http://127.0.0.1:8000")
UI = os.environ.get("HU36_REAL_URL", "http://127.0.0.1:5180")
EVID = sys.argv[1]
ANCHO = int(sys.argv[2]) if len(sys.argv) > 2 else 1365
CORREO = "tecnico@pangea-dev.com"
sys.path.insert(0, os.getcwd())
from app.scripts.seed_usuarios_prueba import PASSWORD_PRUEBA  # noqa: E402  (valor de prueba del repo)

TAG = time.strftime("%H%M%S")
UB_VACIA = f"QA36 Sin equipos {TAG}"
MARCA_NUEVA = f"Vaisala {TAG}"
POLIGONO = {
    "type": "Polygon",
    "coordinates": [[[-77.0, -12.0], [-77.0, -12.01], [-77.01, -12.01], [-77.0, -12.0]]],
}
resultados = []


def caso(cp, que, ok, detalle=""):
    resultados.append({"cp": cp, "que": que, "ok": bool(ok), "detalle": str(detalle)})
    print(f"{'PASA ' if ok else 'FALLA'} {cp} · {que} · {detalle}", flush=True)


class Api:
    # La cookie de sesión es Secure: urllib no la reenvía por http, así que se
    # guarda del Set-Cookie del login y se envía a mano (el navegador sí la acepta
    # en 127.0.0.1).
    def __init__(self):
        self.cookie = None

    def llamar(self, metodo, ruta, cuerpo=None):
        headers = {"Content-Type": "application/json", "Origin": UI}
        if self.cookie:
            headers["Cookie"] = self.cookie
        req = urllib.request.Request(
            API + ruta,
            method=metodo,
            data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req) as r:
                sc = r.headers.get("Set-Cookie")
                if sc:
                    self.cookie = sc.split(";", 1)[0]
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")


def preparar(cookie):
    """Datos del escenario con la sesión del navegador (un solo login por corrida,
    el endpoint de login permite 5 cada 5 minutos)."""
    api = Api()
    api.cookie = cookie
    st, ub = api.llamar(
        "POST",
        "/ubicaciones",
        {"nmbr": UB_VACIA, "lttd": -12.0, "lngtd": -77.0, "plgn_gjsn": POLIGONO, "id_sd": 1},
    )
    assert st == 201, (st, ub)
    st, cx = api.llamar(
        "POST",
        "/conexiones-ftp",
        {
            "nmbr": f"QA36 FTP {TAG}",
            "hst": "127.0.0.1",
            "prt": 21,
            "usr_ftp": "qa36",
            "contrasena_ftp": "qa36-prueba",
            "rt_rmt": "/qa36",
            "frcnc_mnts": 60,
            "id_sd": 1,
        },
    )
    assert st == 201, (st, cx)
    _, marcas = api.llamar("GET", "/dispositivos/marcas")
    _, ubics = api.llamar("GET", "/dispositivos/ubicaciones")
    _, todos = api.llamar("GET", "/dispositivos?por_pagina=100")
    return marcas["items"], ubics["items"], todos["items"]


def texto_filas(filas):
    """Texto de la tabla con espacios normalizados (los nombres largos se
    parten en dos líneas dentro de la celda)."""
    return " ".join(" ".join(filas.all_inner_texts()).split())


def esperar(filas, n, **kw):
    """La fila «Cargando datos...» también es un <tr>: se espera a que
    desaparezca antes de contar, para no leer la tabla a medio cargar."""
    expect(filas.page.get_by_text("Cargando datos...")).to_have_count(0, timeout=15000)
    expect(filas).to_have_count(n, **kw)


def opciones(select):
    return [o.strip() for o in select.locator("option").all_inner_texts()]


def main():
    errores = []
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="msedge", headless=True)
        pag = nav.new_page(viewport={"width": ANCHO, "height": 1000})
        pag.on("pageerror", lambda e: errores.append(str(e)))
        try:
            pag.goto(f"{UI}/login")
            pag.locator("#email").fill(CORREO)
            pag.locator("#password").fill(PASSWORD_PRUEBA)
            pag.locator("button[type=submit]").click()
            pag.wait_for_url(lambda u: "/login" not in u, timeout=15000)
            ck = next(c for c in pag.context.cookies() if c["domain"] in ("127.0.0.1", "localhost"))
            marcas_api, _, equipos = preparar(f"{ck['name']}={ck['value']}")
            marcas_bd = sorted({e["mrc"] for e in equipos})
            ubics_bd = sorted({e["ubicacion_nombre"] for e in equipos})
            # Técnico CENERIS (scope global) elige primero la empresa a operar.
            pag.get_by_role("button", name="Entrar al entorno de Cliente Demo").click()
            pag.wait_for_load_state("networkidle")
            pag.goto(f"{UI}/dispositivos")
            marca = pag.get_by_role("combobox", name="Filtrar por marca")
            proyecto = pag.get_by_role("combobox", name="Filtrar por proyecto")
            estado = pag.get_by_role("combobox", name="Filtrar por estado")
            filas = pag.locator("tbody tr")
            expect(marca).to_be_enabled(timeout=15000)
            expect(filas.first).to_be_visible()
            total = len(equipos)
            cab = [h.strip().lower() for h in pag.locator("thead th").all_inner_texts()]

            def col(nombre):
                i = next(k for k, h in enumerate(cab) if h.startswith(nombre)) + 1
                return [c.strip() for c in pag.locator(f"tbody tr td:nth-child({i})").all_inner_texts()]

            # CP-510 / CP-511: catálogos de los selectores
            om = opciones(marca)[1:]
            caso("CP-510", "selector de marcas = marcas registradas", om == marcas_bd == marcas_api, om)
            op = opciones(proyecto)[1:]
            caso("CP-511", "selector de ubicaciones = solo con ≥1 equipo",
                 sorted(op) == ubics_bd and UB_VACIA not in op, op)

            # CP-505: marca
            marca.select_option("Campbell")
            esperar(filas, sum(e["mrc"] == "Campbell" for e in equipos))
            caso("CP-505", "filtro por marca Campbell", set(col("marca")) == {"Campbell"}, col("marca"))
            pag.screenshot(path=os.path.join(EVID, f"EV-CP-505_real-marca-{ANCHO}.png"), full_page=True)
            marca.select_option("")

            # CP-506: ubicación
            planta = next(u for u in op if "Planta" in u)
            proyecto.select_option(label=planta)
            esperado = sum(e["ubicacion_nombre"] == planta for e in equipos)
            esperar(filas, esperado)
            nombres = [e["nmbr"] for e in equipos if e["ubicacion_nombre"] == planta]
            texto = texto_filas(filas)
            caso("CP-506", f"filtro por ubicación {planta}", all(n in texto for n in nombres), f"{esperado} filas")
            pag.screenshot(path=os.path.join(EVID, f"EV-CP-506_real-ubicacion-{ANCHO}.png"), full_page=True)
            proyecto.select_option("")

            # CP-507: estado
            estado.select_option("Inactivo")
            inact = [e["nmbr"] for e in equipos if e["estd"] == "Inactivo"]
            esperar(filas, len(inact))
            texto = texto_filas(filas)
            caso("CP-507", "filtro por estado Inactivo", all(n in texto for n in inact), inact)
            estado.select_option("")

            # CP-508: acumulativo marca + ubicación (+ estado sin coincidencias)
            marca.select_option("Campbell")
            proyecto.select_option(label=planta)
            esp = [e["nmbr"] for e in equipos if e["mrc"] == "Campbell" and e["ubicacion_nombre"] == planta]
            esperar(filas, len(esp))
            texto = texto_filas(filas)
            caso("CP-508", "Campbell + Planta (AND)", all(n in texto for n in esp), esp)
            pag.screenshot(path=os.path.join(EVID, f"EV-CP-508_real-combinados-{ANCHO}.png"), full_page=True)
            estado.select_option("Inactivo")
            vacio = pag.get_by_text("No se encontraron dispositivos con ese criterio.")
            expect(vacio).to_be_visible()
            caso("CP-508", "Campbell + Planta + Inactivo → sin coincidencias", vacio.is_visible())

            # CP-509: Limpiar filtros
            limpiar = pag.get_by_role("button", name="Limpiar filtros")
            rotulo = limpiar.inner_text()
            limpiar.click()
            for s in (marca, proyecto, estado):
                expect(s).to_have_value("")
            esperar(filas, min(total, 10))
            caso("CP-509", "Limpiar filtros restaura el listado",
                 all(s.input_value() == "" for s in (marca, proyecto, estado)),
                 f"{filas.count()} filas · rótulo «{rotulo}»")
            pag.screenshot(path=os.path.join(EVID, f"EV-CP-509_real-limpiar-{ANCHO}.png"), full_page=True)

            # CP-512: alta con marca y ubicación nuevas
            pag.get_by_role("button", name="Añadir dispositivo").first.click()
            pag.locator("#nmbr").fill(f"QA36 Equipo {TAG}")
            pag.locator("#mrc").fill(MARCA_NUEVA)
            pag.locator("#id_ubccn").select_option(label=UB_VACIA)
            pag.locator("#id_cnxn").select_option(label=f"QA36 FTP {TAG}")
            pag.get_by_role("button", name="GUARDAR", exact=False).last.click()
            expect(marca.locator("option", has_text=MARCA_NUEVA)).to_have_count(1, timeout=10000)
            expect(proyecto.locator("option", has_text=UB_VACIA)).to_have_count(1)
            marca.select_option(MARCA_NUEVA)
            esperar(filas, 1)
            caso("CP-512", "alta con marca/ubicación nuevas refresca selectores", True, MARCA_NUEVA)
            pag.screenshot(path=os.path.join(EVID, f"EV-CP-512_real-alta-{ANCHO}.png"), full_page=True)
            caso("UI", "sin errores JS en la página", not errores, errores)
        except Exception as e:  # el caso en curso queda Fallido con su causa
            pag.screenshot(path=os.path.join(EVID, f"EV-HU36_real-error-{ANCHO}.png"), full_page=True)
            caso("ERROR", "excepción en el flujo", False, repr(e)[:400])
        finally:
            nav.close()
    with open(os.path.join(EVID, f"e2e_real_{ANCHO}.json"), "w", encoding="utf-8") as f:
        json.dump({"ancho": ANCHO, "tag": TAG, "resultados": resultados}, f, ensure_ascii=False, indent=2)
    sys.exit(0 if all(r["ok"] for r in resultados) else 1)


if __name__ == "__main__":
    main()
