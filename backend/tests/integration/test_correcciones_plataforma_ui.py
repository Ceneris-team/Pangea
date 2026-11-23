"""Regresiones de navegación, sesión, filtros y alarmas en Edge con HTTP simulado."""

import json
import os
from urllib.parse import parse_qs, urlparse

import pytest


@pytest.fixture()
def interfaz():
    base = os.environ.get("HT14_UI_URL")
    if not base:
        pytest.skip("Definir HT14_UI_URL para ejecutar las pruebas de navegador")
    from playwright.sync_api import sync_playwright

    estado = {
        "editar": False,
        "perfil_status": 200,
        "error_catalogo": False,
        "cantidad": 2,
        "consultas": [],
        "escrituras": [],
        "errores": [],
        "condiciones": [{"oprdr": ">", "vlr_umbrl": 30}],
    }
    alarma = {
        "id_alrm": 1,
        "nmbr": "Temperatura alta",
        "parametro_nombre": "Temperatura",
        "condicion": "> 30 °C",
        "estd": "Activa",
        "dispositivos": [
            {
                "id_dspstv": 1,
                "nombre": "Equipo 1",
                "en_alarma": True,
                "desde": "2026-11-13T15:00:00Z",
                "ultima_evaluacion": "2026-11-13T15:10:00Z",
                "pendiente_evaluacion": False,
            }
        ],
    }

    def responder(route):
        req = route.request
        if req.resource_type != "fetch":
            route.continue_()
            return
        url = urlparse(req.url)
        path, query = url.path, parse_qs(url.query)
        estado["consultas"].append((path, query))
        datos, status = {"items": [], "total": 0}, 200
        if req.method != "GET":
            estado["escrituras"].append((path, req.post_data_json))
        if path == "/auth/perfil":
            status = estado["perfil_status"]
            datos = {
                "nombre_completo": "Persona QA",
                "correo": "qa@example.com",
                "rol": "Usuario Empresa",
                "scope": "por_cliente",
                "estado": "Activo",
                "debe_cambiar_contrasena": False,
                "zona_horaria": "Asia/Tokyo",
                "operacion_habilitada": True,
                "rol_empresa": "Administrador" if estado["editar"] else "Lector",
                "cliente_id": 1,
                "proyecto_id": 1,
                "puede_editar_alarmas": estado["editar"],
            }
        elif path == "/auth/acceso":
            datos = {
                "version": "qa",
                "empresas": [{"id_clnt": 1, "rol": "Lector", "proyecto_ids": list(range(1, 102))}],
                "proyecto_ids": [],
            }
        elif path == "/auth/zonas-horarias":
            datos = {"zonas_horarias": ["America/Lima", "Asia/Tokyo"]}
        elif path == "/comercial/mi-acceso":
            datos = {"aviso": None, "operacion_habilitada": True}
        elif path == "/alarmas":
            datos = {"total": 1, "pagina": 1, "por_pagina": 10, "items": [alarma]}
        elif path == "/alarmas/1":
            if req.method == "PATCH":
                estado["condiciones"] = req.post_data_json["condiciones"]
                alarma["dispositivos"][0]["pendiente_evaluacion"] = True
            datos = {**alarma, "unidad": "°C", "condiciones": estado["condiciones"]}
        elif path == "/alarmas/1/destinatarios":
            datos = {"items": [{"id": 1, "correo": "operaciones@example.com"}]}
        elif path == "/alarmas/notificaciones":
            datos = {
                "total": 1,
                "items": [
                    {
                        "id": 1,
                        "destinatario": "operaciones@example.com",
                        "tipo": "alarma_activada",
                        "estado": "Enviado",
                        "creada": "2026-11-13T15:00:00Z",
                        "enviada": None,
                        "proximo_intento": None,
                        "ultimo_error": None,
                        "mensaje_id": None,
                        "intentos": [],
                    }
                ],
            }
        elif path == "/mediciones/parametros":
            if estado["error_catalogo"]:
                status, datos = 503, {"detail": "Servicio no disponible"}
            else:
                datos = {
                    "items": [
                        {
                            "id_prmtr": 1,
                            "nmbr": "Temperatura",
                            "undd": "°C",
                            "tipo_dato": "numerico",
                        }
                    ]
                }
        elif path in ("/ubicaciones", "/dispositivos"):
            pagina = int(query.get("pagina", [1])[0])
            limite = int(query.get("por_pagina", [100])[0])
            todos = (
                [{"id_ubccn": i, "nmbr": f"Proyecto {i}"} for i in range(1, estado["cantidad"] + 1)]
                if path == "/ubicaciones"
                else [
                    {"id_dspstv": i, "nmbr": f"Equipo {i}", "id_ubccn": 1}
                    for i in range(1, estado["cantidad"] + 1)
                ]
            )
            datos = {"total": len(todos), "items": todos[(pagina - 1) * limite : pagina * limite]}
        elif path == "/dispositivos/1":
            datos = {
                "id_dspstv": 1,
                "nmbr": "Equipo 1",
                "id_ubccn": 1,
                "ubicacion_nombre": "Proyecto 1",
                "mrc": "Campbell",
                "mdl": "CR1000",
                "estd": "Activo",
                "lttd": 0,
                "lngtd": 0,
            }
        elif path == "/dispositivos/1/estadisticas":
            datos = {
                "total_recibidos": 5,
                "total_procesados": 5,
                "total_fallidos": 0,
                "ultima_fecha_recepcion": "2026-11-13T15:00:00Z",
                "fecha_inicio": "2026-11-06T15:00:00Z",
                "fecha_fin": "2026-11-13T15:00:00Z",
                "id_cnxn": 1,
                "id_ubccn": 1,
            }
        elif path == "/mediciones":
            ids = [int(i) for i in query.get("dispositivo_ids", [1, 2])]
            datos = {
                "total": len(ids),
                "next_cursor": None,
                "items": [
                    {
                        "id_registro": i,
                        "fch_hr": "2026-11-13T15:00:00Z",
                        "ubicacion_nombre": "Proyecto 1",
                        "parametro_nombre": "Temperatura",
                        "undd": "°C",
                        "vlr": 25,
                        "dispositivo_nombre": f"Equipo {i}",
                    }
                    for i in ids
                ],
            }
        elif path == "/exportaciones/limites":
            datos = {"max_dias": 365, "max_filas": 100000, "vigencia_horas": 24}
        elif path == "/exportaciones/dispositivos":
            datos = {"hay_mas": False, "items": []}
        elif path == "/exportaciones" and req.method == "POST":
            datos = {"mensaje": "Exportación solicitada"}
        route.fulfill(status=status, content_type="application/json", body=json.dumps(datos))

    with sync_playwright() as p:
        navegador = p.chromium.launch(channel="msedge", headless=True)
        contexto = navegador.new_context(
            viewport={"width": 1365, "height": 900}, timezone_id="America/Lima"
        )
        pagina = contexto.new_page()
        pagina.on("pageerror", lambda e: estado["errores"].append(str(e)))
        pagina.route("**/*", responder)
        try:
            yield pagina, base, estado
            assert estado["errores"] == []
        finally:
            navegador.close()


