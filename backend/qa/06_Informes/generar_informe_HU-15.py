"""Informe PDF de QA de HU-15 (A4, máximo 3 páginas). Mismo motor que generar_informe_HT-30.2.py.

Ejecutar desde la raíz del repo:
    backend/venv/Scripts/python.exe backend/qa/06_Informes/generar_informe_HU-15.py
Sale backend/qa/06_Informes/Informe_QA_HU-15_<aaaa-mm-dd>.pdf
"""
import sys
from pathlib import Path

# =====================================================================
# DATOS DEL INFORME
# =====================================================================

PROYECTO = None
TABLERO = "PP"
HU = "HU-15"
NOMBRE_HU = "Pipeline de exportación en background con Celery (HU33)"
SUBTAREA_QA = "PP-408"
VERSION = "v0.1"
FECHA = "02/11/2026"
RESPONSABLE = "Elliot (JS), Aseguramiento de Calidad (QA)"
ENTORNO = "Local (API, worker y Beat reales; S3 emulado con moto y buzón Mailpit; contenedor de 2 CPU y 512 MiB) y Lightsail en solo lectura"
RAMAS = "qa-elliot (commit 8a4b672, con dev; el código de exportación es el de f9c0967)"
REVISA = "Product Owner"

VEREDICTO = "APTO CON OBSERVACIONES"
RESUMEN = ("Los criterios de aceptación actualizados se cumplen en local: <b>50 de 50 casos aprobados</b> y <b>0 defectos del producto</b>. "
           "Un mes de telemetría (446 400 filas) se genera en <b>7,5 s (CSV) y 62 s (XLSX)</b> en un worker de 2 CPU y 512 MiB, con 201 MiB de memoria. "
           "El PO decide si el S3 emulado y el buzón local cumplen lo de «servicios reales» (OBS-28 y OBS-32).")

KPIS = [
    ("50 / 50", "casos aprobados<br/>(ronda 2: 19 / 19)", "ok"),
    ("0", "defectos del<br/>producto", "ok"),
    ("5 + 44", "Playwright + pytest<br/>de exportaciones y QA", "ok"),
    ("12 / 12", "requisitos cubiertos<br/>(RTM)", "ok"),
    ("4", "observaciones abiertas<br/>(2 para el PO)", "warn"),
]

SUBTAREAS = [
    ("PP-283", "Implementar exportación asíncrona sin bloquear la interfaz", "Listo", "POST responde 202 con p95 de 22 ms; el identificador se conserva al recargar; límites y aislamiento verificados."),
    ("PP-284", "Procesar exportación por lotes con pandas", "Listo", "Lotes con cursores de servidor (el criterio ya no pide pandas): un mes en 7,5 s (CSV) y 62 s (XLSX), memoria máxima 201 MiB."),
    ("PP-285", "Generar enlace de descarga con expiración de 24 horas", "Listo", "Archivo disponible 24 h, firma de 60 s y correo recibido en el buzón con el enlace; pangea-storage-prod da 403 sin firma."),
    ("PP-286", "Eliminar automáticamente archivos expirados de Object Storage", "Listo", "Beat eliminó el objeto con 2 versiones y 1 marcador en 6 s; Dev debe moverla en Jira (OBS-29)."),
    ("PP-408", "HU-15-T04 · Verificar los criterios de aceptación y registrar evidencias", "Listo", "QA terminó: pruebas ejecutadas, evidencias y defectos registrados, e informe adjunto en esta subtarea."),
]

DEFECTOS_PRODUCTO = 0
FALLOS = [
    ("Pruebas (pytest)", "Una prueba de QA falló al cambiar el alcance de la cuenta.", "Usé un valor inválido ('sede'); el permitido es 'por_sede'.", "Corregido; 7 de 7 aprobadas."),
    ("Entorno (SMTP)", "Mi SMTP local rechazaba el correo.", "El producto exige STARTTLS y no lo ofrecía.", "SMTP local con STARTTLS (aiosmtpd y Mailpit)."),
    ("Entorno (S3)", "No se pudo bajar MinIO.", "Ya no se publica sin cuenta en Docker Hub ni en quay.io.", "Se usó moto como servidor S3 local."),
]

