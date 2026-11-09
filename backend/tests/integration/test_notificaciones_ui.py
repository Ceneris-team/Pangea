"""Interacciones reales en Edge; HTTP simulado. Requiere HT14_UI_URL con Vite."""

import json
import os
from urllib.parse import parse_qs, urlparse

import pytest


@pytest.mark.parametrize("ancho", [1365, 390])
def test_destinatarios_historial_y_alta_en_navegador(ancho):
    base = os.environ.get("HT14_UI_URL")
    if not base:
        pytest.skip("Definir HT14_UI_URL para ejecutar las pruebas de navegador")
    from playwright.sync_api import expect, sync_playwright

    destinatarios = [{"id": 1, "correo": "uno@example.com"}]
    alarma = {
        "id_alrm": 1,
        "nmbr": "Temperatura alta",
        "parametro_nombre": "Temperatura",
        "condicion": "> 30 °C",
        "estd": "Activa",
    }
    altas = []
    errores = []

    def responder(route):
        req = route.request
        if req.resource_type != "fetch":
            route.continue_()
            return
        path = urlparse(req.url).path
        parametros = parse_qs(urlparse(req.url).query)
        datos = {"items": [], "total": 0}
        status = 200
        if path == "/auth/perfil":
            datos = {
                "nombre_completo": "Usuario QA",
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
        elif path == "/auth/acceso":
            datos = {"version": "ht14", "empresas": [], "proyecto_ids": []}
        elif path == "/alarmas" and req.method == "GET":
            datos = {"items": [alarma], "total": 1, "pagina": 1, "por_pagina": 10}
        elif path == "/alarmas" and req.method == "POST":
            altas.append(req.post_data_json)
            datos = {"mensaje": "Alarma creada correctamente", "alarma": alarma}
            status = 201
        elif path == "/alarmas/ubicaciones":
            datos = {"items": [{"id_ubccn": 1, "nmbr": "Estación Norte"}]}
        elif path == "/alarmas/parametros":
            datos = {
                "items": [
                    {
                        "id_prmtr": 1,
                        "nmbr": "Temperatura",
                        "undd": "°C",
                        "dscrpcn": None,
                        "tipo_dato": "numerico",
                    }
                ]
            }
        elif path == "/alarmas/1/destinatarios" and req.method == "GET":
            datos = {"items": destinatarios}
        elif path == "/alarmas/1/destinatarios" and req.method == "POST":
            correo = req.post_data_json["correo"].lower()
            if any(d["correo"] == correo for d in destinatarios):
                status, datos = 409, {"detail": "Este correo ya recibe notificaciones de la alarma"}
            else:
                datos = {"id": len(destinatarios) + 1, "correo": correo}
                destinatarios.append(datos)
                status = 201
        elif path.startswith("/alarmas/1/destinatarios/") and req.method == "DELETE":
            destinatarios[:] = [d for d in destinatarios if str(d["id"]) != path.rsplit("/", 1)[-1]]
            route.fulfill(status=204)
            return
        elif path == "/alarmas/1" and req.method == "PATCH":
            alarma["estd"] = req.post_data_json["estado"]
        elif path == "/alarmas/notificaciones":
            estado = parametros.get("estado", ["Fallido"])[0]
            datos = {
                "total": 1,
                "items": [
                    {
                        "id": 1,
                        "destinatario": "uno@example.com",
                        "tipo": "alarma_activada",
                        "estado": estado,
                        "creada": "2026-11-05T12:00:00Z",
                        "enviada": None,
                        "proximo_intento": None,
                        "ultimo_error": "MessageRejected",
                        "mensaje_id": None,
                        "intentos": [
                            {
                                "numero": 1,
                                "fecha": "2026-11-05T12:00:00Z",
                                "resultado": "Fallido",
                                "error": "MessageRejected",
                            }
                        ],
                    }
                ],
            }
        route.fulfill(status=status, content_type="application/json", body=json.dumps(datos))

    with sync_playwright() as p:
        navegador = p.chromium.launch(channel="msedge", headless=True)
        pagina = navegador.new_page(viewport={"width": ancho, "height": 900})
        pagina.on("pageerror", lambda error: errores.append(str(error)))
        pagina.route("**/*", responder)
        try:
            pagina.goto(f"{base}/alarmas")
            pagina.get_by_role("button", name="Notificaciones", exact=True).click()
            dialogo = pagina.get_by_role("dialog")
            expect(dialogo).to_be_visible()
            expect(dialogo.get_by_text("uno@example.com", exact=True)).to_be_visible()
            dialogo.get_by_label("Correo del destinatario").fill("dos@example.com")
            dialogo.get_by_role("button", name="Añadir correo").click()
            expect(dialogo.get_by_text("dos@example.com", exact=True)).to_be_visible()
            dialogo.get_by_label("Correo del destinatario").fill("dos@example.com")
            dialogo.get_by_role("button", name="Añadir correo").click()
            expect(dialogo.get_by_role("alert")).to_contain_text("ya recibe")
            dialogo.get_by_role("button", name="Quitar dos@example.com").click()
            expect(dialogo.get_by_text("dos@example.com", exact=True)).to_have_count(0)
            dialogo.get_by_label("Resultado", exact=True).select_option("Fallido")
            dialogo.get_by_text("Ver diagnóstico e intentos").click()
            expect(dialogo.get_by_text("Último error: MessageRejected")).to_be_visible()
            dialogo.get_by_role("button", name="Pausar alarma").click()
            expect(dialogo.get_by_text("Estado de la alarma: Inactiva")).to_be_visible()
            assert dialogo.evaluate("e => e.scrollWidth <= e.clientWidth + 1")
            pagina.keyboard.press("Escape")
            expect(dialogo).to_have_count(0)
            pagina.get_by_role("button", name="Crear alarma", exact=True).click()
            pagina.locator("#nmbr").fill("Prueba con destinatarios")
            pagina.locator("#id_ubccn").select_option("1")
            pagina.locator("#id_prmtr").select_option("1")
            pagina.get_by_role("button", name="Siguiente", exact=True).click()
            pagina.locator("#vlr_umbrl").fill("35")
            pagina.get_by_label("Correos para notificaciones").fill(
                "uno@example.com; dos@example.com"
            )
            pagina.get_by_role("button", name="Guardar", exact=True).click()
            expect(pagina).to_have_url(f"{base}/alarmas")
            assert altas[0]["destinatarios"] == ["uno@example.com", "dos@example.com"]
            assert errores == []
        finally:
            navegador.close()
