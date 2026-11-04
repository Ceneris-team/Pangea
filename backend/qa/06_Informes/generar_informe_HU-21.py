"""Informe PDF de QA de HU-21 (PP-414), ronda 1 (A4, máximo 4 páginas). Motor: Plantilla_Informe_QA.py.

La matriz de la sección 4 tiene columnas más estrechas que la plantilla para que quepan cinco roles.
Ejecutar desde la raíz del repo:
    backend/venv/Scripts/python.exe backend/qa/06_Informes/generar_informe_HU-21.py
Sale backend/qa/06_Informes/Informe_QA_HU-21_<aaaa-mm-dd>.pdf
"""
import sys
from pathlib import Path

# =====================================================================
# DATOS DEL INFORME
# =====================================================================

PROYECTO = None
TABLERO = "PP"
HU = "HU-21"
NOMBRE_HU = "Conceder permisos"
SUBTAREA_QA = "PP-414"
VERSION = "v0.1 (borrador: DEF-10 y DEF-11 abiertos)"
FECHA = "04/11/2026"
RESPONSABLE = "Elliot (JS), Aseguramiento de Calidad (QA)"
ENTORNO = "Local (Postgres y Redis en Docker, Edge), tokens reales, sin producción"
RAMAS = "origin/dev en 5430e91 (qa-elliot no incluye la implementación b4a9c9a)"
REVISA = "Product Owner"

VEREDICTO = "NO APTO PARA CIERRE"
RESUMEN = ("<b>CA-01, 02, 04, 05 y 08 se cumplen</b>; <b>CA-03, 06 y 07 fallan en parte</b> por 2 defectos menores de PP-185 (DEF-10 y DEF-11). "
           "Las consultas por API no entregaron proyectos no autorizados. "
           "La regresión pasa con la configuración de QA; <b>por defecto fallan 88 pruebas previas</b> a esta HU (OBS-45), y el PO decide cuándo corregirlas.")

KPIS = [
    ("114 / 118", "casos<br/>aprobados", "fail"),
    ("2", "defectos abiertos<br/>(0 cerrados)", "fail"),
    ("114", "pruebas automatizadas<br/>aprobadas (87 + 27)", "warn"),
    ("5 / 8", "requisitos aprobados<br/>(8 con casos en RTM)", "warn"),
    ("5", "observaciones<br/>(3 para el PO)", "warn"),
]

SUBTAREAS = [
    ("PP-183", "Diseñar panel de permisos por ubicación", "Listo", "CA-01 y CA-04 cumplen en los dos flujos (CP-344 a 358, 380, 434, 437, 438, 444, 450 a 453)."),
    ("PP-184", "Listar ubicaciones y estado de acceso actual", "Listo", "CA-02 y CA-05 cumplen, con 21 consultas por API sin acceso indebido (CP-359 a 364, 381 a 396)."),
    ("PP-185", "Guardar cambios de permisos por usuario", "En curso", "Guardar, retirar y auditar funcionan, pero quedan DEF-10 y DEF-11, menores. Pasa a Listo con RG-37 y RG-38."),
    ("PP-414", "Validar criterios de aceptación, flujos y errores", "Listo", "QA terminó: pruebas ejecutadas, evidencias y defectos registrados, e informe adjunto en esta subtarea."),
]

DEFECTOS_PRODUCTO = 2
FALLOS = [
    ("Producto (DEF-10, abierto)", "Un proyecto inactivo se rechaza con «Hay proyectos que no pertenecen a esta empresa» (CP-371, 372 y 417).", "_validar_asignaciones une pertenencia y estado en una consulta y un solo mensaje.", "Pendiente: separar las dos comprobaciones (RG-37)."),
    ("Producto (DEF-11, abierto)", "Si se revoca antes de la primera lectura de /auth/acceso, los resultados retirados siguen en pantalla (CP-461).", "VigenciaAcceso parte de una versión vacía en cada carga.", "Pendiente: conservar la versión y compararla al cargar (RG-38)."),
    ("Entorno (pytest)", "Falló un test de WebSocket existente.", "DATABASE_URL no apuntaba a la base de test (OBS-55).", "Se fijó la variable: 1 080 de 1 080."),
    ("Pruebas (QA)", "Las primeras corridas dieron falsos resultados.", "Correos .test, una ruta mal escrita, un plan sin tableros y selectores.", "Se corrigieron; los controles positivos confirman que las consultas detectan datos."),
]

