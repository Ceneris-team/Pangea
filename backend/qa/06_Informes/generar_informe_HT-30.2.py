"""Informe PDF de QA de HT-30.2 (A4, máximo 3 páginas). Mismo motor que generar_informe_HU-34.py.

Ejecutar desde la raíz del repo:
    backend/venv/Scripts/python.exe backend/qa/06_Informes/generar_informe_HT-30.2.py
Sale backend/qa/06_Informes/Informe_QA_HT-30.2_<aaaa-mm-dd>.pdf
"""
import sys
from pathlib import Path

# =====================================================================
# DATOS DEL INFORME
# =====================================================================

PROYECTO = None
TABLERO = "PP"
HU = "HT-30.2"
NOMBRE_HU = "Plan de pruebas, parte 2: casos, E2E y ejecución"
SUBTAREA_QA = "PP-403"
VERSION = "v0.1"
FECHA = "02/11/2026"
RESPONSABLE = "Elliot (JS), Aseguramiento de Calidad (QA)"
ENTORNO = "Local (BD pangea_test y pangea_e2e en Docker, Edge) y Lightsail en solo lectura para DEF-01"
RAMAS = "qa-elliot (commit 827755e, con dev hasta f9c0967)"
REVISA = "Product Owner"

VEREDICTO = "APTO CON OBSERVACIONES"
RESUMEN = ("Los flujos principales funcionan de punta a punta: <b>40 de 40 E2E</b> con los 4 roles, regresión del backend sin fallos del "
           "producto y frontend 16 de 16. <b>0 defectos del producto en el alcance de HT-30.2.</b> En la reprueba de defectos abiertos, "
           "<b>DEF-01 quedó cerrado</b>; DEF-02 y DEF-03 siguen abiertos, pero son de HT-06. El PO debe corregir la descripción de PP-336 (OBS-21).")

KPIS = [
    ("42 / 44", "casos aprobados<br/>(2 fallan por HT-06)", "warn"),
    ("0", "defectos del producto<br/>(alcance HT-30.2)", "ok"),
    ("40 / 40", "E2E Playwright<br/>+ frontend 16 / 16", "ok"),
    ("8 / 8", "requisitos cubiertos<br/>(RTM)", "ok"),
    ("5", "observaciones<br/>(1 para el PO)", "warn"),
]

SUBTAREAS = [
    ("PP-400", "HT-30.2 · Elaborar casos de prueba con pasos y resultados esperados", "Listo", "44 casos (CP-128 a 171) con precondición, pasos y resultado esperado, trazados a 8 requisitos en la RTM."),
    ("PP-401", "HT-30.2 · Automatizar las pruebas E2E de los flujos principales", "Listo", "Suite ht30.spec.mjs con 40 tests (F1 a F7), uno por caso; estable en dos corridas seguidas."),
    ("PP-402", "HT-30.2 · Ejecutar las pruebas y registrar resultados e incidencias", "Listo", "E2E 40/40, backend 782/879 (97 solo por OBS-11), frontend 16/16; fallos clasificados y registrados."),
    ("PP-403", "HT-30.2 · Verificar las correcciones y consolidar las evidencias", "Listo", "QA terminó: pruebas ejecutadas, evidencias y defectos registrados, e informe adjunto en esta subtarea."),
]

DEFECTOS_PRODUCTO = 0
FALLOS = [
    ("Pruebas (pytest)", "97 de 879 tests fallaron con 409.", "Tests sin suscripción (OBS-11).", "Sin ese requisito: 97 de 97 aprobados."),
    ("Datos (Playwright)", "CP-149 sin filas.", "Vista de 24 h y datos del 30/10 (OBS-23).", "Rango fijo 29/10 a 31/10; aprobado."),
    ("Pruebas (Playwright)", "CP-144 y 155 pasaron de 5 s.", "Pestañas abiertas y pytest en paralelo (OBS-24).", "Cada test cierra su contexto; 40 de 40 dos veces."),
]

COBERTURA = [
    ("F1", "RQ-HT302-01 · Login de los 4 roles, errores y cierre de sesión", "CP-128 a 136", "Aprobado", "—"),
    ("F2", "RQ-HT302-02 · Cada rol solo entra a sus rutas", "CP-137 a 143", "Aprobado", "—"),
    ("F3", "RQ-HT302-03 · Empresa y dispositivos", "CP-144 a 148", "Aprobado", "OBS-24"),
    ("F4", "RQ-HT302-04 · Consulta de datos con filtros", "CP-149 a 151", "Aprobado", "OBS-23"),
    ("F5", "RQ-HT302-05 · Paneles de punta a punta (incluye HU-19)", "CP-152 a 158", "Aprobado", "—"),
    ("F6", "RQ-HT302-06 · Permisos de ubicación (HU-21) y empresas", "CP-159 a 163", "Aprobado", "—"),
    ("F7", "RQ-HT302-07 · Recuperar contraseña sin revelar cuentas", "CP-164 a 167", "Aprobado", "—"),
    ("Transversal", "RQ-HT302-08 · Regresión y reprueba de DEF-01 a 03", "CP-168 a 171", "Fallido", "DEF-02, 03 (HT-06)"),
]

