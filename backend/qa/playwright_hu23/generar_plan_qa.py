"""PP-426 (HU-23 Listar paneles) ronda 1: amplía el plan de pruebas (Word) de v0.8 a v0.9.

Ejecutar desde backend/: venv/Scripts/python.exe qa/playwright_hu23/generar_plan_qa.py
Clona los párrafos y filas de la HU-15 (el último bloque del plan) para conservar el formato.
"""
import copy
from pathlib import Path

import docx
from docx.text.paragraph import Paragraph

QA = Path(__file__).resolve().parents[1]
SRC = QA / "01_Plan_de_Pruebas" / "Pangea_Plan_de_Pruebas_v0.8.docx"
DST = QA / "01_Plan_de_Pruebas" / "Pangea_Plan_de_Pruebas_v0.9.docx"

d = docx.Document(SRC)
P = list(d.paragraphs)


def hallar(prefijo, desde=0):
    for i in range(desde, len(P)):
        if P[i].text.startswith(prefijo):
            return P[i]
    raise KeyError(prefijo)


def clonar_despues(ref, textos):
    """Inserta, después de `ref`, una copia de `ref` con los textos dados, uno por cada run (los runs sobrantes se quitan)."""
    nuevo = copy.deepcopy(ref._p)
    ref._p.addnext(nuevo)
    par = Paragraph(nuevo, ref._parent)
    if isinstance(textos, str):
        textos = [textos]
    for i, run in enumerate(par.runs):
        if i < len(textos):
            run.text = textos[i]
        else:
            run._r.getparent().remove(run._r)
    return par


def poner_celda(celda, texto):
    par = celda.paragraphs[0]
    runs = par.runs
    if runs:
        runs[0].text = texto
        for r in runs[1:]:
            r._r.getparent().remove(r._r)
    else:
        par.add_run(texto)


def clonar_fila(tabla, modelo, textos):
    nueva = copy.deepcopy(modelo._tr)
    ultima = tabla.rows[-1]
    ultima._tr.addnext(nueva)
    fila = tabla.rows[-1]
    for celda, texto in zip(fila.cells, textos):
        poner_celda(celda, texto)
    return fila


# ----------------------------- portada y resúmenes -----------------------------
sub = hallar("Pangea · Cómo se comprueba")
sub.runs[0].text = sub.runs[0].text.replace(
    " y la exportación en background cumple la HU-15",
    ", la exportación en background cumple la HU-15 y el listado de paneles cumple la HU-23")
assert "HU-23" in sub.text

p_existe = hallar("HU-15 · Lo que existe y lo que falta")
clonar_despues(p_existe, "HU-23 · Lo que existe y lo que falta. Revisión del 02/11/2026 sobre la rama qa-elliot (commit f9b939a). Existe en dev el listado de paneles (código de Jareth, commit 68e3089 y anteriores): en «Tableros personalizables», la tabla con nombre, proyectos, fecha de creación y las acciones Abrir, Duplicar, Compartir con empresa, Editar y Eliminar; el buscador por nombre con retardo de 400 ms; el orden por fecha de creación descendente; el mensaje «Aún no tienes paneles creados» con el botón «Crear panel»; y los endpoints GET /paneles (con ?busqueda=), GET /paneles/{id} y /contenido en routers/panel.py. El historial de git no tiene commits con los códigos PP-210, PP-211 ni PP-212: el código llegó dentro del commit 68e3089. Hallazgos: la búsqueda trata «%» y «_» como comodines (DEF-05); el listado incluye los paneles que otros usuarios compartieron con la empresa aunque la HU dice que no se comparten en v1.0 (OBS-33); y con un proyecto activo el mensaje sin paneles cambia de texto (OBS-34). No falta nada más de la HU.")

p_res = hallar("Casos de prueba: HU-15")
clonar_despues(p_res, "Casos de prueba: HU-23 37 de 40 aprobados en la ronda 1 (28 de API con pytest y 12 de UI con Playwright en Edge); regresión de paneles 55 de 55. Defectos del producto: 1 (DEF-05, menor: la búsqueda trata «%» y «_» como comodines; lo reprueba RG-25). Observaciones: OBS-33 y OBS-34 (las decide el PO). Subtareas: PP-210 y PP-212 en Listo, PP-211 En curso por DEF-05 y PP-426 (QA) en Listo.")

