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
VERSION = "v0.3 (ronda 2, borrador)"
FECHA = "04/11/2026"
RESPONSABLE = "Elliot (JS), Aseguramiento de Calidad (QA)"
ENTORNO = "Local (pytest y Docker) y Lightsail en producción, solo lectura"
RAMAS = "qa-elliot; código revisado en main (commit e1ae09b), que incluye PP-127 y PP-129"
REVISA = "Product Owner"

VEREDICTO = "NO APTO PARA CIERRE"
RESUMEN = ("HT-06 <b>sigue abierta</b>: la subtarea PP-125 no se entregó completa (receptor FTP/TCP, PEN-01), DEF-03 sigue abierto y faltan los tres entornos (PEN-04). "
           "Se cumplen <b>CA2 a CA5</b> con pendientes menores, y CA1 falla. Están <b>cerrados DEF-01, DEF-02 y DEF-08</b>. "
           "Se detectó <b>DEF-09</b> en la ingesta: no entra ningún .dat por un rechazo del FTP. Severidad Media, por confirmar.")

KPIS = [
    ("27 / 33", "casos funcionales<br/>aprobados", "warn"),
    ("2", "defectos abiertos<br/>(3 cerrados)", "warn"),
    ("39 / 46", "pruebas automatizadas<br/>aprobadas (pytest)", "warn"),
    ("3 / 8", "requisitos aprobados<br/>(8 con casos en RTM)", "warn"),
    ("15", "observaciones<br/>(4 para el PO)", "warn"),
]

SUBTAREAS = [
    ("PP-125", "HT-06 · Provisionar Container Service", "Por hacer", "Entrega pendiente: falta el receptor FTP/TCP o que el PO lo descarte (PEN-01, OBS-01). También sigue DEF-03 en docker compose."),
    ("PP-126", "HT-06 · Provisionar base de datos privada", "Listo", "DEF-01 cerrado: la base responde como privada (CP-006 y 007). CP-008 solo pide llevar la guía al repositorio (OBS-47)."),
    ("PP-127", "HT-06 · Provisionar Object Storage", "Listo", "Aprobada con prueba indirecta: el respaldo sobrevivió a tres redeploys (CP-013). Falta ver un .dat real (OBS-51), bloqueado por DEF-09."),
    ("PP-128", "HT-06 · Configurar variables de entorno", "Listo", "DEF-02 cerrado: claves distintas de las del historial en el despliegue activo v21 (CP-023 y 024)."),
    ("PP-129", "HT-06 · Configurar job de respaldo", "Listo", "DEF-08 cerrado; respaldo real de 4,33 MiB en el bucket (CP-343). Vuelve a Por hacer si falla la corrida automática del 08/11 (OBS-51)."),
    ("PP-411", "HT-06 · Validar criterios, flujos y errores", "Listo", "QA terminó: pruebas ejecutadas, evidencias y defectos registrados, e informe adjunto en esta subtarea."),
]

DEFECTOS_PRODUCTO = 5
FALLOS = [
    ("Producto (DEF-01)", "La base de datos de producción era pública (CP-006 y 007).", "Se desplegó con acceso público.", "Cerrado el 02/11: la base ya es privada (RG-01)."),
    ("Producto (DEF-02)", "Contraseña de la base, JWT_SECRET y FTP_CREDENTIAL_KEY en el historial de git.", "containers.json se versionó con valores reales (commit dba450f).", "Cerrado el 04/11: las tres claves se rotaron y ya no coinciden con las del historial (RG-02)."),
    ("Producto (DEF-08)", "El Dockerfile no compilaba (exit 100) y bloqueaba el respaldo de PP-129.", "La imagen base pasó a Debian 13 y el repositorio de PostgreSQL era el de bookworm.", "Cerrado el 04/11: slim-trixie y trixie-pgdg; la imagen se construye (RG-33)."),
    ("Producto (DEF-03)", "docker compose: el worker y el beat no pueden conectarse a la BD local.", "El usuario de la base no coincide con DATABASE_URL.", "Abierto, para desarrollo; sigue en main y dev (RG-03)."),
    ("Producto (DEF-09)", "Ingesta: las conexiones FTP 1 y 3 reciben 530 en cada sondeo; 0 .dat procesados del 01/11 al 04/11.", "Apuntan a Servidor_Prueba, que rechaza el acceso. No apunta a la rotación: el fallo ya existía el 01/11.", "Abierto (HU-05): falta decidir el servidor correcto y si las conexiones son reales."),
    ("Entorno y pruebas", "Docker y AWS CLI faltaban y tres pruebas aprobaban por error (ronda 1).", "Herramientas sin instalar y búsquedas de texto demasiado amplias.", "Se instalaron y se afinaron las pruebas."),
]

