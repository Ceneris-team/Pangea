"""PP-408 (HU-15): amplía los 5 documentos QA de Pangea de v0.6 a v0.7 con la ronda 1 de HU-15.

Ejecutar desde backend/: venv/Scripts/python.exe qa/playwright_hu33/generar_documentos_qa.py
"""
import hashlib
import time
from copy import copy
from pathlib import Path

import openpyxl
from openpyxl.worksheet.cell_range import CellRange

QA = Path(__file__).resolve().parents[1]
EVD = QA / "03_Evidencias" / "HU33-HT15"
FECHA = "02/11/2026"
HORA = time.strftime("%H:%M")
COMMIT = "827755e (qa-elliot, incluye dev f9c0967)"
UBIC = "backend/qa/03_Evidencias/HU33-HT15/"
EXPO = "tests/routers/test_exportaciones.py::"
STOR = "tests/services/test_exportaciones_storage.py::"
CORR = "tests/services/test_exportaciones_correo.py::"
PW = "qa/playwright_hu33/hu33.spec.mjs::HU33 "
L = "Local"
LB = "Local (API y worker reales; bucket simulado en carpeta)"
ID0 = 172

# (requisito, tipo, prioridad, rol, precondición, pasos, datos, esperado, obtenido, estado, test, entorno)
CASOS = [
 ("RQ-HU15-01", "Funcional", "Crítica", "Cliente Final", "BD de test migrada; Celery y S3 simulados", "1. POST /exportaciones con un rango de 1 día. 2. Revisar la respuesta y el registro.", "Proyecto del seed, rango de 1 día, formato csv", "Responde 202; el registro queda Pendiente sin objeto_clave y no hay archivo en el almacén; la tarea se encola.", "202; estado Pendiente; objeto_clave nulo; almacén vacío; encolar_exportacion llamada una vez.", "Aprobado", EXPO + "test_solicitud_no_genera_archivo_en_http_y_persiste_antes_de_encolar", L),
 ("RQ-HU15-01", "E2E", "Crítica", "Cliente Final", "API y worker en marcha; sesión del Cliente Final", "1. Abrir Consulta de datos > Exportar datos. 2. Fijar 29/10 al 31/10. 3. Pulsar Solicitar exportación. 4. Cambiar el formato mientras se prepara.", "cliente@pangea-dev.com (seed), rango 29/10/2026 a 31/10/2026", "Mensaje de confirmación en menos de 5 s; la interfaz sigue usable; la solicitud aparece en la lista.", "Mensaje en 389 ms; el selector de formato respondió; apareció «#N · CSV · Pendiente/En proceso».", "Aprobado", PW + "CA1 solicitar exportación responde de inmediato y no bloquea la interfaz", LB),
 ("RQ-HU15-01", "Funcional", "Alta", "Cliente Final", "Solicitud Pendiente cuya publicación en el broker falló", "1. Crear la solicitud con el broker caído. 2. Ejecutar mantener_exportaciones.", "Broker simulado con error", "La solicitud no se pierde: Beat la vuelve a publicar.", "La solicitud Pendiente se recupera y se encola de nuevo.", "Aprobado", EXPO + "test_recupera_solicitud_si_no_se_publico_en_broker", L),
 ("RQ-HU15-01", "Funcional", "Media", "Cliente Final", "Exportación En proceso con más de 25 minutos", "1. Ejecutar mantener_exportaciones.", "fch_inicio hace 25 min", "Se marca Fallida con mensaje claro y libera el cupo del usuario.", "Fallida con «Se agotó el tiempo de procesamiento…»; el cupo queda libre.", "Aprobado", EXPO + "test_exportacion_atascada_libera_cupo", L),
 ("RQ-HU15-01", "Negativa", "Media", "Cliente Final", "Usuario con el máximo de exportaciones activas (2)", "1. Solicitar una tercera exportación.", "EXPORT_MAX_ACTIVE_PER_USER=2", "La API rechaza la solicitud sin crear trabajo.", "Rechazada; no se crea el registro.", "Aprobado", EXPO + "test_limita_solicitudes_simultaneas", L),
 ("RQ-HU15-01", "Funcional", "Alta", "Sistema", "Exportación Pendiente", "1. Ejecutar generar_exportacion dos veces con el mismo id.", "Reentrega de la tarea", "La segunda ejecución no duplica el archivo ni la notificación.", "Un solo objeto y una sola notificación.", "Aprobado", EXPO + "test_reentrega_de_la_tarea_no_duplica_archivo_ni_notificacion", L),
 ("RQ-HU15-02", "Límite", "Crítica", "Sistema", "10 parámetros × 1 dispositivo × 31 días × 1 lectura por minuto en la BD de test", "1. Solicitar un mes completo en CSV. 2. Ejecutar generar_exportacion. 3. Medir tiempo y pico de memoria.", "446 400 filas; EXPORT_CHUNK_ROWS=500", "Termina sin error de memoria ni timeout (CA2); pico bajo 256 MiB y menos de 120 s.", "Lista con 446 400 filas en 8,55 s; pico de memoria 202,86 MiB.", "Aprobado", EXPO + "test_mes_completo_por_minuto_con_memoria_acotada[csv]", L),
 ("RQ-HU15-02", "Límite", "Crítica", "Sistema", "Mismo conjunto de datos del caso anterior", "1. Solicitar el mes completo en XLSX. 2. Ejecutar generar_exportacion. 3. Medir tiempo y pico de memoria.", "446 400 filas; EXPORT_CHUNK_ROWS=500", "Termina sin error de memoria ni timeout (CA2); pico bajo 256 MiB y menos de 120 s.", "Lista con 446 400 filas en 86,59 s; pico de memoria 202,87 MiB (ver OBS-27).", "Aprobado", EXPO + "test_mes_completo_por_minuto_con_memoria_acotada[xlsx]", L),
 ("RQ-HU15-02", "Funcional", "Alta", "Sistema", "Datos de dos empresas, números y textos, varias páginas de lotes", "1. Exportar en CSV y en XLSX. 2. Contar filas y revisar el contenido.", "Seed de test de dos empresas", "El archivo trae todas las páginas, números y eventos de texto, sin datos de otra empresa.", "Todas las filas del cliente; ninguna de la otra empresa.", "Aprobado", EXPO + "test_exporta_todas_las_paginas_numeros_y_textos_sin_datos_de_otra_empresa[csv|xlsx]", L),
 ("RQ-HU15-02", "Funcional", "Media", "Sistema", "Lecturas por minuto de un dispositivo", "1. Exportar con filtro de valor y con frecuencia de muestreo.", "valor_min/valor_max; frecuencia_muestreo", "El archivo respeta el filtro numérico y el muestreo pedido.", "Solo filas dentro del filtro y una por intervalo.", "Aprobado", EXPO + "test_respeta_filtro_numerico_y_muestreo_explicito", L),
 ("RQ-HU15-03", "Seguridad", "Crítica", "Sistema", "Almacén de exportaciones configurado", "1. Intentar subir con política pública, con ACL pública y sin poder verificar la privacidad.", "Bucket con AllUsers / AuthenticatedUsers / política pública", "No se sube nada a un bucket público ni a uno cuya privacidad no se puede verificar.", "Se rechaza en los tres escenarios; un bucket sin política no se toma como público.", "Aprobado", STOR + "test_no_sube_a_bucket_con_politica_publica, test_no_sube_a_bucket_con_acl_publica, test_bucket_sin_politica_no_implica_publico, test_no_asume_privacidad_si_no_puede_verificarla", L),
 ("RQ-HU15-03", "Seguridad", "Alta", "Cliente Final", "Exportación Lista", "1. POST /descarga. 2. Repetir con otro entorno, otro usuario y con la exportación vencida.", "Identidad simulada", "Devuelve URL firmada de vida corta solo al propietario y en su entorno; 404 para otro entorno o usuario; 410 si venció.", "200 con firma de 60 s o menos; 404; 404; 410.", "Aprobado", EXPO + "test_descarga_revalida_propietario_entorno_y_expiracion", L),
 ("RQ-HU15-03", "E2E", "Alta", "Cliente Final", "Exportación Lista en la interfaz", "1. Pulsar Descargar. 2. Revisar la respuesta de /descarga.", "Exportación del caso CP-173", "La descarga responde 200 con una URL firmada con expiración.", "200; la URL trae X-Expires=60.", "Aprobado", PW + "CA3 la exportación queda Lista con vigencia de 24 horas y se descarga", LB),
 ("RQ-HU15-03", "Funcional", "Media", "Sistema", "Fallo transitorio de S3 durante la subida", "1. Ejecutar generar_exportacion con error de red en la subida. 2. Reintentar.", "BotoCoreError simulado", "Reintenta con la misma clave y no deja archivos huérfanos.", "Misma clave; sin objetos huérfanos; vuelve a Pendiente hasta 3 intentos.", "Aprobado", EXPO + "test_error_transitorio_reusa_clave_y_no_deja_archivos_huerfanos", L),
 ("RQ-HU15-04", "Funcional", "Crítica", "Cliente Final", "SMTP simulado", "1. Ejecutar enviar_correo_exportacion.", "Enlace a la app y fecha de expiración", "El correo lleva el enlace a la app y la fecha de vencimiento, sin adjuntar datos.", "Correo con enlace, vigencia y sin adjuntos.", "Aprobado", CORR + "test_correo_real_usa_smtp_y_enlace_a_app_sin_adjuntar_datos", L),
 ("RQ-HU15-04", "Negativa", "Alta", "Sistema", "Sin SMTP configurado", "1. Ejecutar enviar_correo_exportacion.", "SMTP_HOST vacío", "No se marca la notificación como enviada.", "Lanza error; notificacion_estado no pasa a Enviada.", "Aprobado", CORR + "test_exportacion_sin_smtp_no_se_marca_como_enviada", L),
 ("RQ-HU15-04", "Funcional", "Alta", "Sistema", "Exportación Lista con correo fallido", "1. Ejecutar notificar_exportacion de nuevo.", "Fallo de correo simulado", "Reintenta el correo sin regenerar el archivo.", "Correo enviado en el reintento; sin nuevo archivo.", "Aprobado", EXPO + "test_notificacion_se_reintenta_sin_regenerar_archivo", L),
 ("RQ-HU15-04", "E2E", "Crítica", "Cliente Final", "API y worker (colas exportaciones y celery) en marcha", "1. Solicitar la exportación. 2. Esperar a Lista. 3. Revisar la interfaz y el correo enviado.", "cliente@pangea-dev.com", "La exportación queda Lista con «Disponible hasta» a 24 h y el correo con enlace sale a la dirección del usuario.", "Lista con vigencia de 24,00 h; correo a cliente@pangea-dev.com con enlace y expira_en a 24 h.", "Aprobado", PW + "CA3 la exportación queda Lista con vigencia de 24 horas y se descarga", LB),
 ("RQ-HU15-05", "Límite", "Crítica", "Cliente Final", "Límite EXPORT_MAX_DAYS=31", "1. POST /exportaciones con 40 días.", "fecha_inicio = hoy − 40 días", "422 con mensaje claro de 31 días y sin crear trabajo (CA5).", "422 «El rango máximo por exportación es de 31 días. Divide la consulta en varios periodos.»; 0 registros nuevos.", "Aprobado", EXPO + "test_limite_de_rango_se_rechaza_antes_de_crear_trabajo", L),
 ("RQ-HU15-05", "Negativa", "Alta", "Cliente Final", "Sesión del Cliente Final", "1. POST con formato pdf, fecha sin zona horaria, valor_min mayor que valor_max y cliente ajeno.", "4 cuerpos inválidos", "La API rechaza cada solicitud inválida.", "Las 4 rechazadas.", "Aprobado", EXPO + "test_rechaza_solicitudes_invalidas[cambios0..3]", L),
 ("RQ-HU15-05", "E2E", "Crítica", "Cliente Final", "Sesión del Cliente Final", "1. Fijar 01/09 al 31/10 (60 días). 2. Pulsar Solicitar exportación.", "Rango de 60 días", "Mensaje claro con el máximo de días; no se crea solicitud (CA5).", "«El máximo por exportación es de 31 días. Aplica un rango menor.»; la lista no cambió.", "Aprobado", PW + "CA5 un rango mayor al máximo se rechaza con mensaje claro", LB),
 ("RQ-HU15-05", "Límite", "Alta", "Sistema", "EXPORT_MAX_ROWS y EXPORT_MAX_BYTES reducidos", "1. Generar con topes excedidos en CSV y XLSX.", "Topes bajos", "Falla con mensaje claro y no publica archivo parcial.", "Fallida con mensaje; sin objeto en el almacén.", "Aprobado", EXPO + "test_falla_sin_publicar_archivo_parcial_si_supera_filas, test_limite_de_bytes_no_publica_archivo_parcial[csv|xlsx]", L),
 ("RQ-HU15-05", "Funcional", "Media", "Cliente Final", "Panel de exportaciones abierto", "1. Abrir Exportar datos.", "—", "El panel informa el máximo de días, de registros y la vigencia.", "«Máximo 31 días y 1,000,000 registros. Disponible durante 24 horas…».", "Aprobado", PW + "el panel informa límite de rango y vigencia de 24 horas", LB),
 ("RQ-HU15-06", "Funcional", "Crítica", "Sistema", "Exportación Lista con vigencia vencida", "1. Ejecutar mantener_exportaciones. 2. POST /descarga.", "fch_exprcn = hace 1 s", "Elimina el objeto (todas sus versiones), marca Expirada y la descarga responde 410 (CA4).", "eliminadas=1; objeto borrado; estado Expirada; 410.", "Aprobado", EXPO + "test_limpieza_elimina_version_expirada_y_bloquea_descarga", L),
 ("RQ-HU15-06", "E2E", "Crítica", "Sistema", "API y worker reales; vigencia forzada a vencida", "1. Solicitar y esperar Lista. 2. Forzar el vencimiento. 3. Ejecutar mantener_exportaciones. 4. Revisar el almacén y POST /descarga.", "Exportación #6 del seed", "El archivo desaparece del almacén al vencer y el enlace deja de servir (CA4).", "Objeto borrado, estado Expirada, objeto_clave nulo, 410.", "Aprobado", "qa/playwright_hu33/verificar_ca4.py", LB),
 ("RQ-HU15-06", "Funcional", "Alta", "Sistema", "Exportación vencida con S3 caído", "1. Ejecutar mantener_exportaciones con error al borrar.", "Fallo de borrado simulado", "No marca el archivo como borrado; lo reintenta.", "Sigue con objeto_clave; se reintenta en la siguiente corrida.", "Aprobado", EXPO + "test_falla_de_limpieza_se_reintenta_sin_marcar_borrado", L),
 ("RQ-HU15-06", "Funcional", "Alta", "Sistema", "Bucket versionado con varias exportaciones", "1. Eliminar una exportación. 2. Simular errores parciales de S3.", "Versiones y marcadores de borrado", "Borra todas las versiones de esa clave, no toca otras exportaciones y no confirma el borrado si S3 informa errores.", "Solo se borran las versiones de su clave; con errores parciales lanza error.", "Aprobado", STOR + "test_preserva_version_para_eliminacion_real, test_limpieza_versionada_no_toca_otras_exportaciones, test_no_confirma_borrado_si_s3_informa_errores_parciales", L),
 ("RQ-HU15-06", "Funcional", "Alta", "Sistema", "Configuración de Celery", "1. Leer celery_app.conf.beat_schedule.", "—", "La limpieza está programada en Beat de forma periódica.", "mantener-exportaciones-cada-minuto cada 60 s.", "Aprobado", "qa/03_Evidencias/HU33-HT15/celery_beat_schedule.txt", L),
 ("RQ-HU15-07", "Seguridad", "Crítica", "Cliente Final", "Dos proyectos y un dispositivo de otro proyecto", "1. Listar dispositivos y exportaciones. 2. Solicitar un proyecto y un dispositivo fuera del entorno.", "Seed de test", "El selector y el listado respetan el entorno; lo ajeno se rechaza con 403.", "Solo los del entorno; 403 en lo ajeno.", "Aprobado", EXPO + "test_selector_de_dispositivos_y_listado_respetan_entorno, test_rechaza_proyecto_y_dispositivo_fuera_del_entorno", L),
 ("RQ-HU15-07", "Seguridad", "Crítica", "Cliente Final", "Exportación solicitada", "1. Desactivar al usuario o revocar su proyecto. 2. Generar y descargar.", "Usuario desactivado; permiso revocado", "No se genera ni se descarga después de perder el acceso.", "403 al generar y al descargar.", "Aprobado", EXPO + "test_no_genera_ni_descarga_despues_de_desactivar_usuario, test_revalida_revocacion_de_proyecto_del_lector", L),
 ("RQ-HU15-08", "Regresión", "Alta", "QA", "Suites del backend", "1. Ejecutar pytest sobre tests/ (sin carga). 2. Comparar con la línea base de HT-30.2.", "879 pruebas", "Ninguna falla nueva ni en exportaciones; las fallas conocidas coinciden con OBS-11.", "783 aprobadas, 96 fallidas (OBS-11); 0 fallas en exportaciones. Línea base HT-30.2: 782 y 97.", "Aprobado", "backend/tests (pytest_regresion.html)", L),
]
N = len(CASOS)
ULT = ID0 + N - 1  # CP-202