ESPERADO_TITULO = "Matriz rol × ruta verificada"
ESPERADO_NOTA = ("Cada celda es el comportamiento <b>esperado</b> según la configuración de rutas de dev (router y ProtectedRoute) y quedó "
                 "comprobado con Playwright. Un «Denegado» es un resultado correcto: el rol vuelve a /login. «—» significa que esa combinación no se probó.")
COLUMNAS = ["Admin.", "Técnico", "Cliente", "Comercial"]
ESPERADO = [
    ("Pantalla tras iniciar sesión", ["Panel admin.", "Clientes", "Paneles", "Panel com."], "Panel de cada rol (rutaPorRol)", "CP-128 a 131", "Aprobado"),
    ("/usuarios", ["Permitido", "Denegado", "Denegado", "Denegado"], "Solo Administrador", "CP-138, 140, 141, 143", "Aprobado"),
    ("/planes-suscripciones", ["—", "—", "—", "Permitido"], "Administrador y Comercial", "CP-141", "Aprobado"),
    ("/cola-ingesta", ["—", "—", "Denegado", "—"], "Sin Cliente Final", "CP-139", "Aprobado"),
    ("/dispositivos sin empresa", ["—", "A /clientes", "—", "—"], "CENERIS elige empresa", "CP-142", "Aprobado"),
]
ESPERADO_PIE = "Sin sesión, /usuarios, /paneles y /consulta-datos redirigen a /login (CP-137)."

HERRAMIENTAS = [
    ("Playwright (Edge)", "E2E de UI, flujos F1 a F7", "Prueba como un usuario real los 4 roles, pantallas, mensajes y redirecciones.", 40, 0),
    ("pytest + pytest-html", "Regresión del backend", "Suite existente completa (879 pruebas) para detectar daños en la API.", 782, "97 por OBS-11"),
    ("pytest (reprueba)", "Reprueba de DEF-02 y DEF-04", "Historial de git (HT-06) y sondeo FTP de HU-18, incluido un FTP real.", 23, "2 por DEF-02"),
]
HERRAMIENTAS_NOTA = ("Además: node --test del frontend 16 de 16 (EV-HT302-INF-07); docker compose para DEF-03 (fallida, EV-HT302-INF-10); "
                     "verificar_lightsail.sh en CloudShell para DEF-01 (aprobada, EV-HT302-INF-11). Descartadas: Locust, k6, OWASP ZAP, "
                     "Lighthouse y axe (la HT no los pide; ya hay resultados de k6 en backend/tests/carga).")

EVIDENCIAS = [
    ("Playwright", 40, 0, "extracto: primeras 10 de 40 pruebas",
     "qa/03_Evidencias/HT-30.2/EV-HT302-INF-12_captura-informe-playwright-extracto.png", 0.70,
     "EV-HT302-INF-12. HTML completo: backend/qa/03_Evidencias/HT-30.2/playwright/index.html"),
    ("pytest-html (regresión)", 782, "97 por OBS-11", "extracto: primeras 10 de 97 fallidas",
     "qa/03_Evidencias/HT-30.2/EV-HT302-INF-04_captura-regresion-fallidas-extracto.png", 0.62,
     "EV-HT302-INF-04. HTML: backend/qa/03_Evidencias/HT-30.2/pytest_regresion.html; las 97 pasan en pytest_regresion_sin_suscripcion.html"),
    ("pytest-html (reprueba)", 23, "2 por DEF-02", "extracto: primeras 10 de 25 filas",
     "qa/03_Evidencias/HT-30.2/EV-HT302-INF-09_captura-reverificacion-extracto.png", 0.62,
     "EV-HT302-INF-09. HTML completo: backend/qa/03_Evidencias/HT-30.2/pytest_reverificacion.html"),
]

OBSERVACIONES = [
    ("OBS-21", "La descripción y los criterios de PP-336 en Jira hablan de diagramas de componentes y de secuencia, no de pruebas; QA trabajó según las subtareas.", "PO"),
    ("OBS-30", "DEF-01 se cerró en la consola de Lightsail; falta confirmar que la API de producción sigue leyendo la BD ahora privada.", "Dev"),
    ("OBS-11", "(Ya registrada en HU-18) 97 tests del backend no crean suscripción y fallan con 409; falta un fixture común en tests/conftest.py.", "Dev"),
    ("OBS-22 a 24", "Entorno y pruebas: índice propio de Redis para el límite de logins, rango de fechas fijo en CP-149 y cierre de contextos en la suite.", "QA"),
]

