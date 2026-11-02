"""PP-408 (HU-15) ronda 2: pasa el Plan de Pruebas de v0.7 a v0.8 con los criterios de aceptación actualizados.

Ejecutar desde backend/: venv/Scripts/python.exe qa/playwright_hu33/generar_plan_qa_ronda2.py
"""
from copy import deepcopy
from pathlib import Path

import docx

QA = Path(__file__).resolve().parents[1]
d = docx.Document(QA / "01_Plan_de_Pruebas" / "Pangea_Plan_de_Pruebas_v0.7.docx")
DST = QA / "01_Plan_de_Pruebas" / "Pangea_Plan_de_Pruebas_v0.8.docx"


def par_que_empieza(prefijo):
    for p in d.paragraphs:
        if p.text.startswith(prefijo):
            return p
    raise KeyError(prefijo)


def poner(par, texto, run=0):
    par.runs[run].text = texto
    if run == 0:
        for r in par.runs[1:]:
            r._element.getparent().remove(r._element)


def clonar_despues(ref, modelo, texto):
    nuevo = deepcopy(modelo._element)
    ref._element.addnext(nuevo)
    par = docx.text.paragraph.Paragraph(nuevo, ref._parent)
    poner(par, texto)
    return par


poner(par_que_empieza("HU-15 · Lo que existe y lo que falta"),
    "HU-15 · Lo que existe y lo que falta. Revisión del 02/11/2026 sobre la rama qa-elliot (commit 8a4b672); el código de exportación no cambió desde f9c0967, y la HU actualizó sus criterios de aceptación. "
    "Existe en dev el pipeline de exportación en background (HU33, entregado por Jareth): POST /exportaciones que responde 202 y encola la tarea de Celery, generación por lotes en CSV y XLSX con cursores de servidor, "
    "subida a un bucket privado que se verifica no público, URL firmada de 60 s al descargar, correo con enlace a la aplicación y vigencia de 24 horas, límites de rango, filas, tamaño y trabajos simultáneos, y limpieza programada en Beat cada 60 s. "
    "Los criterios nuevos confirman que no se usa pandas y que la URL firmada dura 60 s (OBS-25 y OBS-26 aceptadas). También exigen comprobar con AWS real la privacidad del bucket, la recepción del correo en el entorno de QA y la integración real con el bucket. "
    "La privacidad de pangea-storage-prod se comprobó (CP-219), pero producción no tiene desplegadas las exportaciones: no hay bucket dedicado, ni variables SMTP, ni un worker de la cola exportaciones (el worker arranca sin --queues); es una entrega pendiente (PEN-06, OBS-28 y OBS-32), por eso la HU no puede cerrarse todavía. PP-286 figura En curso en Jira aunque su código está entregado (OBS-29).")
poner(par_que_empieza("Casos de prueba: HU-15"),
    "Casos de prueba: HU-15 50 de 53 en total: ronda 1 con 31 de 31 aprobados y ronda 2 (criterios actualizados, 02/11/2026) con 17 de 19 aprobados y 2 bloqueados por entorno (recepción real del correo e integración real con un bucket dedicado); la privacidad de pangea-storage-prod se comprobó en AWS real. "
    "Se usaron pytest, Playwright (5 pruebas), procesos reales de API, worker, Beat y un SMTP local con STARTTLS, y un contenedor de 2 CPU y 512 MiB para el rendimiento (CSV 7,50 s y XLSX 62,00 s; memoria residente máxima de 200,8 MiB). "
    "Regresión del backend: 783 de 879 (las 96 restantes solo por OBS-11). Defectos del producto: 0. Observaciones: OBS-25 a OBS-27 aceptadas; abiertas OBS-28 y OBS-32 (cobertura pendiente), OBS-29 (confirmación de Dev) y OBS-31 (mejora técnica).")
poner(par_que_empieza("Para HU-15 define"),
    "Para HU-15 define cómo se comprueba que la exportación de telemetría (HU33) corre en segundo plano con Celery sin bloquear la interfaz, contiene todas las filas y columnas pedidas, conserva sus filtros, aísla a cada usuario, "
    "respeta las revocaciones, mantiene el archivo 24 horas con firmas de 60 s, cumple los límites, genera un mes completo en un worker de 2 CPU y 512 MiB en 120 s o menos y con 256 MiB o menos de memoria, "
    "avisa por correo sin regenerar el archivo, y elimina lo vencido en menos de 5 minutos. También define qué queda bloqueado hasta contar con AWS y SMTP reales.")