def ev_de(c):
    test = c[10]
    if "mes_completo" in test:
        return "Fila de informe", "pytest_benchmark_mes.html", f"Fila de {test.split('::')[-1]} con tiempo y pico de memoria"
    if test.startswith(PW):
        return "Fila de informe", "playwright/index.html", f"Fila del test E2E «{test.replace(PW, '')[:70]}»"
    if "verificar_ca4" in test:
        return "Log", "verificacion_ca4_eliminacion.txt", "Registro de CA4: solicitud, Lista, vencimiento forzado, limpieza, objeto borrado y 410"
    if "celery_beat" in test:
        return "Log", "celery_beat_schedule.txt", "Programación de Beat: mantener-exportaciones-cada-minuto cada 60 s"
    if test.startswith("backend/tests"):
        return "Fila de informe", "pytest_regresion.html", "Resumen de la regresión completa del backend: 783 aprobadas y 96 fallidas por OBS-11"
    return "Fila de informe", "pytest_exportaciones.html", f"Fila de {test.split('::')[-1][:75]}"


EXTRA = [
 ("EV-HU33-INF-01", "CP-172", "Captura", "pytest de exportaciones: resumen (37 aprobadas) y primeras 10 filas", "EV-HU33-INF-01_captura-pytest-exportaciones-extracto.png"),
 ("EV-HU33-INF-02", "CP-178", "Captura", "Benchmark de un mes completo (CSV y XLSX)", "EV-HU33-INF-02_captura-benchmark-mes-completo.png"),
 ("EV-HU33-INF-03", f"CP-{ULT}", "Captura", "Regresión completa del backend: resumen (783 aprobadas, 96 fallidas) y primeras 8 filas", "EV-HU33-INF-03_captura-regresion-extracto.png"),
 ("EV-HU33-INF-04", "CP-173", "Captura", "Informe de Playwright de HU33: 4 pruebas aprobadas", "EV-HU33-INF-04_captura-informe-playwright.png"),
 ("EV-HU33-INF-05", "CP-173", "Informe HTML", "Informe HTML completo de Playwright (4 pruebas)", "playwright/index.html"),
 ("EV-HU33-INF-06", "CP-172", "Informe HTML", "Informe HTML completo de pytest de exportaciones (37 pruebas)", "pytest_exportaciones.html"),
 ("EV-HU33-INF-07", "CP-178", "Informe HTML", "Informe HTML del benchmark de un mes (2 pruebas)", "pytest_benchmark_mes.html"),
 ("EV-HU33-INF-08", f"CP-{ULT}", "Informe HTML", "Informe HTML de la regresión completa (879 pruebas)", "pytest_regresion.html"),
 ("EV-HU33-INF-09", "CP-189", "Log", "Registro del worker de Celery (generar y notificar) durante las pruebas", "worker_celery_log.txt"),
 ("EV-HU33-INF-10", "CP-189", "Log", "Correos de exportación emitidos por el worker (destinatario, enlace, vencimiento)", "correos_enviados.jsonl"),
 ("EV-HU33-INF-11", "CP-183", "Log", "URL firmadas emitidas al descargar (expiración de 60 s)", "firmas_generadas.jsonl"),
 ("EV-HU33-E2E-01", "CP-194", "Captura", "Panel de exportación con el límite de 31 días y la vigencia de 24 horas", "EV-HU33-E2E-01_panel-limites.png"),
 ("EV-HU33-E2E-02", "CP-173", "Captura", "Solicitud confirmada de inmediato; la lista muestra la exportación en proceso", "EV-HU33-E2E-02_solicitud-en-proceso.png"),
 ("EV-HU33-E2E-03", "CP-192", "Captura", "Rango excedido: mensaje claro de 31 días máximos", "EV-HU33-E2E-03_rango-excedido.png"),
 ("EV-HU33-E2E-04", "CP-189", "Captura", "Exportación Lista con «Disponible hasta» y botón Descargar", "EV-HU33-E2E-04_exportacion-lista.png"),
]
N_EVID = N + len(EXTRA)