CONCLUSION = ("<b>APTO CON OBSERVACIONES.</b> Los 7 flujos principales funcionan de punta a punta con los 4 roles y la regresión no encontró "
              "fallos del producto; las 4 subtareas pasan a Listo. Las 2 reprueba fallidas son de defectos de HT-06 (DEF-02 y DEF-03), no de "
              "esta HT. <b>Alcance real</b>: local; producción solo en lectura para DEF-01. No se probaron alarmas (rama fabio), modelo "
              "comercial (feature/PP-47) ni la exportación de HU33, que tienen su propio QA.")
PENDIENTES = [
    ("Corregir la descripción y los criterios de PP-336 o confirmar que los diagramas son otra HT (OBS-21).", "PO"),
    ("Confirmar que la API de producción lee la BD privada (OBS-30).", "Dev"),
    ("HT-06: rotar la contraseña de la BD, JWT_SECRET y FTP_CREDENTIAL_KEY (DEF-02) y alinear el usuario de la BD en docker-compose.yml (DEF-03).", "Dev"),
    ("Agregar el fixture de suscripción a tests/conftest.py (OBS-11).", "Dev"),
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


def resultado(aprobadas, fallidas):
    """Texto y tono del resultado: un texto en «fallidas» explica fallos ajenos al producto (ámbar), no defectos (rojo)."""
    if isinstance(fallidas, str):
        return f"{aprobadas} aprobadas · {fallidas}", "warn"
    return f"{aprobadas} aprobadas · {fallidas} fallidas", "fail" if fallidas else "ok"


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

    # 4 (esperado vs. obtenido): esta HT sí la lleva (4 roles con acceso distinto); renumera el resto
    n0 = 5 if ESPERADO else 4
    if ESPERADO:
        # 4. Esperado vs. obtenido
        n_col = len(COLUMNAS)
        w_val = 1.75 * cm if n_col > 1 else 3.2 * cm
        w_fixed = 3.4 * cm + w_val * n_col + 2.3 * cm + 1.8 * cm
        matriz = [P(f"4. {ESPERADO_TITULO}", S_H), P(ESPERADO_NOTA, S_SMALL), Spacer(1, 3), table(
            ["Acción"] + COLUMNAS + ["Por qué es lo esperado", "Casos", "Resultado"],
            [[a] + [badge(v) for v in vals] + [pq, cs, badge(res)] for a, vals, pq, cs, res in ESPERADO],
            [3.4 * cm] + [w_val] * n_col + [CONTENT_W - w_fixed, 2.3 * cm, 1.8 * cm],
        )]
        if ESPERADO_PIE:
            matriz += [Spacer(1, 2), P(ESPERADO_PIE, S_SMALL)]
        s.append(KeepTogether(matriz))  # el título y la nota no quedan solos al pie de página

    # 5. Herramientas
    s.append(P(f"{n0}. Herramientas y tipo de prueba", S_H))
    s.append(table(
        ["Herramienta", "Tipo de prueba", "Por qué", "Resultado"],
        [[P(h, S_CELL_B), t, pq, badge(*resultado(a, f))]
         for h, t, pq, a, f in HERRAMIENTAS],
        [3.2 * cm, 4.0 * cm, CONTENT_W - 11.4 * cm, 4.2 * cm],
    ))
    if HERRAMIENTAS_NOTA:
        s.append(Spacer(1, 2))
        s.append(P(HERRAMIENTAS_NOTA, S_SMALL))

    # 6. Evidencias
    titulo_ev = P(f"{n0 + 1}. Evidencias: captura del HTML que generó cada herramienta", S_H)
    for i, (h, a, f, que, png, ancho, pie) in enumerate(EVIDENCIAS):
        texto_res, clave_res = resultado(a, f)
        color = TONOS[clave_res][0].hexval()
        s.append(KeepTogether(([titulo_ev] if i == 0 else []) + [  # el título viaja con la primera captura
            P(f'<b>{h}</b>  ·  <font color="{color}"><b>{texto_res}</b></font>  ·  {que}', S_BODY),
            Spacer(1, 3),
            evidence(ROOT / png, CONTENT_W * ancho),
            Spacer(1, 2),
            P(pie, S_SMALL),
        ]))
        if i < len(EVIDENCIAS) - 1:
            s.append(Spacer(1, 8))

    # 7. Observaciones
    s.append(P(f"{n0 + 2}. Observaciones (no cambian el estado)", S_H))
    if OBSERVACIONES:
        s.append(table(
            ["ID", "Observación", "Decide"],
            [[P(i, S_CELL_B), t, badge(d)] for i, t, d in OBSERVACIONES],
            [1.55 * cm, CONTENT_W - 2.85 * cm, 1.3 * cm],
        ))
    else:
        s.append(P("Sin observaciones.", S_BODY))

    # 8. Conclusión
    bloque = [P(f"{n0 + 3}. Conclusión y pendientes", S_H), P(CONCLUSION, S_BODY)]
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