anterior = par_que_empieza("Transversal: aislamiento por entorno, usuario y permisos")
modelo_li = anterior
ref = clonar_despues(anterior, modelo_li, "Criterios actualizados (ronda 2): contenido completo, filtros, aislamiento con otro administrador, revocaciones, vigencia de 24 h, límites visibles y tope de Excel, temporales y rendimiento verificable en un worker de 2 CPU y 512 MiB.")
clonar_despues(ref, modelo_li, "Recepción real del correo e integración real (CP-220 y CP-221): bloqueadas hasta contar con un SMTP con buzón de QA y un bucket de exportaciones dedicado (PEN y OBS-28); la privacidad de pangea-storage-prod ya se comprobó con comandos de solo lectura (CP-219).")
poner(par_que_empieza("Lightsail Object Storage y SMTP reales"),
    "Integración con un bucket de exportaciones y SMTP reales: no existe un bucket dedicado y no hay buzón de QA; quedan como casos bloqueados (CP-220 y CP-221, OBS-28 y OBS-32). Las pruebas usan un bucket simulado en carpeta y un SMTP local con STARTTLS; solo la privacidad de pangea-storage-prod se verificó en AWS real.")
poner(par_que_empieza("Espera real de 24 horas y reloj de Beat"),
    "Espera real de 24 horas: el vencimiento se fuerza en la BD; Beat y el worker sí corrieron reales y limpiaron lo vencido en 60 s (CP-217).")
p = par_que_empieza("Cobertura agregada por QA (HU-15)")
poner(p, "los 37 tests existentes de exportación cubren la API, la tarea, el almacén y el correo con servicios simulados. QA agregó 5 pruebas de Playwright, 7 de pytest para los criterios nuevos (test_criterios_hu15.py), "
         "una verificación contra procesos reales de API, worker, Beat y un SMTP local con STARTTLS (verificar_criterios.py), y la medición de rendimiento en un contenedor de 2 CPU y 512 MiB (ejecutar_rendimiento_referencia.sh).", run=1)
poner(par_que_empieza("HU-15: pytest corre sobre los tests existentes"),
    "HU-15: pytest corre sobre los tests existentes de exportaciones (backend/tests) y sobre test_criterios_hu15.py, con el HTML en backend/qa/03_Evidencias/HU33-HT15; Playwright vive en backend/qa/playwright_hu33 "
    "(hu33.spec.mjs, 5 tests) contra el frontend local en :5173. entorno_local.py levanta la API, un worker de Celery y Beat reales y solo reemplaza el bucket (una carpeta en disco); el correo sale por SMTP al servidor local smtp_local.py, que exige STARTTLS como el producto. "
    "verificar_criterios.py mide el p95 de aceptación y verifica contenido, filtros, aislamiento, vigencia, correo y limpieza. El rendimiento se mide con ejecutar_rendimiento_referencia.sh en un contenedor de 2 CPU y 512 MiB.")
poner(par_que_empieza("HU-15 · Carga y estrés, Object Storage y SMTP reales"),
    "HU-15 · Object Storage y SMTP reales: no se automatizan en esta ronda; se comprueban en el entorno de QA con comandos de solo lectura que ejecuta el usuario (ver «Queda fuera» y OBS-28 y OBS-32). La carga formal de las exportaciones se mide en HT-18.")


# ---- Tablas -------------------------------------------------------------------
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


def quitar_filas(tabla, prefijo):
    for fila in list(tabla.rows):
        if fila.cells[0].text.startswith(prefijo):
            fila._tr.getparent().remove(fila._tr)


T = d.tables
for fila in T[0].rows:
    c0, c1 = fila.cells[0].text, fila.cells[1]
    if c0 == "Versión":
        poner(c1.paragraphs[0], "0.8")
    elif c0 == "Fecha":
        poner(c1.paragraphs[0], c1.text.replace("y ronda 1 de HU-15 (PP-408)", "ronda 1 de HU-15 (PP-408) y ronda 2 de HU-15 con los criterios actualizados"))