DOCS_TXT = {
    "casos": ", HU-15 Pipeline de exportación en background con Celery (HU33; ronda 1: %d casos, todos aprobados, y 2 pruebas no funcionales de volumen)." % N,
}


def ruta(carpeta, nombre):
    return QA / carpeta / f"Pangea_{nombre}_v0.6.xlsx", QA / carpeta / f"Pangea_{nombre}_v0.7.xlsx"


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


def portada(wb, texto_docs):
    ws = wb["Portada"]
    ws["B7"] = "0.7"
    ws["B8"] = ("02/11/2026 — Ronda 1 de HT-06, ronda 2 de HU-18, ronda 1 de HU-26, ronda 1 de HU-34, "
                "ronda 1 de HT-30.2 (PP-402) y ronda 1 de HU-15 (PP-408)")
    if texto_docs:
        ws["B5"] = texto_docs(ws["B5"].value)
    wb.calculation.fullCalcOnLoad = True


def sha(nombre):
    p = EVD / nombre
    return round(p.stat().st_size / 1024, 1), hashlib.sha256(p.read_bytes()).hexdigest()


# ============================== Casos de prueba ==============================
src, dst = ruta("02_Casos_de_Prueba", "Casos_de_Prueba")
wb = openpyxl.load_workbook(src)
ws = wb["Casos de Prueba"]
r = vacia(ws)
assert r == 173, r
for k, c in enumerate(CASOS):
    req, tipo, prio, rol, pre, pasos, datos, esp, obt, estado, test, ent = c
    fila = [f"CP-{ID0 + k}", "HU-15", req, tipo, prio, rol, pre, pasos, datos, esp, obt, estado, "—", f"EV-CP-{ID0 + k}", "QA", FECHA, test, ent, COMMIT]
    estilo(ws, 172, r + k, 19)
    for j, val in enumerate(fila, 1):
        ws.cell(r + k, j, val)

