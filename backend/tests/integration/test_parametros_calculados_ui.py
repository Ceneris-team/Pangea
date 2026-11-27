"""Filtros calculados en Edge con la API y PostgreSQL reales de prueba."""

import json
import os
from urllib.parse import parse_qs, urlparse

import pytest

from app.models import ParametroCalculado
from tests.routers.test_parametros_calculados import definir, preparar_origenes
from tests.routers.test_parametros_calculados import entorno_calculados as entorno_calculados


@pytest.mark.parametrize("ancho", [1365, 390])
def test_listado_filtros_contexto_y_recuperacion(entorno_calculados, ancho, tmp_path):
    base = os.environ.get("CALCULADOS_UI_URL")
    if not base:
        pytest.skip("Definir CALCULADOS_UI_URL para probar la interfaz")
    from playwright.sync_api import expect, sync_playwright

    e = entorno_calculados
    nivel, salida, _ = preparar_origenes(e)
    descripcion_larga = (
        "Descripción completa del balance entre las mediciones de entrada y salida. " * 4
    )
    for i in range(30):
        definir(
            e["db"],
            e["sedes"][0],
            f"Índice de operación {i:02}",
            "Activo" if i % 2 == 0 else "Inactivo",
        )
    for i in range(2):
        p = definir(e["db"], e["sedes"][0], f"Balance {i}")
        if i == 0:
            p.frml = " + ".join([f"(p_{nivel.id_prmtr} - p_{salida.id_prmtr})"] * 6)
            p.dscrpcn = None
        else:
            p.dscrpcn = descripcion_larga
    e["db"].flush()
    definir(e["db"], e["sedes"][1], "Ajeno al proyecto")
    definir(e["db"], e["sedes"][2], "Ajeno a la empresa")
    empresa = str(e["empresas"][0].id_clnt)
    proyecto = str(e["proyectos"][0].id_ubccn)
    e["client"].headers["X-Proyecto-Id"] = proyecto
    consultas, demoradas, errores = [], [], []
    estado = {"fallar": False, "retener": False, "fallar_detalle": False, "fallar_opciones": False}

    def responder(route):
        req = route.request
        if req.resource_type not in {"fetch", "xhr"}:
            if req.url.startswith(base):
                route.continue_()
            else:
                route.abort()
            return
        url = urlparse(req.url)
        if url.path.startswith("/parametros-calculados"):
            assert req.headers["x-cliente-id"] == empresa
            assert req.headers["x-proyecto-id"] == proyecto
            listado = url.path == "/parametros-calculados" and req.method == "GET"
            if listado:
                consultas.append(parse_qs(url.query))
            if (
                (listado and estado["fallar"])
                or (url.path.split("/")[-1].isdigit() and estado["fallar_detalle"])
                or (url.path.endswith("opciones-creacion") and estado["fallar_opciones"])
            ):
                route.fulfill(status=503, json={"detail": "Fallo temporal del listado"})
                return
            respuesta = e["client"].request(
                req.method,
                f"{url.path}?{url.query}",
                **({"json": req.post_data_json} if req.method == "POST" else {}),
            )
            assert respuesta.status_code in {200, 201, 422}, respuesta.text
            if listado and estado["retener"]:
                demoradas.append((route, respuesta.json()))
                return
            route.fulfill(status=respuesta.status_code, json=respuesta.json())
            return
        datos = {"items": [], "total": 0}
        if url.path == "/auth/perfil":
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
                "cliente_id": None,
                "proyecto_id": None,
            }
        elif url.path == "/comercial/mi-acceso":
            datos = {"operacion_habilitada": True, "aviso": None}
        route.fulfill(status=200, json=datos)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        pagina = browser.new_page(viewport={"width": ancho, "height": 1000})
        pagina.add_init_script(
            f"sessionStorage.setItem('pangea_cliente', {json.dumps(empresa)});"
            f"sessionStorage.setItem('pangea_proyecto_v2', {json.dumps(proyecto)});"
        )
        pagina.route("**/*", responder)
        pagina.on("pageerror", lambda err: errores.append(str(err)))
        try:
            pagina.goto(f"{base}/parametros-calculados")
            expect(pagina.get_by_text("Mostrando 1 a 10 de 32 registros")).to_be_visible()
            expect(
                pagina.get_by_role("heading", name="Parámetros calculados", exact=True)
            ).to_be_visible()
            expect(
                pagina.get_by_role("columnheader", name="Descripción", exact=True)
            ).to_be_visible()
            expect(pagina.get_by_role("columnheader")).to_have_count(7)
            fila_sin_descripcion = pagina.locator("tbody tr").filter(has_text="Balance 0")
            expect(fila_sin_descripcion.get_by_role("cell").nth(3)).to_have_text("Sin descripción")
            fila_descripcion = pagina.locator("tbody tr").filter(has_text="Balance 1")
            descripcion = fila_descripcion.get_by_role("cell").nth(3).locator("span")
            expect(descripcion).to_have_text(descripcion_larga.strip())
            expect(descripcion).to_have_attribute("title", descripcion_larga)
            descripcion.scroll_into_view_if_needed()
            assert descripcion.evaluate(
                "el => getComputedStyle(el).textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth"
            )
            pagina.screenshot(
                path=str(tmp_path / f"calculados-descripcion-{ancho}.png"), full_page=True
            )
            if ancho < 768:
                pagina.get_by_role("button", name="Abrir menú de navegación").click()
                menu = pagina.get_by_role("dialog", name="Navegación", exact=True)
                menu.get_by_role("link", name="Parámetros calculados", exact=True).click()
                expect(menu).not_to_be_visible()
            else:
                pagina.get_by_role("link", name="Parámetros calculados", exact=True).click()
            expect(pagina).to_have_url(f"{base}/parametros-calculados")
            contexto = pagina.get_by_label("Contexto del listado")
            expect(contexto).to_contain_text(e["proyectos"][0].nmbr)
            buscar = pagina.get_by_role("searchbox", name="Buscar por nombre")
            filtro_estado = pagina.get_by_role("combobox", name="Estado", exact=True)
            limpiar = pagina.get_by_role("button", name="Limpiar filtros", exact=True)
            expect(limpiar).to_be_disabled()
            for control in [buscar, filtro_estado, limpiar]:
                caja = control.bounding_box()
                assert caja and 0 <= caja["x"] and caja["x"] + caja["width"] <= ancho + 1

            # DEF-18: el error de validación es legible y limpiar recupera el listado.
            filtro_estado.select_option("Activo")
            buscar.fill("caudal\x00")
            expect(pagina.get_by_role("alert")).to_contain_text("caracteres de control")
            assert consultas[-1]["q"] == ["caudal\x00"]
            assert consultas[-1]["estado"] == ["Activo"]
            limpiar.click()
            expect(pagina.get_by_text("Mostrando 1 a 10 de 32 registros")).to_be_visible()

            buscar.fill("  ÍNDICE  ")
            expect(pagina.get_by_text("Mostrando 1 a 10 de 30 registros")).to_be_visible()
            assert consultas[-1]["q"] == ["ÍNDICE"]
            pagina.get_by_role("button", name="Siguiente", exact=True).click()
            expect(pagina.get_by_text("Mostrando 11 a 20 de 30 registros")).to_be_visible()
            expect(pagina.locator("tbody tr")).to_have_count(10)
            assert consultas[-1]["q"] == ["ÍNDICE"] and consultas[-1]["pagina"] == ["2"]
            filtro_estado.select_option("Inactivo")
            expect(pagina.get_by_text("Mostrando 1 a 10 de 15 registros")).to_be_visible()
            assert consultas[-1]["estado"] == ["Inactivo"] and consultas[-1]["pagina"] == ["1"]
            assert all("Inactivo" in fila.inner_text() for fila in pagina.locator("tbody tr").all())
            buscar.fill("Balance")
            expect(
                pagina.get_by_text("No se encontraron parámetros calculados con esos filtros.")
            ).to_be_visible()
            filtro_estado.select_option("Activo")
            expect(pagina.get_by_text("Mostrando 1 a 2 de 2 registros")).to_be_visible()
            pagina.screenshot(
                path=str(tmp_path / f"calculados-filtrados-{ancho}.png"), full_page=True
            )

            # Limpiar durante el debounce no deja que una búsqueda anterior reaparezca.
            buscar.fill("pendiente")
            limpiar.click()
            expect(pagina.get_by_text("Mostrando 1 a 10 de 32 registros")).to_be_visible()
            pagina.wait_for_timeout(400)
            expect(buscar).to_have_value("")
            expect(filtro_estado).to_have_value("")
            expect(limpiar).to_be_disabled()
            assert "q" not in consultas[-1] and "estado" not in consultas[-1]
            assert pagina.evaluate("sessionStorage.getItem('pangea_cliente')") == empresa
            assert pagina.evaluate("sessionStorage.getItem('pangea_proyecto_v2')") == proyecto

            estado["fallar"] = True
            buscar.fill("Balance")
            expect(pagina.get_by_role("alert")).to_contain_text("Fallo temporal del listado")
            expect(pagina.get_by_text("No se encontraron", exact=False)).to_have_count(0)
            expect(buscar).to_have_value("Balance")
            estado["fallar"] = False
            pagina.get_by_role("button", name="Reintentar listado").click()
            expect(pagina.get_by_text("Mostrando 1 a 2 de 2 registros")).to_be_visible()

            estado["retener"] = True
            buscar.fill("índice")
            expect(
                pagina.get_by_text("Cargando parámetros calculados…", exact=True)
            ).to_be_visible()
            estado["retener"] = False
            buscar.fill("Balance")
            expect(pagina.get_by_text("Mostrando 1 a 2 de 2 registros")).to_be_visible()
            assert demoradas
            for route, datos in demoradas:
                route.fulfill(status=200, json=datos)
            pagina.wait_for_timeout(100)
            expect(pagina.get_by_text("Mostrando 1 a 2 de 2 registros")).to_be_visible()
            expect(pagina.locator("tbody tr")).to_have_count(2)

            # La fórmula completa, sus referencias y el ámbito se consultan sin perder filtros.
            filtro_estado.select_option("Activo")
            expect(pagina.get_by_text("Mostrando 1 a 2 de 2 registros")).to_be_visible()
            estado["fallar_detalle"] = True
            pagina.get_by_role("button", name="Ver detalle de Balance 0", exact=True).click()
            detalle = pagina.get_by_role(
                "dialog", name="Detalle del parámetro calculado", exact=True
            )
            expect(detalle.get_by_role("alert")).to_contain_text("Fallo temporal")
            estado["fallar_detalle"] = False
            detalle.get_by_role("button", name="Reintentar detalle").click()
            expect(detalle.get_by_role("heading", name="Balance 0", exact=True)).to_be_visible()
            expect(detalle.get_by_text("Sin descripción", exact=True)).to_be_visible()
            expect(detalle.get_by_label("Parámetros de origen")).to_contain_text(
                "Nivel de entrada (m)"
            )
            expect(detalle.get_by_label("Parámetros de origen")).to_contain_text(
                "Nivel de salida (m)"
            )
            expect(
                detalle.get_by_text("Compartido por los proyectos de", exact=False)
            ).to_be_visible()
            expresion = detalle.locator("dd").filter(has_text="[Nivel de entrada]")
            expect(expresion).to_have_text(
                " + ".join(["([Nivel de entrada] - [Nivel de salida])"] * 6)
            )
            detalle.screenshot(path=str(tmp_path / f"calculados-detalle-{ancho}.png"))
            caja = expresion.bounding_box()
            assert caja and caja["x"] >= 0 and caja["x"] + caja["width"] <= ancho + 1
            detalle.get_by_role("button", name="Cerrar panel", exact=True).click()
            expect(buscar).to_have_value("Balance")
            expect(pagina.get_by_text("Mostrando 1 a 2 de 2 registros")).to_be_visible()

            # La acción de añadir abre un registro real con catálogos y validación de la API.
            estado["fallar_opciones"] = True
            pagina.get_by_role("button", name="Añadir parámetro calculado", exact=True).click()
            crear = pagina.get_by_role("dialog", name="Añadir parámetro calculado", exact=True)
            expect(crear.get_by_role("alert")).to_contain_text("Fallo temporal")
            estado["fallar_opciones"] = False
            crear.get_by_role("button", name="Reintentar opciones").click()
            expect(
                crear.get_by_role("button", name="Insertar Nivel de entrada (m)", exact=True)
            ).to_be_visible()
            crear.get_by_role("textbox", name="Nombre", exact=True).fill("Balance nuevo")
            crear.get_by_role("button", name="Insertar Nivel de entrada (m)", exact=True).click()
            formula = crear.get_by_role("textbox", name="Fórmula", exact=True)
            expect(formula).to_have_value("[Nivel de entrada]")
            formula.fill("[Nivel de entrada] +")
            crear.get_by_label("Unidad de medida", exact=True).fill("m")
            expect(
                crear.get_by_role("combobox", name="Ámbito de aplicación", exact=True)
            ).to_be_visible()
            expect(
                crear.get_by_role("combobox", name="Estado de la definición", exact=True)
            ).to_have_count(0)
            expect(crear.get_by_role("button", name="Guardar", exact=True)).to_be_disabled()
            crear.get_by_role("button", name="Validar fórmula", exact=True).click()
            expect(crear.get_by_role("alert")).to_contain_text("Revisa la fórmula")
            formula.fill("[Nivel de entrada] ** 2")
            crear.get_by_role("button", name="Validar fórmula", exact=True).click()
            expect(crear.get_by_role("alert")).to_contain_text("operaciones +, -, * y /")
            expect(crear.get_by_role("button", name="Guardar", exact=True)).to_be_disabled()
            formula.fill("[Parámetro inexistente] * 2")
            crear.get_by_role("button", name="Validar fórmula", exact=True).click()
            expect(crear.get_by_role("alert")).to_contain_text(
                "[Parámetro inexistente] no está disponible"
            )
            formula.fill("[Nivel de entrada] - [Nivel de salida]")
            crear.get_by_role("textbox", name="Descripción (opcional)").fill("Balance operativo")
            crear.get_by_role("button", name="Validar fórmula", exact=True).click()
            expect(crear.get_by_role("status")).to_have_text("Fórmula válida")
            crear.screenshot(path=str(tmp_path / f"calculados-registro-{ancho}.png"))
            crear.get_by_role("button", name="Guardar", exact=True).click()
            expect(crear).to_have_count(0)
            expect(
                pagina.get_by_role("status").filter(
                    has_text="Parámetro calculado añadido correctamente"
                )
            ).to_be_visible()
            expect(buscar).to_have_value("Balance")
            expect(filtro_estado).to_have_value("Activo")
            expect(pagina.get_by_text("Mostrando 1 a 3 de 3 registros")).to_be_visible()
            expect(pagina.locator("tbody")).to_contain_text("Balance nuevo")
            assert (
                e["db"]
                .query(ParametroCalculado)
                .filter(ParametroCalculado.nmbr == "Balance nuevo")
                .count()
                == 1
            )
            assert (
                e["db"].query(ParametroCalculado).filter_by(nmbr="Balance nuevo").one().estd
                == "Activo"
            )

            # Ausencia real de configuraciones conserva la entrada al registro.
            from app.models import DependenciaCalculo, TrabajoCalculo

            e["db"].query(DependenciaCalculo).delete()
            e["db"].query(TrabajoCalculo).delete()
            e["db"].query(ParametroCalculado).delete()
            e["db"].flush()
            limpiar.click()
            expect(
                pagina.get_by_text(
                    "Aún no hay parámetros calculados configurados en este contexto."
                )
            ).to_be_visible()
            expect(
                pagina.get_by_role("button", name="Añadir parámetro calculado", exact=True)
            ).to_be_visible()
            expect(pagina.get_by_text("Mostrando 0 a 0 de 0 registros")).to_be_visible()
            assert errores == []
        except Exception:
            pagina.screenshot(path=str(tmp_path / f"calculados-error-{ancho}.png"), full_page=True)
            raise
        finally:
            browser.close()
