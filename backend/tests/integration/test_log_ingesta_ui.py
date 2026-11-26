"""HU37: Edge, interfaz real y endpoints reales sobre PostgreSQL de pruebas."""

import datetime as dt
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

from app.tasks.ingesta import _registrar_intento
from tests.routers.test_reprocesos import ejecutar, pedir
from tests.routers.test_reprocesos import entorno as entorno  # noqa: F401


@pytest.mark.parametrize("ancho", [1365, 390])
def test_log_filtros_historia_errores_navegacion_y_movil(entorno, ancho):
    base = os.environ.get("HU37_UI_URL")
    if not base:
        pytest.skip("Definir HU37_UI_URL con el frontend de pruebas")
    from playwright.sync_api import expect, sync_playwright

    e = entorno
    for indice in range(22):
        _registrar_intento(
            e["db"],
            e["archivo"].id_archv,
            "Fallido",
            f"Columna inválida {indice}: " + "detalle de diagnóstico; " * 30,
            None,
            dt.datetime.now(dt.timezone.utc),
        )
    e["db"].commit()
    assert ejecutar(e, pedir(e))["estado"] == "Exitoso"
    fallo = {"lista": False, "detalle": False}
    errores = []

    def responder(route):
        req = route.request
        if req.resource_type not in {"fetch", "xhr"}:
            route.continue_() if req.url.startswith(base) else route.abort()
            return
        url = urlparse(req.url)
        if url.path == "/auth/perfil":
            route.fulfill(
                json={
                    "nombre_completo": "Técnico de pruebas",
                    "correo": "qa@example.com",
                    "rol": "Técnico CENERIS",
                    "scope": "global",
                    "estado": "Activo",
                    "debe_cambiar_contrasena": False,
                    "zona_horaria": "America/Lima",
                    "operacion_habilitada": True,
                    "rol_empresa": None,
                    "cliente_id": e["sede"].id_clnt,
                    "proyecto_id": e["proyecto"].id_ubccn,
                }
            )
        elif url.path == "/comercial/mi-acceso":
            route.fulfill(json={"operacion_habilitada": True, "aviso": None})
        elif url.path.startswith("/ingesta"):
            tipo = "lista" if url.path == "/ingesta/log" else "detalle"
            if fallo[tipo] and not url.path.endswith("dataloggers"):
                fallo[tipo] = False
                route.fulfill(
                    status=503,
                    json={"detail": "No se pudo cargar la información. Intenta nuevamente."},
                )
                return
            r = e["client"].get(f"{url.path}?{url.query}")
            route.fulfill(status=r.status_code, json=r.json())
        else:
            route.fulfill(json={"items": [], "total": 0})

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": ancho, "height": 1000})
        page.add_init_script(
            f"sessionStorage.setItem('pangea_cliente','{e['sede'].id_clnt}');"
            f"sessionStorage.setItem('pangea_proyecto_v2','{e['proyecto'].id_ubccn}');"
        )
        page.route("**/*", responder)
        page.on("pageerror", lambda error: errores.append(str(error)))
        try:
            page.goto(f"{base}/cola-ingesta")
            page.get_by_role("link", name="Consultar log de ingesta").click()
            expect(page.get_by_role("heading", name="Log de ingesta", exact=True)).to_be_visible()
            expect(page.get_by_text("23 evento(s) · 20 por página", exact=True)).to_be_visible()
            expect(page.locator("tbody tr")).to_have_count(20)
            page.get_by_label("Resultado", exact=True).select_option("Fallido")
            page.get_by_role("button", name="APLICAR", exact=True).click()
            expect(page.get_by_text("22 evento(s) · 20 por página", exact=True)).to_be_visible()
            page.get_by_role("button", name="Siguiente", exact=True).click()
            expect(page.locator("tbody tr")).to_have_count(2)
            page.reload()
            expect(page.get_by_text("Página 2 de 2", exact=True)).to_be_visible()
            expect(page.get_by_label("Resultado", exact=True)).to_have_value("Fallido")
            page.get_by_label("Nombre de archivo", exact=True).fill("no-existe")
            page.get_by_role("button", name="APLICAR", exact=True).click()
            expect(
                page.get_by_text(
                    "No hay eventos para los filtros seleccionados en los últimos 90 días.",
                    exact=True,
                )
            ).to_be_visible()
            page.go_back()
            expect(page.get_by_label("Nombre de archivo", exact=True)).to_have_value("")
            expect(page.locator("tbody tr")).to_have_count(2)
            page.get_by_label("Desde", exact=True).fill("2026-11-20")
            page.get_by_label("Hasta", exact=True).fill("2026-11-19")
            page.get_by_role("button", name="APLICAR", exact=True).click()
            expect(page.get_by_role("alert")).to_contain_text("La fecha inicial")
            expect(page.locator("tbody tr")).to_have_count(2)
            page.get_by_role("button", name="Limpiar filtros", exact=True).click()
            expect(page.locator("tbody tr")).to_have_count(20)
            fallo["detalle"] = True
            page.get_by_role("button", name="Ver detalle", exact=True).nth(1).click()
            dialogo = page.get_by_role("dialog", name="Detalle del evento de ingesta")
            expect(dialogo.get_by_role("alert")).to_be_visible()
            dialogo.get_by_role("button", name="Reintentar detalle", exact=True).click()
            expect(dialogo).to_contain_text("Historial de intentos del archivo")
            expect(dialogo).to_contain_text("Procesado")
            expect(dialogo).to_contain_text("Fallido")
            expect(dialogo).to_contain_text("detalle de diagnóstico;")
            expect(dialogo).to_contain_text("No disponible")
            page.keyboard.press("Escape")
            expect(dialogo).to_have_count(0)
            fallo["lista"] = True
            page.get_by_role("button", name="Actualizar", exact=True).click()
            expect(page.get_by_role("button", name="Reintentar carga", exact=True)).to_be_visible()
            page.get_by_role("button", name="Reintentar carga", exact=True).click()
            expect(page.locator("tbody tr")).to_have_count(20)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            capturas = Path(os.environ.get("HU37_QA_DIR", os.environ["TEMP"]))
            capturas.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(capturas / f"hu37-log-{ancho}.png"), full_page=True)
            assert errores == []
        finally:
            browser.close()
