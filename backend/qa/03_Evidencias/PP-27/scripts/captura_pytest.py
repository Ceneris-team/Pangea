import html, re, sys
from playwright.sync_api import sync_playwright
src, png = sys.argv[1], sys.argv[2]
lineas = [l.rstrip() for l in open(src, encoding="utf-8") if "::" in l or "passed" in l or "XFAIL" in l]
lineas = [re.sub(r"\s+\[\s*\d+%\]$", "", l) for l in lineas]
filas = "".join(
    f'<div class="{"x" if "XFAIL" in l or "xfail" in l.lower() else "ok" if "PASSED" in l else "r"}">{html.escape(l)}</div>' for l in lineas
)
doc = f"""<html><body style="font:12px Consolas,monospace;background:#fff;color:#111;padding:12px;width:1100px">
<h3 style="font-family:Segoe UI">pytest · QA PP-27 + suites de reproceso de dev (78edb10, PostgreSQL 16)</h3>{filas}
<style>.ok{{color:#1a7f37}}.x{{color:#9a6700}}.r{{font-weight:bold}}</style></body></html>"""
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 1130, "height": 800})
    pg.set_content(doc)
    pg.screenshot(path=png, full_page=True)
    b.close()
