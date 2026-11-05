"""Informe PDF de QA de HU-21 (PP-414), ronda 2: reprueba de PP-185 (A4, máximo 4 páginas). Motor: Plantilla_Informe_QA.py.

Ejecutar desde la raíz del repo:
    backend/venv/Scripts/python.exe backend/qa/06_Informes/generar_informe_HU-21_ronda2.py
Sale backend/qa/06_Informes/Informe_QA_HU-21_ronda2_<aaaa-mm-dd>.pdf
"""
import sys
from pathlib import Path

# =====================================================================
# DATOS DEL INFORME
# =====================================================================

PROYECTO = None
TABLERO = "PP"
HU = "HU-21"
NOMBRE_HU = "Conceder permisos (ronda 2)"
SUBTAREA_QA = "PP-414"
VERSION = "v0.2"
FECHA = "04/11/2026"
RESPONSABLE = "Elliot (JS), Aseguramiento de Calidad (QA)"
ENTORNO = "Local (Postgres y Redis en Docker, Edge), tokens reales, sin producción"
RAMAS = "ead1a85 (qa/correcciones-pp185), con el mismo código en origin/dev cfe3e19"
REVISA = "Product Owner"

VEREDICTO = "APTO CON OBSERVACIONES"
RESUMEN = ("<b>DEF-10 y DEF-11 quedan corregidos y verificados</b>, y los 8 criterios se cumplen. La reprueba halló <b>DEF-12 y DEF-13</b>, menores, ya corregidos e integrados en dev. "
           "<b>La regresión completa de backend no se repitió</b>: su último dato es de la ronda 1. El PO decide OBS-61 (proyecto activo en sede inactiva).")

KPIS = [
    ("138/138", "casos<br/>aprobados", "ok"),
    ("0", "defectos abiertos<br/>(4 cerrados)", "ok"),
    ("168", "pruebas aprobadas<br/>(100 + 11 + 57)", "warn"),
    ("8 / 8", "requisitos aprobados<br/>(RTM)", "ok"),
    ("3", "observaciones nuevas<br/>(1 para el PO)", "warn"),
]

SUBTAREAS = [
    ("PP-183", "Diseñar panel de permisos por ubicación", "Listo", "Sin cambios desde la ronda 1."),
    ("PP-184", "Listar ubicaciones y estado de acceso actual", "Listo", "Sin cambios desde la ronda 1."),
    ("PP-185", "Guardar cambios de permisos por usuario", "Listo", "DEF-10 a DEF-13 corregidos, reprobados e integrados en dev (cfe3e19). OBS-61 queda para el PO y no bloquea."),
    ("PP-414", "Validar criterios de aceptación, flujos y errores", "Listo", "QA terminó: pruebas ejecutadas, evidencias y defectos registrados, e informe adjunto en esta subtarea."),
]

DEFECTOS_PRODUCTO = 4
FALLOS = [
    ("DEF-10 (cerrado)", "Un proyecto inactivo se rechazaba como ajeno a la empresa.", "Pertenencia y estado se validaban juntos.", "Jareth los separó en 67a8309; RG-37 aprobada."),
    ("DEF-11 (cerrado)", "Una revocación previa a la primera lectura dejaba resultados retirados.", "La versión de acceso partía vacía en cada carga.", "Jareth guarda la versión por usuario y valida antes de cargar (67a8309); RG-38 aprobada."),
    ("DEF-12 (cerrado)", "Con un fallo de /auth/acceso la app quedaba en «Comprobando tus permisos…».", "Solo se trataba el 403; lo introdujo 67a8309.", "QA añadió mensaje, Reintentar y Cerrar sesión (46a4850); RG-41 aprobada."),
    ("DEF-13 (cerrado)", "Un enlace nunca autorizado informaba «Tus permisos cambiaron».", "El filtro de la URL contaba como selección revocada.", "QA añadió un aviso neutro y conserva la selección válida (cfe3e19); RG-42 aprobada."),
    ("Entorno y pruebas (QA)", "Fallos falsos en la reprueba.", "Base de pruebas sin migrar, un 403 mal esperado y un proyecto inyectado a una cuenta que no puede elegirlo.", "Se migró la base local y se corrigieron las pruebas."),
]

