"""PP-408 (HU-15) ronda 2: amplía los 5 documentos QA de v0.7 a v0.8 con los criterios de aceptación actualizados.

Ejecutar desde backend/: venv/Scripts/python.exe qa/playwright_hu33/generar_documentos_qa_ronda2.py
"""
import hashlib
import time
from copy import copy
from pathlib import Path

import openpyxl

QA = Path(__file__).resolve().parents[1]
EVD = QA / "03_Evidencias" / "HU33-HT15"
FECHA = "02/11/2026"
HORA = time.strftime("%H:%M")
COMMIT = "8a4b672 (qa-elliot, con dev; el código de exportación no cambió desde f9c0967)"
UBIC = "backend/qa/03_Evidencias/HU33-HT15/"
EXPO = "tests/routers/test_exportaciones.py::"
CRIT = "qa/03_Evidencias/HU33-HT15/test_criterios_hu15.py::"
VER = "qa/playwright_hu33/verificar_criterios.py"
R = "Local (API, worker, Beat y SMTP real con STARTTLS; bucket simulado en carpeta)"
RF = "Docker local: contenedor de 2 CPU y 512 MiB, como worker-exportaciones"
L = "Local"
ID0 = 203

# (requisito, tipo, prioridad, rol, precondición, pasos, datos, esperado, obtenido, estado, test, entorno)
CASOS = [
 ("RQ-HU15-01", "Límite", "Crítica", "Cliente Final", "API, worker y Beat en marcha", "1. Enviar 30 solicitudes seguidas, esperando a Lista entre una y otra. 2. Medir el tiempo de respuesta de cada POST.", "30 solicitudes de 2 días", "HTTP 202 y percentil 95 de aceptación de 2 s o menos.", "202 en las 30; mediana 16 ms; p95 22 ms; máximo 255 ms.", "Aprobado", VER + " (punto 1)", R),
 ("RQ-HU15-09", "Funcional", "Crítica", "Cliente Final", "Exportación Lista en CSV y en XLSX del mismo rango", "1. Abrir el CSV y el XLSX. 2. Contar filas y compararlas con una consulta directa a la BD. 3. Revisar columnas, zona horaria y decimales.", "29/10 al 31/10/2026, todos los proyectos del cliente", "Todas las filas coincidentes con las 11 columnas del criterio y fecha con zona horaria.", "38 filas en CSV y en XLSX, igual que la BD; 11 columnas; fecha con zona (-05:00); valores con 4 decimales.", "Aprobado", VER + " (punto 2)", R),
 ("RQ-HU15-09", "Funcional", "Alta", "Cliente Final", "Exportación solicitada con filtros", "1. Revisar los filtros guardados con el trabajo. 2. Solicitar un solo dispositivo.", "Rango, proyectos, dispositivo, valores", "Los filtros quedan con el trabajo y se permite exportar un dispositivo.", "fltrs_aplcds guarda rango y proyectos; un dispositivo se filtra y rechaza uno ajeno.", "Aprobado", VER + " (punto 3); " + CRIT + "test_filtros_se_conservan_y_se_permite_un_dispositivo", R),
 ("RQ-HU15-07", "Seguridad", "Crítica", "Administrador", "Exportación de otro usuario (Cliente Final)", "1. Con otro administrador, consultar y descargar la exportación ajena. 2. Consultar un identificador inexistente.", "admin@pangea-dev.com; id inexistente 99999999", "No se puede extraer datos de otro usuario, ni siquiera otro administrador.", "404 al consultar, 404 al descargar y 404 al id inexistente; el listado del administrador no la incluye.", "Aprobado", VER + " (punto 4)", R),
 ("RQ-HU15-07", "Seguridad", "Alta", "Cliente Final", "Exportación Lista de un usuario con alcance global", "1. Cambiar el alcance de la cuenta. 2. Pedir una nueva descarga.", "scp global a por_sede", "Un cambio de alcance bloquea nuevas descargas y nuevas firmas.", "403 o 404 y sin firma nueva.", "Aprobado", CRIT + "test_cambio_de_alcance_bloquea_nuevas_descargas_y_firmas", L),
 ("RQ-HU15-10", "Funcional", "Crítica", "Cliente Final", "Exportación Lista", "1. Leer la fecha límite. 2. Descargar tres veces, recargar y reenviar el correo. 3. Volver a leer la fecha.", "3 descargas y 1 reenvío", "La fecha límite no cambia, cada firma dura 60 s o menos y las 24 h empiezan al terminar la generación.", "Misma fecha límite; firmas de 60 s; fecha límite menos fin de generación = 24 h exactas.", "Aprobado", VER + " (punto 5); " + CRIT + "test_vigencia_no_cambia_al_descargar_reenviar_o_recargar", R),
 ("RQ-HU15-10", "Negativa", "Alta", "Cliente Final", "Exportación vencida", "1. Forzar el vencimiento. 2. Pedir la descarga.", "fch_exprcn = hace 1 s", "La API deniega la descarga y no genera ninguna firma.", "410 y sin firma nueva.", "Aprobado", CRIT + "test_no_firma_despues_de_vencer", L),
 ("RQ-HU15-05", "Límite", "Alta", "Sistema", "Variables de límites sin definir", "1. Leer los límites por defecto.", "Sin EXPORT_*", "31 días, 1 000 000 de filas, 100 MiB, 2 trabajos simultáneos y 24 h; configurables.", "Coinciden con los valores del criterio.", "Aprobado", CRIT + "test_limites_iniciales_son_los_del_criterio", L),
 ("RQ-HU15-05", "Límite", "Alta", "Sistema", "EXPORT_MAX_ROWS mayor que el máximo de Excel", "1. Configurar 5 000 000 de filas. 2. Leer el límite efectivo.", "EXPORT_MAX_ROWS=5000000", "Ninguna exportación supera el límite de filas de Excel.", "El límite efectivo es 1 048 575.", "Aprobado", CRIT + "test_limite_de_filas_nunca_supera_el_maximo_de_excel", L),
 ("RQ-HU15-11", "Límite", "Crítica", "Sistema", "Contenedor de 2 CPU y 512 MiB con 31 días × 1 dispositivo × 10 parámetros × 1 por minuto", "1. Generar el CSV. 2. Medir filas, duración, tamaño y memoria residente máxima.", "446 400 filas; lote por defecto", "Duración de 120 s o menos y memoria residente máxima de 256 MiB o menos.", "446 400 filas; 7,50 s; 54,92 MiB; RSS máximo 200,8 MiB; sin OOM.", "Aprobado", CRIT + "test_rendimiento_un_mes_diez_parametros_por_minuto[csv]", RF),
 ("RQ-HU15-11", "Límite", "Crítica", "Sistema", "Mismo contenedor y datos del caso anterior", "1. Generar el XLSX. 2. Medir filas, duración, tamaño y memoria residente máxima.", "446 400 filas; lote por defecto", "Duración de 120 s o menos y memoria residente máxima de 256 MiB o menos.", "446 400 filas; 62,00 s; 15,83 MiB; RSS máximo 200,6 MiB; sin OOM (ver OBS-31).", "Aprobado", CRIT + "test_rendimiento_un_mes_diez_parametros_por_minuto[xlsx]", RF),
 ("RQ-HU15-02", "Funcional", "Alta", "Sistema", "Exportación en proceso y exportación con fallo de subida", "1. Generar con éxito. 2. Generar con un fallo al subir. 3. Revisar la carpeta temporal.", "Subida con RuntimeError", "Los temporales locales se limpian al terminar normalmente y con excepción.", "Las dos carpetas temporales fueron eliminadas.", "Aprobado", CRIT + "test_temporales_locales_se_limpian_con_exito_y_con_excepcion", L),
 ("RQ-HU15-04", "E2E", "Crítica", "Cliente Final", "SMTP local con STARTTLS; el correo lo envía el código real del producto", "1. Esperar a que una exportación quede Lista. 2. Leer el correo recibido.", "31 correos recibidos en la corrida", "El correo llega con el enlace a la aplicación y la fecha de caducidad, sin adjuntos ni datos.", "Recibido para cliente@pangea-dev.com con el enlace a /consulta-datos?exportacion=ID y «Disponible hasta»; sin adjuntos.", "Aprobado", VER + " (punto 6)", R),
 ("RQ-HU15-04", "E2E", "Crítica", "Cliente Final", "SMTP detenido", "1. Detener el SMTP. 2. Solicitar una exportación. 3. Descargar. 4. Volver a levantar el SMTP y esperar.", "SMTP caído y vuelto a levantar", "El archivo sigue disponible y el correo se reintenta sin regenerarlo.", "Lista con notificación Fallida; descarga 200; correo Enviado a los 55 s; misma clave de archivo; 1 intento de generación.", "Aprobado", VER + " (punto 6)", R),
 ("RQ-HU15-06", "E2E", "Crítica", "Sistema", "Worker, Beat y almacenamiento en marcha", "1. Forzar el vencimiento de una exportación. 2. Esperar a Beat. 3. Revisar el almacén y la descarga.", "Vencimiento forzado", "El objeto vencido se elimina en menos de 5 minutos y la descarga queda denegada.", "Eliminado a los 60 s; estado Expirada; 410.", "Aprobado", VER + " (punto 7)", R),
 ("RQ-HU15-01", "E2E", "Alta", "Cliente Final", "Exportación solicitada en la interfaz", "1. Recargar la página. 2. Abrir Exportar datos. 3. Abrir el enlace con ?exportacion=ID.", "cliente@pangea-dev.com", "La interfaz conserva el identificador de la exportación después de recargar.", "El identificador sigue visible tras recargar y con el enlace.", "Aprobado", "qa/playwright_hu33/hu33.spec.mjs::HU33 recarga: la interfaz conserva el identificador de la exportación", R),
 ("RQ-HU15-03", "Seguridad", "Crítica", "QA con el usuario", "Acceso de lectura a Lightsail", "1. Comprobar con AWS real que el objeto no se descarga sin firma y que el bucket no lista públicamente.", "pangea-storage-prod (el único bucket de Lightsail; no hay uno dedicado a exportaciones)", "El objeto no se descarga sin firma y el bucket no permite listar objetos públicamente.", "Bucket private, sin sobrescritura pública; listar sin firma 403 y objeto sin firma 403. Es el bucket de los .dat, no uno dedicado (OBS-28 y PEN).", "Aprobado", "Comandos de solo lectura en CloudShell (ronda2/privacidad_aws_cloudshell.txt)", "Lightsail (producción), solo lectura"),
("RQ-HU15-04", "E2E", "Crítica", "Cliente Final", "Buzón Mailpit (SMTP local con STARTTLS) y API, worker y Beat reales", "1. Solicitar una exportación. 2. Abrir la bandeja del buzón. 3. Revisar el mensaje.", "cliente@pangea-dev.com", "El solicitante recibe el correo con el enlace a la aplicación y la fecha de caducidad, sin adjuntos ni datos.", "Llegó a la bandeja: para cliente@pangea-dev.com, asunto «Tu exportación está lista - Pangea», enlace a /consulta-datos?exportacion=41 y «Disponible hasta»; sin adjuntos.", "Aprobado", "qa/playwright_hu33/verificar_real.py (CP-220)", "Local: API, worker y Beat reales; buzón Mailpit con STARTTLS (no un buzón en internet)"),
 ("RQ-HU15-12", "E2E", "Crítica", "Cliente Final", "Servidor S3 local (moto) con bucket versionado y privado; API, worker y Beat reales", "1. Solicitar y esperar Lista. 2. Descargar con la URL firmada y sin firma. 3. Agregar una versión y un marcador de borrado. 4. Forzar el vencimiento y esperar a Beat.", "Exportación #41; 2 versiones y 1 marcador", "El flujo completo funciona y la limpieza elimina todas las versiones y marcadores en menos de 5 minutos.", "1 versión subida; la URL firmada descargó 5 780 bytes; sin firma 403; Beat eliminó 2 versiones y 1 marcador en 6 s; descarga posterior 410.", "Aprobado", "qa/playwright_hu33/verificar_real.py (CP-221)", "Local: S3 emulado con moto (no AWS real), API, worker y Beat reales"),
]
N = len(CASOS)
ULT = ID0 + N - 1
BLOQ = [i for i, c in enumerate(CASOS) if c[9] == "Bloqueado"]


