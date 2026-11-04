"""PP-410 (PP-47 modelo comercial) ronda 1: amplía el plan de pruebas (Word) de v0.11 a v0.12.

Ejecutar desde backend/: venv/Scripts/python.exe qa/playwright_pp410/generar_plan_qa.py
Clona los párrafos y filas de la HU-28 (el último bloque del plan) para conservar el formato.
"""
import copy
from pathlib import Path

import docx
from docx.text.paragraph import Paragraph

QA = Path(__file__).resolve().parents[1]
SRC = QA / "01_Plan_de_Pruebas" / "Pangea_Plan_de_Pruebas_v0.11.docx"
DST = QA / "01_Plan_de_Pruebas" / "Pangea_Plan_de_Pruebas_v0.12.docx"

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




def clonar_bloque(titulo_ref, ultimo_ref, titulo, items, plantilla_item):
    """Clona un título y sus viñetas después de `ultimo_ref`."""
    nuevo = copy.deepcopy(titulo_ref._p)
    ultimo_ref._p.addnext(nuevo)
    ref = Paragraph(nuevo, titulo_ref._parent)
    ref.runs[0].text = titulo
    for r_ in ref.runs[1:]:
        r_._r.getparent().remove(r_._r)
    for texto in items:
        n = copy.deepcopy(plantilla_item._p)
        ref._p.addnext(n)
        ref = Paragraph(n, plantilla_item._parent)
        ref.runs[0].text = texto
        for r_ in ref.runs[1:]:
            r_._r.getparent().remove(r_._r)
    return ref


# ----------------------------- portada y resúmenes -----------------------------
sub = hallar("Pangea · Cómo se comprueba")
sub.runs[0].text = sub.runs[0].text.replace(
    " y la creación de alarmas cumple la HU-28",
    ", la creación de alarmas cumple la HU-28 y el modelo comercial multi-sede con vencimientos cumple la HT PP-47")
assert "PP-47" in sub.text

p_existe = hallar("HU-28 · Lo que existe y lo que falta")
clonar_despues(p_existe, "PP-47 · Lo que existe y lo que falta. Revisión del 04/11/2026. PP-317 y PP-318 (modelo Cliente, Sede y Plan) están en dev. PP-320, PP-321 y PP-322 (vencimiento automático, aviso al Administrador Comercial y diagrama ER, commit ccfc588 de Gean Pierre) están solo en origin/feature/PP-47-modelo-comercial, que va 27 commits atrás de dev; QA probó dev unido a esa rama con un merge local (b07660f). PP-319 (límite de sedes) no estaba entregada: el plan no guardaba el máximo de sedes y ninguna sede nueva se rechazaba (PEN-07). A pedido del usuario, QA la implementó en la rama qa/correcciones (db86ba8, y a8d6b35 para el diagrama ER); nada se subió a dev.")

p_res = hallar("Casos de prueba: HU-28")
clonar_despues(p_res, "Casos de prueba: PP-47 37 de 37 aprobados en la ronda 1 (45 pruebas de pytest); regresión 159 de 159 en comercial, contratos, cobros y límites, 23 de 23 en vencimientos (HU47) y 1 020 de 1 020 en el backend completo con PLAN_LIMITS_REQUIRE_SUBSCRIPTION=false. Defectos del producto: 0. Entrega pendiente: PEN-07 (PP-319), corregida por QA en qa/correcciones. Observaciones: OBS-42 a OBS-46; el PO decide OBS-43 y OBS-44.")

p_obj = hallar("Para HU-28 define cómo se comprueba")
clonar_despues(p_obj, "Para PP-47 define cómo se comprueba que un Cliente tiene varias Sedes bajo un mismo plan (CA1); que el sistema rechaza la sede que supera el límite del plan vigente (CA2); que un plan con la renovación pasada y sin cobro pasa solo a vencido y avisa al Administrador Comercial, sin repetirse (CA3); que el historial de cobros conserva todos los pagos sin sobrescribir (CA4); y que HU47 filtra los vencimientos con los datos de esa tarea (CA5). Se prueba con pytest sobre la API y el modelo, en una base de datos local.")