COBERTURA = [
    ("CA-01", "RQ-HU21-01 · Gestión según el tipo de cuenta", "CP-344 a 358, 434, 450 a 453", "Aprobado", "—"),
    ("CA-02", "RQ-HU21-02 · Contexto y acceso actual visibles", "CP-359 a 364, 435, 436, 441, 443, 454", "Aprobado", "—"),
    ("CA-03", "RQ-HU21-03 · Guardado válido y completo", "CP-365 a 379, 439, 440, 446, 447, 475, 476, 478, 488", "Aprobado", "OBS-61"),
    ("CA-04", "RQ-HU21-04 · Cancelación sin persistencia", "CP-380, 437, 438, 444", "Aprobado", "—"),
    ("CA-05", "RQ-HU21-05 · Aislamiento en todas las consultas", "CP-381 a 396, 459, 460, 492 a 494", "Aprobado", "OBS-57"),
    ("CA-06", "RQ-HU21-06 · Aplicación y revocación con sesión abierta", "CP-397 a 405, 427 a 433, 455, 456, 458, 461, 484 a 487, 489 a 491", "Aprobado", "OBS-56, OBS-63"),
    ("CA-07", "RQ-HU21-07 · Retirada de acceso y continuidad administrativa", "CP-406 a 418, 442, 445, 448, 449, 457, 477", "Aprobado", "—"),
    ("CA-08", "RQ-HU21-08 · Trazabilidad del cambio", "CP-419 a 426, 479 a 483", "Aprobado", "OBS-62"),
]

# La matriz rol × acción no se repite: esta ronda reprueba defectos concretos.
ESPERADO_TITULO = ""
ESPERADO_NOTA = ""
COLUMNAS = []
ESPERADO = []
ESPERADO_PIE = ""

HERRAMIENTAS = [
    ("pytest + pytest-html", "Sí", "API y reglas (HU-21 y empresas)", "Las reglas viven en la API. Las 5 fallidas esperan el formato de auditoría anterior a 2392be3 (OBS-62).", 91, 5),
    ("pytest (reprueba)", "Sí", "RG-37 y CA-08 con formato actual", "Verifica DEF-10 y la auditoría vigente. La fallida es exploratoria: sede inactiva (OBS-61).", 9, 1),
    ("Playwright (Edge)", "Sí", "UI y E2E con API real", "La carrera de DEF-11 y los mensajes solo se ven en el navegador.", 11, 0),
    ("node --test", "Sí", "Frontend completo", "Sobre cfe3e19. Log: frontend_final.log.", 57, 0),
    ("pytest (regresión)", "No", "Backend completo", "No repetida en esta ronda, a pedido del usuario por tiempo. Dato de 5430e91 (ronda 1), anterior a 2392be3 y 67a8309.", "Ronda 1: 1 080 con variable · 88 fallan sin ella", None),
    ("Locust, k6, ZAP, axe, Lighthouse, pytest-cov", "No", "Carga, seguridad, accesibilidad y cobertura", "Ni la subtarea ni los criterios los piden.", None, None),
]
HERRAMIENTAS_NOTA = ("<b>Regresión de la ronda 1 sin la variable:</b> mapeos 33, ubicaciones 23, dispositivos 17, ficha de dispositivo 9, columnas pendientes 3, caché HT-10 1, cola de ingesta 1 y límites de plan 1, "
                     "previas a esta HU (OBS-45). pytest corrió sobre 67a8309; DEF-12 y DEF-13 solo cambian frontend.")
MOTIVOS_FALLOS = []
NOTA_FALLOS = "Ninguna de las 6 fallidas de pytest es un defecto: 5 son OBS-62 y 1 es OBS-61. No hay casos bloqueados."