COBERTURA = [
    ("CA1", "RQ-HU15-01 · Solicitud asíncrona: 202, p95 de 2 s, id tras recargar", "CP-172 a 177, 203, 218", "Aprobado", "—"),
    ("Contenido", "RQ-HU15-09 · Todas las filas, 11 columnas y filtros conservados", "CP-181, 204, 205", "Aprobado", "—"),
    ("Volumen", "RQ-HU15-02 y 11 · Un mes por lotes en un worker de 2 CPU y 512 MiB", "CP-178 a 180, 212 a 214", "Aprobado", "OBS-25, 31"),
    ("Almacén", "RQ-HU15-03 · Bucket privado y URL firmada de 60 s", "CP-182 a 185, 219", "Aprobado", "OBS-28"),
    ("Correo", "RQ-HU15-04 · Aviso con enlace, buzón y reintento sin regenerar", "CP-186 a 189, 215, 216, 220", "Aprobado", "OBS-32"),
    ("Límites", "RQ-HU15-05 · Rango, filas, bytes, trabajos y tope de Excel", "CP-190 a 194, 210, 211", "Aprobado", "—"),
    ("Vigencia", "RQ-HU15-10 · 24 h fijas y firmas de 60 s", "CP-208, 209", "Aprobado", "—"),
    ("Limpieza", "RQ-HU15-06 y 12 · Borrado con Beat en menos de 5 minutos, con versiones", "CP-195 a 199, 217, 221", "Aprobado", "OBS-29"),
    ("Aislamiento", "RQ-HU15-07 · Otro administrador, revocaciones y alcance", "CP-200, 201, 206, 207", "Aprobado", "—"),
    ("Regresión", "RQ-HU15-08 · Backend sin fallas nuevas", "CP-202", "Aprobado", "OBS-11"),
]

ESPERADO_TITULO = ""
ESPERADO_NOTA = ""
COLUMNAS = []
ESPERADO = []
ESPERADO_PIE = ""

HERRAMIENTAS = [
    ("pytest + pytest-html", "Funcional, seguridad y tareas de Celery", "37 pruebas de exportación existentes y 7 de QA para los criterios nuevos.", 44, 0),
    ("Playwright (Edge)", "E2E de la interfaz", "Solicitud, rango excedido, descarga y recarga como Cliente Final.", 5, 0),
    ("Scripts con procesos reales", "API, worker, Beat, SMTP, S3 y buzón", "11 verificaciones: p95, contenido, aislamiento, vigencia, correo, descarga firmada y limpieza.", 11, 0),
    ("pytest en Docker", "Rendimiento (2 CPU, 512 MiB)", "446 400 filas: CSV 7,5 s y XLSX 62 s; memoria máxima 200,8 MiB.", 2, 0),
    ("pytest (regresión)", "Backend completo (879)", "Detecta daños en otras historias.", 783, "96 por OBS-11"),
]
HERRAMIENTAS_NOTA = ("Además: comandos de solo lectura en CloudShell para la privacidad de pangea-storage-prod (privado y 403 sin firma). "
                     "Descartadas: Locust y k6 (la carga formal es de HT-18), OWASP ZAP, Lighthouse y axe. "
                     "moto y Mailpit son emuladores locales: no son AWS ni un SMTP en internet.")

def _recorte_buzon():
    """Recorta la captura de la bandeja a su parte útil (encabezado y texto) para que el informe quepa en 3 páginas."""
    import tempfile
    from PIL import Image as _I
    origen = Path(__file__).resolve().parents[1] / "03_Evidencias" / "HU33-HT15" / "EV-HU33-E2E-06_buzon-correo-recibido.png"
    destino = Path(tempfile.gettempdir()) / "recorte_buzon_hu15.png"
    with _I.open(origen) as im:
        im.crop((0, 0, im.width, int(im.height * 0.55))).save(destino)
    return str(destino)