def ev_de(c):
    test = c[10]
    if test.startswith(VER):
        return "Log", "ronda2/verificacion_criterios_ronda2.txt", "Registro de la verificación contra API, worker, Beat y SMTP local: " + test[len(VER) + 2:-1]
    if test.startswith("qa/playwright_hu33/verificar_real.py"):
        return "Log", "ronda2/verificacion_real_ronda2.txt", "Flujo contra S3 local y buzón Mailpit: " + test.split("(")[-1][:-1]
    if test.startswith("Comandos de solo lectura"):
        return "Log", "ronda2/privacidad_aws_cloudshell.txt", "Salida de CloudShell: bucket privado y 403 al listar y al pedir un objeto sin firma"
    if "test_rendimiento" in test:
        return "Log", "rendimiento_referencia_log.txt", "Filas, duración, tamaño y memoria en el contenedor de 2 CPU y 512 MiB"
    if CRIT in test:
        return "Fila de informe", "pytest_criterios_hu15.html", "Fila de " + test.split("::")[-1][:70]
    if test.startswith("qa/playwright_hu33/hu33.spec"):
        return "Fila de informe", "playwright/index.html", "Fila del test E2E de recarga de la interfaz"
    return "Pendiente", "", "Evidencia pendiente: " + test


EXTRA = [
 ("EV-HU33-INF-12", "CP-203", "Captura", "pytest de criterios de la ronda 2: resumen y primeras filas", "EV-HU33-INF-12_captura-pytest-criterios-ronda2.png"),
 ("EV-HU33-INF-13", "CP-203", "Informe HTML", "Informe HTML de pytest de los criterios de la ronda 2 (7 pruebas)", "pytest_criterios_hu15.html"),
 ("EV-HU33-INF-14", "CP-212", "Log", "Rendimiento en el contenedor de 2 CPU y 512 MiB (CSV y XLSX)", "rendimiento_referencia_log.txt"),
 ("EV-HU33-INF-15", "CP-212", "Log", "Resultado JUnit de las pruebas de rendimiento", "pytest_rendimiento_referencia.xml"),
 ("EV-HU33-INF-16", "CP-203", "Log", "Verificación contra procesos reales: p95, contenido, filtros, aislamiento, vigencia, SMTP y limpieza", "ronda2/verificacion_criterios_ronda2.txt"),
 ("EV-HU33-INF-17", "CP-215", "Log", "Registro del worker de Celery durante la verificación de la ronda 2", "ronda2/worker_celery_log_ronda2.txt"),
 ("EV-HU33-INF-18", "CP-217", "Log", "Beat enviando mantener-exportaciones cada 60 s", "ronda2/beat_log_ronda2.txt"),
 ("EV-HU33-INF-20", "CP-220", "Log", "Despliegue activo de producción en CloudShell: sin SMTP, sin EXPORT_S3_BUCKET y worker sin cola exportaciones", "ronda2/produccion_despliegue_cloudshell.txt"),
 ("EV-HU33-INF-21", "CP-219", "Log", "Privacidad de pangea-storage-prod en AWS real: private y 403 sin firma", "ronda2/privacidad_aws_cloudshell.txt"),
 ("EV-HU33-INF-22", "CP-221", "Log", "Flujo completo contra S3 local con versiones, URL firmada y buzón Mailpit", "ronda2/verificacion_real_ronda2.txt"),
 ("EV-HU33-E2E-06", "CP-220", "Captura", "Bandeja de Mailpit con el correo de exportación recibido", "EV-HU33-E2E-06_buzon-correo-recibido.png"),
 ("EV-HU33-INF-19", "CP-215", "Correo", "Correo recibido por SMTP con STARTTLS (el último de la corrida)", None),
 ("EV-HU33-E2E-05", "CP-218", "Captura", "Recarga de la página: la exportación conserva su identificador", "EV-HU33-E2E-05_recarga-conserva-id.png"),
]


