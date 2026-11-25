"""Flujo real de HU38 en escritorio y móvil, con API y PostgreSQL de prueba."""

import json
import os
from urllib.parse import urlparse

import pytest

from tests.routers.test_calculos_completos import calculos as calculos
from tests.routers.test_calculos_completos import drenar, medir
from tests.routers.test_parametros_calculados import entorno_calculados as entorno_calculados


@pytest.mark.parametrize("ancho", [1365, 390])
def test_creacion_historico_consulta_y_grafico(calculos, ancho, tmp_path):
    base = os.environ.get("CALCULADOS_UI_URL")
    if not base:
        pytest.skip("Definir CALCULADOS_UI_URL para probar el flujo visual")
    from playwright.sync_api import expect, sync_playwright

    e = calculos
    medir(e, e["nivel"], 10)
    medir(e, e["salida"], 4)
    empresa, proyecto = str(e["empresas"][0].id_clnt), str(e["proyectos"][0].id_ubccn)
    e["client"].headers["X-Proyecto-Id"] = proyecto
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
                    "nombre_completo": "Técnico QA",
                    "correo": "qa@example.com",
                    "rol": "Técnico CENERIS",
                    "scope": "global",
                    "estado": "Activo",
                    "debe_cambiar_contrasena": False,
                    "zona_horaria": "America/Lima",
                    "operacion_habilitada": True,
                    "rol_empresa": None,
                    "cliente_id": None,
                    "proyecto_id": None,
                }
            )
            return
        if url.path == "/comercial/mi-acceso":
            route.fulfill(json={"operacion_habilitada": True, "aviso": None})
            return
        if url.path.startswith(
            ("/parametros-calculados", "/mediciones", "/ubicaciones", "/dispositivos")
        ):
            r = e["client"].request(
                req.method,
                f"{url.path}?{url.query}",
                **({"json": req.post_data_json} if req.method in {"POST", "PUT"} else {}),
            )
            assert r.status_code in {200, 201, 422}, r.text
            if (
                url.path == "/parametros-calculados"
                and req.method == "POST"
                and r.status_code == 201
            ):
                drenar(e)
            route.fulfill(status=r.status_code, json=r.json())
            return
        route.fulfill(json={"items": [], "total": 0})

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        pagina = browser.new_page(viewport={"width": ancho, "height": 1000})
        pagina.add_init_script(
            f"sessionStorage.setItem('pangea_cliente', {json.dumps(empresa)}); sessionStorage.setItem('pangea_proyecto_v2', {json.dumps(proyecto)});"
        )
        pagina.route("**/*", responder)
        pagina.on("pageerror", lambda err: errores.append(str(err)))
        try:
            pagina.goto(f"{base}/parametros-calculados")
            pagina.get_by_role("button", name="Añadir parámetro calculado", exact=True).click()
            crear = pagina.get_by_role("dialog", name="Añadir parámetro calculado", exact=True)
            crear.get_by_label("Nombre", exact=True).fill("Balance QA")
            crear.get_by_label("Fórmula", exact=True).fill("[Nivel de entrada] - [Nivel de salida]")
            crear.get_by_label("Unidad de medida", exact=True).fill("kg")
            guardar = crear.get_by_role("button", name="Guardar", exact=True)
            expect(guardar).to_be_disabled()
            crear.get_by_role("button", name="Validar fórmula").click()
            expect(crear.get_by_role("alert")).to_contain_text("unidad de salida")
            crear.get_by_label("Unidad de medida", exact=True).fill("m")
            crear.get_by_role("button", name="Validar fórmula").click()
            expect(crear.get_by_role("status")).to_have_text("Fórmula válida")
            expect(guardar).to_be_enabled()
            crear.get_by_role("textbox", name="Fórmula", exact=True).fill(
                "([Nivel de entrada] - [Nivel de salida])"
            )
            expect(guardar).to_be_disabled()
            crear.get_by_role("button", name="Validar fórmula").click()
            expect(guardar).to_be_enabled()
            crear.screenshot(path=str(tmp_path / f"hu38-formulario-{ancho}.png"))
            guardar.click()
            expect(crear).to_have_count(0)
            expect(
                pagina.get_by_role("status").filter(has_text="añadido correctamente")
            ).to_be_visible()
            pagina.get_by_role("button", name="Ver detalle de Balance QA", exact=True).click()
            detalle = pagina.get_by_role(
                "dialog", name="Detalle del parámetro calculado", exact=True
            )
            expect(detalle.get_by_text("Histórico: Completado", exact=True)).to_be_visible()
            expect(detalle.get_by_text("Calculado: 6 m", exact=True)).to_be_visible()
            detalle.get_by_text("Ver fuentes y reglas utilizadas", exact=True).click()
            expect(detalle.get_by_text("Nivel de entrada: 10 m", exact=False)).to_be_visible()
            detalle.screenshot(path=str(tmp_path / f"hu38-resultados-{ancho}.png"))
            assert pagina.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            pagina.goto(f"{base}/consulta-datos?ubicacion_id={proyecto}")
            fila = pagina.locator("tbody tr").filter(has_text="Balance QA")
            expect(fila).to_contain_text("6 m")
            fila.get_by_role("button", name="Ver fórmula y fuentes").click()
            expect(
                pagina.get_by_role("dialog", name="Definición y resultados del cálculo")
            ).to_contain_text("Balance QA")
            pagina.goto(f"{base}/graficos?ubicacion_id={proyecto}")
            pagina.locator("label").filter(has_text="Balance QA").click()
            pagina.get_by_role("button", name="Ver fórmula y fuentes de Balance QA").click()
            expect(
                pagina.get_by_role("dialog", name="Definición y resultados del cálculo")
            ).to_contain_text("Calculado: 6 m")
            assert errores == []
        except Exception:
            pagina.screenshot(path=str(tmp_path / f"hu38-error-{ancho}.png"), full_page=True)
            raise
        finally:
            browser.close()