for fila in T[1].rows:
    if fila.cells[0].text == "HU-15" and fila.cells[1].text.startswith("E2E de UI"):
        valores = ["HU-15", "E2E de UI y verificación contra procesos reales", "Playwright (Edge) y script Python", "Local, BD pangea_e2e, API, worker, Beat y SMTP local; bucket simulado", "5 + 8 verificaciones", "5 aprobadas · 0 fallidas; 8 de 8 verificaciones cumplen"]
        for celda, valor in zip(fila.cells, valores):
            poner(celda.paragraphs[0], valor)
for v in [
    ("HU-15", "Criterios de la ronda 2 (revocaciones, vigencia, límites, temporales)", "pytest + pytest-html", "Local, BD de test en Docker", "7", "7 aprobadas · 0 fallidas"),
    ("HU-15", "Rendimiento en el worker de referencia (2 CPU y 512 MiB)", "pytest en Docker", "Local, contenedor con límites", "2 (CSV y XLSX)", "2 aprobadas · CSV 7,50 s y XLSX 62,00 s; memoria residente máxima 200,8 MiB"),
    ("HU-15", "Privacidad real en AWS, recepción real del correo e integración real", "Comandos de solo lectura y entorno de QA", "Lightsail y entorno de QA", "3 casos", "1 aprobado (privacidad de pangea-storage-prod) · 2 bloqueados (OBS-28 y OBS-32)"),
]:
    fila_nueva(T[1], v)
fila_nueva(T[7], ("R-11", "No existe un bucket dedicado a exportaciones ni se ha comprobado la recepción real del correo; sin eso la HU no puede cerrarse.", "HU-15", "Media", "Alta", "Alto", "El PO decide el bucket y Dev configura SMTP y un worker de la cola exportaciones (PEN-06); luego QA repite CP-220 y CP-221.", "PO", "OBS-28, OBS-32"))
quitar_filas(T[8], "HU-15 ·")
for v in [
    ("HU-15 · CA1: solicitud asíncrona (202, p95 de 2 s o menos, identificador tras recargar)", "CP-172 a CP-177, CP-203 y CP-218", "Cubierto (ronda 2, 02/11/2026)"),
    ("HU-15 · Contenido completo y filtros reproducibles", "CP-181, CP-204 y CP-205", "Cubierto"),
    ("HU-15 · Rendimiento verificable: un mes en el worker de 2 CPU y 512 MiB", "CP-178 a CP-180, CP-212 a CP-214", "Cubierto; OBS-31 (memoria del contenedor cercana al límite en XLSX)"),
    ("HU-15 · Almacén privado y URL firmada de 60 s", "CP-182 a CP-185 y CP-219", "Cubierto; falta un bucket dedicado (OBS-28 y PEN)"),
    ("HU-15 · CA3: aviso por correo y reintento sin regenerar", "CP-186 a CP-189, CP-215 y CP-216", "Parcial: recepción en buzón real pendiente (OBS-32)"),
    ("HU-15 · CA5: límites explícitos y tope de Excel", "CP-190 a CP-194, CP-210 y CP-211", "Cubierto"),
    ("HU-15 · Vigencia y descarga: 24 h y firmas de 60 s", "CP-208 y CP-209", "Cubierto"),
    ("HU-15 · CA4: limpieza con Beat en menos de 5 minutos", "CP-195 a CP-199 y CP-217", "Cubierto; OBS-29 (PP-286 sigue En curso en Jira)"),
    ("HU-15 · Aislamiento y revocaciones", "CP-200, CP-201, CP-206 y CP-207", "Cubierto"),
    ("HU-15 · Regresión del backend", "CP-202", "Cubierto; OBS-11 (96 tests sin suscripción)"),
    ("HU-15 · Recepción real del correo e integración real con bucket", "CP-220 y CP-221", "Bloqueado por entorno (OBS-32 y OBS-28)"),
]:
    fila_nueva(T[8], v)
fila_nueva(T[10], ("Ronda 2 de HU-15 (PP-408): criterios de aceptación actualizados", "02/11/2026", "Ejecutada: 17 de 19 casos aprobados y 2 bloqueados por entorno (SMTP real y bucket dedicado); sin defectos del producto."), modelo=T[10].rows[7])