def sha(nombre):
    p = EVD / nombre
    return round(p.stat().st_size / 1024, 1), hashlib.sha256(p.read_bytes()).hexdigest()


def estilo(ws, origen, destino, ncols):
    for c in range(1, ncols + 1):
        ws.cell(destino, c)._style = copy(ws.cell(origen, c)._style)
    if ws.row_dimensions[origen].height:
        ws.row_dimensions[destino].height = ws.row_dimensions[origen].height


def vacia(ws, col=1, ini=2):
    r = ini
    while ws.cell(r, col).value not in (None, ""):
        r += 1
    return r


def buscar(ws, valor, col=1):
    for r in range(2, ws.max_row + 1):
        if ws.cell(r, col).value == valor:
            return r
    raise KeyError(valor)


def portada(wb, extra_docs):
    ws = wb["Portada"]
    ws["B7"] = "0.8"
    ws["B8"] = ("02/11/2026 — Ronda 1 de HT-06, ronda 2 de HU-18, ronda 1 de HU-26, ronda 1 de HU-34, ronda 1 de HT-30.2 (PP-402), "
                "ronda 1 de HU-15 (PP-408) y ronda 2 de HU-15 con los criterios de aceptación actualizados")
    if extra_docs:
        ws["B5"] = ws["B5"].value.rstrip() + " " + extra_docs
    wb.calculation.fullCalcOnLoad = True


