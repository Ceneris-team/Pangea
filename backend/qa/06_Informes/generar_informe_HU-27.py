import sys
from pathlib import Path
PROYECTO = 'Pangea'
TABLERO = 'PP'
HU = 'HU-27'
NOMBRE_HU = 'Listar alarmas'
SUBTAREA_QA = 'PP-417'
VERSION = 'v1.0'
FECHA = '04/11/2026'
RESPONSABLE = 'JS · Aseguramiento de Calidad'
ENTORNO = 'Local · PostgreSQL Docker, Edge, API real y sesión real'
RAMAS = 'origin/dev 5430e91 · copia aislada Pangea-pp417'
REVISA = 'Product Owner'
VEREDICTO = 'APTO CON OBSERVACIONES'
RESUMEN = 'Los tres criterios y los detalles del listado se verificaron. <b>13/13 casos QA aprobados; 0 defectos del producto.</b> OBS-59 solicita precisar el alcance de las acciones: Gestionar se muestra como disponible próximamente.'
KPIS = [('13/13', 'casos QA<br/>aprobados', 'ok'), ('0', 'defectos abiertos<br/>0 cerrados', 'ok'), ('50', '44 API + 6 UI<br/>aprobadas', 'ok'), ('6/6', 'requisitos<br/>aprobados', 'ok'), ('2', 'observaciones<br/>para el PO', 'warn')]
SUBTAREAS = [('PP-222', 'Diseñar vista listado de alarmas', 'Listo', 'Tabla, columnas, estados y paginado verificados. Alcance de acciones: OBS-59.'), ('PP-223', 'Consultar alarmas por usuario', 'Listo', 'API filtra por dueño; no se muestran alarmas ajenas.'), ('PP-224', 'Implementar filtro por estado', 'Listo', 'Activa/Inactiva, limpieza y búsqueda combinada correctas.'), ('PP-417', 'Validar criterios, flujos y errores', 'Listo', 'QA terminó: pruebas ejecutadas, evidencias y defectos registrados, e informe adjunto en esta subtarea.')]
DEFECTOS_PRODUCTO = 0
FALLOS = [('Entorno · OBS-60', 'La conexión de BD por defecto falla.', 'PostgreSQL de QA escucha en 55432; el valor por defecto usa 5432.', 'Se fijó TEST_DATABASE_URL al contenedor QA. Un control con BD por defecto conserva el error en HTML.'), ('Preparación QA', '7 errores iniciales de fixtures y login 422.', 'Pruebas fuera de tests/ y correos reservados .test.', 'Se ubicó la copia bajo tests/ y se corrigieron las cuentas locales; las corridas finales pasan.')]
COBERTURA = [('CA-01', 'RQ-HU27-01 · Cinco columnas y alarmas propias', 'CP-469; RG-39/40', 'Aprobado', 'OBS-59'), ('CA-02', 'RQ-HU27-02 · Estado', 'CP-467,470', 'Aprobado', '—'), ('CA-03', 'RQ-HU27-03 · Nombre', 'CP-466,471,473', 'Aprobado', '—'), ('Extra', 'RQ-HU27-04 · Paginación de 10', 'CP-462 a 465,472', 'Aprobado', '—'), ('Extra', 'RQ-HU27-05 · Sesión y dueño', 'CP-468,469; RG-39/40', 'Aprobado', '—'), ('Extra', 'RQ-HU27-06 · Vacío y Crear alarma', 'CP-474', 'Aprobado', '—')]
ESPERADO = []
ESPERADO_TITULO = ''
ESPERADO_NOTA = ''
COLUMNAS = []
ESPERADO_PIE = ''
HERRAMIENTAS = [('pytest + pytest-html', 'Sí', 'API y seguridad básica', '37 existentes de HU27/HU28 + 7 casos QA; BD real.', 44, 0), ('Playwright Edge', 'Sí', 'UI E2E real', 'Tabla, filtro, búsqueda, paginación y usuario sin alarmas.', 6, 0), ('pytest regresión', 'Sí', 'Dos configuraciones de negocio', 'Regla de suscripción por defecto: 44/44. PLAN_LIMITS_REQUIRE_SUBSCRIPTION=false: 44/44. BD 55432 en ambas.', 44, 0), ('Node test runner', 'Sí', 'Regresión frontend', 'Suite existente: 47/47. Evidencia: frontend_regresion.log.', 47, 0), ('Locust, k6, ZAP, axe', 'No', 'Carga y escaneo', 'Sin requisitos de carga, estrés, escaneo o accesibilidad.', None, None)]
HERRAMIENTAS_NOTA = 'OBS-60: con la conexión de BD por defecto, un control de test_alarmas.py da 1 error de entorno; no se completó la suite con esa conexión. Las cifras 44/44 no representan toda la suite de backend.'
MOTIVOS_FALLOS = []
NOTA_FALLOS = 'Sin pruebas finales fallidas con BD de QA. Primer HTML de preparación: pytest_preparacion.html (37 aprobadas, 7 errores de fixtures).'
EVIDENCIAS = [('pytest-html', 44, 0, 'extracto: primeras 10 de 44 filas', 'qa/03_Evidencias/HU-27/pytest.png', 1.0, 'EV-CP-462 a 468. HTML: backend/qa/03_Evidencias/HU-27/pytest_hu27.html.'), ('Playwright Edge', 6, 0, 'las seis pruebas completas', 'qa/03_Evidencias/HU-27/playwright.png', 0.75, 'EV-CP-469 a 474. HTML: backend/qa/03_Evidencias/HU-27/playwright/index.html.')]
OBSERVACIONES = [('OBS-59', 'PP-222: Gestionar es visual y aún no opera. CA1 exige acciones, sin definir operaciones. PO confirma si editar/eliminar/activar corresponden a otra HU o deben agregarse aquí.', 'PO'), ('OBS-60', 'Error con BD localhost:5432. QA usó PostgreSQL 55432; ambas reglas de suscripción dan 44/44. Aceptar ese entorno o reparar la conexión por defecto.', 'PO')]
CONCLUSION = '<b>APTO CON OBSERVACIONES.</b> El listado cumple el alcance explícito; el PO confirma las operaciones de Gestionar.'
AVANCE = [('Aprobados', 13, 'ok'), ('Fallidos', 0, 'fail'), ('Bloqueados', 0, 'warn')]
ESTADO_FINAL = [('Subtareas', '4 en Listo', 'ok', 'Estados propuestos; actualizar en Jira.'), ('Criterios', '3 de 3 cumplen', 'ok', 'También paginado, aislamiento y estado vacío.'), ('Regresión', '44/44 y 47/47', 'ok', '44 API en ambas reglas de suscripción; 47 frontend. BD de QA.'), ('Documentos', 'v0.15', 'info', '5 documentos ampliados. Fórmulas para recálculo al abrir.')]
NO_PROBADO = [('Operaciones de Gestionar', 'Parcial', 'Sin definición funcional en los CA', 'Decisión del PO · OBS-59'), ('Backend completo y BD por defecto', 'Parcial', 'Regresión acotada a alarmas; BD por defecto da error', 'Reparar entorno · OBS-60'), ('Carga y producción', 'No aplica', 'Alcance aprobado: local funcional', 'Sin requisito')]
LEYENDA_NO_PROBADO = 'Parcial: cobertura limitada al alcance descrito. No aplica: fuera del alcance aprobado.'
PENDIENTES = [('PP-222 · OBS-59: confirmar las operaciones de Gestionar.', 'PO', 'No'), ('PP-417 · OBS-60: aceptar BD QA o reparar la conexión por defecto.', 'PO', 'No'), ('Cambiar estados en Jira según la sección 1.', 'QA', 'No')]
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
    if paginas > 4:
        print("AVISO: pasa de 4 páginas. Acorta textos, reduce filas del extracto o el ancho de las capturas.")


if __name__ == "__main__":
    main()
