"""Informe PDF de QA de HU-18 (A4, máximo 3 páginas). Mismo motor que generar_informe_HT-06.py.

Ejecutar desde la raíz del repo:
    backend/venv/Scripts/python.exe backend/qa/06_Informes/generar_informe_HU-18.py
Sale backend/qa/06_Informes/Informe_QA_HU-18_<aaaa-mm-dd>.pdf
"""
import sys
from pathlib import Path

# =====================================================================
# DATOS DEL INFORME
# =====================================================================

PROYECTO = None
TABLERO = "PP"
HU = "HU-18"
NOMBRE_HU = "Desactivar dispositivo"
SUBTAREA_QA = "PP-413"
VERSION = "v0.3"
FECHA = "30/10/2026"
RESPONSABLE = "Elliot (JS), Aseguramiento de Calidad (QA)"
ENTORNO = "Local (BD de test, FTP local real y Edge), sin producción; ronda 1 el 28/10 y ronda 2 el 30/10/2026"
RAMAS = "qa-elliot (commit 27ac90a, con la corrección dccdb60 de Jareth integrada desde dev)"
REVISA = "Product Owner"

VEREDICTO = "APTO CON OBSERVACIONES"
RESUMEN = ("Ronda 2. CA1, CA2 y CA3 se cumplen: el dispositivo pasa a Inactivo, el mensaje es el esperado y <b>el polling FTP ya se detiene</b> "
           "(DEF-04 corregido por Jareth en dccdb60 y verificado con un FTP local real). <b>0 defectos abiertos.</b> "
           "Quedan <b>3 observaciones que decide el PO</b> (OBS-09, OBS-10 y OBS-13); no cambian el estado de ninguna subtarea.")

KPIS = [
    ("29 / 29", "casos funcionales<br/>aprobados", "ok"),
    ("0", "defectos abiertos<br/>(1 corregido)", "ok"),
    ("29 / 29", "pruebas automatizadas<br/>aprobadas", "ok"),
    ("6 / 6", "requisitos cubiertos<br/>(RTM)", "ok"),
    ("5", "observaciones<br/>(3 para el PO)", "warn"),
]

SUBTAREAS = [
    ("PP-189", "HU-18 · Implementar acción «Desactivar» con confirmación", "Listo", "Modal, estado Inactivo, mensaje y botón Reactivar funcionan; roles correctos (CP-052 a 058). Solo observaciones del PO (OBS-09, OBS-10)."),
    ("PP-190", "HU-18 · Detener polling FTP del dispositivo desactivado", "Listo", "DEF-04 corregido por Jareth (dccdb60) y verificado en la ronda 2: CP-039 y CP-051 aprobados, también con FTP real."),
    ("PP-191", "HU-18 · Preservar historial de telemetría consultable", "Listo", "Tras desactivar, la telemetría se conserva y se consulta (CP-042 y 043)."),
    ("PP-413", "HU-18 · Validar criterios, flujos y errores", "Listo", "QA terminó: pruebas ejecutadas, evidencias y defectos registrados, e informe adjunto en esta subtarea."),
]

DEFECTOS_PRODUCTO = 1
FALLOS = [
    ("Entorno", "La suscripción obligatoria (409 «modo consulta») impedía desactivar en la base de pruebas; también hubo un 403 y un 429 de login.", "Las bases y fixtures no tenían suscripción vigente, permiso de Tableros ni sesión reutilizada.", "Se creó una suscripción vigente de prueba, se agregó el permiso y se usó un solo login por rol."),
    ("Producto (DEF-04, ronda 1)", "Al desactivar un dispositivo, el sondeo FTP seguía detectando sus archivos nuevos y los encolaba (CP-039, CP-051).", "sondear_conexiones_ftp (backend/app/tasks/ingesta.py) filtraba solo por ConexionFTP.estd = 'Activa' y no miraba Dispositivo.estd.", "Corregido por Jareth (dccdb60): solo se sondean conexiones con un dispositivo Activo. Ronda 2: CP-039, CP-051 y RG-05 a RG-07 aprobados; DEF-04 cerrado."),
]

