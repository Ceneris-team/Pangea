"""PP-426 (HU-23 Listar paneles) ronda 2: reprueba de DEF-05 y paso de los 5 documentos QA de v0.16 a v0.17.

Ejecutar desde backend/: venv/Scripts/python.exe qa/playwright_hu23/generar_documentos_qa_ronda2.py
Solo toca lo de HU-23: CP-237, CP-238 y CP-261, RG-22 a RG-25, DEF-05, la ronda 2, RQ-HU23-03 y la fila de HU-23.
"""
import copy
import hashlib
from pathlib import Path

import docx
import openpyxl
from docx.text.paragraph import Paragraph

QA = Path(__file__).resolve().parents[1]
EVD = QA / "03_Evidencias" / "HU23"
HU = "HU-23"
FECHA = "05/11/2026"
HORA = "09:26"
COMMIT = "d7e1fab (qa-elliot, con 5430e91 de dev)"
UBIC = "backend/qa/03_Evidencias/HU23/"
V0, V1 = "v0.16", "v0.17"


def ruta(carpeta, nombre, v, ext="xlsx"):
    return QA / carpeta / f"Pangea_{nombre}_{v}.{ext}"


def buscar(ws, valor, col=1):
    for r in range(2, ws.max_row + 1):
        if ws.cell(r, col).value == valor:
            return r
    raise KeyError(valor)


def vacia(ws, col=1, ini=2):
    r = ini
    while ws.cell(r, col).value not in (None, ""):
        r += 1
    return r


def estilo(ws, origen, destino, ncols):
    for c in range(1, ncols + 1):
        ws.cell(destino, c)._style = copy.copy(ws.cell(origen, c)._style)
    if ws.row_dimensions[origen].height:
        ws.row_dimensions[destino].height = ws.row_dimensions[origen].height


def portada(wb):
    ws = wb["Portada"]
    ws["B7"] = "0.17"
    ws["B8"] = ws["B8"].value.rstrip() + "; ronda 2 de HU-23 (PP-426, 05/11/2026): reprueba de DEF-05 sobre d7e1fab, que incluye 5430e91 de dev"
    wb.calculation.fullCalcOnLoad = True


def sha(nombre):
    p = EVD / nombre
    return round(p.stat().st_size / 1024, 1), hashlib.sha256(p.read_bytes()).hexdigest()


# ================================ Casos ================================
wb = openpyxl.load_workbook(ruta("02_Casos_de_Prueba", "Casos_de_Prueba", V0))
ws = wb["Casos de Prueba"]
CAMBIOS = {
    "CP-237": ("Devolvió lista vacía: el «%» se busca como texto literal (DEF-05 corregido por Dev en 5430e91).", "EV-CP-237 (ronda 1); EV-HU23-R2-01 (ronda 2)"),
    "CP-238": ("Devolvió lista vacía: el «_» se busca como texto literal (DEF-05 corregido por Dev en 5430e91).", "EV-CP-238 (ronda 1); EV-HU23-R2-01 (ronda 2)"),
    "CP-261": ("Con «%» en el buscador el listado queda vacío y muestra «No se encontraron paneles con ese criterio.» (DEF-05 corregido).", "EV-CP-261 (ronda 1); EV-HU23-R2-02 (ronda 2)"),
}
for cid, (obtenido, ev) in CAMBIOS.items():
    r = buscar(ws, cid)
    ws.cell(r, 11, obtenido)
    ws.cell(r, 12, "Aprobado")
    ws.cell(r, 14, ev)
    ws.cell(r, 16, FECHA)
    ws.cell(r, 19, COMMIT)
wr = wb["Regresión"]
ev_r = {
    "RG-22": ("Aprobado", "28 aprobadas el 05/11/2026 (en la ronda 1: 26 aprobadas y 2 fallidas por DEF-05).", "EV-HU23-INF-01, EV-HU23-R2-01"),
    "RG-23": ("Aprobado", "12 de 12. Ronda 1: 11 aprobadas y 1 fallida por DEF-05. En la ronda 2 se repitió solo CP-261 (el «%» en pantalla) porque Dev cambió únicamente routers/panel.py y sus tests; el frontend no cambió.", "EV-HU23-INF-03, EV-HU23-R2-02"),
    "RG-24": ("Aprobado", "62 aprobadas el 05/11/2026 (55 de la ronda 1 y 7 pruebas nuevas de Dev para PP-211).", "EV-HU23-INF-02, EV-HU23-R2-03"),
    "RG-25": ("Aprobado", "CP-237, CP-238 y CP-261 pasan: pytest de HU-23 28 de 28, Playwright del «%» 1 de 1 y regresión de paneles 62 de 62.", "EV-CP-237, EV-CP-238, EV-CP-261, EV-HU23-R2-01 a EV-HU23-R2-04"),
}
for rid, (res, obs, ev) in ev_r.items():
    r = buscar(wr, rid)
    wr.cell(r, 13, res)
    wr.cell(r, 14, FECHA)
    wr.cell(r, 15, "QA")
    wr.cell(r, 16, obs)
    wr.cell(r, 18, ev)
