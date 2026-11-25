"""Flujo real en Edge con HTTP simulado, sin contactar servicios de producción."""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest


@pytest.mark.parametrize("ancho", [1365, 390])
def test_archivar_no_detiene_captura_y_respuesta_tardia_no_cambia_otro_proyecto(ancho):
    base = os.getenv("HT14_UI_URL")
    if not base:
        pytest.skip("Definir HT14_UI_URL para ejecutar el flujo de navegador")
    from playwright.sync_api import expect, sync_playwright

    poligono = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]}
    proyectos = {
        i: {
            "id_ubccn": i,
            "id_sd": 1,
            "nmbr": nombre,
            "dscrpcn": None,
            "lttd": 0,
            "lngtd": 0,
            "estd": "Activa",
            "monitoreo_activo": True,
            "plgn_gjsn": poligono,
        }
        for i, nombre in [(1, "Alfa"), (2, "Beta")]
    }
    retrasadas = []
    cambios = []
    confirmaciones = []
    errores = []

    def responder(route):
        req = route.request
        if req.resource_type not in {"fetch", "xhr"}:
            if req.url.startswith(base):
                route.continue_()
            else:
                route.abort()
            return
        path = urlparse(req.url).path
        datos = {"items": [], "total": 0}
        if path == "/auth/perfil":
            datos = {
                "nombre_completo": "Técnico QA",
                "correo": "qa@example.com",
                "rol": "Técnico CENERIS",
                "scope": "global",
                "estado": "Activo",
                "debe_cambiar_contrasena": False,
                "zona_horaria": "America/Lima",
                "operacion_habilitada": True,
                "puede_editar_alarmas": True,
                "rol_empresa": None,
                "cliente_id": 1,
                "proyecto_id": None,
            }
        elif path == "/auth/acceso":
            datos = {"version": "continuidad", "empresas": [], "proyecto_ids": [1, 2]}
        elif path == "/comercial/mi-acceso":
            datos = {"aviso": None, "operacion_habilitada": True}
        elif path == "/sedes":
            datos = [{"id_sd": 1, "nmbr": "Sede QA"}]
        elif path == "/ingesta/metricas":
            datos = {"pendientes": 0, "procesando": 0, "exitosos": 0, "fallidos": 1, "total": 1}
        elif path == "/ingesta/cola":
            assert "id_dspstv=2" in req.url
            datos = {
                "items": [
                    {
                        "id_archv": 1,
                        "nmbr_archv": "H_corrupto.dat",
                        "datalogger_nombre": "Equipo QA",
                        "fch_dtccn": "2026-11-23T12:00:00Z",
                        "estado": "Fallido",
                    }
                ],
                "total": 1,
                "pagina": 1,
                "por_pagina": 10,
            }
        elif path == "/ingesta/cola/1":
            datos = {
                "id_archv": 1,
                "nmbr_archv": "H_corrupto.dat",
                "datalogger_nombre": "Equipo QA",
                "fch_dtccn": "2026-11-23T12:00:00Z",
                "fch_prcsd": None,
                "estado": "Fallido",
                "mnsj_errr": "Archivo corrupto, original conservado",
                "rgstrs_prcsds": 0,
            }
        elif path == "/ingesta/cola/1/intentos":
            datos = []
        elif path == "/ingesta/cola/1/original":
            assert req.headers.get("x-cliente-id") == "1"
            route.fulfill(
                status=200,
                content_type="application/octet-stream",
                body=b"\xff\x00original corrupto",
            )
            return
        elif path == "/ubicaciones":
            datos = {"items": list(proyectos.values()), "total": 2, "pagina": 1, "por_pagina": 10}
        elif path in {"/ubicaciones/1", "/ubicaciones/2"}:
            identificador = int(path.rsplit("/", 1)[1])
            if req.method == "GET":
                if identificador == 1:
                    retrasadas.append(route)
                    return
                datos = proyectos[identificador]
            else:
                cambios.append(req.post_data_json)
                proyectos[identificador].update(req.post_data_json)
                datos = {"mensaje": "Proyecto actualizado correctamente"}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(datos))

    with sync_playwright() as p:
        navegador = p.chromium.launch(channel="msedge", headless=True)
        pagina = navegador.new_page(viewport={"width": ancho, "height": 1000})
        pagina.add_init_script(
            "sessionStorage.setItem('pangea_cliente','1'); localStorage.setItem('pangea_rol','Técnico CENERIS');"
        )
        pagina.route("**/*", responder)
        pagina.on("pageerror", lambda error: errores.append(str(error)))
        pagina.on(
            "dialog", lambda dialogo: (confirmaciones.append(dialogo.message), dialogo.accept())
        )
        try:
            pagina.goto(f"{base}/ubicaciones")
            pagina.get_by_role("row").filter(has_text="Alfa").get_by_role(
                "button", name="Editar", exact=True
            ).click()
            expect(pagina.get_by_role("dialog")).to_be_visible()
            pagina.keyboard.press("Escape")
            pagina.get_by_role("row").filter(has_text="Beta").get_by_role(
                "button", name="Editar", exact=True
            ).click()
            expect(pagina.locator("#nmbr")).to_have_value("Beta")
            assert retrasadas
            retrasadas[0].fulfill(
                status=200, content_type="application/json", body=json.dumps(proyectos[1])
            )
            expect(pagina.locator("#nmbr")).to_have_value("Beta")
            pagina.locator("#estd").select_option("Inactiva")
            pagina.get_by_role("button", name="Guardar cambios", exact=True).click()
            expect(pagina.get_by_role("dialog")).to_have_count(0)
            assert cambios[-1]["monitoreo_activo"] is True
            assert cambios[-1]["estd"] == "Inactiva"
            assert confirmaciones == []
            pagina.get_by_role("row").filter(has_text="Beta").get_by_role(
                "button", name="Editar", exact=True
            ).click()
            expect(pagina.locator("#nmbr")).to_have_value("Beta")
            pagina.get_by_label(re.compile("Recoger datos de los equipos")).uncheck()
            pagina.get_by_role("button", name="Guardar cambios", exact=True).click()
            expect(pagina.get_by_role("dialog")).to_have_count(0)
            assert cambios[-1]["monitoreo_activo"] is False
            assert len(confirmaciones) == 1 and "detendrá la recogida" in confirmaciones[0]
            pagina.goto(f"{base}/cola-ingesta?dispositivo_id=2")
            pagina.get_by_role("row").filter(has_text="H_corrupto.dat").click()
            with pagina.expect_download() as descarga:
                pagina.get_by_role("button", name="Descargar original para revisión").click()
            assert Path(descarga.value.path()).read_bytes() == b"\xff\x00original corrupto"
            assert errores == []
        except Exception:
            print(
                {
                    "url": pagina.url,
                    "pantalla": pagina.locator("body").inner_text()[:2500],
                    "errores": errores,
                }
            )
            raise
        finally:
            navegador.close()
