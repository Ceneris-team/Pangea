"""Informe PDF de QA de HU-23 (A4, máximo 3 páginas). Mismo motor que generar_informe_HU-34.py.

Ejecutar desde la raíz del repo:
    backend/venv/Scripts/python.exe backend/qa/06_Informes/generar_informe_HU-23.py
Sale backend/qa/06_Informes/Informe_QA_HU-23_<aaaa-mm-dd>.pdf
"""
import sys
from pathlib import Path

# =====================================================================
# DATOS DEL INFORME
# =====================================================================

PROYECTO = None
TABLERO = "PP"
HU = "HU-23"
NOMBRE_HU = "Listar paneles"
SUBTAREA_QA = "PP-426"
VERSION = "v0.1 (borrador: DEF-05 abierto)"
FECHA = "02/11/2026"
RESPONSABLE = "Elliot (JS), Aseguramiento de Calidad (QA)"
ENTORNO = "Local (BD de test y BD pangea_e2e en Docker, Edge), sin producción"
RAMAS = "qa-elliot (commit f9b939a; el código del listado está en dev, commit 68e3089)"
REVISA = "Product Owner"

VEREDICTO = "APTO CON OBSERVACIONES"
RESUMEN = ("CA1 a CA3 y los detalles de la HU se cumplen: listado con nombre, fecha y acciones, <b>apertura del panel</b>, <b>aislamiento por usuario</b>, "
           "orden descendente y mensaje sin paneles con «Crear panel». <b>1 defecto menor del producto</b> (DEF-05: la búsqueda trata «%» y «_» como "
           "comodines; PP-211 sigue En curso) y <b>2 observaciones que decide el PO</b> (OBS-33 y OBS-34).")

KPIS = [
    ("37 / 40", "casos funcionales<br/>aprobados", "warn"),
    ("1", "defecto del producto<br/>(menor)", "fail"),
    ("37 / 40", "pruebas automatizadas<br/>aprobadas (26 + 11)", "warn"),
    ("7 / 7", "requisitos cubiertos<br/>(RTM; 1 con defecto)", "warn"),
    ("3", "observaciones<br/>(2 nuevas para el PO)", "warn"),
]

SUBTAREAS = [
    ("PP-210", "HU-23 · Diseñar vista listado de paneles", "Listo", "Nombre, fecha y acciones; mensaje «Aún no tienes paneles creados» con «Crear panel» habilitado (CP-222 a 224, 244, 250, 258, 259)."),
    ("PP-211", "HU-23 · Consultar paneles por usuario", "En curso", "Aislamiento y apertura del panel correctos; DEF-05: «%» y «_» devuelven todos los paneles (CP-237, 238 y 261; reprueba RG-25)."),
    ("PP-212", "HU-23 · Ordenar por fecha de creación descendente", "Listo", "Orden descendente por defecto, al buscar y con un panel recién creado (CP-225 a 227, 251)."),
    ("PP-426", "HU-23 · Validar criterios, flujos y errores", "Listo", "QA terminó: pruebas ejecutadas, evidencias y defectos registrados, e informe adjunto en esta subtarea."),
]

DEFECTOS_PRODUCTO = 1
FALLOS = [
    ("DEF-05 (producto, PP-211)", "Buscar «%» o «_» devuelve todos los paneles (10 de 10 en pantalla).", "listar_paneles (routers/panel.py) arma el patrón con f\"%{busqueda}%\" y usa .like() sin escapar.", "Escapar \\, % y _ del texto buscado y declarar el carácter de escape en .like(). Mensaje enviado a Dev."),
    ("Entorno (Playwright)", "Los inicios de sesión se agotaban (429) tras varias corridas.", "El login permite 5 intentos cada 5 minutos.", "Se vació el contador local de Redis y se repitió la suite. No es defecto del producto."),
    ("Prueba de QA", "El E2E del «%» pasó en 29 ms.", "Leía el aviso de la prueba anterior antes de que terminara la búsqueda (400 ms de retardo).", "La prueba ahora espera el filtrado y falla por DEF-05, como el caso de API."),
]