RECORTE_BUZON = _recorte_buzon()

EVIDENCIAS = [
    ("Playwright", 5, 0, "5 pruebas",
     "qa/03_Evidencias/HU33-HT15/EV-HU33-INF-04_captura-informe-playwright.png", 0.70,
     "EV-HU33-INF-04. HTML completo: backend/qa/03_Evidencias/HU33-HT15/playwright/index.html"),
    ("pytest-html (criterios de la ronda 2)", 7, 0, "7 pruebas",
     "qa/03_Evidencias/HU33-HT15/EV-HU33-INF-12_captura-pytest-criterios-ronda2.png", 0.55,
     "EV-HU33-INF-12. HTML completo: backend/qa/03_Evidencias/HU33-HT15/pytest_criterios_hu15.html"),
    ("Buzón (Mailpit)", 1, 0, "correo de exportación recibido por SMTP con STARTTLS (recorte de la captura)",
     RECORTE_BUZON, 0.62,
     "EV-HU33-E2E-06. Log: backend/qa/03_Evidencias/HU33-HT15/ronda2/verificacion_real_ronda2.txt"),
]

OBSERVACIONES = [
    ("OBS-28", "CP-220 y CP-221 se probaron con un S3 emulado y un buzón local, no con AWS real ni un SMTP en internet; la privacidad de pangea-storage-prod sí se comprobó en AWS (solo lectura).", "PO"),
    ("OBS-32", "El correo llegó a un buzón local (Mailpit) con SMTP y STARTTLS, no a un proveedor de correo. El PO confirma si basta.", "PO"),
    ("OBS-29", "PP-286 figura En curso en Jira aunque su código está entregado y verificado.", "Dev"),
    ("OBS-31", "El XLSX de un mes llegó a 492 MiB de memoria del contenedor de 512 MiB (incluye caché de archivos); sin OOM.", "Dev"),
    ("PEN-06", "Producción corre la imagen del 16/10 (sin exportación): al desplegar HU33 hacen falta bucket dedicado, SMTP y un worker de la cola exportaciones. No bloquea esta HU.", "Dev"),
    ("OBS-11", "(Ya registrada en HU-18) 96 tests del backend fallan con 409 porque sus fixtures no crean suscripción; no son de exportaciones. Falta un fixture común en tests/conftest.py.", "Dev"),
    ("OBS-25 a 27", "Aceptadas: el criterio actualizado ya no pide pandas ni URL de 24 h, y el XLSX cumple los 120 s.", "QA"),
]

CONCLUSION = ("<b>APTO CON OBSERVACIONES.</b> Los criterios de aceptación se cumplen con 0 defectos del producto y las 5 subtareas pasan a Listo. "
              "<b>Alcance real</b>: local; el bucket y el correo se probaron con emuladores (OBS-28 y OBS-32) y la privacidad del bucket de producción en AWS real, solo lectura. "
              "No se probó el envío por un SMTP en internet ni la carga formal (HT-18), y producción aún no tiene la exportación (PEN-06).")
PENDIENTES = [
    ("Decidir si el S3 emulado y el buzón local cumplen «servicios reales» o pedir repetirlo con Lightsail y un SMTP (OBS-28 y OBS-32).", "PO"),
    ("Confirmar que PP-286 está terminada y pasarla a Listo en Jira (OBS-29).", "Dev"),
    ("Antes de desplegar HU33: bucket dedicado, SMTP en el worker y un worker de la cola exportaciones (PEN-06).", "Dev"),
    ("Medir la memoria del XLSX en Lightsail dentro de HT-18 (OBS-31).", "Dev"),
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