# ---- Ajustes finales: CP-220 y CP-221 aprobados con servicios locales --------------
poner(par_que_empieza("HU-15 · Lo que existe y lo que falta"),
    "HU-15 · Lo que existe y lo que falta. Revisión del 02/11/2026 sobre la rama qa-elliot (commit 8a4b672); el código de exportación no cambió desde f9c0967, y la HU actualizó sus criterios de aceptación. "
    "Existe en dev el pipeline de exportación en background (HU33, entregado por Jareth): POST /exportaciones que responde 202 y encola la tarea de Celery, generación por lotes en CSV y XLSX con cursores de servidor, "
    "subida a un bucket privado que se verifica no público, URL firmada de 60 s al descargar, correo con enlace a la aplicación y vigencia de 24 horas, límites de rango, filas, tamaño y trabajos simultáneos, y limpieza programada en Beat cada 60 s. "
    "Los criterios nuevos confirman que no se usa pandas y que la URL firmada dura 60 s (OBS-25 y OBS-26 aceptadas). También piden comprobar con servicios reales la privacidad del bucket, la recepción del correo y la integración completa: "
    "la privacidad de pangea-storage-prod se comprobó en AWS real y en solo lectura (CP-219), y el correo y el flujo completo se probaron en local con un servidor S3 emulado (moto) y un buzón SMTP con STARTTLS (Mailpit), sin AWS ni un SMTP en internet; el PO debe aceptar que eso cumple (OBS-28 y OBS-32). "
    "Producción corre la imagen del 16/10 (b948aac), que no incluye la exportación: sus precondiciones de despliegue (bucket dedicado, SMTP y un worker de la cola exportaciones) son una nota para Dev (PEN-06). PP-286 figura En curso en Jira aunque su código está entregado (OBS-29).")
poner(par_que_empieza("Casos de prueba: HU-15"),
    "Casos de prueba: HU-15 50 de 50 aprobados: ronda 1 con 31 de 31 y ronda 2 (criterios actualizados, 02/11/2026) con 19 de 19. Se usaron pytest, Playwright (5 pruebas), procesos reales de API, worker y Beat, un SMTP local con STARTTLS, "
    "un S3 emulado (moto) con un buzón Mailpit para el flujo completo y el correo, y un contenedor de 2 CPU y 512 MiB para el rendimiento (CSV 7,50 s y XLSX 62,00 s; memoria residente máxima de 200,8 MiB). "
    "La privacidad de pangea-storage-prod se comprobó en AWS real, en solo lectura. Regresión del backend: 783 de 879 (las 96 restantes solo por OBS-11). Defectos del producto: 0. "
    "Observaciones: OBS-25 a OBS-27 aceptadas; abiertas OBS-28 y OBS-32 (decisión del PO sobre servicios locales o reales), OBS-29 (confirmación de Dev) y OBS-31 (mejora técnica).")
poner(par_que_empieza("Para HU-15 define"), par_que_empieza("Para HU-15 define").text.replace("También define qué queda bloqueado hasta contar con AWS y SMTP reales.", "También define cómo se comprueba con servicios reales o locales equivalentes."))
poner(par_que_empieza("Recepción real del correo e integración real"),
    "Privacidad real, correo e integración (CP-219 a CP-221): la privacidad de pangea-storage-prod se comprobó con comandos de solo lectura en AWS real; el correo y el flujo completo, con un S3 emulado (moto) y un buzón Mailpit locales (OBS-28 y OBS-32).")
poner(par_que_empieza("Integración con un bucket de exportaciones y SMTP reales"),
    "Un bucket de exportaciones y un SMTP en internet: no se usaron; el flujo completo se probó con un S3 emulado y un buzón local, y el PO decide si eso cumple (OBS-28 y OBS-32). Producción no tiene la exportación ni su configuración (PEN-06): es una nota para Dev, no una prueba de QA.")
p5 = par_que_empieza("Cobertura agregada por QA (HU-15)")
poner(p5, "los 37 tests existentes de exportación cubren la API, la tarea, el almacén y el correo con servicios simulados. QA agregó 5 pruebas de Playwright, 7 de pytest para los criterios nuevos (test_criterios_hu15.py), "
          "verificaciones contra procesos reales de API, worker, Beat, un SMTP local y un S3 emulado con buzón Mailpit (verificar_criterios.py y verificar_real.py), y la medición de rendimiento en un contenedor de 2 CPU y 512 MiB (ejecutar_rendimiento_referencia.sh).", run=1)
