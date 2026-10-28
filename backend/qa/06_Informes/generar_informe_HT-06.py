"""Plantilla del informe PDF de QA por HU (A4, máximo 3 páginas). Formato fijo para cualquier proyecto.

Cómo se usa:
  1. Copia este archivo a QA/06_Informes/generar_informe_<HU>.py
  2. Rellena SOLO el bloque «DATOS DEL INFORME» (reemplaza todo lo que está entre [corchetes]).
     No cambies nada debajo de la línea «MOTOR DEL INFORME»: ahí están el estilo, los colores y el orden.
  3. Ejecútalo desde la raíz del repo:
       backend/.venv/Scripts/python.exe QA/06_Informes/generar_informe_<HU>.py
     Sale QA/06_Informes/Informe_QA_<HU>_<aaaa-mm-dd>.pdf
     (opcional: pasa otra ruta de salida como primer argumento).

Las capturas se generan antes con Plantilla_Capturas_Evidencias.mjs (recortadas y a doble resolución).

Valores de estado que se pintan con color automáticamente:
  verde : Listo, Aprobado, Permitido, Sí, Cumple, APTO, APTO CON OBSERVACIONES
  ámbar : En curso, Bloqueado, Observación, PO
  rojo  : Fallido, No cumple, Defecto, NO APTO
  gris / azul neutro : Por hacer, Pendiente, Denegado..., Oculto..., No, Dev, QA, No aplica
"""
import sys
from pathlib import Path

# =====================================================================
# DATOS DEL INFORME  (lo único que se edita para cada HU)
# =====================================================================

# Nombre del proyecto: por defecto sale del nombre del repositorio (remoto origin o, si no hay, la carpeta)
# (plataforma-san-martin -> "Plataforma San Martin"). Escríbelo a mano solo si debe verse distinto.
PROYECTO = None
TABLERO = "PP"
HU = "HT-06"
NOMBRE_HU = "Estrategia de despliegue e infraestructura en AWS Lightsail"
SUBTAREA_QA = "PP-411"
VERSION = "v0.1 (borrador)"
FECHA = "28/10/2026"
RESPONSABLE = "Elliot (JS), Aseguramiento de Calidad (QA)"
ENTORNO = "Local (pytest y docker compose) y Lightsail en producción, solo lectura"
RAMAS = "qa-elliot (commit bc5b89a); el código de HT-06 está en dev y main"
REVISA = "Product Owner"

VEREDICTO = "NO APTO"
RESUMEN = ("Informe en <b>borrador</b>, con pendientes a la vista. No se cumplen CA2, CA3, CA4 ni CA5, y CA1 solo en parte. "
           "Hay <b>3 defectos del producto</b> (2 críticos: base de datos pública y secretos en el historial de git) y "
           "<b>5 entregas pendientes</b> que no son defectos. <b>4 observaciones necesitan decisión del PO.</b>")

KPIS = [
    ("11 / 29", "casos funcionales<br/>aprobados", "fail"),
    ("3", "defectos<br/>del producto", "fail"),
    ("8 / 22", "pruebas automatizadas<br/>aprobadas (pytest)", "fail"),
    ("8 / 8", "requisitos cubiertos<br/>(RTM)", "ok"),
    ("8", "observaciones<br/>(4 para el PO)", "warn"),
]

SUBTAREAS = [
    ("PP-125", "HT-06 · Provisionar Container Service", "Listo", "Servicio pangea-api con api, worker, beat y redis (CP-003). Falta decidir el receptor FTP/TCP (OBS-01)."),
    ("PP-126", "HT-06 · Provisionar base de datos privada", "Por hacer", "Defecto DEF-01: la base es pública y responde desde internet (CP-006 a 008)."),
    ("PP-127", "HT-06 · Provisionar Object Storage", "Por hacer", "Entrega pendiente PEN-02, no es defecto: el bucket existe pero la app no lo usa (CP-009 a 013)."),
    ("PP-128", "HT-06 · Configurar variables de entorno", "Por hacer", "Defecto DEF-02: secretos en el historial de git sin rotar (CP-023 y 024)."),
    ("PP-129", "HT-06 · Configurar job de respaldo", "Por hacer", "Entrega pendiente PEN-03, no es defecto: no existe la tarea de respaldo (CP-014 a 017)."),
    ("PP-411", "HT-06 · Validar criterios, flujos y errores", "Listo", "QA terminó: pruebas ejecutadas, evidencias y defectos registrados, e informe adjunto en esta subtarea."),
]

DEFECTOS_PRODUCTO = 3
FALLOS = [
    ("Entorno (Docker)", "Docker y AWS CLI no estaban instalados y el motor de Docker no arrancaba.", "Faltaban las herramientas y WSL 2 estaba desactualizado.", "Se instalaron y se ejecutó wsl --update."),
    ("Pruebas (pytest)", "El informe HTML mostraba fragmentos de credenciales dentro de los mensajes de error.", "Las aserciones imprimían el valor encontrado.", "Ahora solo indican si hay exposición; 0 coincidencias de credenciales en el HTML."),
    ("Pruebas (pytest)", "Tres pruebas aprobaban por error (modo privado, entornos y umbral).", "Búsquedas de texto demasiado amplias.", "Se afinaron y ahora fallan con razón."),
    ("Producto (DEF-01 a DEF-03)", "Base pública, secretos en git y worker sin acceso a la BD en docker compose.", "Ver Registro de Defectos.", "Sin resolver: pasan a desarrollo (ronda 1)."),
]