COBERTURA = [
    ("CA1", "RQ-HU18-01 · Desactivar pide confirmación en un modal", "CP-052, 053", "Aprobado", "OBS-10"),
    ("CA2", "RQ-HU18-02 · Confirmar pasa a Inactivo y detiene la ingesta", "CP-030 a 034, 038 a 040, 051, 054", "Aprobado", "OBS-09; DEF-04 cerrado"),
    ("CA3", "RQ-HU18-03 · El listado muestra Inactivo con «Reactivar»", "CP-035, 055", "Aprobado", "—"),
    ("Detalles", "RQ-HU18-04 · Historial de telemetría preservado", "CP-042, 043", "Aprobado", "—"),
    ("", "RQ-HU18-05 · Solo CENERIS y Administrador desactivan", "CP-044 a 050, 057, 058", "Aprobado", "—"),
    ("", "RQ-HU18-06 · Un dispositivo Inactivo se puede reactivar", "CP-036, 037, 041, 056", "Aprobado", "—"),
]

ESPERADO_TITULO = ""
ESPERADO_NOTA = ""
COLUMNAS = []
ESPERADO = []
ESPERADO_PIE = ""

HERRAMIENTAS = [
    ("pytest + pytest-html", "API y reglas de negocio con BD real de test", "Es la herramienta del backend; cubre estados, mensajes, roles, sondeo e historial.", 21, 0),
    ("pytest + pyftpdlib", "Integración con FTP local real", "Prueba el sondeo de Celery sin simular la conexión; comprueba la corrección de DEF-04.", 1, 0),
    ("Playwright (Edge)", "UI y flujos de punta a punta", "Valida modal, mensaje, Reactivar y ocultar acciones al Cliente Final.", 7, 0),
]
HERRAMIENTAS_NOTA = ("Regresión de las suites existentes: 160 aprobadas y 54 fallidas, por fixtures sin suscripción (OBS-11), no por HU-18; tests/tasks pasa completo. Playwright no se reejecutó en la ronda 2 (dccdb60 no cambia la UI). "
                     "Descartadas: Locust y k6 (la HU no pide carga), OWASP ZAP, Lighthouse y axe (no se piden). "
                     "No se usó producción ni un datalogger real (OBS-13).")

EVIDENCIAS = [
    ("pytest-html", 21, 0, "extracto: primeras 10 de 21 filas",
     "qa/03_Evidencias/HU18/EV-HU18-INF-05_captura-informe-pytest.png", 0.72,
     "EV-HU18-INF-05. HTML completo: backend/qa/03_Evidencias/HU18/pytest_hu18.html"),
    ("pytest-html (FTP real)", 1, 0, "CP-051: tras desactivar, el sondeo ya no ingiere",
     "qa/03_Evidencias/HU18/EV-HU18-INF-06_captura-informe-ftp-real.png", 0.72,
     "EV-HU18-INF-06. HTML completo: backend/qa/03_Evidencias/HU18/pytest_hu18_ftp_real.html"),
    ("Playwright", 7, 0, "lista completa de las 7 pruebas de UI (ronda 1)",
     "qa/03_Evidencias/HU18/EV-HU18-INF-07_captura-informe-playwright.png", 0.72,
     "EV-HU18-INF-07. HTML completo: backend/qa/03_Evidencias/HU18/playwright/index.html"),
]

OBSERVACIONES = [
    ("OBS-09", "PP-189: con la regla de suscripción, desactivar devuelve 409 «modo consulta» si la empresa no tiene suscripción vigente. ¿Es intencional?", "PO"),
    ("OBS-10", "PP-189: el botón del modal se llama «Desactivar» (con cuenta regresiva), no «CONFIRMAR» como dice CA2. ¿Se acepta?", "PO"),
    ("OBS-11", "54 de 214 tests existentes fallan por no crear suscripción en sus fixtures; falta un fixture común en tests/conftest.py.", "Dev"),
    ("OBS-12", "QA levantó Postgres, Redis y cuentas de prueba solo en local; se descartan al terminar.", "QA"),
    ("OBS-13", "No se probó en producción ni con un datalogger real; repetir el polling en el servidor de pruebas cuando esté disponible.", "PO"),
]