def v(a, b):
    return QA / a / f"Pangea_{b}_v0.7.xlsx", QA / a / f"Pangea_{b}_v0.8.xlsx"


ESTADOS = {}  # caso -> estado, para la RTM

# ================================ Casos ================================
src, dst = v("02_Casos_de_Prueba", "Casos_de_Prueba")
wb = openpyxl.load_workbook(src)
ws = wb["Casos de Prueba"]
r = vacia(ws)
assert r == 204, r
for k, c in enumerate(CASOS):
    req, tipo, prio, rol, pre, pasos, datos, esp, obt, estado, test, ent = c
    ev = f"EV-CP-{ID0 + k}"
    fila = [f"CP-{ID0 + k}", "HU-15", req, tipo, prio, rol, pre, pasos, datos, esp, obt, estado, "—", ev, "QA", FECHA if estado != "Bloqueado" else "—", test, ent, COMMIT]
    estilo(ws, 203, r + k, 19)
    for j, val in enumerate(fila, 1):
        ws.cell(r + k, j, val)
    ESTADOS[f"CP-{ID0 + k}"] = estado
wr = wb["Regresión"]
rr = vacia(wr)
fila_rg = ("RG-21", "Regresión", "Criterios de la ronda 2 de HU-15", "HU-15", "RQ-HU15-09", "Alta", "7 pruebas de pytest de QA, 8 verificaciones contra API, worker, Beat y SMTP local y 3 contra un S3 emulado y un buzón Mailpit.", "Cubre los criterios nuevos verificables en local.", "Cada ronda", "—", "qa/03_Evidencias/HU33-HT15/test_criterios_hu15.py y qa/playwright_hu33/verificar_criterios.py", "—", "Aprobado", FECHA, "QA", "7 de 7, 8 de 8 y 3 de 3 sobre 8a4b672; el rendimiento en contenedor se mide aparte (CP-212 y CP-213).", "", "EV-HU33-INF-12, EV-HU33-INF-16", "")
estilo(wr, rr - 1, rr, 19)
for j, val in enumerate(fila_rg, 1):
    wr.cell(rr, j, val)
