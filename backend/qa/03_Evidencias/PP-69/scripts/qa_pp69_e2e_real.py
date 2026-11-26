"""QA PP-69 (PP-441): E2E del listado de parámetros calculados contra la app REAL (dev 78edb10).

Datos: seed_pp71.sql + seed_pp69.sql en pangea_qa36 (Cliente Demo: 16 definiciones;
Empresa QA PP71: 1; Empresa QA PP69: 0). Solo CP-563 (permisos.crear=false) y CP-564
(error 500) interceptan la red; el resto va sin simulación.

Uso (desde backend/, con API en 127.0.0.1:8000 y Vite en 127.0.0.1:5180):
    python qa_pp69_e2e_real.py <dir_evidencias> [ancho]
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import json
import os
import sys

from playwright.sync_api import expect, sync_playwright

UI = os.environ.get("PP69_UI", "http://127.0.0.1:5180")
EVID = sys.argv[1]
ANCHO = int(sys.argv[2]) if len(sys.argv) > 2 else 1365
sys.path.insert(0, os.getcwd())
from app.scripts.seed_usuarios_prueba import PASSWORD_PRUEBA  # noqa: E402  (valor de prueba del repo)

VACIO = "Aún no hay parámetros calculados configurados en este contexto"
SIN_COINCIDENCIAS = "No se encontraron parámetros calculados con esos filtros."
resultados = []
os.makedirs(EVID, exist_ok=True)


def caso(cp, que, ok, detalle=""):
    resultados.append({"cp": cp, "que": que, "ok": bool(ok), "detalle": str(detalle)})
    print(f"{'PASA ' if ok else 'FALLA'} {cp} · {que} · {detalle}", flush=True)


def foto(pag, nombre, completa=True):
    pag.screenshot(path=os.path.join(EVID, f"{nombre}-{ANCHO}.png"), full_page=completa)


def main():
    errores = []
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="msedge", headless=True)
        pag = nav.new_page(viewport={"width": ANCHO, "height": 1000})
        pag.on("pageerror", lambda e: errores.append(str(e)))
        pag.goto(f"{UI}/login")
        pag.locator("#email").fill("tecnico@pangea-dev.com")
        pag.locator("#password").fill(PASSWORD_PRUEBA)
        pag.locator("button[type=submit]").click()
        pag.wait_for_url(lambda u: "/login" not in u, timeout=15000)

        def entrar(empresa):
            pag.goto(f"{UI}/clientes")
            pag.get_by_role("button", name=f"Entrar al entorno de {empresa}").click()
            pag.wait_for_load_state("networkidle")
            pag.goto(f"{UI}/parametros-calculados")

        filas = pag.locator("tbody tr")
        pie = pag.get_by_text("Mostrando")
        contexto = pag.get_by_label("Contexto del listado")

        def esperar(total):
            expect(pie).to_contain_text(f"de {total} registros", timeout=8000)
            pag.wait_for_load_state("networkidle")

        def nombres():
            return [t.strip() for t in filas.locator("td:first-child").all_inner_texts()]

        entrar("Cliente Demo")
        esperar(16)

        # CP-555 · CA-01 contexto y aislamiento (página 1 y 2)
        ctx = contexto.inner_text()
        pagina1 = nombres()
        estados1 = filas.locator("td:nth-child(4)").all_inner_texts()

        # CP-556 · CA-02 columnas
        cab = [t.strip() for t in pag.locator("thead th").all_inner_texts()]
        ambito = filas.first.locator("td:nth-child(5)").inner_text()
        acciones = filas.first.locator("td:nth-child(6)").inner_text().strip()
        foto(pag, "EV-CP-556_listado-columnas")
        esperadas = ["Nombre", "Fórmula", "Unidad de medida", "Estado", "Acciones"]
        cab_norm = [c.lower() for c in cab]
        faltan = [c for c in esperadas if c.lower() not in cab_norm]
        caso("CP-556", "Columnas nombre, fórmula, unidad de medida, estado y acciones", not faltan,
             f"cabeceras={cab}; faltan={faltan}")
        caso("CP-556", "Ámbito identificado y acción Ver detalle",
             "Cliente Demo" in ambito and "Compartido" in ambito and acciones == "Ver detalle",
             f"ámbito={ambito!r}; acciones={acciones!r}")

        # CP-558 · CA-03 paginación
        txt_pie1 = pie.inner_text()
        pag1 = pag.get_by_text("Página 1 de 2").is_visible()
        pag.get_by_role("button", name="Siguiente").click()
        expect(pag.get_by_text("Página 2 de 2")).to_be_visible()
        esperar(16)
        pagina2 = nombres()
        estados2 = filas.locator("td:nth-child(4)").all_inner_texts()
        txt_pie2 = pie.inner_text()
        siguiente_off = pag.get_by_role("button", name="Siguiente").is_disabled()
        foto(pag, "EV-CP-558_pagina-2")
        todos = pagina1 + pagina2
        clave = [n.lower() for n in todos]
        ok = (len(pagina1) == 10 and len(pagina2) == 6 and len(set(todos)) == 16 and pag1
              and "Mostrando 1 a 10 de 16" in txt_pie1 and "Mostrando 11 a 16 de 16" in txt_pie2)
        caso("CP-558", "10 por página, total y página actual, sin omitir ni duplicar", ok,
             f"p1={len(pagina1)} p2={len(pagina2)} únicos={len(set(todos))}; '{txt_pie1}' / '{txt_pie2}'")
        caso("CP-560", "En la última página «Siguiente» está deshabilitado", siguiente_off, "")
        caso("CP-559", "Orden por nombre entre páginas", clave == sorted(clave, key=lambda s: s.translate(
            str.maketrans("áéíóúü", "aeiouu"))), todos)

        caso("CP-555", "Contexto Cliente Demo y sin definiciones de otra empresa",
             "Cliente Demo" in ctx and "Caudal de otra empresa" not in todos, f"{ctx}")
        caso("CP-566", "Activo e Inactivo listados sin filtro",
             {"Activo", "Inactivo"} <= set(estados1 + estados2), sorted(set(estados1 + estados2)))

        # CP-557 · CA-02 fórmula extensa resumida en la tabla (está en la página 2)
        fila = filas.filter(has_text="Índice térmico ponderado")
        celda = fila.locator("td:nth-child(2) span")
        resumida = celda.evaluate("e => e.scrollWidth > e.clientWidth")
        titulo = celda.get_attribute("title") or ""
        foto(pag, "EV-CP-557_formula-resumida")

        # CP-561 · CA-04 detalle
        fila.get_by_role("button", name="Ver detalle de Índice térmico ponderado").click()
        panel = pag.get_by_role("dialog")
        expect(panel).to_contain_text("Índice térmico ponderado", timeout=8000)
        pag.wait_for_load_state("networkidle")
        det = panel.inner_text()
        foco_dentro = pag.evaluate("() => !!document.activeElement.closest('[role=dialog]')")
        foto(pag, "EV-CP-561_detalle", completa=False)
        refs = [r for r in ["temperatura", "ph", "conductividad", "orp"] if r in det.lower()]
        caso("CP-557", "Fórmula resumida en la tabla y completa en el detalle",
             resumida and len(titulo) > 150 and det.count("*") >= 11,
             f"recortada={resumida}; title={len(titulo)} car.; '*' en detalle={det.count('*')}")
        ok = (all(t in det for t in ["Descripción", "Combinación ponderada", "Unidad de medida", "Estado",
                                      "Activo", "Ámbito de aplicación", "Cliente Demo"])
              and len(refs) == 4 and "p_1" not in det)
        caso("CP-561", "Detalle: nombre, descripción, fórmula, referencias, unidad, estado y ámbito", ok,
             f"referencias reconocidas={refs}; foco en el panel={foco_dentro}")
        pag.keyboard.press("Escape")
        expect(panel).to_be_hidden()
        pag.get_by_role("button", name="Anterior").click()
        esperar(16)
        filas.filter(has_text="Amplitud sin descripción").get_by_role("button").click()
        expect(panel).to_contain_text("Amplitud sin descripción", timeout=8000)
        expect(panel).to_contain_text("Sin descripción")
        caso("CP-561", "Sin descripción se indica", True, "«Sin descripción»")
        pag.keyboard.press("Escape")

        # CP-565 · Conversación: sin coincidencias ≠ vacío
        pag.get_by_role("searchbox", name="Buscar por nombre").fill("zzz-no-existe")
        esperar(0)
        msg_busq = pag.get_by_role("status").filter(has_text="No se encontraron").inner_text()
        foto(pag, "EV-CP-565_sin-coincidencias")
        pag.get_by_role("button", name="Limpiar filtros").click()
        esperar(16)

        # CP-564 · CA-06 error con reintento, sin mensaje de vacío
        pag.route("**/parametros-calculados?*", lambda r: r.fulfill(
            status=500, content_type="application/json", body=json.dumps({"detail": "Error interno"})))
        pag.get_by_role("button", name="Siguiente").click()
        alerta = pag.get_by_role("alert")
        expect(alerta).to_be_visible()
        txt_err = alerta.inner_text()
        vacio_visible = pag.get_by_text(VACIO).count() > 0
        ctx_visible = contexto.count() > 0
        foto(pag, "EV-CP-564_error-consulta")
        pag.unroute("**/parametros-calculados?*")
        pag.get_by_role("button", name="Reintentar listado").click()
        esperar(16)
        ctx_tras = contexto.inner_text()
        caso("CP-564", "Error con reintento, sin presentarlo como vacío; contexto conservado",
             not vacio_visible and "Reintentar" in txt_err and "Cliente Demo" in ctx_tras,
             f"alerta={txt_err!r}; vacío visible={vacio_visible}; contexto visible durante el error={ctx_visible}; tras reintento={ctx_tras!r}")

        # CP-562 · CA-05 vacío con permiso de crear
        entrar("Empresa QA PP69")
        esperar(0)
        msg_vacio = pag.get_by_role("status").filter(has_text="Aún no hay").inner_text()
        boton = pag.get_by_role("button", name="Añadir parámetro calculado")
        con_boton = boton.is_visible()
        foto(pag, "EV-CP-562_vacio-con-permiso")
        caso("CP-562", "Vacío: mensaje exacto y botón Añadir visible con permiso",
             VACIO in msg_vacio and con_boton, f"{msg_vacio!r}; botón={con_boton}")
        caso("CP-565", "Mensajes distintos: sin coincidencias / vacío / error",
             len({msg_busq.strip(), msg_vacio.strip(), txt_err.strip()}) == 3 and msg_busq.strip() == SIN_COINCIDENCIAS,
             f"{msg_busq!r} | {msg_vacio!r} | {txt_err!r}")

        # CP-563 · CA-05 vacío sin permiso de crear (respuesta real con permisos.crear=false)
        def sin_permiso(route):
            resp = route.fetch()
            cuerpo = resp.json()
            cuerpo["permisos"]["crear"] = False
            route.fulfill(response=resp, body=json.dumps(cuerpo))

        pag.route("**/parametros-calculados?*", sin_permiso)
        pag.reload()
        esperar(0)
        sin_boton = pag.get_by_role("button", name="Añadir parámetro calculado").count() == 0
        sigue_msg = pag.get_by_text(VACIO).is_visible()
        foto(pag, "EV-CP-563_vacio-sin-permiso")
        pag.unroute("**/parametros-calculados?*")
        caso("CP-563", "Vacío sin permiso de crear: mensaje sin botón Añadir", sin_boton and sigue_msg,
             f"sin botón={sin_boton}; mensaje={sigue_msg}")

        caso("General", "Sin errores de JavaScript", not errores, errores)
        nav.close()
    with open(os.path.join(EVID, f"e2e_real_{ANCHO}.json"), "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    fallos = [r for r in resultados if not r["ok"]]
    print(f"RESUMEN {len(resultados) - len(fallos)}/{len(resultados)} comprobaciones aprobadas")


if __name__ == "__main__":
    main()