COBERTURA = [
    ("CA1", "RQ-HT06-01 · Contenedores por componente en el Container Service", "CP-001 a 005", "Fallido", "DEF-03, OBS-01"),
    ("CA2", "RQ-HT06-02 · PostgreSQL en modo privado", "CP-006 a 008", "Fallido", "DEF-01"),
    ("CA3", "RQ-HT06-03 · .dat y exportaciones en Object Storage", "CP-009 a 013", "Bloqueado", "PEN-02, OBS-05"),
    ("CA4", "RQ-HT06-04 · Respaldo semanal cifrado, 12 meses", "CP-014 a 017", "Bloqueado", "PEN-03"),
    ("CA5", "RQ-HT06-05 · Credenciales por variables de entorno", "CP-018 a 024", "Fallido", "DEF-02"),
    ("Otros", "RQ-HT06-06 · Tres entornos separados", "CP-025", "Bloqueado", "PEN-04"),
    ("", "RQ-HT06-07 · Umbral de migración a TimescaleDB", "CP-026 y 029", "Parcial (1/2)", "PEN-05"),
    ("", "RQ-HT06-08 · PostGIS y polígonos GeoJSON", "CP-027 y 028", "Parcial (1/2)", "PEN-05"),
]

ESPERADO_TITULO = ""
ESPERADO_NOTA = ""
COLUMNAS = []
ESPERADO = []
ESPERADO_PIE = ""

HERRAMIENTAS = [
    ("pytest + pytest-html", "Configuración y repositorio (estático)", "Es la herramienta del backend; revisa Docker, variables, respaldo, entornos y documentación sin servicios.", 8, 14),
    ("AWS CLI + CloudShell", "Infraestructura de Lightsail (solo lectura)", "Es la única forma de ver la configuración real: servicio, base, bucket y snapshots.", 3, 2),
    ("Docker Compose", "Integración local", "Comprueba que api, worker y beat arrancan en contenedores separados.", 0, 1),
]
HERRAMIENTAS_NOTA = ("Casos bloqueados: 12, a la espera de entregas pendientes (no cuentan como aprobados ni como defectos). "
                     "Descartadas: Locust y k6 (no hubo carga; el umbral de 3 s solo está como documento), Playwright (HT-06 no tiene pantallas), "
                     "OWASP ZAP, Lighthouse y axe (no se piden). Lightsail y Docker son manuales y no generan HTML: su evidencia son los registros "
                     "lightsail_verificacion_resumen.txt y docker_local_ca1.txt.")

EVIDENCIAS = [
    ("pytest-html", 8, 14, "extracto: resumen y las 22 filas, sin el detalle de los fallos",
     "qa/03_Evidencias/HT-06/EV-HT-06-INF-02_captura-informe-pytest.png", 0.78,
     "EV-HT-06-INF-01. HTML completo: backend/qa/03_Evidencias/HT-06/pytest_ht06_local.html"),
]

OBSERVACIONES = [
    ("OBS-01", "El receptor FTP/TCP no existe como contenedor; la ingesta usa sondeo de Celery. ¿Lo reemplaza?", "PO"),
    ("OBS-02", "containers.example.json dice pangea-app y el servicio real es pangea-api.", "Dev"),
    ("OBS-03", "Redis corre dentro del servicio sin volumen: la cola se pierde en cada redeploy.", "Dev"),
    ("OBS-04", "El bucket pangea-storage-prod no tiene versionado.", "Dev"),
    ("OBS-05", "Redeploy y persistencia sin probar: producción es compartida y el servidor de pruebas está en curso.", "PO"),
    ("OBS-06", "Docker y AWS CLI no estaban instalados en el equipo de QA (ya se instalaron).", "QA"),
    ("OBS-07", "Un solo servicio con 4 contenedores y escala 1: no se escalan por separado.", "PO"),
    ("OBS-08", "Instancia Servidores-ceneris (ajena a Pangea): bases publicadas en 0.0.0.0 y 45 actualizaciones.", "PO"),
]

CONCLUSION = ("<b>NO APTO (borrador).</b> No se cumplen CA2, CA3, CA4 ni CA5, y CA1 se cumple en parte (falta el receptor FTP/TCP). "
              "Hay 3 defectos del producto y 5 entregas pendientes que no son defectos. Estado propuesto: PP-125 Listo; PP-126, PP-127, "
              "PP-128 y PP-129 Por hacer; PP-411 Listo (QA terminó sus pruebas y adjunta este informe). <b>Alcance real</b>: no se probó el redeploy ni la "
              "persistencia, la restauración de un respaldo, la carga ni los entornos de desarrollo y staging (no existen); Lightsail se revisó solo en lectura.")
PENDIENTES = [
    ("Rotar la contraseña de la base, JWT_SECRET y FTP_CREDENTIAL_KEY (DEF-02, PP-128).", "Dev"),
    ("Pasar la base a modo privado tras revisar el VPC peering (DEF-01, PP-126).", "Dev"),
    ("Entregar Object Storage en la app y el respaldo semanal (PEN-02 y PEN-03; PP-127 y PP-129).", "Dev"),
    ("Corregir docker-compose.yml (DEF-03).", "Dev"),
    ("Decidir sobre el receptor FTP/TCP y probar el redeploy en el servidor de pruebas (OBS-01, OBS-05).", "PO"),
    ("Cambiar los estados de las subtareas en Jira según la sección 1.", "QA"),
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
    return ROOT / "QA" / "06_Informes" / f"Informe_QA_{HU}_{fecha_iso}.pdf"


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