f20 = buscar(wr, "RG-20")
wr.cell(f20, 16, "5 de 5 con API y worker reales; bucket simulado.")
wr.cell(f20, 18, "EV-HU33-INF-04, EV-HU33-INF-05, EV-HU33-E2E-05")
wn = wb["Pruebas No Funcionales"]
rn = vacia(wn)
NF = [
 ("NF-03", "Volumen", "HU-15", "Un mes de un dispositivo en CSV, en el worker de referencia", "446 400 filas; contenedor de 2 CPU y 512 MiB", "Duración, tamaño y memoria residente máxima", "120 s o menos y 256 MiB o menos (criterio)", "pytest en Docker (--memory 512m --cpus 2)", "7,50 s; 54,92 MiB; RSS máximo 200,8 MiB", "Cumple", "Pico del contenedor con caché de archivos: 313,9 MiB; sin OOM."),
 ("NF-04", "Volumen", "HU-15", "Un mes de un dispositivo en XLSX, en el worker de referencia", "446 400 filas; contenedor de 2 CPU y 512 MiB", "Duración, tamaño y memoria residente máxima", "120 s o menos y 256 MiB o menos (criterio)", "pytest en Docker (--memory 512m --cpus 2)", "62,00 s; 15,83 MiB; RSS máximo 200,6 MiB", "Cumple", "Pico del contenedor con caché de archivos: 492,1 MiB de 512 MiB; sin OOM (OBS-31)."),
 ("NF-05", "Carga", "HU-15", "Aceptación de solicitudes de exportación", "30 solicitudes seguidas de 2 días", "Percentil 95 del tiempo de respuesta del POST", "2 s o menos (criterio)", "Script Python con la API real", "Mediana 16 ms; p95 22 ms; máximo 255 ms", "Cumple", "Secuencial, no concurrente: la carga formal está en HT-18."),
]
for k, fila in enumerate(NF):
    estilo(wn, rn - 1, rn + k, 11)
    for j, val in enumerate(fila, 1):
        wn.cell(rn + k, j, val)
portada(wb, f"HU-15 ronda 2 (criterios de aceptación actualizados): {N} casos adicionales (CP-{ID0} a CP-{ULT}), todos aprobados; CP-220 y CP-221 con un S3 emulado y un buzón Mailpit locales, no con AWS ni un SMTP en internet.")
wb.save(dst)
print("casos ok")