wr = wb["Regresión"]
rr = vacia(wr)
assert rr == 19, rr
REG = [
 ("RG-18", "Humo", f"Exportaciones del backend (CP-{ID0} a CP-{ULT - 1})", "HU-15", "RQ-HU15-01", "Alta", "Los 37 tests de exportación, almacén y correo.", "Cubre los 6 puntos del procedimiento de PP-408.", "Cada ronda y antes de pasar a producción", "—", "backend/tests/routers/test_exportaciones.py, tests/services/test_exportaciones_storage.py y test_exportaciones_correo.py", "—", "Aprobado", FECHA, "QA", "37 de 37 en 02:25 min sobre 827755e.", "", "EV-HU33-INF-01, EV-HU33-INF-06", ""),
 ("RG-19", "Regresión", "Suite completa del backend", "HU-15", "RQ-HU15-08", "Alta", "Todas las pruebas de backend/tests (sin carga).", "Línea base de regresión de HU-15.", "Cada ronda", "—", "backend/tests (pytest)", "—", "Aprobado", FECHA, "QA", "Backend 783 de 879; las 96 fallidas son las de OBS-11 (fixtures sin suscripción); ninguna en exportaciones. Línea base de HT-30.2: 782 de 879 y 97 fallidas.", "", "EV-HU33-INF-03, EV-HU33-INF-08", "96 por OBS-11 (tests sin suscripción vigente)"),
 ("RG-20", "Humo", "Flujo de exportación en la interfaz", "HU-15", "RQ-HU15-01", "Alta", "Panel de exportación: límites, solicitud sin bloqueo, rango excedido y descarga.", "Flujo visible al usuario de HU33.", "Cada ronda", "—", "qa/playwright_hu33/hu33.spec.mjs", "—", "Aprobado", FECHA, "QA", "4 de 4 con API y worker reales; bucket simulado.", "", "EV-HU33-INF-04, EV-HU33-INF-05", ""),
]
for k, fila in enumerate(REG):
    estilo(wr, 18, rr + k, 19)
    for j, val in enumerate(fila, 1):
        wr.cell(rr + k, j, val)

