"""QA PP-70 (PP-442): capturas de DEF-24 (rótulo), DEF-23/DEF-25 (parte baja del formulario) y DEF-26 (mensaje) en la app real.

Uso (desde backend/ del worktree de dev): python recortes_pp70.py <dir_defectos>
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import os
import sys

from playwright.sync_api import expect, sync_playwright

UI = "http://127.0.0.1:5180"
OUT = sys.argv[1]
sys.path.insert(0, os.getcwd())
from app.scripts.seed_usuarios_prueba import PASSWORD_PRUEBA  # noqa: E402

os.makedirs(OUT, exist_ok=True)
with sync_playwright() as p:
    nav = p.chromium.launch(channel="msedge", headless=True)
    pag = nav.new_page(viewport={"width": 1365, "height": 1000})
    pag.goto(f"{UI}/login")
    pag.locator("#email").fill("tecnico@pangea-dev.com")
    pag.locator("#password").fill(PASSWORD_PRUEBA)
    pag.locator("button[type=submit]").click()
    pag.wait_for_url(lambda u: "/login" not in u, timeout=15000)
    pag.goto(f"{UI}/clientes")
    pag.get_by_role("button", name="Entrar al entorno de Cliente Demo").click()
    pag.wait_for_load_state("networkidle")
    pag.goto(f"{UI}/parametros-calculados")
    pag.get_by_role("button", name="Añadir parámetro calculado").click()
    form = pag.get_by_role("form", name="Registrar definición calculada")
    expect(form.get_by_label("Nombre")).to_be_visible()
    rotulo = form.locator("label").first
    caja = rotulo.bounding_box()
    pag.screenshot(path=os.path.join(OUT, "EV-DEF-24_rotulo-ambito.png"),
                   clip={"x": caja["x"] - 8, "y": caja["y"] - 70, "width": 660, "height": caja["height"] + 130})
    form.get_by_label("Nombre").fill("QA70 Potencia")
    form.get_by_role("button", name="Insertar QA27 Nivel A").click()
    form.get_by_label("Fórmula").press_sequentially(" ** 2")
    form.get_by_label("Unidad de medida").fill("m^2")
    form.get_by_role("button", name="Validar fórmula").click()
    expect(form.get_by_text("Fórmula válida")).to_be_visible()
    form.get_by_label("Estado de la definición").select_option("Inactivo")
    form.get_by_role("button", name="Guardar", exact=True).scroll_into_view_if_needed()
    pag.screenshot(path=os.path.join(OUT, "EV-DEF-23-25_potencia-valida-estado-inactivo.png"))
    # DEF-26: referencia inexistente → mensaje genérico de sintaxis
    form.get_by_label("Estado de la definición").select_option("Activo")
    form.get_by_label("Fórmula").fill("[Parametro inexistente] * 2")
    form.get_by_label("Unidad de medida").fill("m")
    form.get_by_role("button", name="Validar fórmula").click()
    alerta = form.get_by_role("alert")
    expect(alerta).to_be_visible()
    form.get_by_label("Fórmula").scroll_into_view_if_needed()
    pag.screenshot(path=os.path.join(OUT, "EV-DEF-26_referencia-inexistente.png"))
    print("DEF-26:", alerta.inner_text())
    # Cerrar sin guardar: no se deja la definición en la base
    form.get_by_role("button", name="Cancelar").click()
    nav.close()
print("ok")
