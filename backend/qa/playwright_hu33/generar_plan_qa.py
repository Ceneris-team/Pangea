"""PP-408 (HU-15): amplía el Plan de Pruebas de Pangea de v0.6 a v0.7 con HU-15.

Ejecutar desde backend/: venv/Scripts/python.exe qa/playwright_hu33/generar_plan_qa.py
"""
from copy import deepcopy
from pathlib import Path

import docx

QA = Path(__file__).resolve().parents[1]
SRC = QA / "01_Plan_de_Pruebas" / "Pangea_Plan_de_Pruebas_v0.6.docx"
DST = QA / "01_Plan_de_Pruebas" / "Pangea_Plan_de_Pruebas_v0.7.docx"

d = docx.Document(SRC)
P = list(d.paragraphs)  # referencias fijas: los índices cambian al insertar


def poner_texto(par, texto):
    runs = par.runs
    runs[0].text = texto
    for r in runs[1:]:
        r._element.getparent().remove(r._element)


def clonar_despues(ref, modelo, texto):
    """Inserta, justo después de `ref`, una copia de `modelo` con `texto`. Devuelve el párrafo nuevo."""
    nuevo = deepcopy(modelo._element)
    ref._element.addnext(nuevo)
    par = docx.text.paragraph.Paragraph(nuevo, ref._parent)
    poner_texto(par, texto)
    return par


def encadenar(ref, modelo, textos):
    for t in textos:
        ref = clonar_despues(ref, modelo, t)
    return ref


# ---- Portada y resumen -----------------------------------------------------
poner_texto(P[1], P[1].text.replace("y los flujos principales del sistema cumplen la HT-30.2",
                                    "los flujos principales del sistema cumplen la HT-30.2 y la exportación en background cumple la HU-15"))
clonar_despues(P[6], P[6],
    "HU-15 · Lo que existe y lo que falta. Revisión del 02/11/2026 sobre la rama qa-elliot (commit 827755e, que contiene dev hasta f9c0967). "
    "Existe en dev el pipeline de exportación en background (HU33, entregado por Jareth en f9c0967): POST /exportaciones que responde 202 y encola la tarea de Celery, "
    "generación por lotes en CSV y XLSX, subida a un bucket privado que se verifica no público, URL firmada de 60 s al descargar, correo de aviso con vigencia de 24 horas, "
    "límites de rango, filas y tamaño, y limpieza programada en Beat cada 60 s. Falta o difiere: el texto pide pandas y el código usa csv y openpyxl por lotes (OBS-25); "
    "el enlace del correo apunta a la app y la URL firmada dura 60 s, no 24 h (OBS-26); y en local no hay Object Storage ni SMTP reales (OBS-28). "
    "PP-286 figura En curso en Jira aunque su código está entregado (OBS-29).")
clonar_despues(P[12], P[12],
    "Casos de prueba: HU-15 31 de 31 aprobados en la ronda 1 (02/11/2026), con pytest (37 pruebas de exportación), Playwright (4 pruebas), una verificación E2E de la expiración (CA4) por script "
    "y la regresión del backend (783 de 879; las 96 restantes solo por OBS-11). Defectos del producto: 0. Observaciones: OBS-25 y OBS-26 (las decide el PO), OBS-27 (mejora técnica), "
    "OBS-28 (cobertura pendiente) y OBS-29 (confirmación de Dev).")
clonar_despues(P[18], P[18],
    "Para HU-15 define cómo se comprueba que la exportación de telemetría (HU33) corre en segundo plano con Celery sin bloquear la interfaz (CA1), que un mes completo se procesa por lotes "
    "sin errores de memoria ni timeout (CA2), que el usuario recibe el aviso con la descarga vigente 24 horas (CA3), que el archivo se elimina de Object Storage al expirar (CA4) "
    "y que un rango mayor al máximo se rechaza con un mensaje claro (CA5).")

# ---- Alcance: entra ---------------------------------------------------------
ref = clonar_despues(P[50], P[46], "HU-15 · Pipeline de exportación en background con Celery")
encadenar(ref, P[47], [
    "Asíncrono (CA1): POST /exportaciones responde 202 sin generar el archivo; la tarea corre en el worker y la interfaz sigue usable.",
    "Lotes (CA2): un mes completo (446 400 filas) en CSV y XLSX sin errores de memoria ni timeout.",
    "Almacén y descarga (PP-285): bucket privado, URL firmada de vida corta y acceso revalidado en cada descarga.",
    "Notificación (CA3): correo con enlace a la app y vigencia de 24 horas.",
    "Rango máximo (CA5): 31 días, filas y tamaño, con mensaje claro y sin crear trabajo.",
    "Eliminación automática (CA4, PP-286): limpieza programada en Beat y descarga bloqueada tras expirar.",
    "Transversal: aislamiento por entorno, usuario y permisos; regresión del backend.",
])