wn = wb["Pruebas No Funcionales"]
NF = [
 ("NF-01", "Volumen", "HU-15", "Un mes completo de telemetría de un dispositivo en CSV", "446 400 filas (10 parámetros × 31 días × 1 por minuto), lotes de 500", "Tiempo y pico de memoria de la tarea", "Sin errores de memoria ni timeout (CA2)", "pytest (test_mes_completo_por_minuto_con_memoria_acotada)", "8,55 s; pico de memoria 202,86 MiB", "Cumple", "Referencia del test de Dev: menos de 256 MiB y 120 s; el límite duro de la tarea es 1200 s."),
 ("NF-02", "Volumen", "HU-15", "Un mes completo de telemetría de un dispositivo en XLSX", "446 400 filas, lotes de 500", "Tiempo y pico de memoria de la tarea", "Sin errores de memoria ni timeout (CA2)", "pytest (test_mes_completo_por_minuto_con_memoria_acotada)", "86,59 s; pico de memoria 202,87 MiB", "Cumple", "Ver OBS-27: unas 10 veces más lento que CSV; dentro del límite, con poco margen en un servidor más lento."),
]
rn = vacia(wn)
for k, fila in enumerate(NF):
    estilo(wn, 2, rn + k, 11)
    for j, val in enumerate(fila, 1):
        wn.cell(rn + k, j, val)