poner(par_que_empieza("HU-15: pytest corre sobre los tests existentes"),
    "HU-15: pytest corre sobre los tests existentes de exportaciones (backend/tests) y sobre test_criterios_hu15.py, con el HTML en backend/qa/03_Evidencias/HU33-HT15; Playwright vive en backend/qa/playwright_hu33 "
    "(hu33.spec.mjs, 5 tests) contra el frontend local en :5173. entorno_local.py levanta la API, un worker de Celery y Beat reales; en modo simulado solo reemplaza el bucket (una carpeta) y en modo QA_REAL=1 usa un S3 emulado (moto) y un buzón Mailpit con STARTTLS configurados en .env.qa, sin parchear el producto. "
    "verificar_criterios.py y verificar_real.py comprueban p95, contenido, filtros, aislamiento, vigencia, correo, descarga firmada y limpieza con varias versiones. El rendimiento se mide con ejecutar_rendimiento_referencia.sh en un contenedor de 2 CPU y 512 MiB.")
poner(par_que_empieza("HU-15 · Object Storage y SMTP reales"),
    "HU-15 · AWS y SMTP en internet: no se automatizan; la privacidad de pangea-storage-prod se comprobó a mano con comandos de solo lectura, y el correo y el flujo completo con servicios locales (ver OBS-28 y OBS-32). La carga formal de las exportaciones se mide en HT-18.")


def fijar(tabla, prefijo, valores, col=0):
    for fila in tabla.rows:
        if fila.cells[col].text.startswith(prefijo):
            for celda, valor in zip(fila.cells, valores):
                poner(celda.paragraphs[0], valor)
            return
    raise KeyError(prefijo)


for fila in T[1].rows:
    if fila.cells[0].text == "HU-15" and fila.cells[1].text.startswith("E2E de UI"):
        for celda, valor in zip(fila.cells, ["HU-15", "E2E de UI y verificación contra procesos reales", "Playwright (Edge) y scripts Python", "Local, BD pangea_e2e, API, worker, Beat; SMTP local, S3 emulado y buzón Mailpit", "5 + 11 verificaciones", "5 aprobadas · 0 fallidas; 11 de 11 verificaciones cumplen"]):
            poner(celda.paragraphs[0], valor)
    if fila.cells[0].text == "HU-15" and fila.cells[1].text.startswith("Privacidad real"):
        for celda, valor in zip(fila.cells, ["HU-15", "Privacidad real en AWS, correo e integración con S3", "Comandos de solo lectura, moto y Mailpit", "Lightsail (solo lectura) y local", "3 casos", "3 aprobados (CP-219 en AWS real; CP-220 y CP-221 con servicios locales)"]):
            poner(celda.paragraphs[0], valor)
fijar(T[7], "R-11", ["R-11", "Producción corre una imagen (16/10) sin la exportación y sin bucket dedicado, SMTP ni worker de la cola exportaciones: al desplegar HU33 habría que configurarlos.", "HU-15", "Media", "Media", "Medio", "Dev y el PO preparan estas tres cosas antes de desplegar HU33 (PEN-06).", "Dev", "PEN-06"])
fijar(T[8], "HU-15 · Almacén privado", ["HU-15 · Almacén privado y URL firmada de 60 s", "CP-182 a CP-185 y CP-219", "Cubierto; privacidad real de pangea-storage-prod comprobada en solo lectura"])
fijar(T[8], "HU-15 · CA3", ["HU-15 · CA3: aviso por correo, buzón y reintento sin regenerar", "CP-186 a CP-189, CP-215, CP-216 y CP-220", "Cubierto; OBS-32 (buzón local, el PO decide)"])
fijar(T[8], "HU-15 · Recepción real", ["HU-15 · Flujo completo con S3 y limpieza de versiones", "CP-221", "Cubierto con S3 emulado; OBS-28 (el PO decide)"])
fijar(T[10], "Ronda 2 de HU-15", ["Ronda 2 de HU-15 (PP-408): criterios de aceptación actualizados", "02/11/2026", "Ejecutada: 19 de 19 casos aprobados; sin defectos del producto; el PO decide OBS-28 y OBS-32."])

for s in d.sections:
    for par in s.footer.paragraphs:
        par.runs[0].text = par.runs[0].text.replace("v0.7", "v0.8")
d.save(DST)
print("plan ok", DST.name)
