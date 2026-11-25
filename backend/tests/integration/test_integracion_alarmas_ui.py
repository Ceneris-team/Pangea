"""Compatibilidad de condiciones, canal de correo y permisos tras el merge."""

import os
from urllib.parse import urlparse

import pytest

from tests.routers.test_reprocesos import entorno as entorno


@pytest.mark.parametrize("ancho,edicion", [(1365, True), (390, True), (390, False)])
def test_condicion_y_canal_compartidos_con_api_real(entorno, ancho, edicion, tmp_path):
    base = os.getenv("REPROCESOS_UI_URL")
    if not base:
        pytest.skip("Definir REPROCESOS_UI_URL para el flujo de integración")
    from playwright.sync_api import expect, sync_playwright

    e = entorno
    r = e["client"].post(
        "/alarmas",
        json={
            "nmbr": "Nivel del proyecto",
            "id_ubccn": e["proyecto"].id_ubccn,
            "id_prmtr": e["parametro"].id_prmtr,
            "condiciones": [{"oprdr": ">", "vlr_umbrl": 5}],
            "destinatarios": ["operador@example.com"],
        },
    )
    assert r.status_code == 201, r.text
    errores = []
    cambios = []

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
                    "scope": "global",
                    "estado": "Activo",
                    "debe_cambiar_contrasena": False,
                    "zona_horaria": "America/Lima",
                    "operacion_habilitada": True,
                    "puede_editar_alarmas": edicion,
                    "rol_empresa": None,
                    "cliente_id": e["sede"].id_clnt,
                    "proyecto_id": e["proyecto"].id_ubccn,
                }
            )
        elif url.path == "/comercial/mi-acceso":
            route.fulfill(json={"operacion_habilitada": True, "aviso": None})
        elif url.path.startswith("/alarmas"):
            kw = {"json": req.post_data_json} if req.method in {"POST", "PUT", "PATCH"} else {}
            r = e["client"].request(req.method, f"{url.path}?{url.query}", **kw)
            assert r.status_code == 200, r.text
            if req.method != "GET":
                cambios.append((url.path, req.post_data_json))
            route.fulfill(json=r.json())
        else:
            route.fulfill(json={"items": [], "total": 0})

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": ancho, "height": 1000})
        page.add_init_script(
            f"sessionStorage.setItem('pangea_cliente','{e['sede'].id_clnt}'); sessionStorage.setItem('pangea_proyecto_v2','{e['proyecto'].id_ubccn}');"
        )
        page.route("**/*", responder)
        page.on("pageerror", lambda error: errores.append(str(error)))
        try:
            page.goto(f"{base}/alarmas")
            expect(page.get_by_text("Pendiente de lectura", exact=True)).to_be_visible()
            page.get_by_role("button", name="Condición de Nivel del proyecto", exact=True).click()
            editor = page.get_by_role("dialog", name="Condición de Nivel del proyecto", exact=True)
            (
                expect(editor.get_by_role("combobox", name="Operador", exact=True)).to_be_enabled()
                if edicion
                else expect(
                    editor.get_by_role("combobox", name="Operador", exact=True)
                ).to_be_disabled()
            )
            if edicion:
                editor.get_by_role("textbox", name="Valor umbral (m)", exact=True).fill("14")
                editor.get_by_role("button", name="Actualizar", exact=True).click()
                expect(editor).to_have_count(0)
                expect(page.get_by_text("> 14 m", exact=True)).to_be_visible()
            else:
                expect(editor.get_by_role("button", name="Actualizar", exact=True)).to_have_count(0)
                editor.get_by_role("button", name="Cerrar", exact=True).click()
            page.get_by_role(
                "button", name="Configurar notificaciones de Nivel del proyecto", exact=True
            ).click()
            panel = page.get_by_role(
                "dialog", name="Configurar notificaciones de Nivel del proyecto", exact=True
            )
            expect(panel.get_by_text("operador@example.com", exact=True)).to_be_visible()
            if edicion:
                panel.get_by_role("switch", name="Correo electrónico", exact=True).uncheck()
                panel.get_by_role("button", name="Guardar", exact=True).click()
                expect(
                    panel.get_by_role("status").filter(
                        has_text="Notificaciones configuradas correctamente"
                    )
                ).to_be_visible()
                assert cambios[-1][1] == {"canal_email_activo": False}
            else:
                expect(panel.get_by_role("button", name="Guardar", exact=True)).to_have_count(0)
                assert cambios == []
            page.screenshot(
                path=str(tmp_path / f"alarmas-integradas-{ancho}-{edicion}.png"), full_page=True
            )
            assert errores == []
        finally:
            browser.close()