CONCLUSION = ("<b>APTO CON OBSERVACIONES.</b> CA1, CA2 y CA3 se cumplen; DEF-04 quedó corregido (dccdb60) y verificado con pytest, con un FTP local real y en "
              "regresión. Estado propuesto: PP-189, PP-190, PP-191 y PP-413 en Listo (QA terminó y adjunta este informe). "
              "<b>Alcance real</b>: no se probó producción ni un datalogger real, el worker no se ejecutó y Playwright no se reejecutó en la ronda 2 (sin cambios de UI).")
PENDIENTES = [
    ("Decidir si desactivar debe poder hacerse en modo consulta (OBS-09) y si el botón se llama CONFIRMAR (OBS-10).", "PO"),
    ("Repetir la prueba de polling en el servidor de pruebas cuando esté disponible (OBS-13).", "PO"),
    ("Agregar un fixture común con suscripción vigente en tests/conftest.py (OBS-11).", "Dev"),
    ("Cambiar los estados de las subtareas en Jira según la sección 1.", "QA"),
]

# =====================================================================
# MOTOR DEL INFORME
# =====================================================================
from PIL import Image as PILImage  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.pdfgen import canvas as rl_canvas  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[2]


def nombre_repositorio():
    import subprocess
    try:
        url = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"],
                             capture_output=True, text=True, check=True).stdout.strip()
        nombre = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    except Exception:
        nombre = ROOT.name
    return " ".join(w.capitalize() for w in nombre.replace("_", "-").split("-") if w)


if not PROYECTO:
    PROYECTO = nombre_repositorio()

FONTS = Path("C:/Windows/Fonts")
try:
    pdfmetrics.registerFont(TTFont("UI", str(FONTS / "segoeui.ttf")))
    pdfmetrics.registerFont(TTFont("UI-B", str(FONTS / "segoeuib.ttf")))
    pdfmetrics.registerFont(TTFont("UI-I", str(FONTS / "segoeuii.ttf")))
    pdfmetrics.registerFont(TTFont("UI-BI", str(FONTS / "segoeuiz.ttf")))
    pdfmetrics.registerFontFamily("UI", normal="UI", bold="UI-B", italic="UI-I", boldItalic="UI-BI")
    F, FB = "UI", "UI-B"
except Exception:  # fuera de Windows
    F, FB = "Helvetica", "Helvetica-Bold"

NAVY = colors.HexColor("#1F3A5F")
INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#5B6770")
LINE = colors.HexColor("#D5DBE1")
ZEBRA = colors.HexColor("#F4F6F8")
OK, OK_BG = colors.HexColor("#1E7B4A"), colors.HexColor("#E3F3EA")
WARN, WARN_BG = colors.HexColor("#9A5B00"), colors.HexColor("#FFF4DE")
DENY, DENY_BG = colors.HexColor("#8A2D2D"), colors.HexColor("#F8E7E7")
INFO, INFO_BG = colors.HexColor("#33536F"), colors.HexColor("#E6EEF5")
GRAY, GRAY_BG = colors.HexColor("#4B5563"), colors.HexColor("#ECEEF1")

TONOS = {"ok": (OK, OK_BG), "warn": (WARN, WARN_BG), "fail": (DENY, DENY_BG),
         "info": (INFO, INFO_BG), "gray": (GRAY, GRAY_BG)}

W, H = A4
MARGIN = 1.6 * cm
CONTENT_W = W - 2 * MARGIN


def st(name, **kw):
    base = dict(fontName=F, fontSize=9, leading=12, textColor=INK)
    base.update(kw)
    return ParagraphStyle(name, **base)


S_TITLE = st("title", fontName=FB, fontSize=17, leading=21, textColor=NAVY)
S_SUB = st("sub", fontSize=9, leading=12.5, textColor=MUTED)
S_H = st("h", fontName=FB, fontSize=11.5, leading=14, textColor=NAVY, spaceBefore=7, spaceAfter=3, keepWithNext=1)
S_BODY = st("body", fontSize=9, leading=12.5)
S_SMALL = st("small", fontSize=7.8, leading=10, textColor=MUTED)
S_CELL = st("cell", fontSize=8.2, leading=10.4)
S_CELL_B = st("cellb", fontName=FB, fontSize=8.2, leading=10.4)
S_HEAD = st("head", fontName=FB, fontSize=8.2, leading=10.4, textColor=colors.white)
S_BADGE = st("badge", fontName=FB, fontSize=7.8, leading=10, alignment=TA_CENTER)
S_KPI_N = st("kpin", fontName=FB, fontSize=20, leading=23, alignment=TA_CENTER)
S_KPI_L = st("kpil", fontSize=7.8, leading=9.6, textColor=MUTED, alignment=TA_CENTER)