EVIDENCIAS = [
    ("pytest-html (reprueba)", 9, 1, "las 10 filas; la fallida es OBS-61",
     "qa/03_Evidencias/HU21/reprueba_pp185/EV-HU21-R2-INF-01_captura-pytest.png", 0.63,
     "EV-HU21-R2-02. HTML completo: backend/qa/03_Evidencias/HU21/reprueba_pp185/pytest_pp185_reprueba.html. Suite de HU-21 y empresas: pytest_pp185_foco.html (EV-HU21-R2-01)."),
    ("Playwright (Edge)", 11, 0, "contadores y las 11 pruebas",
     "qa/03_Evidencias/HU21/reprueba_pp185/EV-HU21-R2-INF-02_captura-playwright.png", 0.72,
     "EV-HU21-R2-04. HTML completo: backend/qa/03_Evidencias/HU21/reprueba_pp185/playwright/index.html. Frontend: frontend_final.log (EV-HU21-R2-03)."),
]

OBSERVACIONES = [
    ("DEF-10", "PP-185 · Media, cerrado: rechazo de proyecto inactivo con motivo incorrecto. RG-37 aprobada.", "Dev"),
    ("DEF-11", "PP-185 · Media, cerrado: revocación previa a la primera lectura sin detectar. RG-38 aprobada.", "Dev"),
    ("DEF-12", "PP-185 · Baja, cerrado: pantalla fija si falla /auth/acceso. RG-41 aprobada.", "QA"),
    ("DEF-13", "PP-185 · Baja, cerrado: aviso falso con un enlace no autorizado. RG-42 aprobada.", "QA"),
    ("OBS-45", "(Ya registrada en PP-47) Sin la variable fallan 88 pruebas por fixtures sin suscripción vigente. ¿Se corrigen ahora o después?", "PO"),
    ("OBS-56", "(Ya registrada en HU-21) Los 60 s de la firma se comprobaron con un almacén simulado. ¿Se acepta?", "PO"),
    ("OBS-57", "(Ya registrada en HU-21) No se probó el historial de alarmas de un proyecto revocado. ¿Debe cubrirse?", "PO"),
    ("OBS-61", "Un proyecto activo en una sede inactiva se acepta en el flujo empresarial; el anterior lo rechaza. ¿Debe rechazarse también?", "PO"),
    ("OBS-62", "5 pruebas CA-08 de test_hu21_qa.py esperan el formato de auditoría antiguo. El actual se verifica en CP-479 a 483.", "QA"),
    ("OBS-63", "«Sesión abierta» falló 1 de 9 veces en una corrida larga sin traza; no se pudo explicar. Pasó en todas las posteriores.", "QA"),
]

CONCLUSION = "<b>APTO CON OBSERVACIONES.</b> PP-185 pasa a Listo y la HU queda completa; siguen abiertas las decisiones del PO y la regresión completa, que el usuario dejó fuera de esta ronda por tiempo y no bloquea."
AVANCE = [("Aprobados", 138, "ok"), ("Fallidos", 0, "fail"), ("Bloqueados", 0, "warn")]
ESTADO_FINAL = [
    ("Subtareas", "4 de 4 en Listo", "ok", "PP-183, PP-184, PP-185 y PP-414."),
    ("Criterios", "8 de 8 cumplen", "ok", "CA-03 queda sujeto a la decisión de OBS-61."),
    ("Defectos", "4 cerrados · 0 abiertos", "ok", "DEF-10 y DEF-11 de Jareth; DEF-12 y DEF-13 corregidos por QA, en dev."),
    ("Regresión", "No repetida", "warn", "Ronda 1 sobre 5430e91: 1 080 con la variable; 88 fallan sin ella, previas a esta HU (OBS-45). Frontend actual: 57 de 57."),
]
NO_PROBADO = [
    ("Regresión completa de backend", "Parcial", "Se priorizó PP-185 por tiempo; solo corrió HU-21 y empresas", "Correrla en las dos configuraciones"),
    ("Entorno desplegado", "No aplica", "Los criterios no lo piden", "Nada"),
]
LEYENDA_NO_PROBADO = "<b>Parcial:</b> se probó solo una parte. <b>Bloqueado:</b> no se puede probar hasta resolver lo indicado. <b>No aplica:</b> no se pide en esta HU."
PENDIENTES = [
    ("Decidir OBS-61: si un proyecto en sede inactiva debe rechazarse.", "PO", "No"),
    ("Decidir OBS-45, OBS-56 y OBS-57.", "PO", "No"),
    ("Correr la regresión completa de backend en las dos configuraciones.", "QA", "No"),
    ("Actualizar las 5 pruebas CA-08 al formato actual (OBS-62).", "QA", "No"),
    ("Cambiar los estados de las subtareas en Jira según la sección 1.", "QA", "No"),
]