# ============================== Evidencias ==============================
src, dst = v("03_Evidencias", "Registro_de_Evidencias")
wb = openpyxl.load_workbook(src)
ws = wb["Registro"]
# recalcula tamaño y hash de lo que se regeneró en esta ronda (informe de Playwright y capturas)
for fila in range(2, ws.max_row + 1):
    if ws.cell(fila, 3).value == "HU-15":
        nombre = ws.cell(fila, 6).value
        if nombre and (EVD / nombre).is_file():
            kb, h = sha(nombre)
            ws.cell(fila, 10, kb)
            ws.cell(fila, 11, h)
r = vacia(ws)
filas = []
for k, c in enumerate(CASOS):
    tipo, nombre, que = ev_de(c)
    if nombre:
        kb, h = sha(nombre)
        filas.append((f"EV-CP-{ID0 + k}", f"CP-{ID0 + k}", "HU-15", tipo, que, nombre, UBIC, "QA", f"{FECHA} {HORA}", kb, h, COMMIT, "Adjuntada", c[9], ""))
    else:
        filas.append((f"EV-CP-{ID0 + k}", f"CP-{ID0 + k}", "HU-15", "Log", que, "—", "—", "QA", "—", "—", "—", "—", "Pendiente", "Bloqueado", "Requiere un buzón de QA con SMTP real (OBS-32) o un bucket de exportaciones dedicado (OBS-28 y PEN)."))
ultimo_eml = sorted((EVD / "ronda2" / "correos_smtp").glob("*.eml"))[-1]
for ide, caso, tipo, que, nombre in EXTRA:
    if nombre is None:
        nombre = f"ronda2/correos_smtp/{ultimo_eml.name}"
    kb, h = sha(nombre)
    filas.append((ide, caso, "HU-15", tipo, que, nombre, UBIC, "QA", f"{FECHA} {HORA}", kb, h, COMMIT, "Adjuntada", "Aprobado", ""))
for k, f in enumerate(filas):
    estilo(ws, r - 1, r + k, 15)
    for j, val in enumerate(f, 1):
        ws.cell(r + k, j, val)
N_EVID = len(filas)
portada(wb, "")
wb.save(dst)
print("evidencias ok", N_EVID)

# ============================== Defectos ==============================
src, dst = v("04_Defectos", "Registro_de_Defectos")
wb = openpyxl.load_workbook(src)
ws = wb["Observaciones"]
cierre = {
    "OBS-25": "El criterio actualizado dice «No imponer pandas como dependencia»: la técnica actual (csv y openpyxl por lotes) es la esperada.",
    "OBS-26": "El criterio actualizado fija URL firmada de hasta 60 s, sin extender la vigencia del archivo: el diseño actual es el esperado.",
    "OBS-27": "Medido en el worker de referencia (2 CPU y 512 MiB): XLSX en 62,00 s y CSV en 7,50 s, dentro de los 120 s del criterio (NF-03 y NF-04).",
}
for oid, texto in cierre.items():
    f = buscar(ws, oid)
    ws.cell(f, 8, "Aceptada")
    ws.cell(f, 13, FECHA)
    ws.cell(f, 14, texto)