# ----------------------------- alcance: entra -----------------------------
t_hu28 = hallar("HU-28 · Crear alarma")
ultimo = hallar("Nombre y errores: alfanumérico de máximo 100")
item = hallar("Guardar (CA3): estado Activa")
clonar_bloque(t_hu28, ultimo, "PP-47 · Modelo de datos comercial multi-sede y vencimientos", [
    "Cliente con varias Sedes (CA1): un solo contrato, sede sin datos comerciales y plan reutilizable del catálogo (PP-317 y PP-318).",
    "Planes y límites (HU42, HU43, HU45): límites de sedes, ubicaciones, dispositivos y usuarios; no se asigna un plan sin límites (PP-317, PP-318 y PP-319).",
    "Límite de sedes (CA2): rechazo con 409 de la sede que lo supera, límite 0 sin tope, sedes de otro cliente y plan vencido (PP-319).",
    "Vencimiento automático (CA3): tarea de Celery Beat cada día, vence solo sin cobro, una sola vez, y aviso solo al Administrador Comercial (PP-320 y PP-321).",
    "Cobros y vencimientos (CA4 y CA5): historial sin sobrescribir ni borrar, validaciones y permisos; filtros de HU47 con los datos de la tarea; diagrama ER (PP-322).",
], item)

# ----------------------------- alcance: queda fuera -----------------------------
t_fuera = hallar("HU-28", P.index(hallar("Queda fuera")))
ultimo_f = hallar("Carga y estrés, OWASP ZAP, Lighthouse y axe: la HU no los pide; se descartan Locust, k6, ZAP, Lighthouse y axe.", P.index(t_fuera))
item_f = hallar("Producción y flujo multiempresa por cliente: solo se prueba en local.")
clonar_bloque(t_fuera, ultimo_f, "PP-47", [
    "Pantalla de Planes y suscripciones y de vencimientos (HU47) con Playwright: la HT es de modelo de datos y automatización; se verifica por API (OBS-46).",
    "Envío real del correo (HT-14 / SES): el aviso se verifica con el envío simulado (OBS-46).",
    "Pasarela de pago real: la HT la deja explícitamente fuera.",
    "Cobertura de código (pytest-cov) y carga o estrés: no se pidieron; se descartan Locust, k6, ZAP, Lighthouse y axe.",
], item_f)

# ----------------------------- estrategia -----------------------------
cob = hallar("Cobertura agregada por QA (HU-28)")
clonar_despues(cob, ["Cobertura agregada por QA (PP-47): ", "los tests existentes (test_vencimientos.py de servicios y de routers, test_limites_plan.py, test_comercial.py, test_contratos.py y test_registrar_cobro.py) cubren la tarea de vencimiento, los límites existentes, los contratos y los cobros. QA agrega 37 casos de punta a punta sobre CA1 a CA5 y el endpoint de sedes de PP-319."])

org = hallar("HU-28: pytest vive en backend/qa/03_Evidencias/HU28")
clonar_despues(org, "PP-47: pytest vive en backend/qa/03_Evidencias/PP-410 (test_pp410_qa.py, 45 pruebas) y reutiliza las fixtures de tests/; se ejecuta desde un worktree con dev unido a feature/PP-47-modelo-comercial y la BD de test en un contenedor Docker propio (qa-pp410-pg, puerto 55432). Las capturas salen de backend/qa/playwright_pp410/capture.mjs.")

no_auto = hallar("HU-28 · Carga, estrés, seguridad web y accesibilidad")
clonar_despues(no_auto, "PP-47 · Carga, estrés, seguridad web y accesibilidad: no se automatizan; la HT no tiene esos requisitos.")

datos = hallar("HU-28: los datos son los del seed del proyecto")
clonar_despues(datos, "PP-47: los datos los crean las propias pruebas dentro de una transacción que se revierte; no se usan cuentas reales ni se tocan los contenedores del proyecto.")

h9 = hallar("9 · Verificación de criterios de aceptación")
h9.runs[0].text = h9.runs[0].text.replace("PP-408 y PP-426)", "PP-408, PP-426 y PP-410)")
assert "PP-410" in h9.text

# ----------------------------- tablas -----------------------------
T = d.tables
fila_de = {
    "Versión": ("0.11", "0.12"),
}
for fila in T[0].rows:
    clave = fila.cells[0].text.strip()
    celda = fila.cells[1]
    if clave == "Versión":
        poner_celda(celda, "0.12")
    elif clave == "Fecha":
        poner_celda(celda, celda.text.rstrip() + " y ronda 1 de PP-47 (PP-410, 04/11/2026)")
    elif clave == "Entregable":
        poner_celda(celda, celda.text.rstrip() + " · PP-410 · PP-47 · Modelo de datos comercial multi-sede y automatización de vencimientos")
    elif clave == "Subtareas":
        poner_celda(celda, celda.text.rstrip() + " · PP-47: PP-317, PP-318, PP-319, PP-320, PP-321 y PP-322 (desarrollo, según Jira) · PP-410 (validar criterios de aceptación, flujos y errores; registrar evidencias y defectos)")