COBERTURA = [
    ("CA-01", "RQ-HU21-01 · Gestión según el tipo de cuenta", "CP-344 a 358, 434, 450 a 453", "Aprobado", "—"),
    ("CA-02", "RQ-HU21-02 · Contexto y acceso actual visibles", "CP-359 a 364, 435, 436, 441, 443, 454", "Aprobado", "—"),
    ("CA-03", "RQ-HU21-03 · Guardado válido y completo", "CP-365 a 379, 439, 440, 446, 447", "Fallido", "DEF-10"),
    ("CA-04", "RQ-HU21-04 · Cancelación sin persistencia", "CP-380, 437, 438, 444", "Aprobado", "—"),
    ("CA-05", "RQ-HU21-05 · Aislamiento en todas las consultas", "CP-381 a 396, 459, 460", "Aprobado", "OBS-57"),
    ("CA-06", "RQ-HU21-06 · Aplicación y revocación con sesión abierta", "CP-397 a 405, 427 a 433, 455, 456, 458, 461", "Fallido", "DEF-11, OBS-56"),
    ("CA-07", "RQ-HU21-07 · Retirada de acceso y continuidad administrativa", "CP-406 a 418, 442, 445, 448, 449, 457", "Fallido", "DEF-10"),
    ("CA-08", "RQ-HU21-08 · Trazabilidad del cambio", "CP-419 a 426", "Aprobado", "—"),
]

ESPERADO_TITULO = "Matriz rol × acción verificada (API y pantalla)"
ESPERADO_NOTA = ("Cada celda es el <b>comportamiento esperado</b> según los criterios y los detalles de la HU. <b>Aprobado</b> significa que el sistema hizo exactamente eso. "
                 "Un «Denegado» es un resultado correcto, no un error.")
COLUMNAS = ["Admin<br/>CENERIS", "Admin<br/>empresa", "Técnico<br/>empresa", "Lector", "Cliente<br/>Final"]
ESPERADO = [
    ("Gestionar permisos de Cliente Final", ["Permitido", "Denegado<br/>403", "Denegado<br/>403", "Denegado<br/>403", "Denegado<br/>403"], "CA-01: solo CENERIS", "CP-344, 347 a 352", "Aprobado"),
    ("Editar miembro de su empresa", ["Permitido", "Permitido", "Denegado<br/>403", "Denegado<br/>403", "Denegado<br/>403"], "CA-01: solo administradores", "CP-344, 345, 349 a 351", "Aprobado"),
    ("Editar miembro de otra empresa", ["Permitido", "Denegado<br/>403", "Denegado<br/>403", "Denegado<br/>403", "Denegado<br/>403"], "CA-01: su empresa", "CP-345 a 351", "Aprobado"),
    ("Ver proyecto no asignado de su empresa", ["Permitido", "Permitido", "Permitido", "Denegado", "Denegado"], "CA-05: rol y asignación", "CP-381, 382, 392", "Aprobado"),
    ("Ver proyecto de otra empresa", ["Permitido", "Denegado", "Denegado", "Denegado", "Denegado"], "CA-05: aislamiento", "CP-385, 386, 392, 393", "Aprobado"),
    ("Guardar selección vacía", ["Permitido<br/>(anterior)", "Denegado<br/>422", "Denegado<br/>403", "Denegado<br/>403", "Denegado<br/>403"], "CA-07", "CP-373, 406", "Aprobado"),
]
ESPERADO_PIE = "El Administrador CENERIS ve otra empresa según el entorno seleccionado. Técnico CENERIS y Administrador Comercial: se probó que no pueden gestionar accesos (CP-347, 348, 453)."

HERRAMIENTAS = [
    ("pytest + pytest-html", "Sí", "API, seguridad básica y WebSocket real", "Las reglas viven en la API y los CA piden probar peticiones directas. Usa tokens reales y Postgres; 7 pruebas usan servidor y Redis reales.", 87, 3),
    ("Playwright (Edge)", "Sí", "UI y flujos de punta a punta", "Mensajes, cancelación y revocación con dos sesiones abiertas solo se ven en pantalla.", 27, 1),
    ("pytest (regresión)", "Sí", "Backend completo, dos configuraciones", "HU-21 cambia usuarios, empresas y el filtro de acceso. Con la variable y DATABASE_URL de test: 1 080 aprobadas. Por defecto: 992 aprobadas y 88 fallidas.", 992, 88),
    ("npm run test:series", "Sí", "Regresión de frontend", "Suite propia del frontend. Log: npm_test.log.", 47, 0),
    ("Locust, k6, ZAP, axe, Lighthouse, pytest-cov", "No", "Carga, seguridad, accesibilidad y cobertura", "Ni PP-414 ni los criterios los piden.", None, None),
]
HERRAMIENTAS_NOTA = ("<b>Regresión por defecto:</b> mapeos 33, ubicaciones 23, dispositivos 17, ficha de dispositivo 9, columnas pendientes 3, caché HT-10 1, cola de ingesta 1 y límites de plan 1. "
                     "Los mismos fallos aparecen en el commit base f9c0967, registrados en OBS-45: no son de esta HU.")