f = buscar(ws, "OBS-28")
ws.cell(f, 2, "CP-219, CP-220, CP-221")
ws.cell(f, 4, "Los criterios piden comprobar con servicios reales (AWS, SMTP) y no con simulaciones. QA lo hizo así: la privacidad de pangea-storage-prod con AWS real en solo lectura (CP-219: private y 403 sin firma), y el flujo completo (CP-221) y el correo (CP-220) con un servidor S3 emulado (moto) y un buzón SMTP con STARTTLS (Mailpit) en local, sin gastar en AWS. Eso no es AWS ni un buzón en internet. El criterio dice «contra AWS real»: el PO debe aceptar que la validación local cumple.")
ws.cell(f, 5, "El PO confirma si la validación local (moto y Mailpit) cumple el criterio, o pide repetirla con un bucket de prueba en Lightsail y un SMTP real.")
ws.cell(f, 9, "Decisión del PO"); ws.cell(f, 11, "PO")
f = buscar(ws, "OBS-29")
ws.cell(f, 2, "CP-195, CP-196, CP-199, CP-217")
r = vacia(ws)
OBS = [
 ("OBS-31", "CP-213", "HU-15", "En el contenedor de 512 MiB, la exportación XLSX de un mes llegó a 492,1 MiB de memoria del contenedor (incluye la caché de archivos del sistema). La memoria residente del proceso fue de 200,6 MiB y no hubo OOM, pero el margen frente al límite es corto.", "Vigilar el consumo en Lightsail dentro de HT-18; valorar recomendar CSV para rangos largos.", "QA", FECHA, "Abierta", "Mejora técnica", "Baja", "Dev", "", "", ""),
 ("OBS-32", "CP-220", "HU-15", "El correo se verificó con el código real enviando por SMTP con STARTTLS a un buzón local (Mailpit), no a un buzón en internet. Para el criterio «recepción en el entorno de QA» es una prueba de entrega real al buzón del entorno, pero no pasa por un proveedor de correo.", "Ver OBS-28: el PO confirma si basta con el buzón local o pide repetirlo con un SMTP real.", "QA", FECHA, "Abierta", "Decisión del PO", "Baja", "PO", "", "", ""),
]
for k, f_ in enumerate(OBS):
    estilo(ws, r - 1, r + k, 14)
    for j, val in enumerate(f_, 1):
        ws.cell(r + k, j, val)
pe = wb["Pendientes de entrega"]
rp = vacia(pe)
sig = max(int(str(pe.cell(i, 1).value)[4:]) for i in range(2, rp) if str(pe.cell(i, 1).value).startswith("PEN-")) + 1
estilo(pe, rp - 1, rp, 11)
for j, val in enumerate((f"PEN-{sig:02d}", "—", "HU-15", "Precondiciones para desplegar HU33 en producción: (1) bucket privado dedicado y EXPORT_S3_BUCKET; (2) variables SMTP en el worker; (3) un worker para la cola exportaciones (el worker actual arranca sin --queues). Producción corre hoy la imagen api-b948aac.16 (16/10/2026), que no incluye la exportación (llegó el 30/10/2026).", "Dev y PO", "—", "Por hacer: nota para el despliegue", "Cuando se despliegue HU33", "No (de PP-285 ni PP-408)", "Hallazgo de QA al revisar el despliegue activo de pangea-api", "No es un defecto ni bloquea a QA. Evidencia: ronda2/produccion_despliegue_cloudshell.txt. El PO decide además si el bucket debe ser dedicado o basta el prefijo exportaciones/ en pangea-storage-prod."), 1):
    pe.cell(rp, j, val)
wh = wb["Historial de rondas"]
rh = vacia(wh)
fila = ("2", "HU-15", FECHA, COMMIT, str(N), str(N - len(BLOQ)), "0", str(len(BLOQ)), "0", "0", "2", str(N_EVID),
        "Segunda ronda de HU-15 con los criterios actualizados: pytest de QA, procesos reales (API, worker, Beat y SMTP local) y rendimiento en un contenedor de 2 CPU y 512 MiB; 0 defectos; "
        "19 de 19 aprobados: CP-219 contra AWS real (solo lectura) y CP-220 y CP-221 con un S3 emulado (moto) y un buzón Mailpit locales; el PO debe aceptar que eso cumple «servicios reales» (OBS-28 y OBS-32); OBS-25, OBS-26 y OBS-27 aceptadas.")
estilo(wh, rh - 1, rh, 13)
for j, val in enumerate(fila, 1):
    wh.cell(rh, j, val)
portada(wb, "")
wb.save(dst)
print("defectos ok")

# ================================ RTM ================================
src, dst = v("05_Matriz_Trazabilidad_RTM", "Matriz_Trazabilidad_RTM")
wb = openpyxl.load_workbook(src)
ws = wb["RTM"]
por_req = {}
for k, c in enumerate(CASOS):
    por_req.setdefault(c[0], []).append(f"CP-{ID0 + k}")