COBERTURA = [
    ("CA1", "RQ-HT06-01 · Contenedores por componente en el Container Service", "CP-001 a 005, 340, 343", "Fallido (5/7)", "DEF-03, PEN-01"),
    ("CA2", "RQ-HT06-02 · PostgreSQL en modo privado", "CP-006 a 008", "Parcial (2/3)", "OBS-47"),
    ("CA3", "RQ-HT06-03 · .dat y exportaciones en Object Storage", "CP-009 a 013", "Aprobado (indirecta)", "OBS-05, OBS-48, OBS-51"),
    ("CA4", "RQ-HT06-04 · Respaldo semanal cifrado, 12 meses", "CP-014 a 017, 341, 342", "Aprobado", "OBS-49, OBS-51"),
    ("CA5", "RQ-HT06-05 · Credenciales por variables de entorno", "CP-018 a 024", "Aprobado", "DEF-02 (cerrado)"),
    ("Otros", "RQ-HT06-06 · Tres entornos separados", "CP-025", "Bloqueado", "PEN-04"),
    ("", "RQ-HT06-07 · Umbral de migración a TimescaleDB", "CP-026 y 029", "Parcial (1/2)", "PEN-05"),
    ("", "RQ-HT06-08 · PostGIS y polígonos GeoJSON", "CP-027 y 028", "Parcial (1/2)", "PEN-05"),
]

ESPERADO_TITULO = ""
ESPERADO_NOTA = ""
COLUMNAS = []
ESPERADO = []
ESPERADO_PIE = ""

# (herramienta, ¿se usó?, tipo de prueba, por qué se usó o no, aprobadas, fallidas)
HERRAMIENTAS = [
    ("pytest + pytest-html", "Sí", "Configuración del repositorio", "Revisa Docker, variables, respaldo, entornos y documentación sin servicios.", 15, 7),
    ("pytest + pytest-html", "Sí", "Backend de HT-06", "Prueba el código de PP-127 y PP-129 contra PostgreSQL real.", 24, 0),
    ("AWS CLI + CloudShell", "Sí", "Infraestructura de Lightsail", "Única forma de ver servicio, base, bucket y claves en producción, solo en lectura. Evidencia: lightsail_ronda2_resumen.txt y lightsail_ronda2_complemento.txt.", 9, 0),
    ("Docker + S3 simulado", "Sí", "Build, respaldo y restauración", "Ejecuta el respaldo cifrado de punta a punta. Evidencia: docker_ronda2_respaldo.txt.", 3, 0),
    ("Docker Compose", "Sí", "Arranque local", "Comprueba que api, worker y beat arrancan y se conectan a la base. Evidencia: docker_local_ca1.txt.", 0, 1),
    ("Locust y k6", "No", "Carga y estrés", "HT-06 no pide pruebas de carga.", None, None),
    ("Playwright", "No", "Interfaz (E2E)", "HT-06 no tiene pantallas.", None, None),
    ("OWASP ZAP", "No", "Seguridad web", "Ningún criterio pide un escaneo web.", None, None),
    ("Lighthouse y axe", "No", "Rendimiento y accesibilidad de pantalla", "HT-06 no tiene pantallas.", None, None),
]

# (caso, qué pide, por qué no se aprobó, qué falta, quién lo resuelve, tono)
MOTIVOS_FALLOS = [
    ("CP-005", "Receptor FTP/TCP en su propio contenedor.", "No existe ese contenedor; la ingesta usa sondeo de Celery y nadie confirmó que lo reemplace.", "Que el PO lo decida y, si sigue en alcance, entregarlo (PEN-01).", "PO", None),
    ("CP-008", "Modo privado documentado para el equipo.", "La guía ACCESO_DB_PRIVADA.pdf está fuera del repositorio.", "Llevarla al repositorio y enlazarla desde el README (OBS-47).", "Dev", None),
    ("CP-025", "Desarrollo, staging y producción definidos.", "No hay definición y en Lightsail solo existe producción.", "Definir los tres entornos con sus variables (PEN-04).", "Dev", None),
    ("CP-026", "Umbral de migración a TimescaleDB documentado.", "El umbral de 5 clientes o 3 s no está en la documentación.", "Documentarlo (PEN-05).", "Dev", None),
    ("CP-027", "Restricción de PostGIS documentada.", "PostGIS no se menciona en la documentación.", "Documentarla junto con la de TimescaleDB (PEN-05).", "Dev", None),
]
NOTA_FALLOS = ("<b>Las 7 pruebas pytest fallidas:</b> 5 corresponden a estos casos, una por caso. Las otras 2 son de CP-023 y CP-024, ya aprobados: "
               "las claves viejas siguen en el historial de git, el test no distingue una rotación y la rotación se comprobó en producción.")

