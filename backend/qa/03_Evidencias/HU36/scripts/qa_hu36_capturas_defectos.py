"""QA HU36 (PP-436): capturas de los casos fallidos en la app REAL.

DEF-17 (CP-510): registra 4 equipos con la misma marca escrita distinto y captura
el selector de marcas desplegado. DEF-16 (CP-506, CP-509): captura los rótulos
«Proyecto» y «Limpiar filtros». DEF-15 (CP-514): abre en el navegador
GET /dispositivos con %00 y captura la respuesta 500.
Un solo login por corrida. Uso desde backend/: python qa_hu36_capturas_defectos.py <dir>
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.getcwd())
from app.scripts.seed_usuarios_prueba import PASSWORD_PRUEBA  # noqa: E402  (valor de prueba del repo)

API, UI, EVID = "http://127.0.0.1:8000", "http://127.0.0.1:5180", sys.argv[1]
TAG = time.strftime("%H%M%S")
MARCA = f"Hobo{TAG}"


def api(cookie, metodo, ruta, cuerpo=None):
    req = urllib.request.Request(
        API + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo else None,
        headers={"Content-Type": "application/json", "Cookie": cookie, "X-Cliente-Id": "1"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


with sync_playwright() as p:
    nav = p.chromium.launch(channel="msedge", headless=True)
    pag = nav.new_page(viewport={"width": 1365, "height": 900})
    pag.goto(f"{UI}/login")
    pag.locator("#email").fill("tecnico@pangea-dev.com")
    pag.locator("#password").fill(PASSWORD_PRUEBA)
    pag.locator("button[type=submit]").click()
    pag.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    pag.get_by_role("button", name="Entrar al entorno de Cliente Demo").click()
    pag.wait_for_load_state("networkidle")
    ck = next(c for c in pag.context.cookies() if c["domain"] in ("127.0.0.1", "localhost"))
    cookie = f"{ck['name']}={ck['value']}"

    # Datos DEF-17: la misma marca escrita de 4 formas (como la registraría un usuario)
    _, ubs = api(cookie, "GET", "/dispositivos/ubicaciones")
    id_ub = next(u["id_ubccn"] for u in ubs["items"] if "Planta" in u["nmbr"])
    for i, m in enumerate([MARCA, MARCA.lower(), f" {MARCA}", f"{MARCA} "]):
        st, cx = api(cookie, "POST", "/conexiones-ftp", {
            "nmbr": f"QA36 FTP var{i} {TAG}", "hst": "127.0.0.1", "prt": 21, "usr_ftp": "qa36",
            "contrasena_ftp": "qa36-prueba", "rt_rmt": "/qa36", "frcnc_mnts": 60, "id_sd": 1})
        assert st == 201, st
        st, _ = api(cookie, "POST", "/dispositivos", {
            "nmbr": f"QA36 Var{i} {TAG}", "mrc": m, "id_ubccn": id_ub, "id_cnxn": cx["conexion"]["id_cnxn"]
            if "conexion" in cx else cx.get("id_cnxn")})
        assert st == 201, st

    pag.goto(f"{UI}/dispositivos")
    marca = pag.get_by_role("combobox", name="Filtrar por marca")
    expect(marca).to_be_enabled(timeout=15000)
    expect(pag.get_by_text("Cargando datos...")).to_have_count(0, timeout=15000)

    # DEF-16: rótulos (con un filtro aplicado para que aparezca el botón)
    marca.select_option("Campbell")
    expect(pag.get_by_role("button", name="Limpiar filtros")).to_be_visible()
    expect(pag.get_by_text("Cargando datos...")).to_have_count(0, timeout=15000)
    caja = pag.locator("table").bounding_box()
    filtros = pag.get_by_role("combobox", name="Filtrar por proyecto").bounding_box()
    y0 = filtros["y"] - 20
    pag.screenshot(path=os.path.join(EVID, "EV-CP-506-509_DEF-16_rotulos.png"),
                   clip={"x": caja["x"] - 10, "y": y0, "width": caja["width"] + 20,
                         "height": caja["y"] + 110 - y0})

    # DEF-17: selector de marcas desplegado (size para mostrar todas las opciones en la captura)
    marca.select_option("")
    opciones = [o.strip() for o in marca.locator("option").all_inner_texts()]
    h = marca.element_handle()  # con size>1 el rol pasa de combobox a listbox
    h.evaluate("(s) => { s.size = s.options.length; s.style.height = 'auto'; s.style.position='relative'; s.style.zIndex=50; }")
    b = h.bounding_box()
    pag.screenshot(path=os.path.join(EVID, "EV-CP-510_DEF-17_marcas-repetidas.png"),
                   clip={"x": b["x"] - 220, "y": b["y"] - 15, "width": b["width"] + 240, "height": b["height"] + 30})
    repetidas = [o for o in opciones if o.strip().lower() == MARCA.lower()]

    # DEF-15: la API real abierta en el navegador con %00
    ctx2 = nav.new_context(viewport={"width": 900, "height": 260})
    ctx2.add_cookies(pag.context.cookies())  # misma sesión, sin otro login
    api_tab = ctx2.new_page()
    api_tab.set_extra_http_headers({"X-Cliente-Id": "1"})
    estados = {}
    for nombre, ruta in [("ok", "/dispositivos?marca=Campbell&por_pagina=1"), ("nul", "/dispositivos?marca=Campbell%00")]:
        r = api_tab.goto(API + ruta)
        estados[nombre] = r.status
        api_tab.evaluate(f"""(s) => {{ const d=document.createElement('div');
            d.style='font:13px Segoe UI;background:#1f3a5f;color:#fff;padding:6px 10px';
            d.textContent='GET {API}{ruta}  →  HTTP ' + s; document.body.prepend(d); }}""", r.status)
        api_tab.screenshot(path=os.path.join(EVID, f"EV-CP-514_DEF-15_api-{nombre}.png"))
    nav.close()

res = {"tag": TAG, "marca": MARCA, "opciones_marca": opciones, "repetidas": repetidas, "http": estados}
json.dump(res, open(os.path.join(EVID, "capturas_defectos.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(json.dumps(res, ensure_ascii=False))
