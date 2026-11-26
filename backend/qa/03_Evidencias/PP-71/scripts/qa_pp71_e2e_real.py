"""QA PP-71 (PP-437): E2E contra la app REAL (backend + frontend de dev 78edb10).

Login real del Técnico CENERIS sembrado por app.scripts.seed_usuarios_prueba y
definiciones de seed_pp71.sql (14 en Cliente Demo: 9 Activo, 5 Inactivo; 1 en
Empresa QA PP71). Solo CP-524 y CP-525 interceptan la red (error 500 y respuesta
lenta); el resto va sin simulación.

Uso (desde backend/, con API en 127.0.0.1:8000 y Vite en 127.0.0.1:5180):
    python qa_pp71_e2e_real.py <dir_evidencias> [ancho]
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import json
import os
import sys
import time
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

UI = os.environ.get("PP71_UI", "http://127.0.0.1:5180")
EVID = sys.argv[1]
ANCHO = int(sys.argv[2]) if len(sys.argv) > 2 else 1365
sys.path.insert(0, os.getcwd())
from app.scripts.seed_usuarios_prueba import PASSWORD_PRUEBA  # noqa: E402  (valor de prueba del repo)

resultados = []
os.makedirs(EVID, exist_ok=True)


def caso(cp, que, ok, detalle=""):
    resultados.append({"cp": cp, "que": que, "ok": bool(ok), "detalle": str(detalle)})
    print(f"{'PASA ' if ok else 'FALLA'} {cp} · {que} · {detalle}", flush=True)


def foto(pag, nombre):
    pag.screenshot(path=os.path.join(EVID, f"{nombre}-{ANCHO}.png"), full_page=True)


def main():
    errores, consultas = [], []
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="msedge", headless=True)
        pag = nav.new_page(viewport={"width": ANCHO, "height": 1000})
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.on(
            "request",
            lambda r: consultas.append(parse_qs(urlparse(r.url).query))
            if urlparse(r.url).path == "/parametros-calculados" else None,
        )
        pag.goto(f"{UI}/login")
        pag.locator("#email").fill("tecnico@pangea-dev.com")
        pag.locator("#password").fill(PASSWORD_PRUEBA)
        pag.locator("button[type=submit]").click()
        pag.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        pag.get_by_role("button", name="Entrar al entorno de Cliente Demo").click()
        pag.wait_for_load_state("networkidle")
        pag.goto(f"{UI}/parametros-calculados")

        buscar = pag.get_by_role("searchbox", name="Buscar por nombre")
        estado = pag.get_by_role("combobox", name="Estado")
        limpiar = pag.get_by_role("button", name="Limpiar filtros")
        filas = pag.locator("tbody tr")
        pie = pag.get_by_text("Mostrando")
        listado = pag.get_by_role("region", name="Listado de parámetros calculados")

        def esperar(total):
            expect(pie).to_contain_text(f"de {total} registros", timeout=8000)
            pag.wait_for_load_state("networkidle")

        def nombres():
            return filas.locator("td:first-child").all_inner_texts()

        # CP-515 · CA-01
        esperar(14)
        cab = [t.strip().lower() for t in pag.locator("thead th").all_inner_texts()]
        contexto = pag.get_by_label("Contexto del listado").inner_text()
        foto(pag, "EV-CP-515_listado-inicial")
        faltan = [c for c in ("nombre", "unidad", "descripción", "estado") if c not in cab]
        caso("CP-515", "Columnas nombre, unidad, descripción y estado", not faltan,
             f"cabeceras={cab}; faltan={faltan}")
        caso("CP-515", "Contexto visible: Cliente Demo", "Cliente Demo" in contexto, contexto)

        # CP-516 · CA-01 aislamiento
        buscar.fill("caudal")
        esperar(4)
        n = nombres()
        caso("CP-516", "No aparece la definición de otra empresa", "Caudal de otra empresa" not in n, n)

        # CP-517 · CA-02
        buscar.fill("")
        esperar(14)
        with pag.expect_response(lambda r: "q=CAUDAL" in r.url):
            buscar.fill("  CAUDAL  ")
        esperar(4)
        n = nombres()
        ok = len(n) == 4 and all("caudal" in x.lower() for x in n)
        ultima = consultas[-1]
        caso("CP-517", "Parcial, sin mayúsculas ni espacios", ok and ultima.get("q") == ["CAUDAL"],
             f"{n}; q enviada={ultima.get('q')}")
        foto(pag, "EV-CP-517_busqueda-caudal")

        # CP-519 · CA-03
        buscar.fill("")
        esperar(14)
        totales = {}
        for valor, esperado in [("Inactivo", 5), ("Activo", 9), ("", 14)]:
            estado.select_option(valor)
            esperar(esperado)
            est = filas.locator("td:nth-child(4)").all_inner_texts()
            totales[valor or "Todos"] = (len(est), set(est))
            if valor == "Inactivo":
                foto(pag, "EV-CP-519_estado-inactivo")
        ok = (totales["Inactivo"] == (5, {"Inactivo"}) and totales["Activo"] == (9, {"Activo"})
              and totales["Todos"][0] == 10 and totales["Todos"][1] == {"Activo", "Inactivo"})
        opciones = estado.locator("option").all_inner_texts()
        caso("CP-519", "Activo / Inactivo / Todos los estados", ok and opciones[0] == "Todos los estados",
             f"{totales}; opciones={opciones}")

        # CP-520 · CA-04 combinación
        buscar.fill("caudal")
        estado.select_option("Inactivo")
        esperar(2)
        n = nombres()
        caso("CP-520", "Nombre + estado acumulativos; total del filtrado",
             sorted(n) == ["Caudal específico", "Caudal máximo"], n)
        foto(pag, "EV-CP-520_caudal-inactivo")

        # CP-521 · CA-04 paginación
        estado.select_option("")
        buscar.fill("a")
        esperar(13)
        pag.get_by_role("button", name="Siguiente").click()
        expect(pag.get_by_text("Página 2 de 2")).to_be_visible()
        pag.wait_for_load_state("networkidle")
        n = nombres()
        q2 = consultas[-1]
        ok_pag = (len(n) == 3 and all("a" in x.lower() for x in n) and q2.get("q") == ["a"]
                  and q2.get("pagina") == ["2"] and "Mostrando 11 a 13 de 13" in pie.inner_text())
        foto(pag, "EV-CP-521_pagina-2-con-filtro")
        estado.select_option("Activo")
        expect(pag.get_by_text("Página 1 de 1")).to_be_visible()
        q3 = consultas[-1]
        caso("CP-521", "Página 2 conserva filtros; cambiar filtro vuelve a página 1",
             ok_pag and q3.get("pagina") == ["1"], f"pág2={n} q={q2}; tras filtro={q3}")

        # CP-522 · CA-05 limpiar
        buscar.fill("a")
        estado.select_option("Inactivo")
        esperar(5)
        limpiar.click()
        esperar(14)
        ok = (buscar.input_value() == "" and estado.input_value() == ""
              and "Página 1 de 2" in listado.inner_text()
              and "Cliente Demo" in pag.get_by_label("Contexto del listado").inner_text())
        foto(pag, "EV-CP-522_limpiar-filtros")
        caso("CP-522", "Limpiar: búsqueda vacía, Todos, página 1, contexto conservado", ok,
             f"q='{buscar.input_value()}' estado='{estado.input_value()}' consulta={consultas[-1]}")

        # CP-523 · CA-06 sin coincidencias
        buscar.fill("zzz-no-existe")
        esperar(0)
        msg = pag.get_by_text("No se encontraron parámetros calculados")
        ok = msg.is_visible() and limpiar.is_enabled() and buscar.is_editable()
        foto(pag, "EV-CP-523_sin-coincidencias")
        caso("CP-523", "Mensaje sin resultados y condiciones editables", ok,
             msg.inner_text() if msg.count() else "sin mensaje")

        # CP-524 · CA-06 error y reintento
        buscar.fill("")
        esperar(14)
        pag.route("**/parametros-calculados?*", lambda r: r.fulfill(
            status=500, content_type="application/json", body=json.dumps({"detail": "Error interno"})))
        estado.select_option("Inactivo")
        alerta = pag.get_by_role("alert")
        expect(alerta).to_be_visible()
        foto(pag, "EV-CP-524_error-consulta")
        txt = alerta.inner_text()
        pag.unroute("**/parametros-calculados?*")
        pag.get_by_role("button", name="Reintentar listado").click()
        esperar(5)
        reint = consultas[-1]
        caso("CP-524", "Error informado; reintento conserva filtros",
             estado.input_value() == "Inactivo" and reint.get("estado") == ["Inactivo"],
             f"alerta='{txt}'; reintento={reint}")

        # CP-525 · CA-06 respuesta anterior no pisa la reciente
        limpiar.click()
        esperar(14)

        def lenta(route):
            if parse_qs(urlparse(route.request.url).query).get("estado") == ["Activo"]:
                time.sleep(2.5)
            route.continue_()

        pag.route("**/parametros-calculados?*", lenta)
        estado.select_option("Activo")
        pag.wait_for_timeout(150)
        estado.select_option("Inactivo")
        pag.wait_for_timeout(4000)
        est = set(filas.locator("td:nth-child(4)").all_inner_texts())
        foto(pag, "EV-CP-525_respuesta-lenta")
        pag.unroute("**/parametros-calculados?*")
        caso("CP-525", "La respuesta lenta (Activo) no reemplaza a Inactivo",
             est == {"Inactivo"} and "de 5 registros" in pie.inner_text(), f"estados={est}")

        # CP-526 · cambio de empresa
        limpiar.click()
        esperar(14)
        pag.get_by_role("button", name="Siguiente").click()
        expect(pag.get_by_text("Página 2 de 2")).to_be_visible()
        pag.goto(f"{UI}/clientes")
        pag.get_by_role("button", name="Entrar al entorno de Empresa QA PP71").click()
        pag.wait_for_load_state("networkidle")
        pag.goto(f"{UI}/parametros-calculados")
        esperar(1)
        n = nombres()
        ctx = pag.get_by_label("Contexto del listado").inner_text()
        foto(pag, "EV-CP-526_cambio-empresa")
        caso("CP-526", "Nueva empresa: consulta su contexto y página 1",
             n == ["Caudal de otra empresa"] and "Empresa QA PP71" in ctx
             and "Página 1 de 1" in listado.inner_text(), f"{n}; {ctx}")

        caso("—", "Sin errores de JavaScript en la página", not errores, errores)
        nav.close()
    with open(os.path.join(EVID, f"e2e_real_{ANCHO}.json"), "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)


main()