def test_menu_movil_foco_y_solo_lectura(interfaz):
    from playwright.sync_api import expect

    pagina, base, estado = interfaz
    pagina.set_viewport_size({"width": 390, "height": 844})
    pagina.goto(f"{base}/alarmas")
    expect(pagina.get_by_role("button", name="Crear alarma", exact=True)).to_have_count(0)
    pagina.get_by_role("button", name="Abrir menú de navegación").click()
    menu = pagina.get_by_role("dialog", name="Navegación", exact=True)
    expect(menu.get_by_role("link", name="Consulta de datos", exact=True)).to_be_visible()
    menu.get_by_role("link", name="Consulta de datos", exact=True).click()
    expect(menu).to_be_hidden()
    expect(pagina).to_have_url(f"{base}/consulta-datos")
    pagina.get_by_role("button", name="Abrir configuración de mi perfil").click()
    perfil = pagina.get_by_role("dialog", name="Mi perfil", exact=True)
    expect(perfil).to_be_visible()
    for _ in range(18):
        pagina.keyboard.press("Tab")
        assert perfil.evaluate("e => e.contains(document.activeElement)")
    for _ in range(18):
        pagina.keyboard.press("Shift+Tab")
        assert perfil.evaluate("e => e.contains(document.activeElement)")
    pagina.keyboard.press("Escape")
    expect(perfil).to_be_hidden()
    expect(pagina.get_by_role("button", name="Abrir configuración de mi perfil")).to_be_focused()
    pagina.goto(f"{base}/alarmas/nueva")
    expect(pagina).to_have_url(f"{base}/alarmas")
    pagina.get_by_role("button", name="Notificaciones", exact=True).click()
    dialogo = pagina.locator("dialog[open]")
    expect(dialogo.get_by_role("button", name="Pausar alarma")).to_have_count(0)
    expect(dialogo.get_by_role("button", name="Añadir correo")).to_have_count(0)
    expect(dialogo.get_by_text("Alarma activada · 14/11/2026, 0:00:00")).to_be_visible()
    assert estado["escrituras"] == []