MOTIVOS_FALLOS = []
NOTA_FALLOS = "Las 3 fallidas de pytest son DEF-10 y la de Playwright es DEF-11. No hay casos bloqueados."

EVIDENCIAS = [
    ("pytest-html", 87, 3, "extracto: primeras 10 de 90 filas",
     "qa/03_Evidencias/HU21/EV-HU21-INF-01_captura-informe-pytest.png", 0.6,
     "EV-HU21-INF-01. HTML completo: backend/qa/03_Evidencias/HU21/pytest_hu21.html. Regresión: pytest_regresion.html (EV-HU21-INF-05) y pytest_regresion_sin_variable.html (EV-HU21-INF-06)."),
    ("Playwright (Edge)", 27, 1, "extracto: contadores y primeras 10 de 28 filas",
     "qa/03_Evidencias/HU21/EV-HU21-INF-02_captura-informe-playwright.png", 0.72,
     "EV-HU21-INF-02. HTML completo: backend/qa/03_Evidencias/HU21/playwright/index.html"),
]

OBSERVACIONES = [
    ("DEF-10", "PP-185 · Media: el rechazo por proyecto inactivo dice que no pertenece a la empresa. Se reprueba con RG-37.", "Dev"),
    ("DEF-11", "PP-185 · Media: la pantalla no detecta una revocación ocurrida antes de la primera lectura de acceso. Se reprueba con RG-38.", "Dev"),
    ("OBS-45", "(Ya registrada en PP-47) Por defecto fallan 88 de 1 080 pruebas por fixtures sin suscripción vigente. ¿Se corrigen ahora o después?", "PO"),
    ("OBS-55", "Un test de WebSocket falla si DATABASE_URL no apunta a la base de test. Es de entorno, no del producto.", "Dev"),
    ("OBS-56", "Los 60 s de la firma se comprobaron con un almacén simulado, no con la caducidad real en S3. ¿Se acepta o se prueba en un bucket real?", "PO"),
    ("OBS-57", "No se probó el historial de alarmas ya creadas sobre un proyecto revocado: CA-05 no lo nombra. ¿Debe cubrirse?", "PO"),
    ("OBS-58", "Los commits de la implementación no citan PP-183, PP-184 ni PP-185.", "Dev"),
]

CONCLUSION = "<b>NO APTO PARA CIERRE (borrador).</b> Falta corregir y reprobar DEF-10 y DEF-11; son menores y las consultas por API no entregaron proyectos no autorizados."
AVANCE = [("Aprobados", 114, "ok"), ("Fallidos", 4, "fail"), ("Bloqueados", 0, "warn")]
ESTADO_FINAL = [
    ("Subtareas", "3 de 4 en Listo", "warn", "PP-185 sigue En curso por DEF-10 y DEF-11."),
    ("Criterios", "5 de 8 cumplen", "warn", "CA-03, CA-06 y CA-07 fallan solo en los casos de esos defectos."),
    ("Defectos", "0 cerrados · 2 abiertos", "fail", "DEF-10 y DEF-11, severidad Media, asignados a Jareth."),
    ("Regresión", "1 080 · 88 fallan", "warn", "1 080 de 1 080 con PLAN_LIMITS_REQUIRE_SUBSCRIPTION=false y DATABASE_URL de test. Por defecto fallan 88, previas a esta HU (OBS-45)."),
]
NO_PROBADO = [
    ("Caducidad real de la firma en S3", "Parcial", "Se usó un almacén simulado, sin coste", "Decisión del PO (OBS-56)"),
    ("Historial de alarmas de un proyecto revocado", "Parcial", "CA-05 no lo nombra", "Decisión del PO (OBS-57)"),
    ("Producción", "No aplica", "Los criterios no la piden", "Nada"),
]
LEYENDA_NO_PROBADO = "<b>Parcial:</b> se probó solo una parte. <b>Bloqueado:</b> no se puede probar hasta resolver lo indicado. <b>No aplica:</b> no se pide en esta HU."
PENDIENTES = [
    ("Corregir DEF-10 y DEF-11 en PP-185 y avisar con el commit.", "Dev", "Sí"),
    ("Reprobar RG-37 y RG-38 y actualizar este informe.", "QA", "Sí"),
    ("Decidir OBS-45: corregir ahora o después las 88 pruebas previas.", "PO", "No"),
    ("Decidir OBS-56 y OBS-57.", "PO", "No"),
    ("Agregar a tests/conftest.py la suscripción vigente de las 88 pruebas (OBS-45).", "Dev", "No"),
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
          badge("No aplica", "gray") if a is None else badge(f"{a} aprobadas · {f} fallidas", "fail" if f > 0 else "ok")]
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
    if paginas > 4:
        print("AVISO: pasa de 4 páginas. Acorta textos, reduce filas del extracto o el ancho de las capturas.")


if __name__ == "__main__":
    main()