# ---- Alcance: queda fuera ---------------------------------------------------
poner_texto(P[74], "Modelo comercial multi-sede (PP-47): sin código en dev; tiene su propio QA (PP-410). La exportación en background (PP-408) entra en este plan como HU-15.")
ref = clonar_despues(P[76], P[72], "HU-15")
encadenar(ref, P[73], [
    "Lightsail Object Storage y SMTP reales: las pruebas usan un bucket simulado en carpeta y SMTP simulado (OBS-28); se repiten en un entorno de prueba cuando el PO lo autorice.",
    "Carga y estrés (Locust, k6): la carga de las exportaciones se mide formalmente en HT-18; aquí solo se mide un mes de un dispositivo.",
    "Espera real de 24 horas y reloj de Beat: el vencimiento se fuerza en la BD y la tarea de limpieza se ejecuta directamente; la programación se verifica por configuración (cada 60 s).",
    "Seguridad web, rendimiento de pantalla y accesibilidad: se descartan OWASP ZAP, Lighthouse y axe porque ningún criterio los pide.",
])

# ---- Estrategia -------------------------------------------------------------
# el modelo tiene 2 runs (negrita + texto): se copia entero y se reescriben ambos
nuevo = deepcopy(P[87]._element)
P[87]._element.addnext(nuevo)
par = docx.text.paragraph.Paragraph(nuevo, P[87]._parent)
par.runs[0].text = "Cobertura agregada por QA (HU-15): "
par.runs[1].text = ("los 37 tests existentes de exportación (test_exportaciones.py, test_exportaciones_storage.py y test_exportaciones_correo.py) cubren la API, la tarea, el almacén y el correo "
                    "con servicios simulados, pero no la interfaz ni el flujo con la API y el worker en marcha. QA agregó 4 pruebas de Playwright, una verificación E2E de la expiración por script "
                    "(verificar_ca4.py) y un entorno local con bucket simulado en carpeta (entorno_local.py).")
clonar_despues(P[97], P[97],
    "HU-15: pytest corre sobre los tests existentes de exportaciones (backend/tests) y guarda el HTML en backend/qa/03_Evidencias/HU33-HT15; Playwright vive en backend/qa/playwright_hu33 "
    "(hu33.spec.mjs, 4 tests) contra el frontend local en :5173, con la API y un worker de Celery reales levantados por entorno_local.py, que solo reemplaza el bucket (una carpeta en disco) "
    "y el SMTP (un archivo de correos). verificar_ca4.py fuerza el vencimiento y ejecuta la tarea de limpieza del producto.")
clonar_despues(P[106], P[106], "HU-15 · Carga y estrés, Object Storage y SMTP reales: no se automatizan en esta ronda (ver «Queda fuera» y OBS-28).")
clonar_despues(P[124], P[124],
    "HU-15: los datos son los del seed del proyecto (cliente@pangea-dev.com y la telemetría del 29 al 31/10/2026 de pangea_e2e) y, para el volumen, 446 400 lecturas sintéticas que el test crea dentro de "
    "una transacción y revierte. El bucket simulado se borra al terminar; los correos guardados no contienen datos de telemetría.")
poner_texto(P[131], "9 · Verificación de criterios de aceptación (PP-411, PP-413, PP-415, PP-418, PP-400 y PP-408)")


# ---- Tablas ------------------------------------------------------------------
def fila_nueva(tabla, valores, modelo=None):
    modelo = modelo or tabla.rows[-1]
    nueva = deepcopy(modelo._tr)
    tabla.rows[-1]._tr.addnext(nueva)
    fila = tabla.rows[-1]
    for celda, valor in zip(fila.cells, valores):
        parrafos = celda.paragraphs
        runs = parrafos[0].runs
        if runs:
            runs[0].text = valor
            for r in runs[1:]:
                r._element.getparent().remove(r._element)
        else:
            parrafos[0].add_run(valor)
        for extra in parrafos[1:]:
            extra._element.getparent().remove(extra._element)