t1 = T[1]
m = t1.rows[-1]
for textos in [
    ("PP-47", "API y modelo (multi-sede, límites, vencimiento, cobros, vencimientos y diagrama ER)", "pytest + pytest-html", "Local, BD de test en Docker", "45", "45 aprobadas · 0 fallidas"),
    ("PP-47", "Regresión (comercial, contratos, cobros, límites, ubicaciones, solicitudes, empresas y vencimientos)", "pytest + pytest-html", "Local, BD de test en Docker", "182", "182 aprobadas · 0 fallidas"),
    ("PP-47", "Regresión del backend completo", "pytest", "Local, BD de test en Docker", "1 020", "1 020 aprobadas · 0 fallidas"),
]:
    clonar_fila(t1, m, textos)

t2 = T[2]
m = t2.rows[-1]
for textos in [
    ("API y reglas de negocio (PP-47)", "Multi-sede, límites del plan, vencimiento automático, cobros y vencimientos", "pytest + pytest-html", "Existe: 45 pruebas en backend/qa/03_Evidencias/PP-410/test_pp410_qa.py"),
    ("Regresión (PP-47)", "Comercial, contratos, cobros, límites, ubicaciones, solicitudes, empresas, vencimientos y backend completo", "pytest + pytest-html", "Ejecutada: 182 y 1 020 aprobadas. RG-29 a RG-32"),
]:
    clonar_fila(t2, m, textos)

t4 = T[4]
m = t4.rows[-1]
clonar_fila(t4, m, ("pytest + pytest-html (PP-47)", "Modelo comercial, límites de sedes, vencimiento automático, cobros y vencimientos", "backend/qa/03_Evidencias/PP-410/test_pp410_qa.py", "Bajo demanda de QA; no corre en CI", "Existe"))

t7 = T[7]
m = t7.rows[-1]
for textos in [
    ("R-14", "PP-320 a PP-322 y la corrección de PP-319 no están en dev; si no se integran, la HT no queda cerrada y puede haber conflictos con dev.", "PP-47", "Alta", "Media", "Alto", "Dev sube la rama, abre el PR hacia dev y resuelve conflictos (OBS-42).", "Dev", "OBS-42"),
    ("R-15", "El límite de sedes contradice la decisión previa «la sede es un detalle interno»; un cambio de regla afectaría lo construido.", "PP-47", "Media", "Media", "Medio", "El PO confirma que el límite de sedes es requisito vigente (OBS-44).", "PO", "OBS-44"),
]:
    clonar_fila(t7, m, textos)

t8 = T[8]
m = t8.rows[-1]
for textos in [
    ("PP-47 · CA1: cliente con varias sedes bajo un plan", "CP-303 a CP-305", "Cubierto"),
    ("PP-47 · HU42, HU43 y HU45: planes con límites", "CP-306 a CP-310", "Cubierto; OBS-44 (decide el PO)"),
    ("PP-47 · CA2: rechazo de la sede que excede el límite", "CP-311 a CP-320", "Cubierto; PEN-07 corregida por QA (PP-319)"),
    ("PP-47 · CA3: vencimiento automático y aviso", "CP-321 a CP-327", "Cubierto; OBS-42 (integración a dev)"),
    ("PP-47 · CA4: historial de cobros sin sobrescribir", "CP-328 a CP-334", "Cubierto; OBS-43 (período del cobro, decide el PO)"),
    ("PP-47 · CA5: HU47 consulta de vencimientos", "CP-335 a CP-338", "Cubierto"),
    ("PP-47 · PP-322: diagrama entidad-relación", "CP-339", "Cubierto"),
]:
    clonar_fila(t8, m, textos)

t10 = T[10]
m = t10.rows[-1]
clonar_fila(t10, m, ("Ronda 1 de PP-47 (PP-410)", "04/11/2026", "Ejecutada: 37 de 37 casos aprobados; sin defectos del producto; PEN-07 (PP-319) corregida por QA en qa/correcciones; OBS-42 a OBS-46 (el PO decide OBS-43 y OBS-44)"))

# ----------------------------- pie de página -----------------------------
for sec in d.sections:
    for par in sec.footer.paragraphs:
        for run in par.runs:
            if "Plan de Pruebas y Automatización v0.11" in run.text:
                run.text = run.text.replace("v0.11", "v0.12").replace("HU-23, HU-28 ·", "HU-23, HU-28, PP-47 ·")
d.save(DST)
print("plan ok")