# Resumen: fila de HU-15 en «Resultado por historia» (se desplaza lo que sigue)
su = wb["Resumen"]
f0 = 40
fusion = [str(m) for m in su.merged_cells.ranges if m.min_row >= f0]
for m in fusion:
    su.unmerge_cells(m)
alturas = {i: su.row_dimensions[i].height for i in range(f0, su.max_row + 1)}
su.move_range(f"A{f0}:H{su.max_row}", rows=1, cols=0, translate=True)
for i, h in alturas.items():
    su.row_dimensions[i + 1].height = h
for m in fusion:
    cr = CellRange(m)
    cr.shift(row_shift=1)
    su.merge_cells(cr.coord)
for j in range(1, 9):
    c0, c1 = su.cell(39, j), su.cell(40, j)
    c1._style = copy(c0._style)
    val = c0.value
    if isinstance(val, str) and val.startswith("="):
        for col in "ABCDEF":
            val = val.replace(f"{col}39", f"{col}40")
    c1.value = val
su["A40"] = "HU-15"
su.row_dimensions[40].height = su.row_dimensions[39].height

portada(wb, lambda t: t.rstrip().rstrip(".") + DOCS_TXT["casos"])
wb.save(dst)
print("casos ok")

# ================================ Evidencias ================================
src, dst = ruta("03_Evidencias", "Registro_de_Evidencias")
wb = openpyxl.load_workbook(src)
ws = wb["Registro"]
r = vacia(ws)
assert r == 202, r
filas = []
for k, c in enumerate(CASOS):
    tipo, nombre, que = ev_de(c)
    kb, h = sha(nombre)
    filas.append((f"EV-CP-{ID0 + k}", f"CP-{ID0 + k}", "HU-15", tipo, que, nombre, UBIC, "QA", f"{FECHA} {HORA}", kb, h, COMMIT, "Adjuntada", c[9], ""))