p_obj = hallar("Para HU-15 define cómo se comprueba")
clonar_despues(p_obj, "Para HU-23 define cómo se comprueba que el Cliente Final, al entrar en «Tableros personalizables», ve todos sus paneles con nombre, fecha de creación y acciones, ordenados del más reciente al más antiguo; que cada usuario ve solo sus propios paneles; que al seleccionar el nombre se abre el panel con sus ubicaciones y widgets; que el buscador filtra por nombre o fragmento sin distinguir mayúsculas y sin tratar «%» ni «_» como comodines; y que sin paneles aparece «Aún no tienes paneles creados» con el botón «Crear panel» visible y habilitado.")

# ----------------------------- alcance: entra -----------------------------
t_hu15 = hallar("HU-15 · Pipeline de exportación en background")
ultimo_hu15 = hallar("Privacidad real, correo e integración (CP-219 a CP-221)")
nuevo_tit = copy.deepcopy(t_hu15._p)
ultimo_hu15._p.addnext(nuevo_tit)
tit = Paragraph(nuevo_tit, t_hu15._parent)
tit.runs[0].text = "HU-23 · Listar paneles"
item = hallar("Asíncrono (CA1)")
ref = tit
for texto in [
    "Listado (CA1): nombre, fecha de creación y acciones de todos los paneles del usuario; por API (GET /paneles) y en pantalla.",
    "Abrir (CA2): seleccionar el nombre o «Abrir» abre el panel con sus ubicaciones y widgets; id inexistente (404) o no numérico (422).",
    "Búsqueda (CA3): por nombre o fragmento, sin distinguir mayúsculas, vacía, sin resultados, con acento, con caracteres especiales (%, _, comillas, SQL y HTML) y con 5 000 caracteres.",
    "Detalle de la conversación: aislamiento entre usuarios y sedes, orden por fecha descendente y el estado sin paneles con «Crear panel»; los paneles compartidos con la empresa solo se documentan (OBS-33).",
    "Errores y roles: 401, 403 (sin permiso sobre Tableros) y Lectura permitida.",
]:
    nuevo = copy.deepcopy(item._p)
    ref._p.addnext(nuevo)
    ref = Paragraph(nuevo, item._parent)
    ref.runs[0].text = texto
    for r_ in ref.runs[1:]:
        r_._r.getparent().remove(r_._r)

# regresión común
reg = hallar("Regresión: se reejecutan las suites")
reg.runs[-1].text = reg.runs[-1].text.rstrip().rstrip(".") + "; para HU-23, la suite de paneles (test_paneles.py)."

# ----------------------------- alcance: queda fuera -----------------------------
fuera_hu15 = [p for p in P if p.text.startswith("Seguridad web, rendimiento de pantalla y accesibilidad: se descartan OWASP ZAP, Lighthouse y axe porque ningún criterio")][-1]
t_fuera = hallar("HU-15", P.index(hallar("Queda fuera")))
item_fuera = hallar("Un bucket de exportaciones y un SMTP en internet")
nuevo = copy.deepcopy(t_fuera._p)
fuera_hu15._p.addnext(nuevo)
tit_f = Paragraph(nuevo, t_fuera._parent)
tit_f.runs[0].text = "HU-23"
ref = tit_f
for texto in [
    "Producción y flujo multiempresa (rol Lector con proyectos asignados): solo se prueba en local (OBS-18).",
    "Mensaje con proyecto activo: se revisó en el código y no se ejecutó en pantalla (OBS-34).",
    "Mapa de estaciones del panel abierto: en local falta la clave de Google Maps (VITE_GOOGLE_MAPS_API_KEY); no se evaluó el mapa.",
    "Carga y estrés, OWASP ZAP, Lighthouse y axe: la HU no los pide; se descartan Locust, k6, ZAP, Lighthouse y axe.",
]:
    nuevo = copy.deepcopy(item_fuera._p)
    ref._p.addnext(nuevo)
    ref = Paragraph(nuevo, item_fuera._parent)
    ref.runs[0].text = texto
    for r_ in ref.runs[1:]:
        r_._r.getparent().remove(r_._r)