portada(wb)
wb.save(ruta("02_Casos_de_Prueba", "Casos_de_Prueba", V1))
print("casos ok")

# ============================== Evidencias ==============================
wb = openpyxl.load_workbook(ruta("03_Evidencias", "Registro_de_Evidencias", V0))
ws = wb["Registro"]
r = vacia(ws)
NUEVAS = [
    ("EV-HU23-R2-01", "CP-237, CP-238", "Informe HTML", "Informe de pytest de HU-23 en la ronda 2: 28 de 28 aprobadas; CP-237 y CP-238 pasan tras la corrección de DEF-05", "pytest_hu23_reprueba.html", "Aprobado"),
    ("EV-HU23-R2-02", "CP-261", "Captura", "Pantalla tras la corrección: «%» en el buscador deja el listado vacío con «No se encontraron paneles con ese criterio.»", "EV-HU23-E2E-08_reprueba-porcentaje-corregido.png", "Aprobado"),
    ("EV-HU23-R2-03", "RG-24", "Informe HTML", "Informe de la regresión de paneles (tests/routers/test_paneles.py): 62 de 62 aprobadas (55 y 7 nuevas de Dev)", "pytest_regresion_reprueba.html", "Informativo"),
    ("EV-HU23-R2-04", "CP-237, CP-238", "Captura", "Captura del informe pytest de la ronda 2 (extracto: resumen con 28 aprobadas y las primeras 10 filas)", "EV-HU23-R2-04_captura-informe-pytest-reprueba.png", "Informativo"),
]
for k, (ide, caso, tipo, que, nombre, res) in enumerate(NUEVAS):
    kb, h = sha(nombre)
    estilo(ws, r - 1, r + k, 15)
    for j, val in enumerate((ide, caso, HU, tipo, que, nombre, UBIC, "QA", f"{FECHA} {HORA}", kb, h, COMMIT, "Adjuntada", res, ""), 1):
        ws.cell(r + k, j, val)
portada(wb)
wb.save(ruta("03_Evidencias", "Registro_de_Evidencias", V1))
print("evidencias ok", len(NUEVAS))

# ============================== Defectos ==============================
wb = openpyxl.load_workbook(ruta("04_Defectos", "Registro_de_Defectos", V0))
wd = wb["Defectos"]
r = buscar(wd, "DEF-05")
wd.cell(r, 12, wd.cell(r, 12).value + "; reprueba: pytest_hu23_reprueba.html (EV-HU23-R2-01) y EV-HU23-E2E-08 (EV-HU23-R2-02)")
wd.cell(r, 16, "Cerrado")
wd.cell(r, 17, FECHA)
wd.cell(r, 18, wd.cell(r, 18).value + " Corregido por Jareth en 5430e91 (PP-211): escapa la barra invertida, el % y el _ y declara escape en .like(). Verificado por QA el 05/11/2026 sobre d7e1fab: pytest de HU-23 28 de 28, Playwright del «%» (CP-261) aprobado y regresión de paneles 62 de 62.")
wd.cell(r, 19, "RG-25 (aprobada el 05/11/2026)")
wh = wb["Historial de rondas"]
rh = wh.max_row + 1  # las rondas recientes van al final, tras la zona en blanco
estilo(wh, rh - 1, rh, 13)
fila = ("2", HU, FECHA, COMMIT, "29", "29", "0", "0", "0", "1", "0", "3",
        "Reprueba de DEF-05 (PP-211) con la corrección de Dev (5430e91): 28 de 28 en pytest de HU-23 y el caso del «%» (CP-261) en Playwright, ambos aprobados; regresión de paneles 62 de 62. "
        "No se repitieron los otros 11 casos de UI porque el frontend no cambió. DEF-05 cerrado; OBS-33 y OBS-34 siguen abiertas para el PO.")
for j, val in enumerate(fila, 1):
    wh.cell(rh, j, val)
portada(wb)
wb.save(ruta("04_Defectos", "Registro_de_Defectos", V1))
print("defectos ok")

# ================================ RTM ================================
wb = openpyxl.load_workbook(ruta("05_Matriz_Trazabilidad_RTM", "Matriz_Trazabilidad_RTM", V0))
ws = wb["RTM"]
r = buscar(ws, "RQ-HU23-03")
ws.cell(r, 10, "Aprobado")
ws.cell(r, 11, "DEF-05 (cerrado)")
hist = wb["Historias"]
r = buscar(hist, HU)
hist.cell(r, 17, "Sin defectos abiertos: DEF-05 (menor, PP-211) lo corrigió Jareth en 5430e91 y QA lo cerró el 05/11/2026 con RG-25. Decisiones del PO, que no son defectos: OBS-33 (paneles compartidos con la empresa frente a «no se comparten en v1.0») y OBS-34 (mensaje con proyecto activo).")
hist.cell(r, 18, hist.cell(r, 18).value + " Reprueba del 05/11/2026 sobre d7e1fab (qa-elliot), que incluye 5430e91 de dev (corrección de DEF-05 en routers/panel.py).")
wd = wb["Fuente defectos"]
r = buscar(wd, "DEF-05")
wd.cell(r, 3, "Cerrado")
wf = wb["Fuente casos"]
for cid in CAMBIOS:
    wf.cell(buscar(wf, cid), 3, "Aprobado")