def test_error_temporal_conserva_entorno_y_reintenta(interfaz):
    from playwright.sync_api import expect

    pagina, base, estado = interfaz
    estado["perfil_status"] = 503
    pagina.goto(f"{base}/alarmas")
    expect(pagina.get_by_role("heading", name="No pudimos comprobar tu sesión")).to_be_visible()
    pagina.evaluate(
        "() => { sessionStorage.setItem('pangea_cliente', '1'); sessionStorage.setItem('pangea_proyecto_v2', '1'); }"
    )
    pagina.reload()
    expect(pagina.get_by_role("button", name="Reintentar", exact=True)).to_be_visible()
    assert pagina.evaluate("sessionStorage.getItem('pangea_proyecto_v2')") == "1"
    assert pagina.url == f"{base}/alarmas"
    estado["perfil_status"] = 200
    pagina.get_by_role("button", name="Reintentar", exact=True).click()
    expect(
        pagina.get_by_role("heading", name="Gestión de Alarmas y Notificaciones")
    ).to_be_visible()
    assert pagina.evaluate("sessionStorage.getItem('pangea_proyecto_v2')") == "1"
    estado["perfil_status"] = 401
    pagina.reload()
    expect(pagina).to_have_url(f"{base}/login")
    assert pagina.evaluate("sessionStorage.getItem('pangea_proyecto_v2')") is None


def test_catalogos_completos_equipo_de_origen_y_error_recuperable(interfaz):
    from playwright.sync_api import expect

    pagina, base, estado = interfaz
    estado["cantidad"] = 101
    estado["error_catalogo"] = True
    pagina.goto(f"{base}/graficos?ubicacion_id=1&dispositivo_ids=101")
    expect(pagina.get_by_role("alert")).to_contain_text("No se pudieron cargar los parámetros")
    expect(pagina.locator("#ubicacion-graficos option")).to_have_count(102)
    expect(pagina.get_by_text("Equipos seleccionados: Equipo 101", exact=True)).to_be_visible()
    pagina.get_by_role("button", name="Dataloggers", exact=False).click()
    panel = pagina.get_by_role("dialog", name="Dataloggers", exact=True)
    expect(panel.get_by_role("checkbox")).to_have_count(101)
    expect(panel.get_by_role("checkbox", name="Equipo 101", exact=True)).to_be_checked()
    pagina.keyboard.press("Escape")
    estado["error_catalogo"] = False
    pagina.get_by_role("button", name="Reintentar catálogos").click()
    expect(pagina.get_by_role("alert")).to_have_count(0)
    assert any(
        path == "/ubicaciones" and query.get("pagina") == ["2"]
        for path, query in estado["consultas"]
    )
    assert any(
        path == "/dispositivos" and query.get("pagina") == ["2"]
        for path, query in estado["consultas"]
    )