for ide, caso, tipo, que, nombre in EXTRA:
    kb, h = sha(nombre)
    filas.append((ide, caso, "HU-15", tipo, que, nombre, UBIC, "QA", f"{FECHA} {HORA}", kb, h, COMMIT, "Adjuntada", "Aprobado", ""))
for k, f in enumerate(filas):
    estilo(ws, 201, r + k, 15)
    for j, val in enumerate(f, 1):
        ws.cell(r + k, j, val)
portada(wb, lambda t: t.replace("HU-34 y HT-30.2", "HU-34, HT-30.2 y HU-15"))
wb.save(dst)
print("evidencias ok", len(filas))

# ================================= Defectos =================================
src, dst = ruta("04_Defectos", "Registro_de_Defectos")
wb = openpyxl.load_workbook(src)
ws = wb["Observaciones"]
r = vacia(ws)
assert r == 26, r
OBS = [
 ("OBS-25", "CP-178, CP-179", "HU-15", "El texto de la tarea pide procesar en lotes «con pandas». El código usa csv y openpyxl (modo write_only) con un cursor de servidor que lee por lotes (EXPORT_CHUNK_ROWS); pandas no está en el proyecto. El objetivo (no cargar todo el histórico en memoria) se cumple: un mes de 446 400 filas tuvo un pico de 202,86 MiB.", "Confirmar con el PO si se acepta la técnica actual, o pedir a Dev migrar a pandas con chunksize.", "QA", FECHA, "Abierta", "Decisión del PO", "Media", "PO", "", "", ""),
 ("OBS-26", "CP-183, CP-186, CP-189", "HU-15", "CA3 pide un enlace de descarga válido 24 horas. El correo enlaza a la app (/consulta-datos?exportacion=ID) y la vigencia de 24 h es la del archivo. La URL firmada de Object Storage se emite al pulsar Descargar y dura 60 s. El usuario puede descargar durante 24 h, pero el enlace firmado no dura 24 h.", "Confirmar con el PO que este diseño (más seguro: el acceso se revalida en cada descarga) cumple CA3, o pedir una URL firmada de 24 h en el correo.", "QA", FECHA, "Abierta", "Decisión del PO", "Media", "PO", "", "", ""),
 ("OBS-27", "CP-179", "HU-15", "La exportación XLSX de un mes (446 400 filas) tarda 86,59 s en local frente a 8,55 s en CSV. Está dentro del límite del test (120 s) y de la tarea (1200 s), pero con poco margen en un servidor más lento.", "Medir en Lightsail dentro de HT-18 y valorar recomendar CSV para rangos largos.", "QA", FECHA, "Abierta", "Mejora técnica", "Baja", "Dev", "", "", ""),
 ("OBS-28", "CP-173, CP-189, CP-196", "HU-15", "Las pruebas E2E usaron un bucket simulado en carpeta y SMTP simulado: sin EXPORT_S3_BUCKET la API responde 503. No se probó contra Lightsail Object Storage real ni con SMTP real.", "Repetir los casos E2E en un entorno de prueba con Object Storage y SMTP reales cuando el PO lo autorice.", "QA", FECHA, "Abierta", "Cobertura pendiente", "Media", "QA", "", "", ""),
 ("OBS-29", "CP-195, CP-196, CP-199", "HU-15", "PP-286 (eliminación automática) figura «En curso» en Jira, pero la tarea mantener_exportaciones y su programación en Beat (cada 60 s) están entregadas y pasaron todos los casos.", "Dev confirma que PP-286 está terminada y la pasa a Listo.", "QA", FECHA, "Abierta", "Confirmación", "Baja", "Dev", "", "", ""),
]
for k, f in enumerate(OBS):
    estilo(ws, 25, r + k, 14)
    for j, val in enumerate(f, 1):
        ws.cell(r + k, j, val)
wh = wb["Historial de rondas"]
rh = vacia(wh)
assert rh == 4, rh
fila = ("1", "HU-15", FECHA, COMMIT, str(N), str(N), "0", "0", "0", "0", "5", str(N_EVID),
        "Primera ronda de HU-15 (PP-408): local con API y worker reales y bucket simulado; 0 defectos; 5 observaciones (OBS-25 a OBS-29); regresión del backend sin fallas nuevas (96 por OBS-11).")
estilo(wh, 3, rh, 13)
for j, val in enumerate(fila, 1):
    wh.cell(rh, j, val)
portada(wb, lambda t: t.replace("HU-34 y HT-30.2", "HU-34, HT-30.2 y HU-15"))
wb.save(dst)
print("defectos ok")