COBERTURA = [
    ("CA1", "RQ-HU23-01 · Listado con nombre, fecha de creación y acciones de los paneles del usuario", "CP-222 a 224, 250, 258", "Aprobado", "—"),
    ("CA2", "RQ-HU23-02 · Al seleccionar el nombre se abre el panel con sus ubicaciones y widgets", "CP-241 a 243, 256, 257", "Aprobado", "—"),
    ("CA3", "RQ-HU23-03 · La búsqueda por nombre o fragmento muestra solo los paneles que coinciden", "CP-233 a 240, 249, 253 a 255, 261", "Fallido", "DEF-05"),
    ("Detalle", "RQ-HU23-04 · Cada usuario ve solo sus paneles (no compartidos en v1.0)", "CP-228 a 232, 252, 260", "Aprobado", "OBS-33"),
    ("Detalle", "RQ-HU23-05 · Orden por fecha de creación descendente por defecto", "CP-225 a 227, 251", "Aprobado", "—"),
    ("Detalle", "RQ-HU23-06 · Sin paneles: «Aún no tienes paneles creados» y «Crear panel»", "CP-244, 245, 259", "Aprobado", "OBS-34"),
    ("Transversal", "RQ-HU23-07 · Sin sesión 401, sin permiso 403 y Lectura permitida", "CP-246 a 248", "Aprobado", "OBS-18"),
]

ESPERADO_TITULO = ""
ESPERADO_NOTA = ""
COLUMNAS = []
ESPERADO = []
ESPERADO_PIE = ""

HERRAMIENTAS = [
    ("pytest + pytest-html", "API y reglas de negocio con BD real de test", "Es la herramienta del backend; cubre listado, orden, aislamiento, búsqueda con caracteres especiales y errores.", 26, 2),
    ("Playwright (Edge)", "UI y flujos de punta a punta", "Valida columnas, orden, búsqueda, abrir panel, mensaje sin paneles y aislamiento con 3 cuentas.", 11, 1),
]
HERRAMIENTAS_NOTA = ("Regresión: test_paneles.py, 55 de 55 aprobadas (RG-24). Descartadas: Locust, k6, OWASP ZAP, Lighthouse y axe (la HU no los pide). "
                     "No se ejecutó en pantalla el mensaje con un proyecto activo (OBS-34) ni se probó el mapa de estaciones (falta la clave de Google Maps en local).")

EVIDENCIAS = [
    ("pytest-html", 26, 2, "extracto: primeras 10 de 28 filas",
     "qa/03_Evidencias/HU23/EV-HU23-INF-04_captura-informe-pytest.png", 0.72,
     "EV-HU23-INF-04. HTML completo: backend/qa/03_Evidencias/HU23/pytest_hu23.html"),
    ("Playwright", 11, 1, "lista completa de las 12 pruebas de UI",
     "qa/03_Evidencias/HU23/EV-HU23-INF-05_captura-informe-playwright.png", 0.72,
     "EV-HU23-INF-05. HTML completo: backend/qa/03_Evidencias/HU23/playwright/index.html"),
    ("Playwright", 0, 1, "CP-261: «%» en el buscador deja los 10 paneles (DEF-05)",
     "qa/03_Evidencias/HU23/EV-HU23-E2E-07_busqueda-porcentaje.png", 0.55,
     "EV-CP-261. Captura: backend/qa/03_Evidencias/HU23/EV-HU23-E2E-07_busqueda-porcentaje.png"),
]

OBSERVACIONES = [
    ("DEF-05", "PP-211 (menor): la búsqueda trata «%» y «_» como comodines y devuelve todos los paneles; no hay fuga de datos. Corregir y reprobar con RG-25.", "Dev"),
    ("OBS-33", "PP-211: la HU dice que los paneles no se comparten en v1.0, pero existe «Compartir con empresa»: otro usuario de la sede ve el panel compartido. Por defecto es privado.", "PO"),
    ("OBS-34", "PP-210: con un proyecto activo y sin paneles, el mensaje es «Aún no hay paneles para X», no el literal de la HU (revisado en el código).", "PO"),
    ("OBS-18", "(Ya registrada en HU-26) No se probó producción ni un Cliente Final «por cliente» con rol Lector y proyectos asignados.", "PO"),
]

CONCLUSION = ("<b>APTO CON OBSERVACIONES (borrador).</b> Los criterios se cumplen salvo la búsqueda con «%» y «_» (DEF-05, menor, sin fuga de datos). "
              "Estado propuesto: PP-210, PP-212 y PP-426 en Listo; PP-211 En curso hasta que Dev corrija DEF-05 y QA apruebe RG-25 (CP-237, 238 y 261). "
              "<b>Alcance real</b>: solo local; no se probó producción, cuentas «por cliente», el mapa de estaciones ni el mensaje con proyecto activo en pantalla.")
PENDIENTES = [
    ("Corregir DEF-05 en listar_paneles escapando «%» y «_» y avisar con el commit y el código PP-211.", "Dev"),
    ("Reprobar RG-25 (CP-237, 238 y 261), actualizar los documentos y emitir la versión final de este informe.", "QA"),
    ("Decidir si compartir con la empresa queda como alcance adicional (OBS-33) y si el mensaje con proyecto activo es aceptable (OBS-34).", "PO"),
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