def test_consulta_aplica_y_restablece_todo_incluida_exportacion(interfaz):
    from datetime import datetime, timedelta

    from playwright.sync_api import expect

    pagina, base, estado = interfaz
    pagina.goto(f"{base}/dispositivos/1")
    pagina.get_by_role("button", name="Consultar datos", exact=True).click()
    expect(pagina).to_have_url(f"{base}/consulta-datos?ubicacion_id=1&dispositivo_ids=1")
    expect(pagina.locator("tbody").get_by_text("Equipo 1", exact=True)).to_be_visible()
    expect(pagina.locator("tbody").get_by_text("Equipo 2", exact=True)).to_have_count(0)
    pagina.get_by_role("button", name="Filtros", exact=False).click()
    filtros = pagina.get_by_role("dialog", name="Filtros", exact=True)
    expect(filtros.get_by_role("button", name="Aplicar filtros", exact=True)).to_have_count(1)
    parametros = filtros.get_by_role("group", name="Parámetros", exact=True)
    parametros.locator("label").click()
    expect(parametros.get_by_role("checkbox")).to_be_checked()
    filtros.get_by_label("Fecha inicio", exact=True).fill("2020-01-01T00:00")
    filtros.get_by_label("Fecha fin", exact=True).fill("2020-01-03T00:00")
    filtros.get_by_label("Frecuencia de muestreo (min)", exact=True).fill("5")
    filtros.get_by_label("Valor mínimo", exact=True).fill("30")
    filtros.get_by_label("Valor máximo", exact=True).fill("20")
    filtros.get_by_role("button", name="Aplicar filtros", exact=True).click()
    expect(filtros.get_by_role("alert")).to_contain_text("mínimo no puede ser mayor")
    filtros.get_by_label("Valor mínimo", exact=True).fill("10")
    filtros.get_by_role("button", name="Aplicar filtros", exact=True).click()
    expect(filtros).to_be_hidden()
    expect(pagina.locator("tbody").get_by_text("Equipo 1", exact=True)).to_be_visible()
    assert any(
        path == "/mediciones"
        and query.get("valor_min") == ["10"]
        and query.get("dispositivo_ids") == ["1"]
        and query.get("parametro_ids") == ["1"]
        and query.get("frecuencia_muestreo") == ["5"]
        and query.get("fecha_inicio") == ["2020-01-01T05:00:00.000Z"]
        and query.get("fecha_fin") == ["2020-01-03T05:00:00.000Z"]
        for path, query in estado["consultas"]
    )
    pagina.get_by_role("button", name="Exportar datos CSV / Excel").click()
    pagina.get_by_role("button", name="Solicitar exportación").click()
    expect(pagina.get_by_text("Exportación solicitada", exact=True)).to_be_visible()
    assert estado["escrituras"][-1][1]["dispositivo_ids"] == [1]
    pagina.get_by_role("button", name="Filtros", exact=False).click()
    filtros.get_by_role("button", name="Restablecer todo").click()
    expect(filtros.get_by_label("Valor mínimo", exact=True)).to_have_value("")
    expect(filtros.get_by_label("Valor máximo", exact=True)).to_have_value("")
    expect(filtros.get_by_label("Frecuencia de muestreo (min)", exact=True)).to_have_value("")
    expect(filtros.locator('input[type="checkbox"]:checked')).to_have_count(0)
    expect(filtros.get_by_role("checkbox", name="Equipo 1", exact=True)).not_to_be_checked()
    pagina.keyboard.press("Escape")
    expect(pagina.locator("tbody").get_by_text("Equipo 2", exact=True)).to_be_visible()
    ultima = [query for path, query in estado["consultas"] if path == "/mediciones"][-1]
    assert (
        "valor_min" not in ultima
        and "ubicacion_ids" not in ultima
        and "dispositivo_ids" not in ultima
        and "parametro_ids" not in ultima
        and "valor_max" not in ultima
        and "frecuencia_muestreo" not in ultima
    )
    inicio = datetime.fromisoformat(ultima["fecha_inicio"][0])
    fin = datetime.fromisoformat(ultima["fecha_fin"][0])
    assert fin - inicio == timedelta(hours=24)
    assert inicio.year > 2020


def test_historial_desde_estadisticas_conserva_el_equipo(interfaz):
    from playwright.sync_api import expect

    pagina, base, estado = interfaz
    estado["editar"] = True
    pagina.goto(f"{base}/dispositivos")
    fila = pagina.locator("tbody tr").filter(has_text="Equipo 1")
    fila.get_by_role("button", name="Ver estadísticas", exact=True).click()
    pagina.get_by_role("button", name="VER HISTORIAL DE DATOS", exact=True).click()
    expect(pagina).to_have_url(f"{base}/consulta-datos?ubicacion_id=1&dispositivo_ids=1")
    expect(pagina.locator("tbody").get_by_text("Equipo 1", exact=True)).to_be_visible()
    expect(pagina.locator("tbody").get_by_text("Equipo 2", exact=True)).to_have_count(0)


def test_edicion_y_estado_de_incidente_desde_la_pantalla(interfaz):
    from playwright.sync_api import expect

    pagina, base, estado = interfaz
    estado["editar"] = True
    pagina.goto(f"{base}/alarmas")
    expect(pagina.get_by_text("1 equipo en alarma", exact=True)).to_be_visible()
    pagina.get_by_text("Ver equipos y fechas", exact=True).click()
    expect(pagina.get_by_text("Desde 14/11/2026, 0:00:00", exact=True)).to_be_visible()
    pagina.get_by_role("button", name="Editar condiciones", exact=True).click()
    editor = pagina.locator("dialog[open]")
    editor.get_by_label("Umbral 1", exact=True).fill("40")
    editor.get_by_role("button", name="Añadir condición").click()
    editor.get_by_label("Operador 2", exact=True).select_option("<")
    editor.get_by_label("Umbral 2", exact=True).fill("10")
    editor.get_by_role("button", name="Guardar condiciones").click()
    expect(editor).to_have_count(0)
    expect(pagina.get_by_text("Pendiente de lectura", exact=True)).to_be_visible()
    assert estado["condiciones"] == [
        {"oprdr": ">", "vlr_umbrl": 40},
        {"oprdr": "<", "vlr_umbrl": 10},
    ]