T = d.tables
# 0: datos del documento
for fila in T[0].rows:
    c0, c1 = fila.cells[0].text, fila.cells[1]
    if c0 == "Entregable":
        poner_texto(c1.paragraphs[0], c1.text + " · PP-408 · HU-15 · Pipeline de exportación en background con Celery")
    elif c0 == "Versión":
        poner_texto(c1.paragraphs[0], "0.7")
    elif c0 == "Fecha":
        poner_texto(c1.paragraphs[0], c1.text.replace("y ronda 1 de HT-30.2 (PP-402)", "ronda 1 de HT-30.2 (PP-402) y ronda 1 de HU-15 (PP-408)"))
    elif c0 == "Subtareas":
        poner_texto(c1.paragraphs[0], c1.text + " · HU-15: PP-283, PP-284, PP-285 y PP-286 (desarrollo, según Jira) · PP-408 (verificar los criterios de aceptación y registrar evidencias)")
# 1: resumen por HU
for v in [
    ("HU-15", "Funcional, seguridad y tareas de Celery", "pytest + pytest-html", "Local, BD de test en Docker; S3 y SMTP simulados", "37", "37 aprobadas · 0 fallidas"),
    ("HU-15", "Volumen (un mes de telemetría, CSV y XLSX)", "pytest + pytest-html", "Local, BD de test en Docker", "2 (incluidas en las 37)", "2 aprobadas · pico de 202,9 MiB; CSV 8,55 s y XLSX 86,59 s"),
    ("HU-15", "E2E de UI y de expiración", "Playwright (Edge) y script Python", "Local, BD pangea_e2e, API y worker reales, bucket simulado", "4 + 1 verificación", "4 aprobadas · 0 fallidas; CA4 cumple"),
    ("HU-15", "Regresión del backend", "pytest + pytest-html", "Local, BD de test en Docker", "879", "783 aprobadas · 96 fallidas por OBS-11 (0 en exportaciones)"),
]:
    fila_nueva(T[1], v)
# 4: herramientas
for v in [
    ("pytest + pytest-html (HU-15)", "Tareas de exportación, almacén, correo, límites y volumen", "backend/tests/routers/test_exportaciones.py y backend/tests/services/test_exportaciones_*.py", "Con la suite del backend; no corre en CI", "Existe"),
    ("Playwright con Edge (HU-15)", "Flujos de la interfaz de exportación como Cliente Final", "backend/qa/playwright_hu33/hu33.spec.mjs", "Bajo demanda de QA; sin CI", "Existe"),
    ("Script E2E (HU-15)", "Entorno local con bucket y correo simulados y verificación de la expiración", "backend/qa/playwright_hu33/entorno_local.py y verificar_ca4.py", "Bajo demanda de QA", "Existe"),
]:
    fila_nueva(T[4], v)
# 7: riesgos
fila_nueva(T[7], ("R-10", "La exportación XLSX de un mes tarda 86 s en local y podría acercarse a los límites en un servidor más lento.", "HU-15", "Media", "Media", "Medio", "Medir en Lightsail dentro de HT-18 y valorar recomendar CSV en rangos largos.", "Dev", "OBS-27"))
# 8: criterios
for v in [
    ("HU-15 · CA1: solicitar la exportación no bloquea la interfaz", "CP-172 a CP-177", "Cubierto (ronda 1, 02/11/2026)"),
    ("HU-15 · CA2: un mes completo sin errores de memoria ni timeout", "CP-178 a CP-181", "Cubierto; OBS-25 (pandas) y OBS-27 (XLSX lento)"),
    ("HU-15 · Almacén privado y URL firmada", "CP-182 a CP-185", "Cubierto; OBS-28 (sin Object Storage real)"),
    ("HU-15 · CA3: aviso por correo con enlace y vigencia de 24 horas", "CP-186 a CP-189", "Cubierto; OBS-26 (la URL firmada dura 60 s, decide el PO)"),
    ("HU-15 · CA5: rango máximo rechazado con mensaje claro", "CP-190 a CP-194", "Cubierto (ronda 1, 02/11/2026)"),
    ("HU-15 · CA4: eliminación automática al expirar", "CP-195 a CP-199", "Cubierto; OBS-29 (PP-286 sigue En curso en Jira)"),
    ("HU-15 · Acceso, aislamiento y regresión", "CP-200 a CP-202", "Cubierto; OBS-11 (96 tests sin suscripción)"),
]:
    fila_nueva(T[8], v)
# 10: hitos
fila_nueva(T[10], ("Ronda 1 de HU-15 (PP-408)", "02/11/2026", "Ejecutada: 31 de 31 casos aprobados; sin defectos del producto; OBS-25 a OBS-29."), modelo=T[10].rows[7])

# ---- Pie de página -------------------------------------------------------------
for s in d.sections:
    for par in s.footer.paragraphs:
        r0 = par.runs[0]
        r0.text = r0.text.replace("v0.6", "v0.7").replace("HU-34, HT-30.2", "HU-34, HT-30.2, HU-15")

d.save(DST)
print("plan ok", DST.name)