EVIDENCIAS = [
    ("pytest-html · suite local de QA", 15, 7, "extracto: resumen y las primeras 12 de 22 filas (los 7 fallos y 5 aprobadas)",
     "qa/03_Evidencias/HT-06/EV-HT-06-INF-04_captura-informe-pytest-ronda2.png", 0.6,
     "EV-HT-06-INF-04. HTML completo: backend/qa/03_Evidencias/HT-06/pytest_ht06_ronda2.html"),
    ("pytest-html · backend de HT-06", 24, 0, "extracto: resumen y las primeras 6 de 24 filas",
     "qa/03_Evidencias/HT-06/EV-HT-06-INF-06_captura-informe-backend.png", 0.6,
     "EV-HT-06-INF-06. HTML completo: backend/qa/03_Evidencias/HT-06/pytest_backend_ht06.html"),
]

OBSERVACIONES = [
    ("OBS-01", "No hay receptor FTP/TCP en contenedor; la ingesta usa sondeo de Celery (PEN-01). ¿Lo reemplaza?", "PO"),
    ("OBS-02", "containers.example.json no refleja producción: dice pangea-app y trae un contenedor frontend.", "Dev"),
    ("OBS-03", "Redis corre dentro del servicio sin volumen: la cola se pierde en cada redeploy.", "Dev"),
    ("OBS-04", "El bucket pangea-storage-prod no tiene versionado.", "Dev"),
    ("OBS-05", "CP-013 aprobado con prueba indirecta; falta la prueba directa con un archivo y un redeploy.", "Dev"),
    ("OBS-06", "Docker y AWS CLI no estaban instalados en QA (ya se instalaron).", "QA"),
    ("OBS-07", "Un solo servicio con 5 contenedores y escala 1: no se escalan por separado.", "PO"),
    ("OBS-08", "Instancia Servidores-ceneris (ajena a Pangea): bases publicadas en 0.0.0.0.", "PO"),
    ("OBS-47", "La documentación de PP-126 a PP-129 está fuera del repositorio.", "Dev"),
    ("OBS-48", "Exportaciones y respaldos usan dos buckets distintos (ceneris-pangea-archivos-prod y pangea-storage-prod).", "PO"),
    ("OBS-49", "Si el respaldo falla, solo queda en el log: no hay alerta.", "Dev"),
    ("OBS-50", "El .dat se archiva como texto UTF-8; la imagen worker.19 no indica su commit.", "Dev"),
    ("OBS-51", "Por confirmar: respaldo automático del 08/11/2026 y primer .dat real en datos-crudos/ (bloqueado por DEF-09).", "QA"),
    ("OBS-52", "api, beat y worker-exportaciones tienen credenciales que no necesitan.", "Dev"),
    ("OBS-53", "No se ha restaurado un respaldo real: solo se probó en local, con 500 filas.", "Dev"),
    ("DEF-01", "Cerrados DEF-01, DEF-02 y DEF-08: base pública, claves en el historial de git y Dockerfile que no compilaba.", "QA"),
    ("DEF-03", "Abierto (Media): usuario de la base distinto al de DATABASE_URL en docker compose.", "Dev"),
    ("DEF-09", "Abierto (Media, por confirmar; HU-05): FTP con 530. Crítica si son dataloggers reales; Baja si son de prueba.", "Dev"),
    ("PEN-04", "No entregados: PEN-04 (tres entornos, bloquea el cierre) y PEN-05 (documentación del umbral y de PostGIS).", "Dev"),
]

CONCLUSION = "<b>NO APTO PARA CIERRE.</b> HT-06 sigue abierta hasta resolver los pendientes que bloquean el cierre."
AVANCE = [("Aprobados", 27, "ok"), ("Fallido", 1, "fail"), ("Bloqueados", 5, "warn")]

ESTADO_FINAL = [
    ("Subtareas", "5 de 6 en Listo", "warn", "PP-125 en Por hacer. PP-127 en Listo con prueba indirecta."),
    ("CA1 · Contenedores", "Fallido", "fail", "Falta el receptor FTP/TCP (PEN-01) y sigue DEF-03."),
    ("CA2 a CA5", "Cumplen", "ok", "Con pendientes menores; CA3 con prueba indirecta."),
    ("Defectos de HT-06", "3 cerrados · 1 abierto", "warn", "Cerrados DEF-01, DEF-02 y DEF-08. Abierto DEF-03."),
    ("Ingesta (HU-05)", "1 abierto", "warn", "DEF-09 no es de HT-06, pero impide comprobar un .dat real."),
]

