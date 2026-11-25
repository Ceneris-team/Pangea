"""Filtros de proyectos: Edge con API y PostgreSQL de prueba, sin proveedores externos."""

import os
from urllib.parse import parse_qs, urlparse

import pytest

from tests.routers.test_ubicaciones import (
    client as client,
)
from tests.routers.test_ubicaciones import (
    crear_ubicacion_directa,
)
from tests.routers.test_ubicaciones import (
    tecnico_editor as tecnico_editor,
)


@pytest.mark.parametrize("ancho", [1365, 390])
def test_filtros_limpieza_errores_respuestas_tardias_y_edicion(
    client, db_session, tecnico_editor, ancho, tmp_path
):
    base = os.getenv("UBICACIONES_UI_URL")
    if not base:
        pytest.skip("Definir UBICACIONES_UI_URL para probar el listado en el navegador")
    from playwright.sync_api import expect, sync_playwright

    for i in range(11):
        crear_ubicacion_directa(db_session, tecnico_editor, f"Norte {i:02d}")
    crear_ubicacion_directa(db_session, tecnico_editor, "Norte archivado", estado="Inactiva")
    crear_ubicacion_directa(db_session, tecnico_editor, "Sur", estado="Inactiva")
    consultas, retenidas, errores = [], [], []
    control = {"fallar": False, "retener": False}

    def responder(route):
        req = route.request
        if req.resource_type not in {"fetch", "xhr"}:
            route.continue_() if req.url.startswith(base) else route.abort()
            return
        url = urlparse(req.url)
        if url.path == "/auth/perfil":
            route.fulfill(
                json={
                    "nombre_completo": "Técnico QA",
                    "correo": "qa@example.com",
                    "rol": "Técnico CENERIS",
                    "scope": "por_sede",
                    "estado": "Activo",
                    "debe_cambiar_contrasena": False,
                    "zona_horaria": "America/Lima",
                    "operacion_habilitada": True,
                    "rol_empresa": None,
                    "cliente_id": tecnico_editor.id_clnt,
                    "proyecto_id": None,
                }
            )
        elif url.path == "/comercial/mi-acceso":
            route.fulfill(json={"operacion_habilitada": True, "aviso": None})
        elif url.path == "/sedes":
            route.fulfill(json=[])
        elif url.path.startswith("/ubicaciones"):
            if url.path == "/ubicaciones":
                query = parse_qs(url.query)
                consultas.append((query, req.headers))
                if control["fallar"]:
                    control["fallar"] = False
                    route.fulfill(status=503, json={"detail": "Fallo temporal de prueba"})
                    return
            respuesta = client.request(
                req.method,
                url.path + (f"?{url.query}" if url.query else ""),
                json=req.post_data_json if req.method == "PUT" else None,
            )
            assert respuesta.status_code == 200, respuesta.text
            if url.path == "/ubicaciones" and control["retener"]:
                retenidas.append((route, respuesta.json()))
                return
            route.fulfill(status=respuesta.status_code, json=respuesta.json())
        else:
            route.fulfill(json={"items": [], "total": 0})

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=os.getenv("QA_BROWSER", "msedge"), headless=True)
        pagina = browser.new_page(viewport={"width": ancho, "height": 1000})
        pagina.add_init_script(
            f"sessionStorage.setItem('pangea_cliente', '{tecnico_editor.id_clnt}')"
        )
        pagina.route("**/*", responder)
        pagina.on("pageerror", lambda error: errores.append(str(error)))
        try:
            pagina.goto(f"{base}/ubicaciones")
            buscar = pagina.get_by_role("textbox", name="Buscar por nombre de proyecto")
            estado = pagina.get_by_role("combobox", name="Estado del proyecto")
            limpiar = pagina.get_by_role("button", name="Limpiar filtros")
            filas = pagina.get_by_role("table", name="Listado de proyectos").locator("tbody tr")
            expect(filas).to_have_count(10)
            expect(limpiar).to_be_disabled()
            expect(estado).to_have_value("")
            expect(pagina.get_by_text("Mostrando 1 a 10 de 13 registros")).to_be_visible()

            buscar.fill("  NORTE  ")
            estado.select_option("Activa")
            expect(pagina.get_by_text("Mostrando 1 a 10 de 11 registros")).to_be_visible()
            assert consultas[-1][0] == {
                "busqueda": ["NORTE"],
                "estado": ["Activa"],
                "pagina": ["1"],
                "por_pagina": ["10"],
            }
            pagina.get_by_role("button", name="Siguiente", exact=True).click()
            expect(filas).to_have_count(1)
            expect(filas).to_contain_text("Norte 10")
            assert consultas[-1][0]["pagina"] == ["2"]

            estado.select_option("Inactiva")
            expect(filas).to_have_count(1)
            expect(filas).to_contain_text("Norte archivado")
            expect(filas).to_contain_text("Recogida habilitada")
            assert consultas[-1][0]["pagina"] == ["1"]
            estado.select_option("")
            expect(pagina.get_by_text("Mostrando 1 a 10 de 12 registros")).to_be_visible()
            buscar.fill("No existe")
            expect(
                pagina.get_by_text("No se encontraron proyectos con los filtros seleccionados")
            ).to_be_visible()
            expect(pagina.get_by_text("Mostrando 0 a 0 de 0 registros")).to_be_visible()
            limpiar.click()
            expect(buscar).to_have_value("")
            expect(estado).to_have_value("")
            expect(pagina.get_by_text("Mostrando 1 a 10 de 13 registros")).to_be_visible()
            assert consultas[-1][0] == {"pagina": ["1"], "por_pagina": ["10"]}

            # El debounce pendiente no debe restaurar un filtro que se limpió.
            buscar.fill("Pendiente")
            limpiar.click()
            pagina.wait_for_timeout(450)
            expect(filas).to_have_count(10)
            assert "busqueda" not in consultas[-1][0]

            # El error no debe dejar visibles datos o totales de la consulta previa.
            control["fallar"] = True
            estado.select_option("Inactiva")
            expect(pagina.get_by_role("alert")).to_contain_text("No se pudo cargar el listado")
            expect(filas).to_have_count(0)
            expect(estado).to_have_value("Inactiva")
            pagina.get_by_role("button", name="Reintentar", exact=True).click()
            expect(filas).to_have_count(2)
            assert consultas[-1][0]["estado"] == ["Inactiva"]

            control["retener"] = True
            estado.select_option("Activa")
            expect(pagina.get_by_role("status")).to_have_text("Cargando proyectos...")
            pagina.wait_for_timeout(100)
            assert retenidas
            control["retener"] = False
            estado.select_option("Inactiva")
            expect(filas).to_have_count(2)
            for route, datos in retenidas:
                route.fulfill(json=datos)
            pagina.wait_for_timeout(100)
            expect(filas).to_have_count(2)
            expect(filas).to_contain_text(["Norte archivado", "Sur"])

            # Editar el único resultado de la segunda página conserva filtros
            # y vuelve a una página válida si ya no pertenece al estado elegido.
            buscar.fill("Norte")
            estado.select_option("Activa")
            expect(pagina.get_by_text("Mostrando 1 a 10 de 11 registros")).to_be_visible()
            pagina.get_by_role("button", name="Siguiente", exact=True).click()
            expect(filas).to_have_count(1)
            filas.get_by_role("button", name="Editar", exact=True).click()
            formulario = pagina.get_by_role("dialog")
            formulario.get_by_label("Organización del proyecto").select_option("Inactiva")
            formulario.get_by_role("button", name="Guardar cambios", exact=True).click()
            expect(formulario).not_to_be_visible()
            expect(pagina.get_by_text("Mostrando 1 a 10 de 10 registros")).to_be_visible()
            expect(buscar).to_have_value("Norte")
            expect(estado).to_have_value("Activa")
            assert consultas[-1][0]["pagina"] == ["1"]

            for consulta, headers in consultas:
                assert headers["x-cliente-id"] == str(tecnico_editor.id_clnt)
            for control_ui in (buscar, estado, limpiar):
                control_ui.scroll_into_view_if_needed()
                caja = control_ui.bounding_box()
                assert caja and caja["x"] >= 0 and caja["x"] + caja["width"] <= ancho + 1
            pagina.screenshot(path=str(tmp_path / f"filtros-proyectos-{ancho}.png"), full_page=True)
            assert errores == []
        finally:
            browser.close()
