"""HU36: flujo en Edge con HTTP simulado; requiere HU36_UI_URL local."""

import json
import os
from urllib.parse import parse_qs, urlparse

import pytest


@pytest.mark.parametrize("ancho", [1365, 390])
def test_filtros_acumulativos_limpieza_paginacion_y_recuperacion(ancho, tmp_path):
    base = os.environ.get("HU36_UI_URL")
    if not base:
        pytest.skip("Definir HU36_UI_URL para ejecutar el flujo de navegador")
    from playwright.sync_api import expect, sync_playwright

    equipos = [
        {
            "id_dspstv": i,
            "nmbr": f"Equipo {i:03}",
            "mrc": "Campbell",
            "id_ubccn": 1,
            "ubicacion_nombre": "Proyecto 001",
            "estd": "Activo",
        }
        for i in range(1, 13)
    ] + [
        {
            "id_dspstv": 13,
            "nmbr": "Equipo inactivo",
            "mrc": "Campbell",
            "id_ubccn": 2,
            "ubicacion_nombre": "Proyecto 002",
            "estd": "Inactivo",
        },
        {
            "id_dspstv": 14,
            "nmbr": "Equipo Vaisala",
            "mrc": "Vaisala",
            "id_ubccn": 2,
            "ubicacion_nombre": "Proyecto 002",
            "estd": "Activo",
        },
    ]
    proyectos = [{"id_ubccn": i, "nmbr": f"Proyecto {i:03}"} for i in range(1, 102)]
    consultas, retrasadas, errores, catalogos_pendientes = [], [], [], []
    estado = {"error_catalogo": True, "retener_campbell": False, "retener_catalogo": False}

    def responder(route):
        req = route.request
        if req.resource_type not in {"fetch", "xhr"}:
            if req.url.startswith(base):
                route.continue_()
            else:
                route.abort()
            return
        url = urlparse(req.url)
        ruta, query = url.path, parse_qs(url.query)
        datos, status = {"items": [], "total": 0}, 200
        if ruta == "/auth/perfil":
            datos = {
                "nombre_completo": "Técnico QA",
                "correo": "qa@example.com",
                "rol": "Técnico CENERIS",
                "scope": "global",
                "estado": "Activo",
                "debe_cambiar_contrasena": False,
                "zona_horaria": "America/Lima",
                "operacion_habilitada": True,
                "rol_empresa": None,
                "cliente_id": 1,
                "proyecto_id": None,
            }
        elif ruta == "/comercial/mi-acceso":
            datos = {"aviso": None, "operacion_habilitada": True}
        elif ruta == "/dispositivos/ubicaciones":
            datos = {"items": proyectos}
            if estado["retener_catalogo"]:
                catalogos_pendientes.append((route, datos))
                return
        elif ruta == "/dispositivos/marcas":
            if estado["error_catalogo"]:
                datos, status = {"detail": "Fallo temporal de catálogo"}, 503
            else:
                datos = {"items": ["Campbell", "Vaisala"]}
        elif ruta == "/dispositivos":
            consultas.append(query)
            filtrados = equipos
            for campo, parametro in [
                ("mrc", "marca"),
                ("id_ubccn", "id_ubccn"),
                ("estd", "estado"),
            ]:
                if parametro in query:
                    filtrados = [e for e in filtrados if str(e[campo]) == query[parametro][0]]
            if "busqueda" in query:
                texto = query["busqueda"][0].lower()
                filtrados = [
                    e for e in filtrados if texto in e["nmbr"].lower() or texto in e["mrc"].lower()
                ]
            pagina, limite = int(query.get("pagina", [1])[0]), int(query["por_pagina"][0])
            datos = {
                "total": len(filtrados),
                "pagina": pagina,
                "por_pagina": limite,
                "items": filtrados[(pagina - 1) * limite : pagina * limite],
            }
            if estado["retener_campbell"] and query.get("marca") == ["Campbell"]:
                retrasadas.append((route, datos))
                return
        route.fulfill(status=status, content_type="application/json", body=json.dumps(datos))

    with sync_playwright() as p:
        navegador = p.chromium.launch(channel="msedge", headless=True)
        pagina = navegador.new_page(viewport={"width": ancho, "height": 1000})
        pagina.add_init_script("sessionStorage.setItem('pangea_cliente','1')")
        pagina.route("**/*", responder)
        pagina.on("pageerror", lambda error: errores.append(str(error)))
        try:
            pagina.goto(f"{base}/dispositivos")
            marca = pagina.get_by_role("combobox", name="Filtrar por marca")
            proyecto = pagina.get_by_role("combobox", name="Filtrar por proyecto")
            filtro_estado = pagina.get_by_role("combobox", name="Filtrar por estado")
            filas = pagina.locator("tbody tr")
            expect(pagina.get_by_role("alert")).to_contain_text("No se pudieron cargar")
            expect(marca).to_be_disabled()
            estado["error_catalogo"] = False
            estado["retener_catalogo"] = True
            pagina.get_by_role("button", name="Reintentar filtros").click()
            expect(pagina.get_by_role("status")).to_have_text("Cargando opciones de filtros…")
            expect(proyecto).to_be_disabled()
            assert catalogos_pendientes
            for route, datos in catalogos_pendientes:
                route.fulfill(status=200, content_type="application/json", body=json.dumps(datos))
            expect(marca).to_be_enabled()
            expect(proyecto.locator("option")).to_have_count(102)
            expect(marca.locator("option")).to_have_count(3)

            # CA1: marca exacta y paginación conservando el filtro.
            marca.select_option("Campbell")
            expect(filas).to_have_count(10)
            pagina.get_by_role("button", name="Siguiente", exact=True).click()
            expect(filas).to_have_count(3)
            assert consultas[-1]["marca"] == ["Campbell"]
            assert consultas[-1]["pagina"] == ["2"]

            # CA2/CA4/CA5: cambiar proyecto reinicia página; tres filtros AND.
            proyecto.select_option("2")
            expect(filas).to_have_count(1)
            expect(filas).to_contain_text("Equipo inactivo")
            assert consultas[-1]["pagina"] == ["1"]
            filtro_estado.select_option("Activo")
            expect(
                pagina.get_by_text("No se encontraron dispositivos con ese criterio.")
            ).to_be_visible()
            assert consultas[-1]["marca"] == ["Campbell"]
            assert consultas[-1]["id_ubccn"] == ["2"]
            assert consultas[-1]["estado"] == ["Activo"]
            expect(pagina.get_by_text("Mostrando 0 a 0 de 0 registros")).to_be_visible()
            filtro_estado.select_option("Inactivo")
            expect(filas).to_contain_text("Equipo inactivo")
            expect(proyecto.locator("option")).to_have_count(102)
            expect(marca.locator("option")).to_have_count(3)

            # La búsqueda sigue combinándose, y limpiar elimina todo.
            buscar = pagina.get_by_role("textbox", name="Buscar dispositivos")
            buscar.fill("No existe")
            expect(
                pagina.get_by_text("No se encontraron dispositivos con ese criterio.")
            ).to_be_visible()
            pagina.get_by_role("button", name="Limpiar filtros").click()
            expect(buscar).to_have_value("")
            for selector in [marca, proyecto, filtro_estado]:
                expect(selector).to_have_value("")
            expect(filas).to_have_count(10)
            assert consultas[-1] == {"pagina": ["1"], "por_pagina": ["10"]}

            # Limpiar durante la espera de búsqueda tampoco la restaura después.
            buscar.fill("Búsqueda pendiente")
            pagina.get_by_role("button", name="Limpiar filtros").click()
            pagina.wait_for_timeout(450)
            expect(filas).to_have_count(10)
            assert consultas[-1] == {"pagina": ["1"], "por_pagina": ["10"]}

            # Una respuesta tardía de Campbell no reemplaza la de Vaisala.
            estado["retener_campbell"] = True
            marca.select_option("Campbell")
            expect(pagina.get_by_text("Cargando datos...")).to_be_visible()
            marca.select_option("Vaisala")
            expect(filas).to_contain_text("Equipo Vaisala")
            assert retrasadas
            for route, datos in retrasadas:
                route.fulfill(status=200, content_type="application/json", body=json.dumps(datos))
            pagina.wait_for_timeout(100)
            expect(filas).to_have_count(1)
            expect(filas).to_contain_text("Equipo Vaisala")

            for selector in [marca, proyecto, filtro_estado]:
                selector.scroll_into_view_if_needed()
                caja = selector.bounding_box()
                assert caja and caja["x"] >= 0 and caja["x"] + caja["width"] <= ancho + 1
            pagina.screenshot(path=str(tmp_path / f"hu36-{ancho}.png"), full_page=True)
            assert errores == []
        finally:
            navegador.close()
