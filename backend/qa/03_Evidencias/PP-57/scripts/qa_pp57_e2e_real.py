"""QA PP-57 (PP-438): E2E contra la app REAL (backend + frontend de dev 78edb10).

Login real del Técnico CENERIS (seed_usuarios_prueba) y proyectos de seed_pp57.sql:
Cliente Demo tiene 19 proyectos (17 Activa, 2 Inactiva); Empresa QA PP71 tiene
«QA57 Laguna Ajena». Solo CP-536 intercepta la red (error 500 y respuesta lenta).

Uso (desde backend/, con API en 127.0.0.1:8000 y Vite en 127.0.0.1:5180):
    python qa_pp57_e2e_real.py <dir_evidencias> [ancho]
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import json
import os
import sys
import time
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

UI = os.environ.get("PP57_UI", "http://127.0.0.1:5180")
EVID = sys.argv[1]
ANCHO = int(sys.argv[2]) if len(sys.argv) > 2 else 1365
sys.path.insert(0, os.getcwd())
from app.scripts.seed_usuarios_prueba import PASSWORD_PRUEBA  # noqa: E402  (valor de prueba del repo)

TOTAL, INACTIVAS = 19, 2
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
            if urlparse(r.url).path == "/ubicaciones" else None,
        )
        pag.goto(f"{UI}/login")
        pag.locator("#email").fill("tecnico@pangea-dev.com")
        pag.locator("#password").fill(PASSWORD_PRUEBA)
        pag.locator("button[type=submit]").click()
        pag.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        pag.get_by_role("button", name="Entrar al entorno de Cliente Demo").click()
        pag.wait_for_load_state("networkidle")
        pag.goto(f"{UI}/ubicaciones")

        buscar = pag.get_by_role("textbox", name="Buscar por nombre de proyecto")
        estado = pag.get_by_role("combobox", name="Estado del proyecto")
        limpiar = pag.get_by_role("button", name="Limpiar filtros")
        tabla = pag.get_by_role("table", name="Listado de proyectos")
        filas = tabla.locator("tbody tr")
        pie = pag.get_by_text("Mostrando")

        def esperar(total):
            expect(pie).to_contain_text(f"de {total} registros", timeout=8000)
            pag.wait_for_load_state("networkidle")

        def nombres():
            return [t.strip() for t in filas.locator("td:first-child").all_inner_texts()]

        def estados():
            return {t.split("\n")[0].strip() for t in filas.locator("td:nth-child(5)").all_inner_texts()}

        # CP-529 · CA-01
        esperar(TOTAL)
        n = nombres()
        opciones = estado.locator("option").all_inner_texts()
        ok = (buscar.is_visible() and buscar.input_value() == "" and estado.input_value() == ""
              and opciones == ["Todos los estados", "Activo", "Archivado"] and len(n) == 10
              and "QA57 Laguna Ajena" not in n and "Mostrando 1 a 10 de 19" in pie.inner_text())
        foto(pag, "EV-CP-529_listado-inicial")
        caso("CP-529", "Listado autorizado, buscador y «Todos los estados» inicial", ok,
             f"opciones={opciones}; filas={len(n)}; pie='{pie.inner_text()}'")

        # CP-539 · orden alfabético y 10 por página
        caso("CP-539", "Orden alfabético por nombre", n == sorted(n, key=str.lower), n)

        # CP-530 · CA-02
        with pag.expect_response(lambda r: "busqueda=" in r.url):
            buscar.fill("  LAGUNA  ")
        esperar(2)
        n = nombres()
        ultima = consultas[-1]
        caso("CP-530", "Parcial, sin mayúsculas ni espacios", sorted(n) == ["QA57 Laguna Norte", "QA57 Laguna Sur"]
             and ultima.get("busqueda") == ["LAGUNA"], f"{n}; busqueda enviada={ultima.get('busqueda')}")
        foto(pag, "EV-CP-530_busqueda-laguna")
        buscar.fill("90%")
        esperar(1)
        caso("CP-530", "«%» se busca como texto", nombres() == ["QA57 Canal 90%"], nombres())

        # CP-531 · CA-03
        buscar.fill("")
        esperar(TOTAL)
        estado.select_option("Inactiva")
        esperar(INACTIVAS)
        est_arch = estados()
        n_arch = nombres()
        foto(pag, "EV-CP-531_estado-archivado")
        estado.select_option("Activa")
        esperar(TOTAL - INACTIVAS)
        est_act = estados()
        buscar.fill("norte")
        esperar(1)
        estado.select_option("")
        esperar(2)
        n_todos = nombres()
        caso("CP-531", "Activo/Archivado filtran; «Todos» conserva la búsqueda",
             est_arch == {"Archivado"} and est_act == {"Activo"} and buscar.input_value() == "norte"
             and sorted(n_todos) == ["QA57 Laguna Norte", "QA57 Pozo Norte"],
             f"archivados={n_arch} {est_arch}; activos={est_act}; todos+norte={n_todos}")
        texto_arch = tabla.inner_text()
        caso("CP-531", "Archivado con recogida habilitada (no implica monitoreo detenido)",
             "Recogida habilitada" in texto_arch, "fila QA57 Laguna Norte")

        # CP-532 · CA-04 combinación
        estado.select_option("Inactiva")
        esperar(1)
        n = nombres()
        foto(pag, "EV-CP-532_norte-archivado")
        caso("CP-532", "Nombre + estado simultáneos", n == ["QA57 Laguna Norte"], n)

        # CP-533 · CA-05 página 1 al filtrar; paginar conserva filtros
        limpiar.click()
        esperar(TOTAL)
        buscar.fill("qa")
        esperar(17)
        pag.get_by_role("button", name="Siguiente").click()
        expect(pie).to_contain_text("Mostrando 11 a 17 de 17")
        pag.wait_for_load_state("networkidle")
        q2 = consultas[-1]
        n2 = nombres()
        foto(pag, "EV-CP-533_pagina-2-con-filtro")
        ok_pag = len(n2) == 7 and all("qa" in x.lower() for x in n2) and q2.get("busqueda") == ["qa"] and q2.get("pagina") == ["2"]
        estado.select_option("Inactiva")
        esperar(2)
        q3 = consultas[-1]
        caso("CP-533", "Página 2 conserva filtros; cambiar filtro vuelve a página 1 y actualiza total",
             ok_pag and q3.get("pagina") == ["1"] and "Mostrando 1 a 2 de 2" in pie.inner_text(),
             f"pág2={len(n2)} q={q2}; tras filtro={q3}; pie='{pie.inner_text()}'")

        # CP-534 · CA-06 limpiar
        limpiar.click()
        esperar(TOTAL)
        ok = (buscar.input_value() == "" and estado.input_value() == ""
              and "Mostrando 1 a 10 de 19" in pie.inner_text() and consultas[-1].get("pagina") == ["1"]
              and "QA57 Laguna Ajena" not in tabla.inner_text())
        foto(pag, "EV-CP-534_limpiar-filtros")
        caso("CP-534", "Limpiar: búsqueda vacía, Todos, página 1, misma empresa", ok,
             f"q='{buscar.input_value()}' estado='{estado.input_value()}' consulta={consultas[-1]}")
        caso("CP-534", "Rótulo del botón", limpiar.inner_text().strip().upper() == "LIMPIAR FILTROS",
             limpiar.inner_text())

        # CP-535 · CA-07 sin coincidencias
        buscar.fill("zzz-no-existe")
        esperar(0)
        msg = pag.get_by_text("No se encontraron proyectos con los filtros seleccionados", exact=True)
        ok = msg.is_visible() and limpiar.is_enabled() and buscar.is_editable() and estado.is_enabled()
        foto(pag, "EV-CP-535_sin-coincidencias")
        caso("CP-535", "Mensaje exacto y controles disponibles", ok, msg.inner_text() if msg.count() else "sin mensaje")

        # CP-536 · CA-08 cargando, error y reintento
        limpiar.click()
        esperar(TOTAL)

        def fallar(route):
            time.sleep(1.2)
            route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "Error interno"}))

        pag.route("**/ubicaciones?*", fallar)
        estado.select_option("Inactiva")
        cargando = tabla.get_by_role("status")
        expect(cargando).to_be_visible(timeout=1000)
        txt_carga = cargando.inner_text()
        foto(pag, "EV-CP-536_cargando")
        alerta = pag.get_by_role("alert")
        expect(alerta).to_be_visible(timeout=6000)
        foto(pag, "EV-CP-536_error-consulta")
        txt = alerta.inner_text()
        pag.unroute("**/ubicaciones?*")
        pag.get_by_role("button", name="Reintentar").click()
        esperar(INACTIVAS)
        reint = consultas[-1]
        caso("CP-536", "Cargando, «No se pudo cargar el listado» y reintento conserva filtros",
             "Cargando" in txt_carga and "No se pudo cargar el listado" in txt
             and estado.input_value() == "Inactiva" and reint.get("estado") == ["Inactiva"],
             f"carga='{txt_carga}'; alerta='{txt}'; reintento={reint}")

        # CP-536 · respuesta lenta no pisa la más reciente
        limpiar.click()
        esperar(TOTAL)

        def lenta(route):
            if parse_qs(urlparse(route.request.url).query).get("estado") == ["Activa"]:
                time.sleep(2.5)
            route.continue_()

        pag.route("**/ubicaciones?*", lenta)
        estado.select_option("Activa")
        pag.wait_for_timeout(150)
        estado.select_option("Inactiva")
        pag.wait_for_timeout(4000)
        est = estados()
        foto(pag, "EV-CP-536_respuesta-lenta")
        pag.unroute("**/ubicaciones?*")
        caso("CP-536", "La respuesta lenta (Activo) no reemplaza a Archivado",
             est == {"Archivado"} and f"de {INACTIVAS} registros" in pie.inner_text(), f"estados={est}")

        # CP-537 · aislamiento al cambiar de empresa
        limpiar.click()
        esperar(TOTAL)
        pag.goto(f"{UI}/clientes")
        pag.get_by_role("button", name="Entrar al entorno de Empresa QA PP71").click()
        pag.wait_for_load_state("networkidle")
        pag.goto(f"{UI}/ubicaciones")
        esperar(1)
        n = nombres()
        foto(pag, "EV-CP-537_otra-empresa")
        caso("CP-537", "Otra empresa: solo sus proyectos", n == ["QA57 Laguna Ajena"], n)

        caso("—", "Sin errores de JavaScript en la página", not errores, errores)
        nav.close()
    with open(os.path.join(EVID, f"e2e_real_{ANCHO}.json"), "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)


main()
