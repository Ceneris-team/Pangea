"""QA HU36 (PP-436): E2E en Edge con HTTP simulado; requiere HU36_UI_URL.

CP-509: «Limpiar filtros» (visibilidad, rótulo, restauración, accesibilidad).
CP-512: al registrar un dispositivo con marca y ubicación nuevas, ambas
aparecen en los selectores sin recargar la página.
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import json
import os
from urllib.parse import parse_qs, urlparse

import pytest

EVID = os.environ.get("HU36_EVID")


@pytest.mark.parametrize("ancho", [1365, 390])
def test_qa_hu36_limpiar_y_alta_refresca_catalogos(ancho):
    base = os.environ.get("HU36_UI_URL")
    if not base:
        pytest.skip("Definir HU36_UI_URL")
    from playwright.sync_api import expect, sync_playwright

    ubic = [{"id_ubccn": 1, "nmbr": "Proyecto Norte"}, {"id_ubccn": 2, "nmbr": "Proyecto Sur"}]
    todas_ubic = ubic + [{"id_ubccn": 3, "nmbr": "Proyecto Nuevo"}]
    equipos = [
        {"id_dspstv": 1, "nmbr": "EQ Norte Campbell", "mrc": "Campbell", "id_ubccn": 1,
         "ubicacion_nombre": "Proyecto Norte", "estd": "Activo"},
        {"id_dspstv": 2, "nmbr": "EQ Sur Vaisala", "mrc": "Vaisala", "id_ubccn": 2,
         "ubicacion_nombre": "Proyecto Sur", "estd": "Inactivo"},
    ]
    marcas = ["Campbell", "Vaisala"]
    llamadas = {"marcas": 0, "ubic": 0}
    errores = []

    def responder(route):
        req = route.request
        if req.resource_type not in {"fetch", "xhr"}:
            route.continue_() if req.url.startswith(base) else route.abort()
            return
        url = urlparse(req.url)
        ruta, q = url.path, parse_qs(url.query)
        datos, status = {"items": [], "total": 0}, 200
        if ruta == "/auth/perfil":
            datos = {"nombre_completo": "Técnico QA", "correo": "qa@example.test",
                     "rol": "Técnico CENERIS", "scope": "global", "estado": "Activo",
                     "debe_cambiar_contrasena": False, "zona_horaria": "America/Lima",
                     "operacion_habilitada": True, "rol_empresa": None, "cliente_id": 1,
                     "proyecto_id": None}
        elif ruta == "/comercial/mi-acceso":
            datos = {"aviso": None, "operacion_habilitada": True}
        elif ruta == "/dispositivos/marcas":
            llamadas["marcas"] += 1
            datos = {"items": sorted({e["mrc"] for e in equipos})}
        elif ruta == "/dispositivos/ubicaciones":
            llamadas["ubic"] += 1
            usadas = {e["id_ubccn"] for e in equipos}
            datos = {"items": [u for u in todas_ubic if u["id_ubccn"] in usadas]}
        elif ruta == "/ubicaciones":
            datos = {"items": todas_ubic, "total": 3}
        elif ruta == "/conexiones-ftp":
            datos = {"items": [{"id_cnxn": 9, "nmbr": "FTP QA", "estd": "Activa"}], "total": 1}
        elif ruta == "/dispositivos" and req.method == "POST":
            cuerpo = json.loads(req.post_data)
            u = next(x for x in todas_ubic if x["id_ubccn"] == cuerpo["id_ubccn"])
            equipos.append({"id_dspstv": 3, "nmbr": cuerpo["nmbr"], "mrc": cuerpo["mrc"],
                            "id_ubccn": u["id_ubccn"], "ubicacion_nombre": u["nmbr"],
                            "estd": "Activo"})
            datos, status = {"mensaje": "ok", "id_dspstv": 3}, 201
        elif ruta == "/dispositivos":
            f = equipos
            for campo, p in [("mrc", "marca"), ("id_ubccn", "id_ubccn"), ("estd", "estado")]:
                if p in q:
                    f = [e for e in f if str(e[campo]) == q[p][0]]
            datos = {"total": len(f), "pagina": 1, "por_pagina": 10, "items": f}
        route.fulfill(status=status, content_type="application/json", body=json.dumps(datos))

    def foto(pag, nombre):
        if EVID:
            pag.screenshot(path=os.path.join(EVID, f"{nombre}-{ancho}.png"), full_page=True)

    with sync_playwright() as p:
        nav = p.chromium.launch(channel="msedge", headless=True)
        pag = nav.new_page(viewport={"width": ancho, "height": 1000})
        pag.add_init_script("sessionStorage.setItem('pangea_cliente','1')")
        pag.route("**/*", responder)
        pag.on("pageerror", lambda e: errores.append(str(e)))
        try:
            pag.goto(f"{base}/dispositivos")
            marca = pag.get_by_role("combobox", name="Filtrar por marca")
            proyecto = pag.get_by_role("combobox", name="Filtrar por proyecto")
            estado = pag.get_by_role("combobox", name="Filtrar por estado")
            filas = pag.locator("tbody tr")
            expect(marca).to_be_enabled()
            expect(filas).to_have_count(2)
            limpiar = pag.get_by_role("button", name="Limpiar filtros")

            # CP-509: sin filtros el botón no se muestra; con filtros sí.
            expect(limpiar).to_have_count(0)
            marca.select_option("Campbell")
            proyecto.select_option("1")
            estado.select_option("Activo")
            expect(filas).to_have_count(1)
            expect(filas).to_contain_text("EQ Norte Campbell")
            expect(limpiar).to_be_visible()
            foto(pag, "EV-CP-508_filtros-combinados")
            rotulo = limpiar.inner_text()
            print(f"\nROTULO_LIMPIAR={rotulo!r}")
            limpiar.focus()
            pag.keyboard.press("Enter")  # accesible por teclado
            for s in (marca, proyecto, estado):
                expect(s).to_have_value("")
            expect(filas).to_have_count(2)
            expect(limpiar).to_have_count(0)
            foto(pag, "EV-CP-509_limpiar-filtros")

            # CP-512: alta con marca y ubicación nuevas refresca selectores.
            antes = dict(llamadas)
            expect(marca.locator("option")).to_have_count(3)
            expect(proyecto.locator("option")).to_have_count(3)
            pag.get_by_role("button", name="Añadir dispositivo").first.click()
            pag.locator("#nmbr").fill("EQ Nuevo Hobo")
            pag.locator("#mrc").fill("Hobo")
            pag.locator("#id_ubccn").select_option("3")
            pag.locator("#id_cnxn").select_option("9")
            pag.get_by_role("button", name="GUARDAR", exact=False).last.click()
            expect(marca.locator("option", has_text="Hobo")).to_have_count(1)
            expect(proyecto.locator("option", has_text="Proyecto Nuevo")).to_have_count(1)
            assert llamadas["marcas"] > antes["marcas"] and llamadas["ubic"] > antes["ubic"]
            marca.select_option("Hobo")
            expect(filas).to_have_count(1)
            expect(filas).to_contain_text("EQ Nuevo Hobo")
            foto(pag, "EV-CP-512_alta-refresca-catalogo")
            assert errores == []
        finally:
            nav.close()