# =====================================================================
# MOTOR DEL INFORME  (no editar: formato fijo para todas las HU)
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


def barra_avance(items):
    """Barra de casos por estado, proporcional al total, con su leyenda debajo."""
    items = [i for i in items if i[1] > 0]
    total = sum(n for _, n, _ in items)
    barra = Table([[""] * len(items)], colWidths=[CONTENT_W * n / total for _, n, _ in items], rowHeights=[0.34 * cm])
    barra.setStyle(TableStyle([("BACKGROUND", (i, 0), (i, 0), TONOS[c][0]) for i, (_, _, c) in enumerate(items)]))
    leyenda = " · ".join(f'<font color="{TONOS[c][0].hexval()}"><b>{n} {t.lower()}</b></font>' for t, n, c in items)
    return KeepTogether([barra, Spacer(1, 2), P(f"Casos funcionales ({total}): {leyenda}", S_SMALL)])


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
        [1.4 * cm, 7.3 * cm, 3.4 * cm, 2.7 * cm, CONTENT_W - 14.8 * cm],
    ))

    # 4. Esperado vs. obtenido (condicional). Sin ESPERADO, las secciones siguientes se renumeran solas.
    resta = 0 if ESPERADO else 1
    if ESPERADO:
        s.append(P(f"4. {ESPERADO_TITULO}", S_H))
        s.append(P(ESPERADO_NOTA, S_SMALL))
        s.append(Spacer(1, 3))
        n_col = len(COLUMNAS)
        w_val = 1.72 * cm if n_col > 1 else 3.2 * cm
        w_fixed = 3.1 * cm + w_val * n_col + 1.7 * cm + 1.9 * cm
        s.append(table(
            ["Acción"] + COLUMNAS + ["Por qué es lo esperado", "Casos", "Resultado"],
            [[a] + [badge(v) for v in vals] + [pq, cs, badge(res)] for a, vals, pq, cs, res in ESPERADO],
            [3.1 * cm] + [w_val] * n_col + [CONTENT_W - w_fixed, 1.7 * cm, 1.9 * cm],
        ))
        if ESPERADO_PIE:
            s.append(Spacer(1, 2))
            s.append(P(ESPERADO_PIE, S_SMALL))

    # 5. Herramientas
    s.append(P(f"{5 - resta}. Herramientas y tipo de prueba", S_H))
    s.append(table(
        ["Herramienta", "¿Se usó?", "Tipo de prueba", "Por qué se usó o no", "Resultado"],
        [[P(h, S_CELL_B), badge(u, "ok" if u == "Sí" else "gray"), t, pq,
          badge("No aplica", "gray") if a is None else badge(a, "warn") if isinstance(a, str) else badge(f"{a} aprobadas · {f} fallida{'s' if f != 1 else ''}", "gray" if f > 0 else "ok")]
         for h, u, t, pq, a, f in HERRAMIENTAS],
        [2.9 * cm, 1.5 * cm, 2.9 * cm, CONTENT_W - 11.1 * cm, 3.8 * cm],
    ))
    if HERRAMIENTAS_NOTA:
        s.append(Spacer(1, 3))
        s.append(P(HERRAMIENTAS_NOTA, S_CELL))
    if MOTIVOS_FALLOS:
        s.append(P("Casos bloqueados: por qué y qué falta", S_H))
        s.append(table(
            ["Caso", "Qué pide", "Por qué no se aprobó", "Qué falta", "Resuelve"],
            [[P(c, S_CELL_B), q, p, f, badge(r, t)] for c, q, p, f, r, t in MOTIVOS_FALLOS],
            [1.5 * cm, 3.6 * cm, CONTENT_W - 12.0 * cm, 5.0 * cm, 1.9 * cm],
        ))
    if NOTA_FALLOS:
        s.append(Spacer(1, 3))
        s.append(P(NOTA_FALLOS, S_BODY))

    # 6. Evidencias
    titulo_ev = P(f"{6 - resta}. Evidencias: captura del HTML que generó cada herramienta", S_H)
    for i, (h, a, f, que, png, ancho, pie) in enumerate(EVIDENCIAS):
        color = WARN.hexval() if isinstance(f, int) and f > 0 else OK.hexval()
        s.append(KeepTogether(([titulo_ev] if i == 0 else []) + [  # el título viaja con la primera captura
            P(f'<b>{h}</b>  ·  <font color="{color}"><b>{a} aprobadas · {f} fallida{"s" if f != 1 else ""}</b></font>  ·  {que}', S_BODY),
            Spacer(1, 3),
            evidence(ROOT / png, CONTENT_W * ancho),
            Spacer(1, 2),
            P(pie, S_SMALL),
        ]))
        if i < len(EVIDENCIAS) - 1:
            s.append(Spacer(1, 8))

    # 7. Observaciones
    s.append(P(f"{7 - resta}. Observaciones (no cambian el estado)", S_H))
    if OBSERVACIONES:
        s.append(table(
            ["ID", "Observación", "Decide"],
            [[P(i, S_CELL_B), t, badge(d)] for i, t, d in OBSERVACIONES],
            [1.55 * cm, CONTENT_W - 2.85 * cm, 1.3 * cm],
        ))
    else:
        s.append(P("Sin observaciones.", S_BODY))

    # 8. Conclusión
    bloque = [P(f"{8 - resta}. Conclusión y pendientes", S_H), P(CONCLUSION, S_BODY), Spacer(1, 4), barra_avance(AVANCE), Spacer(1, 3),
              table(["Tema", "Estado", "Qué significa"],
                    [[P(t, S_CELL_B), badge(e, c), d] for t, e, c, d in ESTADO_FINAL],
                    [3.3 * cm, 3.1 * cm, CONTENT_W - 6.4 * cm])]
    if NO_PROBADO:
        bloque += [Spacer(1, 3),
                   table(["No se probó", "Estado", "Por qué", "Qué falta"],
                         [[t, badge(e), d, f] for t, e, d, f in NO_PROBADO],
                         [3.9 * cm, 1.9 * cm, CONTENT_W - 10.4 * cm, 4.6 * cm]),
                   Spacer(1, 2), P(LEYENDA_NO_PROBADO, S_CELL)]
    if PENDIENTES:
        bloque += [Spacer(1, 3),
                   table(["#", "Pendiente", "Responsable", "¿Bloquea?"],
                         [[str(i), t, badge(r), badge(b, "fail" if b == "Sí" else "gray")] for i, (t, r, b) in enumerate(PENDIENTES, start=1)],
                         [0.7 * cm, CONTENT_W - 5.5 * cm, 2.4 * cm, 2.4 * cm])]
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
    return Path(__file__).resolve().parent / f"Informe_QA_{HU}_ronda2_{fecha_iso}.pdf"


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
    if paginas > 4:
        print("AVISO: pasa de 4 páginas. Acorta textos, reduce filas del extracto o el ancho de las capturas.")


if __name__ == "__main__":
    main()