# ----------------------------- estrategia -----------------------------
cob = hallar("Cobertura agregada por QA (HU-15)")
clonar_despues(cob, ["Cobertura agregada por QA (HU-23): ", "los tests existentes de paneles (test_paneles.py) cubren el listado básico, el orden, el aislamiento entre usuarios y la búsqueda simple, pero no el formato de la fecha, el listado sin paginar, la búsqueda con acento, comodines, comillas y SQL, el acceso entre sedes, el contenido del panel abierto, el 401 ni el comportamiento de los paneles compartidos. QA agregó 28 pruebas de pytest (test_hu23_qa.py) y 12 recorridos de Playwright (hu23.spec.mjs) con tres cuentas locales: el Cliente Final del seed, un usuario sin paneles y otro usuario."])

org = hallar("HU-15: pytest corre sobre los tests existentes de exportaciones")
clonar_despues(org, "HU-23: pytest vive en backend/qa/03_Evidencias/HU23 (test_hu23_qa.py, 28 tests) y reutiliza los fixtures de tests/; Playwright vive en backend/qa/playwright_hu23 (hu23.spec.mjs, 12 tests) y corre contra la app local (backend en 8000 contra pangea_e2e y Vite en 5173). Usa tres cuentas: cliente@pangea-dev.com del seed y qa.sinpaneles@ y qa.otro@ pangea-dev.com, creadas solo para la prueba; se eliminan al terminar.")

no_auto = hallar("HU-15 · AWS y SMTP en internet")
clonar_despues(no_auto, "HU-23 · Carga, estrés, seguridad web y accesibilidad: no se automatizan; la HU no tiene esos requisitos. Producción y cuentas por cliente: OBS-18.")

datos = hallar("HU-15: los datos son los del seed del proyecto")
clonar_despues(datos, "HU-23: los datos son los del seed del proyecto (cliente@pangea-dev.com con los paneles de QA de rondas anteriores) y los que crean los tests y los recorridos (paneles «QA …»). Para el aislamiento y el usuario sin paneles se crearon en pangea_e2e dos cuentas locales (qa.sinpaneles@ y qa.otro@ pangea-dev.com) y el panel «QA Panel ajeno»; se eliminan al terminar. Ninguna contraseña ni clave se escribe en los registros.")

h9 = hallar("9 · Verificación de criterios de aceptación")
h9.runs[0].text = h9.runs[0].text.replace("PP-400 y PP-408)", "PP-400, PP-408 y PP-426)")
assert "PP-426" in h9.text

# ----------------------------- tablas -----------------------------
T = d.tables
fila_de = {
    "Entregable": ("PP-408 · HU-15 · Pipeline de exportación en background con Celery", "PP-408 · HU-15 · Pipeline de exportación en background con Celery · PP-426 · HU-23 · Listar paneles"),
    "Versión": ("0.8", "0.9"),
    "Fecha": ("ronda 2 de HU-15 con los criterios actualizados", "ronda 2 de HU-15 con los criterios actualizados y ronda 1 de HU-23 (PP-426)"),
    "Subtareas": ("PP-408 (verificar los criterios de aceptación y registrar evidencias)", "PP-408 (verificar los criterios de aceptación y registrar evidencias) · HU-23: PP-210, PP-211 y PP-212 (desarrollo, según Jira) · PP-426 (validar criterios de aceptación, flujos y errores; registrar evidencias y defectos)"),
}
for fila in T[0].rows:
    clave = fila.cells[0].text.strip()
    if clave in fila_de:
        viejo, nuevo_txt = fila_de[clave]
        celda = fila.cells[1]
        texto = celda.text
        assert viejo in texto, (clave, texto)
        poner_celda(celda, texto.replace(viejo, nuevo_txt))

t1 = T[1]
m = t1.rows[-1]
for textos in [
    ("HU-23", "API (listado, orden, aislamiento, búsqueda, abrir panel y errores)", "pytest + pytest-html", "Local, BD de test en Docker", "28", "26 aprobadas · 2 fallidas (DEF-05)"),
    ("HU-23", "E2E de UI como Cliente Final", "Playwright (Edge)", "Local, BD pangea_e2e, API en 8000 y Vite en 5173", "12", "11 aprobadas · 1 fallida (DEF-05)"),
    ("HU-23", "Regresión de paneles", "pytest + pytest-html", "Local, BD de test en Docker", "55", "55 aprobadas · 0 fallidas"),
]:
    clonar_fila(t1, m, textos)