portada(wb)
wb.save(ruta("05_Matriz_Trazabilidad_RTM", "Matriz_Trazabilidad_RTM", V1))
print("rtm ok")

# ================================ Plan ================================
d = docx.Document(ruta("01_Plan_de_Pruebas", "Plan_de_Pruebas", V0, "docx"))
P, T = list(d.paragraphs), d.tables


def run_text(par, viejo, nuevo):
    assert viejo in par.text, viejo
    for run in par.runs:
        if viejo in run.text:
            run.text = run.text.replace(viejo, nuevo)
            return
    raise AssertionError(viejo)


def celda(c, texto):
    par = c.paragraphs[0]
    par.runs[0].text = texto
    for run in par.runs[1:]:
        run._r.getparent().remove(run._r)


par8 = next(p for p in P if p.text.startswith("HU-23 ") and "Lo que existe" in p.text[:40])
run_text(par8, "la búsqueda trata «%» y «_» como comodines (DEF-05);", "la búsqueda trataba «%» y «_» como comodines (DEF-05, corregido por Jareth en 5430e91 y verificado el 05/11/2026);")
par19 = next(p for p in P if p.text.startswith("Casos de prueba: HU-23"))
par19.runs[0].text = (
    "Casos de prueba: HU-23 40 de 40 aprobados tras la ronda 2 (en la ronda 1 fueron 37 de 40: 28 de API con pytest y 12 de UI con Playwright en Edge); "
    "regresión de paneles 62 de 62. Defectos del producto: 1 (DEF-05, menor: la búsqueda trataba «%» y «_» como comodines), cerrado el 05/11/2026 con RG-25. "
    "Observaciones: OBS-33 y OBS-34 (las decide el PO). Subtareas: PP-210, PP-211 y PP-212 sin defectos abiertos y PP-426 (QA) en Listo; el estado en Jira lo cambia el usuario."
)
for fila, txt in ((26, "28 aprobadas · 0 fallidas (ronda 2; en la ronda 1 fallaron 2 por DEF-05)"), (27, "12 aprobadas · 0 fallidas (ronda 2: se repitió CP-261; en la ronda 1 falló 1 por DEF-05)"), (28, "62 aprobadas · 0 fallidas")):
    celda(T[1].rows[fila].cells[5], txt)
celda(T[1].rows[28].cells[4], "62")
celda(T[2].rows[18].cells[3], "Ejecutada: 62 aprobadas (55 de la ronda 1 y 7 nuevas de Dev). RG-22 a RG-25 aprobadas el 05/11/2026")
celda(T[7].rows[12].cells[6], "Corregido por Dev en 5430e91 (escapa % y _ en routers/panel.py); QA lo verificó con RG-25 el 05/11/2026.")
celda(T[8].rows[37].cells[2], "Cubierto; DEF-05 (% y _ como comodines) corregido y verificado el 05/11/2026")
modelo = T[10].rows[14]
nueva = copy.deepcopy(modelo._tr)
T[10].rows[-1]._tr.addnext(nueva)
fila_n = T[10].rows[-1]
for c, txt in zip(fila_n.cells, ("Ronda 2 de HU-23 (PP-426)", FECHA, "Ejecutada: reprueba de DEF-05 con la corrección de Dev (5430e91): CP-237, CP-238 y CP-261 aprobados, pytest de HU-23 28 de 28 y regresión de paneles 62 de 62; DEF-05 cerrado")):
    celda(c, txt)
# Fecha y versión de la portada
for fila in T[0].rows:
    k = fila.cells[0].text
    if k == "Versión":
        celda(fila.cells[1], "0.17")
    elif k == "Fecha":
        txt = fila.cells[1].text.rstrip()
        celda(fila.cells[1], txt + "; ronda 2 de HU-23 (PP-426, 05/11/2026), reprueba de DEF-05")
# Resumen de la ronda, tras el de HU-21
ref = next(p for p in P if p.text.startswith("PP-185 ") and "v0.16" in p.text[:20])
nuevo = copy.deepcopy(ref._p)
ref._p.addnext(nuevo)
par = Paragraph(nuevo, ref._parent)
par.runs[0].text = ("PP-426 — v0.17 — 05/11/2026. Ronda 2 de HU-23 en entorno local, d7e1fab (qa-elliot, con 5430e91 de dev). "
                    "Reprueba de DEF-05 por orden del usuario: pytest de HU-23 28 de 28, Playwright del «%» 1 de 1 y regresión de paneles 62 de 62. "
                    "No se repitieron los otros 11 casos de UI porque el frontend no cambió.")
for sec in d.sections:
    for p in sec.footer.paragraphs:
        for run in p.runs:
            if "v0.16" in run.text:
                run.text = run.text.replace("v0.16", "v0.17")
d.save(ruta("01_Plan_de_Pruebas", "Plan_de_Pruebas", V1, "docx"))
print("plan ok")