# (qué no se probó, estado, por qué, qué falta)
NO_PROBADO = [
    ("Restaurar un respaldo real", "Parcial", "Se restauró solo en local, con 500 filas (CP-341).", "Restaurar uno real en una base de prueba (OBS-53)."),
    ("Persistencia con un .dat", "Parcial", "Se comprobó con un respaldo, no con un .dat (CP-013).", "Subir un archivo de prueba y redesplegar (OBS-05)."),
    ("Archivar un .dat real", "Bloqueado", "No entra ninguno por el fallo FTP (DEF-09).", "Corregir DEF-09 y ver el primer .dat (OBS-51)."),
    ("Entornos de desarrollo y staging", "Bloqueado", "No existen; solo hay producción.", "Definirlos y crearlos (PEN-04)."),
    ("Carga y estrés", "No aplica", "HT-06 no pide estas pruebas.", "Nada."),
]
LEYENDA_NO_PROBADO = "<b>Parcial:</b> se probó solo una parte. <b>Bloqueado:</b> no se puede probar hasta resolver lo indicado. <b>No aplica:</b> esta HT no lo pide."

# (pendiente, responsable, ¿bloquea el cierre de HT-06?)
PENDIENTES = [
    ("Decidir si el receptor FTP/TCP sigue o lo reemplaza el sondeo de Celery (OBS-01, PEN-01).", "PO", "Sí"),
    ("Corregir el usuario de la base en docker-compose.yml (DEF-03).", "Dev", "Sí"),
    ("Definir los tres entornos (PEN-04).", "Dev", "Sí"),
    ("Decidir el servidor FTP y corregir o desactivar las conexiones 1 y 3 (DEF-09).", "Dev", "No"),
    ("Documentar umbral y PostGIS, y llevar la documentación de PP-126 a PP-129 al repositorio (PEN-05, OBS-47).", "Dev", "No"),
    ("Subir un archivo de prueba y redesplegar pangea-api (OBS-05).", "Dev", "No"),
    ("Restaurar un respaldo real en una base de prueba y comprobar sus datos (OBS-53).", "Dev", "No"),
    ("Decidir si exportaciones, respaldos y .dat usan un solo bucket (OBS-48).", "PO", "No"),
    ("Mirar el bucket el 08/11/2026 y cuando entre el primer .dat (OBS-51).", "QA", "No"),
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
S_H_LIBRE = st("hlibre", fontName=FB, fontSize=11.5, leading=14, textColor=NAVY, spaceBefore=7, spaceAfter=3)
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
        ["Herramienta", "¿Se usó?", "Tipo de prueba", "Por qué se usó o no", "Resultado"],
        [[P(h, S_CELL_B), badge(u, "ok" if u == "Sí" else "gray"), t, pq,
          badge("No aplica", "gray") if a is None else badge(f"{a} aprobadas · {f} fallidas", "fail" if f > 0 else "ok")]
         for h, u, t, pq, a, f in HERRAMIENTAS],
        [2.9 * cm, 1.5 * cm, 2.9 * cm, CONTENT_W - 11.1 * cm, 3.8 * cm],
    ))
    s.append(P("Casos bloqueados: por qué y qué falta", S_H))
    s.append(table(
        ["Caso", "Qué pide", "Por qué no se aprobó", "Qué falta", "Resuelve"],
        [[P(c, S_CELL_B), q, p, f, badge(r, t)] for c, q, p, f, r, t in MOTIVOS_FALLOS],
        [1.5 * cm, 3.6 * cm, CONTENT_W - 12.0 * cm, 5.0 * cm, 1.9 * cm],
    ))
    s.append(Spacer(1, 3))
    s.append(P(NOTA_FALLOS, S_BODY))

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
    bloque = [P("7. Conclusión y pendientes", S_H), P(CONCLUSION, S_BODY), Spacer(1, 4), barra_avance(AVANCE), Spacer(1, 3),
              table(["Tema", "Estado", "Qué significa"],
                    [[P(t, S_CELL_B), badge(e, c), d] for t, e, c, d in ESTADO_FINAL],
                    [3.3 * cm, 3.1 * cm, CONTENT_W - 6.4 * cm]),
              Spacer(1, 3),
              table(["No se probó", "Estado", "Por qué", "Qué falta"],
                    [[t, badge(e), d, f] for t, e, d, f in NO_PROBADO],
                    [3.9 * cm, 1.9 * cm, CONTENT_W - 10.4 * cm, 4.6 * cm]),
              Spacer(1, 2), P(LEYENDA_NO_PROBADO, S_CELL),
              Spacer(1, 3),
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
    if paginas > 3:
        print("AVISO: pasa de 3 páginas. Acorta textos, reduce filas del extracto o el ancho de las capturas.")


if __name__ == "__main__":
    main()
