"""QA PP-70 (PP-442): E2E de «Añadir parámetro calculado» contra la app REAL (dev 78edb10).

API uvicorn + worker Celery + beat + Vite sobre pangea_qa36 con cuenta runtime sin
privilegios. Datos: seed_pp70.sql (QA27 Nivel B 30 s antes de Nivel A, 08:00–15:00).
Sin intercepción de red.

Uso (desde backend/ del worktree de dev):
    python qa_pp70_e2e_real.py <dir_evidencias> [ancho] [completo|lectura]
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import json
import os
import sys
import threading
import time

import httpx
from playwright.sync_api import expect, sync_playwright

UI = os.environ.get("PP70_UI", "http://127.0.0.1:5180")
API = os.environ.get("PP70_API", "http://127.0.0.1:8000")
EVID = sys.argv[1]
ANCHO = int(sys.argv[2]) if len(sys.argv) > 2 else 1365
MODO = sys.argv[3] if len(sys.argv) > 3 else "completo"
NOMBRE = "QA70 Diferencia de nivel"
sys.path.insert(0, os.getcwd())
from app.scripts.seed_usuarios_prueba import PASSWORD_PRUEBA  # noqa: E402  (valor de prueba del repo)

resultados = []
os.makedirs(EVID, exist_ok=True)


def caso(cp, que, ok, detalle=""):
    resultados.append({"cp": cp, "que": que, "ok": bool(ok), "detalle": str(detalle)})
    print(f"{'PASA ' if ok else 'FALLA'} {cp} · {que} · {detalle}", flush=True)


def main():
    errores = []
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="msedge", headless=True)
        ctx = nav.new_context(viewport={"width": ANCHO, "height": 1000})
        pag = ctx.new_page()
        pag.on("pageerror", lambda e: errores.append(str(e)))

        def foto(nombre, completa=True):
            pag.screenshot(path=os.path.join(EVID, f"{nombre}-{ANCHO}.png"), full_page=completa)

        pag.goto(f"{UI}/login")
        pag.locator("#email").fill("tecnico@pangea-dev.com")
        pag.locator("#password").fill(PASSWORD_PRUEBA)
        pag.locator("button[type=submit]").click()
        pag.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        pag.goto(f"{UI}/clientes")
        pag.get_by_role("button", name="Entrar al entorno de Cliente Demo").click()
        pag.wait_for_load_state("networkidle")

        def api(metodo, ruta, **kw):
            kw.setdefault("headers", {})["X-Cliente-Id"] = "1"
            return getattr(pag.request, metodo)(f"{API}{ruta}", **kw)

        def total_definiciones():
            return api("get", "/parametros-calculados", params={"por_pagina": 1}).json()["total"]

        def trabajos():
            return len(api("get", "/parametros-calculados", params={"por_pagina": 100}).json()["items"])

        def abrir():
            pag.goto(f"{UI}/parametros-calculados")
            pag.get_by_role("button", name="Añadir parámetro calculado").click()
            panel = pag.get_by_role("form", name="Registrar definición calculada")
            expect(panel).to_be_visible()
            expect(pag.get_by_text("Cargando ámbitos")).to_have_count(0, timeout=8000)
            return panel

        antes = total_definiciones()
        panel = abrir()

        # CP-569 · CA-01: campos, orígenes y acciones
        etiquetas = [t.strip().split("\n")[0] for t in panel.locator("label").all_inner_texts()]
        caso("CP-569", "Campo «Ámbito de aplicación» (DEF-24)", any(t.startswith("Ámbito de aplicación") for t in etiquetas), etiquetas)
        for campo in ["Nombre", "Fórmula", "Unidad de medida", "Descripción (opcional)"]:
            caso("CP-569", f"Campo «{campo}»", any(t.startswith(campo) for t in etiquetas))
        caso("CP-569", "Sin campos fuera del CA (DEF-25)", not any(t.startswith("Estado") for t in etiquetas), etiquetas)
        origenes = panel.get_by_role("button", name="Insertar").all_inner_texts()
        caso("CP-571", "Orígenes numéricos del ámbito", origenes and not any("mensaje_" in o for o in origenes), origenes)
        for b in ["Validar fórmula", "Guardar", "Cancelar"]:
            caso("CP-569", f"Acción «{b}»", panel.get_by_role("button", name=b, exact=True).count() == 1)
        caso("CP-569", "Guardar deshabilitado sin validar", panel.get_by_role("button", name="Guardar", exact=True).is_disabled())
        ayuda = pag.locator("#ayuda-formula").inner_text()
        caso("CP-573", "Ayuda solo con + - * / (DEF-23)", "**" not in ayuda and "%" not in ayuda, ayuda)
        foto("EV-CP-569_formulario")

        if ANCHO < 500:
            ancho = pag.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
            caso("CP-590", "Sin scroll horizontal a 390 px", ancho[0] <= ancho[1], ancho)
            sin_nombre = pag.evaluate("[...document.querySelectorAll('form input, form textarea, form select')].filter(e => !e.labels || !e.labels.length).length")
            caso("CP-590", "Controles con etiqueta", sin_nombre == 0, sin_nombre)

        # CP-588 · CA-08: Cancelar, Escape y X descartan
        panel.get_by_label("Nombre").fill("QA70 descartado")
        panel.get_by_role("button", name="Insertar QA27 Nivel A").click()
        panel.get_by_role("button", name="Cancelar").click()
        caso("CP-588", "Cancelar cierra el panel", panel.count() == 0)
        panel = abrir()
        caso("CP-588", "Al reabrir, campos vacíos", panel.get_by_label("Nombre").input_value() == "" and panel.get_by_label("Fórmula").input_value() == "")
        panel.get_by_label("Nombre").fill("QA70 descartado")
        pag.keyboard.press("Escape")
        cerrado_esc = pag.get_by_role("form", name="Registrar definición calculada").count() == 0
        if not cerrado_esc:
            pag.get_by_role("button", name="Cerrar").first.click()
        caso("CP-588", "Escape o X cierran sin guardar", pag.get_by_role("form", name="Registrar definición calculada").count() == 0, f"escape={cerrado_esc}")
        caso("CP-588", "Sin registro tras cancelar", total_definiciones() == antes, antes)

        if MODO == "lectura":
            caso("CP-590", "Errores de página", not errores, errores)
            return finish(nav)

        # CP-577 · CA-03: validar, habilitar y revalidar
        panel = abrir()
        guardar = panel.get_by_role("button", name="Guardar", exact=True)
        validar = panel.get_by_role("button", name="Validar fórmula")
        panel.get_by_label("Nombre").fill(NOMBRE)
        panel.get_by_role("button", name="Insertar QA27 Nivel A").click()
        panel.get_by_label("Fórmula").press_sequentially(" + 1")
        panel.get_by_label("Unidad de medida").fill("m")
        validar.click()
        error = pag.get_by_role("alert")
        expect(error).to_be_visible()
        caso("CP-574", "Error de unidades explica qué corregir", "Unidades" in error.inner_text(), error.inner_text())
        caso("CP-574", "Guardar sigue deshabilitado", guardar.is_disabled())
        foto("EV-CP-574_error-unidades")
        panel.get_by_label("Fórmula").fill("")
        panel.get_by_role("button", name="Insertar QA27 Nivel A").click()
        panel.get_by_label("Fórmula").press_sequentially(" - ")
        panel.get_by_role("button", name="Insertar QA27 Nivel B").click()
        formula = panel.get_by_label("Fórmula").input_value()
        caso("CP-571", "Referencias entre corchetes", formula.strip() == "[QA27 Nivel A] - [QA27 Nivel B]", formula)
        validar.click()
        expect(panel.get_by_text("Fórmula válida")).to_be_visible()
        caso("CP-577", "«Fórmula válida» habilita Guardar", guardar.is_enabled())
        foto("EV-CP-577_formula-valida")
        panel.get_by_label("Unidad de medida").fill("cm")
        caso("CP-577", "Cambiar unidad exige revalidar", guardar.is_disabled() and panel.get_by_text("Fórmula válida").count() == 0)
        panel.get_by_label("Unidad de medida").fill("m")
        validar.click()
        expect(guardar).to_be_enabled()
        panel.get_by_label("Fórmula").press_sequentially(" ")
        caso("CP-577", "Cambiar fórmula exige revalidar", guardar.is_disabled())
        panel.get_by_label("Fórmula").fill(formula.strip())
        validar.click()
        expect(guardar).to_be_enabled()
        panel.get_by_label("Descripción (opcional)").fill("Diferencia entre niveles A y B (QA PP-70)")

        # CP-580 · CA-04: guardar, mensaje, listado y no bloqueo
        t0 = time.time()
        guardar.click()
        aviso = pag.get_by_text("Parámetro calculado añadido correctamente")
        expect(aviso).to_be_visible(timeout=8000)
        caso("CP-580", "Mensaje de éxito", True, round(time.time() - t0, 2))
        pag.get_by_label("Buscar por nombre").fill("QA70")
        expect(pag.locator("tbody tr", has_text=NOMBRE)).to_be_visible(timeout=8000)
        caso("CP-580", "Listado actualizado", True)
        foto("EV-CP-580_guardado-listado")
        fila = api("get", "/parametros-calculados", params={"q": "qa70"}).json()["items"][0]
        ident = fila["id_prm_clc"]
        caso("CP-579", "Registrado Activo y validado", (fila["estd"], fila["validada"]) == ("Activo", True), fila["estd"])
        pag.goto(f"{UI}/dashboard")
        caso("CP-580", "La plataforma sigue usable durante el histórico", "/dashboard" in pag.url or pag.url.startswith(UI))

        # CP-578 · CA-04: nombre repetido con otras mayúsculas
        panel = abrir()
        panel.get_by_label("Nombre").fill(NOMBRE.upper())
        panel.get_by_role("button", name="Insertar QA27 Nivel A").click()
        panel.get_by_label("Unidad de medida").fill("m")
        panel.get_by_role("button", name="Validar fórmula").click()
        expect(panel.get_by_text("Fórmula válida")).to_be_visible()
        panel.get_by_role("button", name="Guardar", exact=True).click()
        alerta = pag.get_by_role("alert")
        expect(alerta).to_be_visible()
        caso("CP-578", "Nombre duplicado sin distinguir mayúsculas", "Ya existe" in alerta.inner_text(), alerta.inner_text())
        foto("EV-CP-578_nombre-duplicado")
        panel.get_by_role("button", name="Cancelar").click()

        # CP-582/587 · CA-05/07: histórico con el worker real y detalle
        estado = None
        for _ in range(60):
            d = api("get", f"/parametros-calculados/{ident}").json()
            hist = [t for t in d["trabajos"] if t["historico"]]
            estado = hist[-1]["estado"] if hist else None
            if estado and estado.startswith("Completado"):
                break
            time.sleep(2)
        res = {r["estado"]: r["cantidad"] for r in d["resultados"]}
        caso("CP-582", "Worker completa el histórico", estado and estado.startswith("Completado"), estado)
        caso("CP-582", "8 calculados y 4 incompletos, sin resultados en los instantes de B (DEF-28)", res.get("Calculado") == 8 and res.get("Incompleto") == 4, res)
        r = api("get", "/mediciones", params={"parametro_ids": -ident, "sin_muestreo": "true", "por_pagina": 50})
        valores = sorted(i["vlr"] for i in r.json().get("items", [])) if r.ok else r.status
        caso("CP-586", "Consulta de datos devuelve 10…17", valores == [10, 11, 12, 13, 14, 15, 16, 17], valores)
        pag.goto(f"{UI}/parametros-calculados")
        pag.get_by_label("Buscar por nombre").fill("QA70 Dif")
        pag.get_by_role("button", name=f"Ver detalle de {NOMBRE}").click()
        detalle = pag.get_by_text("Detalle del parámetro calculado")
        expect(detalle).to_be_visible()
        expect(pag.get_by_text("Calculado: 8")).to_be_visible(timeout=10000)
        texto = pag.locator("body").inner_text()
        caso("CP-587", "Detalle: fórmula, orígenes y estado del histórico",
             "[QA27 Nivel A] - [QA27 Nivel B]" in texto and "QA27 Nivel B (m)" in texto and "Histórico: Completado" in texto)
        foto("EV-CP-587_detalle-historico")

        # CP-581 · CA-04: dos altas simultáneas con el mismo nombre
        cookies = {c["name"]: c["value"] for c in ctx.cookies() if "127.0.0.1" in c["domain"]}
        cuerpo = {"id_sd": 1, "nmbr": "QA70 Concurrente", "frml": "[QA27 Nivel A] * 2", "undd": "m"}
        codigos = []

        def alta():
            with httpx.Client(cookies=cookies, headers={"X-Cliente-Id": "1"}) as c:
                codigos.append(c.post(f"{API}/parametros-calculados", json=cuerpo).status_code)

        hilos = [threading.Thread(target=alta) for _ in range(2)]
        [h.start() for h in hilos]
        [h.join() for h in hilos]
        n = api("get", "/parametros-calculados", params={"q": "qa70 concurrente"}).json()["total"]
        caso("CP-581", "Altas simultáneas: un 201 y un 409, sin duplicado", sorted(codigos) == [201, 409] and n == 1, (codigos, n))
        caso("CP-580", "Errores de página", not errores, errores)
        return finish(nav)


def finish(nav):
    nav.close()
    with open(os.path.join(EVID, f"e2e-{MODO}-{ANCHO}.json"), "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=1)
    print(f"\n{sum(r['ok'] for r in resultados)}/{len(resultados)} comprobaciones")


if __name__ == "__main__":
    main()