# ================================== RTM ==================================
src, dst = ruta("05_Matriz_Trazabilidad_RTM", "Matriz_Trazabilidad_RTM")
wb = openpyxl.load_workbook(src)
ws = wb["RTM"]
r = vacia(ws)
assert r == 35, r
ORI = "HU-15 — subtareas PP-283 a PP-286 y PP-408 (procedimiento y criterios de aceptación)"
REQ = [
 ("RQ-HU15-01", "La exportación se genera de forma asíncrona (Celery): la petición responde de inmediato y no bloquea la interfaz (CA1).", "PP-283", "—", "OBS-28", "RG-18, RG-20"),
 ("RQ-HU15-02", "La exportación se procesa por lotes sin cargar todo el histórico; un mes completo no da errores de memoria ni timeout (CA2).", "PP-284", "—", "OBS-25, OBS-27", "RG-18"),
 ("RQ-HU15-03", "El archivo se sube a Object Storage privado y se descarga con URL firmada con expiración, sin exponer el bucket.", "PP-285", "—", "OBS-26, OBS-28", "RG-18, RG-20"),
 ("RQ-HU15-04", "El usuario recibe una notificación con el enlace de descarga cuando la exportación está lista; la vigencia es de 24 horas (CA3).", "PP-285", "—", "OBS-26, OBS-28", "RG-18, RG-20"),
 ("RQ-HU15-05", "Se limita el rango máximo exportable y se rechaza con un mensaje claro lo que lo excede (CA5).", "PP-283", "—", "—", "RG-18, RG-20"),
 ("RQ-HU15-06", "Los archivos exportados se eliminan automáticamente de Object Storage al expirar su vigencia (CA4).", "PP-286", "—", "OBS-29", "RG-18"),
 ("RQ-HU15-07", "Transversal: acceso y aislamiento (entorno, propietario, usuario activo y permisos revalidados al generar y descargar).", "PP-283", "—", "—", "RG-18"),
 ("RQ-HU15-08", "Transversal: regresión del backend sin fallas nuevas.", "PP-408", "—", "OBS-11 (96 tests sin suscripción)", "RG-19"),
]
for k, (rid, txt, bk, dfs, obs, reg) in enumerate(REQ):
    fr = r + k
    estilo(ws, 34, fr, 13)
    casos_req = ", ".join(f"CP-{ID0 + i}" for i, c in enumerate(CASOS) if c[0] == rid)
    ws.cell(fr, 1, rid); ws.cell(fr, 2, txt); ws.cell(fr, 3, ORI); ws.cell(fr, 4, "HU-15")
    ws.cell(fr, 5, bk); ws.cell(fr, 6, "Alta"); ws.cell(fr, 7, casos_req)
    for col in (8, 9):
        f = ws.cell(fr, col).value
        if not (isinstance(f, str) and f.startswith("=")):
            ws.cell(fr, col).value = ws.cell(34, col).value.replace("34", str(fr))
    ws.cell(fr, 10, "Aprobado"); ws.cell(fr, 11, dfs); ws.cell(fr, 12, obs); ws.cell(fr, 13, reg)

wh = wb["Historias"]
rh = vacia(wh)
assert rh == 7, rh
rqs = ", ".join(x[0] for x in REQ)
for col in range(1, 19):
    wh.cell(rh, col)._style = copy(wh.cell(6, col)._style)
wh.cell(rh, 1, "HU-15"); wh.cell(rh, 2, "HU33"); wh.cell(rh, 3, "Pipeline de exportación en background con Celery")
wh.cell(rh, 4, "Exportación de datos"); wh.cell(rh, 5, "En curso"); wh.cell(rh, 6, "Listo"); wh.cell(rh, 7, "Listo"); wh.cell(rh, 8, rqs)
wh.cell(rh, 17, "No es un defecto: sin defectos del producto ni entregas pendientes. PP-286 figura En curso en Jira aunque su código está entregado y verificado (OBS-29). Quedan decisiones del PO: OBS-25 (pandas) y OBS-26 (enlace firmado de 24 h).")
wh.cell(rh, 18, "Probado sobre 827755e: qa-elliot con dev hasta f9c0967 (Jareth): tasks/exportaciones.py, services/exportaciones.py, services/exportaciones_storage.py, routers/exportaciones.py y ExportacionesPanel.tsx.")

wf = wb["Fuente casos"]
rf = vacia(wf)
assert rf == 173, rf
for k, c in enumerate(CASOS):
    estilo(wf, 172, rf + k, 3)
    wf.cell(rf + k, 1, f"CP-{ID0 + k}"); wf.cell(rf + k, 2, "HU-15"); wf.cell(rf + k, 3, c[9])
portada(wb, lambda t: t.replace("HU-34 y HT-30.2", "HU-34, HT-30.2 y HU-15"))
wb.save(dst)
print("rtm ok")