def tono(valor):
    """Color de una etiqueta según su texto (ver la tabla del docstring)."""
    v = valor.replace("<br/>", " ").strip().lower()
    if v.startswith(("no apto", "fallido", "no cumple", "defecto")):
        return "fail"
    if v.startswith(("en curso", "bloqueado", "observaci")) or v == "po":
        return "warn"
    if v.startswith(("listo", "aprobado", "permitido", "sí", "si ", "cumple", "apto")) or v == "si":
        return "ok"
    if v.startswith(("denegado", "oculto", "dev", "qa")):
        return "info"
    return "gray"


def P(text, style=S_CELL):
    return Paragraph(text, style)


def badge(text, clave=None):
    fg, bg = TONOS[clave or tono(text)]
    return Paragraph(f'<font color="{fg.hexval()}">{text}</font>', S_BADGE), bg


def table(header, rows, widths):
    """Tabla con encabezado oscuro y filas alternas. Las celdas (Paragraph, fondo) salen de badge()."""
    data = [[P(h, S_HEAD) for h in header]]
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 2.4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for ri, r in enumerate(rows, start=1):
        if ri % 2 == 0:
            cmds.append(("BACKGROUND", (0, ri), (-1, ri), ZEBRA))
        out = []
        for ci, c in enumerate(r):
            if isinstance(c, tuple):
                out.append(c[0])
                cmds.append(("BACKGROUND", (ci, ri), (ci, ri), c[1]))
            else:
                out.append(P(c) if isinstance(c, str) else c)
        data.append(out)
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle(cmds))
    return t


def callout(title, lines, clave):
    fg, bg = TONOS[clave]
    body = [P(f"<b>{title}</b>", st("ct", fontName=FB, fontSize=9.5, leading=12, textColor=fg))]
    body += [P(line, S_BODY) for line in lines]
    t = Table([[body]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 3.5, fg),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def kpis(items):
    gap = 0.25 * cm
    w = (CONTENT_W - gap * (len(items) - 1)) / len(items)
    row, widths = [], []
    for i, (n, label, clave) in enumerate(items):
        fg = TONOS[clave][0]
        row.append([P(f'<font color="{fg.hexval()}">{n}</font>', S_KPI_N), P(label, S_KPI_L)])
        widths.append(w)
        if i < len(items) - 1:
            row.append("")
            widths.append(gap)
    t = Table([row], colWidths=widths)
    cmds = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]
    for i in range(0, len(row), 2):
        cmds += [("BACKGROUND", (i, 0), (i, 0), ZEBRA), ("BOX", (i, 0), (i, 0), 0.5, LINE)]
    t.setStyle(TableStyle(cmds))
    return t


def evidence(img_path, width):
    if img_path.exists():
        with PILImage.open(img_path) as im:
            w_px, h_px = im.size
        content = Image(str(img_path), width=width, height=width * h_px / w_px)
    else:  # la plantilla se puede probar sin capturas
        ruta = img_path.relative_to(ROOT).as_posix()
        if "[" in ruta:  # plantilla en blanco
            texto = f'<font color="{MUTED.hexval()}">[Captura recortada del HTML de la herramienta]<br/>{ruta}</font>'
        else:
            texto = f'<font color="{DENY.hexval()}">[Falta la captura: {ruta}]</font>'
        content = P(texto, st("miss", fontSize=9, leading=13, alignment=TA_CENTER))
    t = Table([[content]], colWidths=[width + 2], rowHeights=None if img_path.exists() else [3 * cm])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    t.hAlign = "CENTER"
    return t