t2 = T[2]
m = t2.rows[-1]
for textos in [
    ("API y reglas de negocio (HU-23)", "Listado, orden, aislamiento entre usuarios, búsqueda, abrir panel, estado vacío y errores", "pytest + pytest-html", "Existe: 28 pruebas en backend/qa/03_Evidencias/HU23/test_hu23_qa.py"),
    ("Extremo a extremo (HU-23)", "Listado, orden, búsqueda, abrir panel, sin paneles y otro usuario", "Playwright (Edge)", "Existe: 12 pruebas en backend/qa/playwright_hu23/hu23.spec.mjs"),
    ("Regresión (HU-23)", "Suite de paneles (listar, crear, editar, eliminar, ubicaciones y widgets)", "pytest + pytest-html", "Ejecutada: 55 aprobadas. RG-22 a RG-25"),
]:
    clonar_fila(t2, m, textos)

t4 = T[4]
m = t4.rows[-1]
for textos in [
    ("pytest + pytest-html (HU-23)", "Listado, orden, aislamiento, búsqueda y errores de paneles", "backend/qa/03_Evidencias/HU23/test_hu23_qa.py", "Bajo demanda de QA; no corre en CI", "Existe"),
    ("Playwright con Edge (HU-23)", "Flujos del listado de paneles como Cliente Final", "backend/qa/playwright_hu23/hu23.spec.mjs", "Bajo demanda de QA; sin CI", "Existe"),
]:
    clonar_fila(t4, m, textos)

t7 = T[7]
m = t7.rows[-1]
for textos in [
    ("R-12", "La búsqueda de paneles trata % y _ como comodines y muestra paneles de más.", "HU-23", "Media", "Baja", "Bajo", "Dev escapa % y _ en routers/panel.py (DEF-05); QA lo reprueba con RG-25.", "Dev", "DEF-05"),
    ("R-13", "Los paneles compartidos con la empresa contradicen «no se comparten en v1.0»; un cambio de regla afectaría lo ya construido.", "HU-23", "Media", "Media", "Medio", "El PO decide si queda como alcance adicional o se retira (OBS-33).", "PO", "OBS-33"),
]:
    clonar_fila(t7, m, textos)

t8 = T[8]
m = t8.rows[-1]
for textos in [
    ("HU-23 · CA1: listado con nombre, fecha y acciones", "CP-222 a CP-224, CP-250 y CP-258", "Cubierto"),
    ("HU-23 · CA2: abrir el panel con ubicaciones y widgets", "CP-241 a CP-243, CP-256 y CP-257", "Cubierto"),
    ("HU-23 · CA3: búsqueda por nombre o fragmento", "CP-233 a CP-240, CP-249, CP-253 a CP-255 y CP-261", "Parcial: DEF-05 (% y _ como comodines)"),
    ("HU-23 · Cada usuario ve solo sus paneles", "CP-228 a CP-232, CP-252 y CP-260", "Cubierto; OBS-33 (paneles compartidos, decide el PO)"),
    ("HU-23 · Orden por fecha de creación descendente", "CP-225 a CP-227 y CP-251", "Cubierto"),
    ("HU-23 · Sin paneles: mensaje y «Crear panel»", "CP-244, CP-245 y CP-259", "Cubierto; OBS-34 (mensaje con proyecto activo, decide el PO)"),
    ("HU-23 · Errores y permisos", "CP-246 a CP-248", "Cubierto"),
]:
    clonar_fila(t8, m, textos)

t10 = T[10]
m = t10.rows[-1]
clonar_fila(t10, m, ("Ronda 1 de HU-23 (PP-426)", "02/11/2026", "Ejecutada: 37 de 40 casos aprobados; 1 defecto menor (DEF-05) y 2 observaciones para el PO (OBS-33 y OBS-34)"))

# ----------------------------- pie de página -----------------------------
for sec in d.sections:
    for par in sec.footer.paragraphs:
        for run in par.runs:
            if "Plan de Pruebas y Automatización v0.8" in run.text:
                run.text = run.text.replace("v0.8", "v0.9").replace("HT-30.2, HU-15 ·", "HT-30.2, HU-15, HU-23 ·")
d.save(DST)
print("plan ok")