filas_rtm = {ws.cell(r_, 1).value: r_ for r_ in range(2, ws.max_row + 1) if str(ws.cell(r_, 1).value).startswith("RQ-HU15")}
r_nueva = vacia(ws)
NUEVOS = {
 "RQ-HU15-09": "Contenido completo y filtros reproducibles: todas las filas coincidentes con sus 11 columnas, filtros conservados y un dispositivo permitido.",
 "RQ-HU15-10": "Vigencia y descarga: 24 h desde que termina la generación, misma fecha tras descargar o reenviar, firmas de 60 s y descarga denegada al vencer.",
 "RQ-HU15-11": "Rendimiento verificable: 31 días, 1 dispositivo, 10 parámetros por minuto (446 400 filas) en un worker de 2 CPU y 512 MiB, en 120 s o menos y con 256 MiB o menos de memoria residente.",
 "RQ-HU15-12": "Integración real: el flujo completo funciona con el bucket privado real, Celery, Redis y Beat, y limpia versiones y marcadores.",
}
BACK = {"RQ-HU15-09": "PP-283", "RQ-HU15-10": "PP-285", "RQ-HU15-11": "PP-284", "RQ-HU15-12": "PP-408"}
OBS_RQ = {"RQ-HU15-01": "—", "RQ-HU15-02": "OBS-31", "RQ-HU15-03": "OBS-28", "RQ-HU15-04": "OBS-32", "RQ-HU15-06": "OBS-29", "RQ-HU15-12": "OBS-28", "RQ-HU15-11": "OBS-31"}
for rid, txt in NUEVOS.items():
    estilo(ws, r_nueva - 1, r_nueva, 13)
    ws.cell(r_nueva, 1, rid); ws.cell(r_nueva, 2, txt)
    ws.cell(r_nueva, 3, "HU-15 — criterios de aceptación actualizados (ronda 2)")
    ws.cell(r_nueva, 4, "HU-15"); ws.cell(r_nueva, 5, BACK[rid]); ws.cell(r_nueva, 6, "Alta")
    ws.cell(r_nueva, 11, "—"); ws.cell(r_nueva, 12, "—"); ws.cell(r_nueva, 13, "RG-21" if rid != "RQ-HU15-12" else "—")
    fm = ws.cell(r_nueva - 1, 8).value
    for col in (8, 9):
        ws.cell(r_nueva, col).value = ws.cell(r_nueva - 1, col).value.replace(str(r_nueva - 1), str(r_nueva))
    filas_rtm[rid] = r_nueva
    r_nueva += 1
for rid, fila in filas_rtm.items():
    nuevos = por_req.get(rid, [])
    previos = ws.cell(fila, 7).value or ""
    if nuevos:
        ws.cell(fila, 7, ", ".join([x for x in [previos] if x] + nuevos))
    todos = [x.strip() for x in (ws.cell(fila, 7).value or "").split(",") if x.strip()]
    estados = ["Aprobado" if int(x[3:]) < ID0 else ESTADOS.get(x, "Aprobado") for x in todos]
    ok = estados.count("Aprobado")
    ws.cell(fila, 10, "Aprobado" if ok == len(estados) else ("Bloqueado" if ok == 0 else f"Parcial ({ok}/{len(estados)})"))
    if rid in OBS_RQ:
        previo = ws.cell(fila, 12).value
        ws.cell(fila, 12, OBS_RQ[rid] if previo in (None, "—", "") else ", ".join(dict.fromkeys(x.strip() for x in (previo + ", " + OBS_RQ[rid]).split(",") if x.strip() and x.strip() != "—")))
    if rid in ("RQ-HU15-03", "RQ-HU15-04", "RQ-HU15-06"):
        ws.cell(fila, 13, ws.cell(fila, 13).value)
hist = wb["Historias"]
fh = buscar(hist, "HU-15")
hist.cell(fh, 8, ", ".join(filas_rtm))
hist.cell(fh, 17, "Sin defectos del producto ni entregas pendientes de las subtareas. Quedan decisiones del PO: OBS-28 y OBS-32 (los servicios reales se probaron en local con un S3 emulado y un buzón Mailpit) y, para cuando se despliegue HU33 a producción, las precondiciones de PEN-06. PP-286 figura En curso en Jira aunque su código está entregado (OBS-29).")
hist.cell(fh, 18, "Probado sobre 8a4b672: qa-elliot con dev; el código de exportación (tasks/exportaciones.py, services/exportaciones.py, services/exportaciones_storage.py, routers/exportaciones.py y ExportacionesPanel.tsx) no cambió desde f9c0967 (Jareth).")
wf = wb["Fuente casos"]
rf = vacia(wf)
for k, c in enumerate(CASOS):
    estilo(wf, rf - 1, rf + k, 3)
    wf.cell(rf + k, 1, f"CP-{ID0 + k}"); wf.cell(rf + k, 2, "HU-15"); wf.cell(rf + k, 3, c[9])
portada(wb, "")
wb.save(dst)
print("rtm ok")