class NumberedCanvas(rl_canvas.Canvas):
    """Encabezado y pie con «Pág. X de Y» (necesita el total, por eso guarda cada página)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self._decorate(total)
            super().showPage()
        super().save()

    def _decorate(self, total):
        self.setFillColor(NAVY)
        self.rect(0, H - 1.05 * cm, W, 1.05 * cm, stroke=0, fill=1)
        self.setFillColor(colors.white)
        self.setFont(FB, 9.5)
        self.drawString(MARGIN, H - 0.68 * cm, f"{PROYECTO.upper()}  ·  Informe de QA")
        self.setFont(F, 9)
        self.drawRightString(W - MARGIN, H - 0.68 * cm, f"{HU}  ·  Evidencia de {SUBTAREA_QA}")
        self.setStrokeColor(LINE)
        self.setLineWidth(0.5)
        self.line(MARGIN, 1.25 * cm, W - MARGIN, 1.25 * cm)
        self.setFillColor(MUTED)
        self.setFont(F, 7.8)
        self.drawString(MARGIN, 0.85 * cm, f"Informe QA {HU}  ·  {VERSION}  ·  {FECHA}  ·  {RESPONSABLE}")
        self.drawRightString(W - MARGIN, 0.85 * cm, f"Pág. {self._pageNumber} de {total}")


def build():
    s = []

    # Título y datos
    s.append(P(f"{HU} · {NOMBRE_HU}", S_TITLE))
    s.append(Spacer(1, 3))
    s.append(P(f"Proyecto {PROYECTO} (tablero {TABLERO})  ·  {ENTORNO}  ·  Fecha {FECHA}<br/>"
               f"Ramas revisadas: {RAMAS}  ·  Revisa: {REVISA}", S_SUB))
    s.append(Spacer(1, 8))

    # Veredicto
    fg, bg = TONOS[tono(VEREDICTO)]
    verdict = Table([[
        P(f'<font color="white"><b>{VEREDICTO}</b></font>',
          st("v", fontName=FB, fontSize=11, leading=14, alignment=TA_CENTER)),
        P(RESUMEN, S_BODY),
    ]], colWidths=[5.0 * cm, CONTENT_W - 5.0 * cm])
    verdict.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), fg), ("BACKGROUND", (1, 0), (1, 0), bg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    s.append(verdict)
    s.append(Spacer(1, 6))
    s.append(kpis(KPIS))

    # 1. Subtareas
    s.append(P("1. Subtareas y estado propuesto", S_H))
    s.append(table(
        ["Subtarea", "Tarea", "Estado", "Fundamento"],
        [[P(c, S_CELL_B), t, badge(e), f] for c, t, e, f in SUBTAREAS],
        [1.7 * cm, 5.2 * cm, 1.6 * cm, CONTENT_W - 8.5 * cm],
    ))

    # 2. Fallos previos
    s.append(Spacer(1, 9))
    if FALLOS:
        lineas = [f"<b>{o}.</b> <i>Síntoma:</i> {si} <i>Causa:</i> {ca} <i>Solución:</i> {so}"
                  for o, si, ca, so in FALLOS]
    else:
        lineas = ["No hubo fallos previos: todas las pruebas pasaron en la primera ronda."]
    n = DEFECTOS_PRODUCTO
    s.append(callout(
        f"2. Fallos previos y cómo se resolvieron  ·  {n} defecto{'s' if n != 1 else ''} del producto",
        lineas, "fail" if n else "warn",
    ))

    # 3. Cobertura por criterio
    s.append(P("3. Cobertura por criterio de aceptación", S_H))
    s.append(table(
        ["Criterio", "Requisito verificado", "Casos", "Resultado", "Obs."],
        [[P(c, S_CELL_B), r, cs, badge(res), o] for c, r, cs, res, o in COBERTURA],
        [2.1 * cm, 8.3 * cm, 3.0 * cm, 1.75 * cm, CONTENT_W - 15.15 * cm],
    ))

    # 4 (esperado vs. obtenido): no aplica a esta HU
    if ESPERADO:
        # 4. Esperado vs. obtenido
        s.append(P(f"4. {ESPERADO_TITULO}", S_H))
        s.append(P(ESPERADO_NOTA, S_SMALL))
        s.append(Spacer(1, 3))
        n_col = len(COLUMNAS)
        w_val = 1.75 * cm if n_col > 1 else 3.2 * cm
        w_fixed = 4.5 * cm + w_val * n_col + 2.3 * cm + 1.8 * cm
        s.append(table(
            ["Acción"] + COLUMNAS + ["Por qué es lo esperado", "Casos", "Resultado"],
            [[a] + [badge(v) for v in vals] + [pq, cs, badge(res)] for a, vals, pq, cs, res in ESPERADO],
            [4.5 * cm] + [w_val] * n_col + [CONTENT_W - w_fixed, 2.3 * cm, 1.8 * cm],
        ))
        if ESPERADO_PIE:
            s.append(Spacer(1, 2))
            s.append(P(ESPERADO_PIE, S_SMALL))

    # 5. Herramientas
    s.append(P("4. Herramientas y tipo de prueba", S_H))
    s.append(table(
        ["Herramienta", "Tipo de prueba", "Por qué", "Resultado"],
        [[P(h, S_CELL_B), t, pq, badge(f"{a} aprobadas · {f} fallidas", "fail" if isinstance(f, int) and f > 0 else "ok")]
         for h, t, pq, a, f in HERRAMIENTAS],
        [3.2 * cm, 4.0 * cm, CONTENT_W - 11.4 * cm, 4.2 * cm],
    ))
    if HERRAMIENTAS_NOTA:
        s.append(Spacer(1, 2))
        s.append(P(HERRAMIENTAS_NOTA, S_SMALL))

    # 6. Evidencias
    titulo_ev = P("5. Evidencias: captura del HTML que generó cada herramienta", S_H)
    for i, (h, a, f, que, png, ancho, pie) in enumerate(EVIDENCIAS):
        color = DENY.hexval() if isinstance(f, int) and f > 0 else OK.hexval()
        s.append(KeepTogether(([titulo_ev] if i == 0 else []) + [  # el título viaja con la primera captura
            P(f'<b>{h}</b>  ·  <font color="{color}"><b>{a} aprobadas · {f} fallidas</b></font>  ·  {que}', S_BODY),
            Spacer(1, 3),
            evidence(ROOT / png, CONTENT_W * ancho),
            Spacer(1, 2),
            P(pie, S_SMALL),
        ]))
        if i < len(EVIDENCIAS) - 1:
            s.append(Spacer(1, 8))

    # 7. Observaciones
    s.append(P("6. Observaciones (no cambian el estado)", S_H))
    if OBSERVACIONES:
        s.append(table(
            ["ID", "Observación", "Decide"],
            [[P(i, S_CELL_B), t, badge(d)] for i, t, d in OBSERVACIONES],
            [1.55 * cm, CONTENT_W - 2.85 * cm, 1.3 * cm],
        ))
    else:
        s.append(P("Sin observaciones.", S_BODY))

    # 8. Conclusión
    bloque = [P("7. Conclusión y pendientes", S_H), P(CONCLUSION, S_BODY)]
    if PENDIENTES:
        bloque += [Spacer(1, 4), table(
            ["#", "Pendiente", "Responsable"],
            [[str(i), t, badge(r)] for i, (t, r) in enumerate(PENDIENTES, start=1)],
            [0.7 * cm, CONTENT_W - 2.9 * cm, 2.2 * cm],
        )]
    s.append(KeepTogether(bloque))
    return s


def salida():
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    try:
        d, m, a = FECHA.split("/")
        fecha_iso = f"{a}-{m}-{d}"
    except ValueError:
        fecha_iso = FECHA
    return Path(__file__).resolve().parent / f"Informe_QA_{HU}_{fecha_iso}.pdf"


def main():
    out = salida()
    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=1.55 * cm, bottomMargin=1.6 * cm,
        title=f"Informe de QA · {HU} {NOMBRE_HU}", author=RESPONSABLE, subject=f"Evidencia de {SUBTAREA_QA}",
    )
    doc.build(build(), canvasmaker=NumberedCanvas)
    paginas = doc.page
    print("ok", out, f"({paginas} páginas)")
    if paginas > 3:
        print("AVISO: pasa de 3 páginas. Acorta textos, reduce filas del extracto o el ancho de las capturas.")


if __name__ == "__main__":
    main()
