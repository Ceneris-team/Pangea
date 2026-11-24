"""HU32 en Edge: API de Pangea y PostgreSQL de prueba mediante TestClient.

Solo se simulan la sesión visual y los fallos de transporte. Las mediciones,
catálogos, validaciones y páginas se resuelven con los endpoints reales.
"""

import datetime as dt
import json
import os
from urllib.parse import parse_qs, urlencode, urlparse

import pytest

from app.models import EventoTexto, Telemetria
from tests.routers.test_filtros_avanzados import series as series
from tests.routers.test_mediciones import agregar_permiso
from tests.routers.test_mediciones import client as client
from tests.routers.test_mediciones import escenario_basico as escenario_basico


@pytest.mark.parametrize("ancho", [1365, 390])
def test_condiciones_validacion_paginas_limpieza_y_respuestas_tardias(
    client, db_session, series, ancho, tmp_path
):
    base = os.environ.get("HU32_UI_URL")
    if not base:
        pytest.skip("Definir HU32_UI_URL para probar la interfaz")
    from playwright.sync_api import expect, sync_playwright

    e, temp, nivel, _ = series
    # El formulario introduce fechas con precisión de minutos; las muestras
    # de este escenario quedan antes del minuto final seleccionado.
    for modelo in [Telemetria, EventoTexto]:
        db_session.query(modelo).filter(modelo.id_dspstv == e["dispositivo"].id_dspstv).update(
            {modelo.fch_hr: dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=2)}
        )
    db_session.flush()
    for modulo in ["Dispositivos", "Ubicaciones"]:
        agregar_permiso(db_session, e["usuario"], e["sede"], modulo, "Lectura", e["rol"])
    consultas, demoradas, errores = [], [], []
    estado = {"fallar": False, "retener": False}

    def responder(route):
        req = route.request
        if req.resource_type not in {"fetch", "xhr"}:
            if req.url.startswith(base):
                route.continue_()
            else:
                route.abort()
            return
        url = urlparse(req.url)
        if url.path in {"/mediciones", "/mediciones/parametros", "/dispositivos", "/ubicaciones"}:
            params = parse_qs(url.query)
            if url.path == "/mediciones":
                consultas.append(params)
                if estado["fallar"]:
                    route.fulfill(status=503, json={"detail": "Fallo temporal de consulta"})
                    return
                params["por_pagina"] = ["2"]
            respuesta = client.get(f"{url.path}?{urlencode(params, doseq=True)}")
            assert respuesta.status_code == 200, respuesta.text
            if url.path == "/mediciones" and estado["retener"]:
                demoradas.append((route, respuesta.json()))
                return
            route.fulfill(status=respuesta.status_code, json=respuesta.json())
            return
        datos = {"items": [], "total": 0}
        if url.path == "/auth/perfil":
            datos = {
                "nombre_completo": "Cliente QA",
                "correo": "qa@example.com",
                "rol": "Cliente Final",
                "scope": "por_sede",
                "estado": "Activo",
                "debe_cambiar_contrasena": False,
                "zona_horaria": "America/Lima",
                "operacion_habilitada": True,
                "rol_empresa": None,
                "cliente_id": None,
                "proyecto_id": None,
            }
        elif url.path == "/auth/acceso":
            datos = {"version": "hu32", "empresas": [], "proyecto_ids": [e["ubicacion"].id_ubccn]}
        elif url.path == "/comercial/mi-acceso":
            datos = {"operacion_habilitada": True, "aviso": None}
        route.fulfill(status=200, json=datos)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        pagina = browser.new_page(viewport={"width": ancho, "height": 1000})
        pagina.route("**/*", responder)
        pagina.on("pageerror", lambda err: errores.append(str(err)))
        try:
            pagina.goto(
                f"{base}/consulta-datos?ubicacion_id={e['ubicacion'].id_ubccn}&dispositivo_ids={e['dispositivo'].id_dspstv}"
            )
            expect(pagina.get_by_text("Mostrando 2 de 9 registros")).to_be_visible()
            boton_filtros = pagina.locator("header").get_by_role(
                "button", name="Filtros", exact=False
            )

            def abrir():
                boton_filtros.click()
                return pagina.get_by_role("dialog", name="Filtros", exact=True)

            panel = abrir()
            selector = panel.get_by_role("combobox", name="Añadir condición por parámetro")
            expect(selector.locator("option")).to_have_count(
                3
            )  # Dos numéricos; el texto no se ofrece.
            expect(panel.get_by_text("Frecuencia de muestreo", exact=False)).to_have_count(0)
            selector.select_option(str(temp.id_prmtr))
            condicion = panel.get_by_role(
                "group", name=f"Condición de {temp.nmbr} (°C)", exact=True
            )
            condicion.get_by_role("textbox", name="Valor mínimo", exact=True).fill("10")
            condicion.get_by_role("textbox", name="Valor máximo", exact=True).fill("0")
            antes = len(consultas)
            panel.get_by_role("button", name="Aplicar filtros", exact=True).click()
            expect(panel.get_by_role("alert")).to_contain_text("el mínimo no puede ser mayor")
            assert len(consultas) == antes
            condicion.get_by_role("textbox", name="Valor mínimo", exact=True).fill("abc")
            panel.get_by_role("button", name="Aplicar filtros", exact=True).click()
            expect(panel.get_by_role("alert")).to_contain_text("decimales válidos")
            condicion.get_by_role("textbox", name="Valor mínimo", exact=True).fill("-5,25")
            condicion.get_by_role("textbox", name="Valor máximo", exact=True).fill("5.5")
            selector.select_option(str(nivel.id_prmtr))
            condicion_nivel = panel.get_by_role(
                "group", name=f"Condición de {nivel.nmbr} (m)", exact=True
            )
            condicion_nivel.get_by_role("textbox", name="Valor mínimo", exact=True).fill("1")
            condicion_nivel.get_by_role("textbox", name="Valor máximo", exact=True).fill("2")
            panel.screenshot(path=str(tmp_path / f"hu32-panel-{ancho}.png"))
            for entrada in panel.get_by_role("textbox").all():
                caja = entrada.bounding_box()
                assert caja and 0 <= caja["x"] and caja["x"] + caja["width"] <= ancho + 1
            panel.get_by_role("button", name="Aplicar filtros", exact=True).click()
            expect(panel).to_have_count(0)
            expect(pagina.get_by_text("Mostrando 2 de 5 registros")).to_be_visible()
            resumen = pagina.get_by_role("region", name="Condiciones aplicadas")
            expect(resumen).to_contain_text("≥ -5.25 °C y ≤ 5.5 °C")
            expect(resumen).to_contain_text("≥ 1 m y ≤ 2 m")
            reglas = json.loads(consultas[-1]["condiciones"][0])
            assert reglas[0]["minimo"] == "-5.25"
            assert "frecuencia_muestreo" not in consultas[-1]
            for cantidad in [4, 5]:
                pagina.get_by_role("button", name="Cargar más", exact=True).click()
                expect(pagina.get_by_text(f"Mostrando {cantidad} de 5 registros")).to_be_visible()
                assert json.loads(consultas[-1]["condiciones"][0]) == reglas
            expect(pagina.locator("tbody tr")).to_have_count(5)

            # Editar y cerrar no altera lo aplicado.
            panel = abrir()
            panel.get_by_role("textbox", name="Valor mínimo", exact=True).first.fill("100")
            pagina.keyboard.press("Escape")
            expect(resumen).to_contain_text("≥ -5.25 °C")
            expect(pagina.get_by_text("Mostrando 5 de 5 registros")).to_be_visible()

            # Fuera del rango excluye ambos límites; se conservan las series sin condición.
            panel = abrir()
            condicion = panel.get_by_role(
                "group", name=f"Condición de {temp.nmbr} (°C)", exact=True
            )
            condicion.get_by_role("textbox", name="Valor mínimo", exact=True).fill("0")
            condicion.get_by_role("textbox", name="Valor máximo", exact=True).fill("10")
            condicion.get_by_role("combobox", name="Mostrar lecturas").select_option("fuera")
            panel.get_by_role("button", name="Aplicar filtros", exact=True).click()
            expect(pagina.get_by_text("Mostrando 2 de 4 registros")).to_be_visible()
            expect(resumen).to_contain_text("< 0 °C o > 10 °C")

            # Limpiar solo condiciones mantiene proyecto, equipo y período.
            anterior = consultas[-1]
            resumen.get_by_role("button", name="Limpiar filtros avanzados").click()
            expect(resumen).to_have_count(0)
            expect(pagina.get_by_text("Mostrando 2 de 9 registros")).to_be_visible()
            assert "condiciones" not in consultas[-1]
            for campo in ["ubicacion_ids", "dispositivo_ids", "fecha_inicio", "fecha_fin"]:
                assert consultas[-1][campo] == anterior[campo]

            # Error y reintento conservan la condición y usan la consulta real.
            panel = abrir()
            panel.get_by_role("combobox", name="Añadir condición por parámetro").select_option(
                str(temp.id_prmtr)
            )
            panel.get_by_role("textbox", name="Valor mínimo", exact=True).fill("100")
            estado["fallar"] = True
            panel.get_by_role("button", name="Aplicar filtros", exact=True).click()
            expect(pagina.get_by_role("alert")).to_contain_text("Fallo temporal")
            expect(resumen).to_contain_text("≥ 100 °C")
            estado["fallar"] = False
            pagina.get_by_role("button", name="Reintentar consulta").click()
            expect(pagina.get_by_text("Mostrando 2 de 4 registros")).to_be_visible()

            # Una respuesta tardía de otra condición no sustituye la consulta nueva.
            panel = abrir()
            panel.get_by_role("textbox", name="Valor mínimo", exact=True).fill("0")
            estado["retener"] = True
            panel.get_by_role("button", name="Aplicar filtros", exact=True).click()
            expect(pagina.get_by_text("Cargando datos...", exact=True)).to_be_visible()
            estado["retener"] = False
            panel = abrir()
            panel.get_by_role("textbox", name="Valor mínimo", exact=True).fill("100")
            panel.get_by_role("button", name="Aplicar filtros", exact=True).click()
            expect(pagina.get_by_text("Mostrando 2 de 4 registros")).to_be_visible()
            assert demoradas
            for route, datos in demoradas:
                route.fulfill(status=200, json=datos)
            pagina.wait_for_timeout(100)
            expect(pagina.get_by_text("Mostrando 2 de 4 registros")).to_be_visible()
            expect(resumen).to_contain_text("≥ 100 °C")

            # Solo el parámetro condicionado: conjunto vacío explícito, con edición disponible.
            panel = abrir()
            panel.get_by_role("checkbox", name=temp.nmbr, exact=False).locator("..").click()
            panel.get_by_role("button", name="Aplicar filtros", exact=True).click()
            expect(
                pagina.get_by_text("No hay registros para los filtros seleccionados.")
            ).to_be_visible()
            pagina.screenshot(path=str(tmp_path / f"hu32-vacio-{ancho}.png"), full_page=True)
            assert errores == []
        except Exception:
            pagina.screenshot(path=str(tmp_path / f"hu32-error-{ancho}.png"), full_page=True)
            raise
        finally:
            browser.close()
