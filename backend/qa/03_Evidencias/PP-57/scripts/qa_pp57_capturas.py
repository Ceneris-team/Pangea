"""QA PP-57 (PP-438): capturas de los reportes pytest y de la reproducción de DEF-20.

Uso: python qa_pp71_capturas.py <dir_evidencias>
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import html
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

EVID = Path(sys.argv[1])

with sync_playwright() as p:
    nav = p.chromium.launch(channel="msedge", headless=True)
    pag = nav.new_page(viewport={"width": 1200, "height": 330})
    for html_rep, nombre in [
        ("pytest_pp57_api.html", "EV-PP57-01_pytest-api"),
        ("pytest_regresion_dev.html", "EV-PP57-02_pytest-regresion"),
    ]:
        ruta = EVID / html_rep
        if not ruta.exists():
            continue
        pag.goto(ruta.resolve().as_uri())
        pag.wait_for_load_state("networkidle")
        # Solo resumen y fallos: oculta las filas aprobadas para que la captura sea legible.
        pag.evaluate("""() => {
            document.querySelectorAll('tbody.results-table-row').forEach(t => {
                if (!t.querySelector('.col-result')?.textContent.match(/Fail|Error/)) t.style.display = 'none';
            });
            document.querySelectorAll('.extras-row,.logwrapper').forEach(e => e.style.display = 'none');
        }""")
        pag.screenshot(path=str(EVID / f"{nombre}.png"), full_page=True)
    texto = (EVID / "defectos" / "def20_api_real.txt").read_text(encoding="utf-8")
    pag.set_content(
        "<body style='font:14px Consolas,monospace;background:#0b1220;color:#e5e7eb;padding:24px'>"
        "<h3 style='font-family:Segoe UI'>DEF-20 · GET /ubicaciones con byte NUL (API real)</h3>"
        f"<pre style='white-space:pre-wrap'>{html.escape(texto)}</pre></body>"
    )
    pag.set_viewport_size({"width": 1100, "height": 260})
    pag.screenshot(path=str(EVID / "defectos" / "EV-CP-530_DEF-20_api-nul.png"))
    nav.close()
print("ok", sorted(os.listdir(EVID)))
