"""PP-426 (HU-23 Listar paneles) ronda 1: amplía los libros QA de v0.8 a v0.9 (casos, evidencias, defectos y RTM).

Ejecutar desde backend/: venv/Scripts/python.exe qa/playwright_hu23/generar_documentos_qa.py
El plan de pruebas (Word) lo amplía generar_plan_qa.py, en esta misma carpeta.
"""
import hashlib
import re
import time
from copy import copy
from pathlib import Path

import openpyxl
from openpyxl.formatting.formatting import ConditionalFormattingList
from openpyxl.formula import Tokenizer
from openpyxl.formula.tokenizer import Token
from openpyxl.worksheet.cell_range import CellRange, MultiCellRange

QA = Path(__file__).resolve().parents[1]
EVD = QA / "03_Evidencias" / "HU23"
FECHA = "02/11/2026"
HORA = time.strftime("%H:%M")
COMMIT = "f9b939a (qa-elliot)"
UBIC = "backend/qa/03_Evidencias/HU23/"
T = "qa/03_Evidencias/HU23/test_hu23_qa.py::"
E = "qa/playwright_hu23/hu23.spec.mjs::"
L = "Local"
LE = "Local (API en 8000 contra pangea_e2e y Vite en 5173, Edge)"
ID0 = 222
HU = "HU-23"

# (requisito, tipo, prioridad, rol, precondición, pasos, datos, esperado, obtenido, estado, defecto, test, evidencia(tipo, archivo, qué))
PYT = "pytest_hu23.html"
PW = "playwright/index.html"


def fila_pytest(test):
    return ("Fila de informe", PYT, f"Fila de {test[:70]} en el informe de pytest")


CASOS = [
 ("RQ-HU23-01", "Funcional", "Alta", "Cliente Final", "Cliente Final con Edición sobre Tableros y 1 panel propio", "1. GET /paneles.", "Panel «QA Panel uno»", "200 y cada fila trae id, nombre, fecha de creación, visibilidad y es_propietario (los datos de las acciones).", "200; los 5 campos presentes; es_propietario verdadero y visibilidad Privado.", "Aprobado", "—", T + "test_ca1_cada_fila_trae_nombre_fecha_y_datos_para_las_acciones", fila_pytest("test_ca1_cada_fila_trae_nombre_fecha_y_datos")),
 ("RQ-HU23-01", "Límite", "Alta", "Cliente Final", "12 paneles propios", "1. Crear 12 paneles. 2. GET /paneles.", "12 paneles QA", "El listado trae todos los paneles del usuario, sin paginar ni recortar.", "12 de 12 en la respuesta.", "Aprobado", "—", T + "test_ca1_el_listado_trae_todos_los_paneles_del_usuario", fila_pytest("test_ca1_el_listado_trae_todos_los_paneles")),
 ("RQ-HU23-01", "Funcional", "Media", "Cliente Final", "Panel creado con fecha conocida", "1. Crear un panel con fch_crcn 15/03/2026 10:30 UTC. 2. GET /paneles.", "2026-03-15T10:30Z", "La fecha de creación se devuelve en ISO y coincide con la registrada.", "La fecha devuelta es igual a la registrada.", "Aprobado", "—", T + "test_ca1_fecha_de_creacion_es_iso_y_coincide_con_la_registrada", fila_pytest("test_ca1_fecha_de_creacion_es_iso")),
 ("RQ-HU23-05", "Funcional", "Alta", "Cliente Final", "4 paneles con fechas distintas (hace 10, 9, 8 y 7 días)", "1. GET /paneles sin parámetros.", "QA A, QA B, QA C, QA D", "Orden por fecha de creación descendente por defecto: del más reciente al más antiguo.", "QA D, QA C, QA B, QA A.", "Aprobado", "—", T + "test_orden_por_defecto_fecha_de_creacion_descendente", fila_pytest("test_orden_por_defecto_fecha_de_creacion")),
 ("RQ-HU23-05", "Funcional", "Media", "Cliente Final", "3 paneles, 2 con «Estación» en el nombre y fechas distintas", "1. GET /paneles?busqueda=estación.", "busqueda=estación", "El orden descendente se mantiene dentro de los resultados de la búsqueda.", "QA Estación nueva y luego QA Estación vieja.", "Aprobado", "—", T + "test_orden_se_mantiene_al_buscar", fila_pytest("test_orden_se_mantiene_al_buscar")),
 ("RQ-HU23-05", "Funcional", "Alta", "Cliente Final", "1 panel existente de hace un día", "1. POST /paneles con un nombre nuevo. 2. GET /paneles.", "nmbr=«QA Nuevo»", "El panel recién creado aparece primero en el listado.", "201 y «QA Nuevo» es el primer elemento.", "Aprobado", "—", T + "test_panel_recien_creado_aparece_primero", fila_pytest("test_panel_recien_creado_aparece_primero")),
 ("RQ-HU23-04", "Seguridad", "Crítica", "Cliente Final", "Dos usuarios de la misma sede, cada uno con un panel", "1. Listar como usuario 1. 2. Listar como usuario 2.", "«QA De usuario 1» y «QA De usuario 2»", "Cada usuario solo ve sus propios paneles.", "Usuario 1 ve solo el suyo y usuario 2 solo el suyo.", "Aprobado", "—", T + "test_aislamiento_dos_usuarios_de_la_misma_sede_ven_solo_lo_suyo", fila_pytest("test_aislamiento_dos_usuarios_de_la_misma_sede")),
 ("RQ-HU23-04", "Seguridad", "Alta", "Cliente Final", "Un panel de otro usuario llamado «QA Secreto ajeno»", "1. GET /paneles?busqueda=secreto.", "busqueda=secreto", "La búsqueda no revela paneles de otros usuarios.", "Lista vacía.", "Aprobado", "—", T + "test_aislamiento_busqueda_no_filtra_paneles_ajenos", fila_pytest("test_aislamiento_busqueda_no_filtra_paneles")),
 ("RQ-HU23-04", "Seguridad", "Crítica", "Cliente Final", "Panel de otro usuario con id conocido", "1. GET /paneles/{id}. 2. GET /paneles/{id}/contenido.", "id de un panel ajeno", "Abrir un panel ajeno por su id devuelve 404 en el detalle y en el contenido.", "404 y 404.", "Aprobado", "—", T + "test_aislamiento_abrir_panel_ajeno_por_id_devuelve_404", fila_pytest("test_aislamiento_abrir_panel_ajeno_por_id")),
 ("RQ-HU23-04", "Seguridad", "Media", "Cliente Final", "El dueño usa «Compartir con empresa» y otro usuario de la sede tiene Lectura sobre la ubicación", "1. PUT /paneles/{id}/visibilidad con Empresa. 2. Listar como el otro usuario.", "vsbldd=Empresa", "Según el detalle de la HU, los paneles no se comparten entre usuarios en v1.0; el panel debería seguir sin verse.", "El otro usuario ve el panel en su listado con es_propietario falso; es una función del producto que la HU no describe (OBS-33, decide el PO). Por defecto el panel sigue privado.", "Aprobado", "—", T + "test_obs_panel_compartido_con_empresa_si_aparece_a_otro_usuario", fila_pytest("test_obs_panel_compartido_con_empresa")),
 ("RQ-HU23-04", "Seguridad", "Alta", "Cliente Final", "Panel privado y un usuario de otra sede", "1. Listar como el usuario de otra sede.", "Otra sede y otro usuario", "Un panel privado nunca se ve desde otra sede.", "Lista vacía.", "Aprobado", "—", T + "test_aislamiento_panel_privado_nunca_se_ve_en_otra_sede", fila_pytest("test_aislamiento_panel_privado_nunca_se_ve")),
 ("RQ-HU23-03", "Funcional", "Alta", "Cliente Final", "3 paneles: «Resumen de estaciones», «Calidad del agua» y «Alarmas»", "1. Buscar el nombre completo. 2. Buscar «estaci». 3. Buscar «agua».", "Nombre completo y fragmentos", "El listado muestra únicamente los paneles que coinciden con el nombre o el fragmento.", "Una coincidencia en cada búsqueda.", "Aprobado", "—", T + "test_ca3_busqueda_por_nombre_completo_y_por_fragmento", fila_pytest("test_ca3_busqueda_por_nombre_completo")),
 ("RQ-HU23-03", "Funcional", "Alta", "Cliente Final", "Panel «QA Panel ÁGUILA»", "1. Buscar «panel» (parte intermedia). 2. Buscar «QA PANEL» (mayúsculas).", "panel y QA PANEL", "La búsqueda coincide en cualquier posición y sin distinguir mayúsculas.", "El panel aparece en las dos búsquedas.", "Aprobado", "—", T + "test_ca3_busqueda_en_cualquier_posicion_y_sin_mayusculas", fila_pytest("test_ca3_busqueda_en_cualquier_posicion")),
 ("RQ-HU23-03", "Negativa", "Media", "Cliente Final", "2 paneles propios", "1. GET /paneles?busqueda=.", "busqueda vacío", "Una búsqueda vacía devuelve todos los paneles.", "Los 2 paneles.", "Aprobado", "—", T + "test_ca3_busqueda_vacia_o_con_espacios_devuelve_todo", fila_pytest("test_ca3_busqueda_vacia_o_con_espacios")),
 ("RQ-HU23-03", "Negativa", "Media", "Cliente Final", "1 panel propio", "1. Buscar un texto que no está en ningún nombre.", "zzz-no-existe", "Sin coincidencias devuelve una lista vacía.", "Lista vacía y 200.", "Aprobado", "—", T + "test_ca3_busqueda_sin_coincidencias_lista_vacia", fila_pytest("test_ca3_busqueda_sin_coincidencias")),
 ("RQ-HU23-03", "Negativa", "Media", "Cliente Final", "2 paneles propios sin «%» en el nombre", "1. Buscar «%».", "busqueda=%", "Ningún panel coincide: ningún nombre contiene «%».", "Devolvió los 2 paneles: el «%» se usa como comodín de LIKE (DEF-05).", "Fallido", "DEF-05", T + "test_ca3_busqueda_con_comodin_porcentaje_no_debe_devolver_todo", fila_pytest("test_ca3_busqueda_con_comodin_porcentaje")),
 ("RQ-HU23-03", "Negativa", "Media", "Cliente Final", "2 paneles propios sin «_» en el nombre (el nombre solo admite letras, números y espacios)", "1. Buscar «_».", "busqueda=_", "Ningún panel coincide: ningún nombre contiene «_».", "Devolvió los 2 paneles: el «_» coincide con cualquier carácter (DEF-05).", "Fallido", "DEF-05", T + "test_ca3_busqueda_con_guion_bajo_no_debe_actuar_como_comodin", fila_pytest("test_ca3_busqueda_con_guion_bajo")),
 ("RQ-HU23-03", "Seguridad", "Alta", "Cliente Final", "1 panel propio", "1. Buscar «' OR '1'='1», «'; DROP TABLE pnl;--» y «<script>alert(1)</script>». 2. Listar de nuevo.", "3 cadenas de inyección", "Ninguna búsqueda rompe el servicio ni devuelve datos; la tabla sigue intacta.", "Listas vacías y el panel «QA Uno» sigue en el listado.", "Aprobado", "—", T + "test_ca3_busqueda_con_comilla_y_sql_no_rompe", fila_pytest("test_ca3_busqueda_con_comilla_y_sql")),
 ("RQ-HU23-03", "Funcional", "Baja", "Cliente Final", "Panel «QA Estación»", "1. Buscar «estación».", "busqueda=estación", "La búsqueda con acento encuentra el panel.", "Una coincidencia.", "Aprobado", "—", T + "test_ca3_busqueda_con_acento_distingue_acentos", fila_pytest("test_ca3_busqueda_con_acento")),
 ("RQ-HU23-02", "Funcional", "Alta", "Cliente Final", "Panel propio sin ubicaciones ni widgets", "1. GET /paneles/{id}. 2. GET /paneles/{id}/contenido.", "Panel «QA Vacío»", "El panel se abre y su contenido viene vacío, sin errores.", "200; ubicaciones y widgets vacíos.", "Aprobado", "—", T + "test_ca2_abrir_panel_vacio_devuelve_estructura_sin_ubicaciones_ni_widgets", fila_pytest("test_ca2_abrir_panel_vacio_devuelve")),
 ("RQ-HU23-02", "Funcional", "Crítica", "Cliente Final", "Panel con 1 ubicación añadida y 1 widget de línea", "1. GET /paneles/{id}. 2. GET /paneles/{id}/contenido.", "Panel «QA Con contenido», ubicación «QA Estación A»", "Al abrir el panel se ven su nombre, sus ubicaciones y sus widgets.", "Detalle con el nombre; 1 ubicación «QA Estación A» y 1 widget tipo línea.", "Aprobado", "—", T + "test_ca2_abrir_panel_con_ubicaciones_y_widgets_los_muestra", fila_pytest("test_ca2_abrir_panel_con_ubicaciones")),
 ("RQ-HU23-02", "Negativa", "Media", "Cliente Final", "Sesión de Cliente Final", "1. GET /paneles/987654. 2. GET /paneles/abc.", "id inexistente e id no numérico", "Un id inexistente devuelve 404 y uno no numérico, 422.", "404 y 422.", "Aprobado", "—", T + "test_ca2_abrir_panel_inexistente_404_y_id_invalido_422", fila_pytest("test_ca2_abrir_panel_inexistente_404")),
 ("RQ-HU23-06", "Funcional", "Crítica", "Cliente Final", "Usuario sin paneles", "1. GET /paneles.", "Sin paneles", "200 y lista vacía, sin error (el mensaje y el botón son de la pantalla).", "200 y lista vacía.", "Aprobado", "—", T + "test_sin_paneles_devuelve_lista_vacia_y_no_error", fila_pytest("test_sin_paneles_devuelve_lista_vacia")),
 ("RQ-HU23-06", "Funcional", "Alta", "Cliente Final", "Usuario con Edición sobre Tableros y sin paneles", "1. Listar. 2. POST /paneles. 3. Listar.", "nmbr=«QA Primero»", "Sin paneles, el usuario puede crear uno y verlo en el listado.", "201 y el listado trae «QA Primero».", "Aprobado", "—", T + "test_sin_paneles_el_usuario_puede_crear_uno_y_listarlo", fila_pytest("test_sin_paneles_el_usuario_puede_crear")),
 ("RQ-HU23-07", "Negativa", "Crítica", "Sin sesión", "Sin token", "1. GET /paneles. 2. GET /paneles/1.", "Sin Authorization", "Sin autenticación se rechaza con 401.", "401 y 401.", "Aprobado", "—", T + "test_error_sin_autenticacion_devuelve_401", fila_pytest("test_error_sin_autenticacion_devuelve_401")),
 ("RQ-HU23-07", "Seguridad", "Crítica", "Cliente Final", "Usuario sin permiso sobre Tableros", "1. GET /paneles. 2. GET /paneles/1.", "Sin fila en prms_usr_sd", "Sin permiso sobre Tableros se rechaza con 403.", "403 y 403.", "Aprobado", "—", T + "test_error_sin_permiso_sobre_tableros_devuelve_403_en_listado_y_detalle", fila_pytest("test_error_sin_permiso_sobre_tableros_devuelve_403")),
 ("RQ-HU23-07", "Seguridad", "Media", "Cliente Final", "Usuario con solo Lectura sobre Tableros", "1. GET /paneles.", "Lectura", "Con Lectura sobre Tableros puede listar.", "200.", "Aprobado", "—", T + "test_error_usuario_con_solo_lectura_puede_listar", fila_pytest("test_error_usuario_con_solo_lectura_puede_listar")),
 ("RQ-HU23-03", "Límite", "Baja", "Cliente Final", "Sesión de Cliente Final", "1. Buscar con una cadena de 5 000 caracteres.", "busqueda de 5 000 caracteres", "El servicio responde sin error.", "200.", "Aprobado", "—", T + "test_error_orden_y_busqueda_muy_larga_no_rompen", fila_pytest("test_error_orden_y_busqueda_muy_larga")),
 # --------------------------- Playwright (Edge) ---------------------------
 ("RQ-HU23-01", "E2E", "Crítica", "Cliente Final", "cliente@pangea-dev.com con 10 paneles propios en pangea_e2e", "1. Iniciar sesión. 2. Abrir Tableros personalizables. 3. Revisar columnas, fechas y acciones.", "cliente@pangea-dev.com", "El listado muestra Nombre, Fecha de creación y Acciones; cada fila trae fecha dd/mm/aaaa y Abrir, Duplicar, Editar y Eliminar.", "Las 3 columnas y las 4 acciones en la primera fila; fecha con formato dd/mm/aaaa; 10 filas o más.", "Aprobado", "—", E + "CA1 el listado muestra nombre, fecha de creación y acciones de cada panel", ("Captura", "EV-HU23-E2E-01_listado.png", "Pantalla del flujo: listado de paneles con nombre, proyectos, fecha de creación y acciones")),
 ("RQ-HU23-05", "E2E", "Alta", "Cliente Final", "Listado abierto", "1. Leer la columna de fechas. 2. Comparar el orden de paneles creados el mismo día.", "Paneles de QA HU26 y QA HU34", "Las fechas no aumentan hacia abajo y, el mismo día, el panel más nuevo va primero.", "Fechas en orden descendente; QA HU34 34963 antes que QA HU34 1107 y este antes que QA HU26 41510.", "Aprobado", "—", E + "Detalle: orden por fecha de creación descendente por defecto", ("Fila de informe", PW, "Fila del recorrido «orden por fecha de creación descendente»")),
 ("RQ-HU23-04", "E2E", "Crítica", "Cliente Final", "Existe «QA Panel ajeno» de otro usuario de la misma sede", "1. Revisar los nombres del listado.", "qa.otro@pangea-dev.com (otro usuario)", "Solo se ven los paneles propios.", "«QA Panel ajeno» no aparece.", "Aprobado", "—", E + "Detalle: solo se ven los paneles propios (no el de otro usuario)", ("Fila de informe", PW, "Fila del recorrido «solo se ven los paneles propios»")),
 ("RQ-HU23-03", "E2E", "Crítica", "Cliente Final", "Listado abierto", "1. Escribir «hu26» en el buscador. 2. Escribir un nombre completo.", "hu26 y «QA HU34 1107»", "El listado se actualiza y muestra solo los paneles que coinciden, sin distinguir mayúsculas.", "5 paneles con «HU26» con el texto en minúsculas; 1 panel con el nombre completo.", "Aprobado", "—", E + "CA3 búsqueda por fragmento filtra el listado, sin distinguir mayúsculas", ("Captura", "EV-HU23-E2E-02_busqueda.png", "Pantalla del flujo: búsqueda «hu26» con 5 paneles")),
 ("RQ-HU23-03", "E2E", "Alta", "Cliente Final", "Listado abierto", "1. Escribir un texto que no existe.", "zzz-no-existe", "Se muestra «No se encontraron paneles con ese criterio» y no el mensaje de sin paneles.", "El aviso de sin resultados; «Aún no tienes paneles creados» no aparece.", "Aprobado", "—", E + "CA3 búsqueda sin coincidencias muestra el aviso de sin resultados", ("Captura", "EV-HU23-E2E-03_busqueda-sin-resultados.png", "Pantalla del flujo: aviso «No se encontraron paneles con ese criterio»")),
 ("RQ-HU23-03", "E2E", "Media", "Cliente Final", "Búsqueda sin resultados activa", "1. Borrar el texto del buscador.", "Buscador vacío", "El listado vuelve a mostrar todos los paneles.", "10 filas o más de nuevo.", "Aprobado", "—", E + "CA3 borrar la búsqueda restituye el listado completo", ("Fila de informe", PW, "Fila del recorrido «borrar la búsqueda restituye el listado»")),
 ("RQ-HU23-02", "E2E", "Crítica", "Cliente Final", "Panel nuevo con 1 ubicación y 1 widget de tarjeta", "1. Crear el panel, añadir ubicación y widget. 2. Volver al listado. 3. Seleccionar el nombre del panel.", "«QA HU23 <n>» y ubicación [DEMO] Río Rímac - Margen Izquierda", "El panel nuevo sale primero; al seleccionar su nombre se abre con sus ubicaciones y widgets.", "Primero en el listado con su proyecto; abierto muestra el título, la estación y «Widgets (1)».", "Aprobado", "—", E + "CA2 panel con ubicación y widget: sale primero en el listado y su nombre lo abre con su contenido", ("Captura", "EV-HU23-E2E-05_panel-abierto.png", "Pantalla del flujo: panel abierto desde el listado con su ubicación y su widget")),
 ("RQ-HU23-02", "E2E", "Alta", "Cliente Final", "Listado abierto", "1. Comparar el enlace de «Abrir» con el del nombre en la primera fila.", "Primera fila", "«Abrir» lleva al mismo panel que el nombre.", "Los dos enlaces tienen el mismo destino.", "Aprobado", "—", E + "CA2 el botón Abrir lleva al mismo panel que el nombre", ("Fila de informe", PW, "Fila del recorrido «el botón Abrir lleva al mismo panel»")),
 ("RQ-HU23-01", "E2E", "Media", "Cliente Final", "Panel «QA HU23 <n>» primero en el listado", "1. Pulsar Eliminar en la primera fila. 2. Confirmar.", "Panel creado por la prueba", "La acción Eliminar retira el panel del listado (limpieza de los datos de la prueba).", "El panel ya no aparece.", "Aprobado", "—", E + "Limpieza: elimina el panel creado en la prueba", ("Fila de informe", PW, "Fila del recorrido «Eliminar retira el panel del listado»")),
 ("RQ-HU23-06", "E2E", "Crítica", "Cliente Final", "qa.sinpaneles@pangea-dev.com sin paneles", "1. Iniciar sesión. 2. Abrir Tableros personalizables. 3. Revisar el mensaje y los botones «Crear panel». 4. Pulsar el del centro.", "qa.sinpaneles@pangea-dev.com", "Se muestra «Aún no tienes paneles creados» y el botón «Crear panel» visible y habilitado.", "Mensaje exacto; 2 botones «Crear panel» visibles y habilitados; el del centro abre el formulario.", "Aprobado", "—", E + "Detalle: muestra «Aún no tienes paneles creados» y «Crear panel» visible y habilitado", ("Captura", "EV-HU23-E2E-06_sin-paneles.png", "Pantalla del flujo: mensaje «Aún no tienes paneles creados» y botón «Crear panel»")),
 ("RQ-HU23-04", "E2E", "Alta", "Cliente Final", "qa.otro@pangea-dev.com con un solo panel", "1. Iniciar sesión con el otro usuario. 2. Revisar el listado.", "qa.otro@pangea-dev.com", "Ve solo su propio panel y ninguno del Cliente Final.", "Solo «QA Panel ajeno».", "Aprobado", "—", E + "Detalle: el otro usuario ve solo su panel y no los del Cliente Final", ("Fila de informe", PW, "Fila del recorrido «el otro usuario ve solo su panel»")),
 ("RQ-HU23-03", "E2E", "Media", "Cliente Final", "Listado con 10 paneles", "1. Escribir «%» en el buscador. 2. Esperar el filtrado.", "busqueda=%", "Ningún panel coincide: ningún nombre contiene «%».", "El listado siguió mostrando los 10 paneles (DEF-05).", "Fallido", "DEF-05", E + "CA3 el carácter % no debe actuar como comodín", ("Captura", "EV-HU23-E2E-07_busqueda-porcentaje.png", "Pantalla del fallo: «%» devuelve los 10 paneles")),
]
N = len(CASOS)
ULT = ID0 + N - 1
FALLIDOS = [i for i, c in enumerate(CASOS) if c[9] == "Fallido"]
assert N == 40 and len(FALLIDOS) == 3, (N, FALLIDOS)
N_OK = N - len(FALLIDOS)

REQ = {
    "RQ-HU23-01": ("Al acceder al módulo «Tableros Personalizables», el sistema muestra el listado de todos los paneles del usuario con el nombre, la fecha de creación y las acciones disponibles.", "PP-210"),
    "RQ-HU23-02": ("Al seleccionar el nombre de un panel del listado, el sistema abre el panel mostrando su contenido con las ubicaciones y los widgets asociados.", "PP-210 / PP-211"),
    "RQ-HU23-03": ("Al ingresar un nombre o fragmento en el buscador, el listado se actualiza y muestra únicamente los paneles que coinciden.", "PP-211"),
    "RQ-HU23-04": ("Cada usuario solo puede ver y gestionar sus propios paneles; los paneles no se comparten entre usuarios en v1.0.", "PP-211"),
    "RQ-HU23-05": ("El listado se ordena por fecha de creación de forma descendente por defecto.", "PP-212"),
    "RQ-HU23-06": ("Si el usuario no tiene paneles, el sistema muestra «Aún no tienes paneles creados» y el botón «Crear panel» permanece visible y habilitado.", "PP-210"),
    "RQ-HU23-07": ("Transversal: sin sesión se rechaza (401), sin permiso sobre Tableros se rechaza (403) y con Lectura se puede listar.", "PP-211"),
}
ESTADOS = {f"CP-{ID0 + k}": c[9] for k, c in enumerate(CASOS)}


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


REF = re.compile(r"(\$?)([A-Z]{1,3})(\$?)(\d+)")


def _mapear_refs(formula, fn):
    """Aplica fn(fila)->fila a las referencias sin hoja de una fórmula (las que llevan «Hoja!» no se tocan)."""
    if not (isinstance(formula, str) and formula.startswith("=")):
        return formula
    salida = "="
    for t in Tokenizer(formula).items:
        if t.type == Token.OPERAND and t.subtype == Token.RANGE and "!" not in t.value:
            salida += REF.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{fn(int(m.group(4)))}", t.value)
        else:
            salida += t.value
    return salida


def insertar_fila(ws, fila):
    """Inserta una fila vacía en `fila` desplazando lo de abajo y corrigiendo las fórmulas internas de la hoja."""
    maxr, maxc = ws.max_row, ws.max_column
    fusionadas = [(str(m), m.min_row) for m in list(ws.merged_cells.ranges) if m.min_row >= fila]
    for m, _ in fusionadas:
        ws.unmerge_cells(m)
    for r in range(maxr, fila - 1, -1):
        for c in range(1, maxc + 1):
            origen, destino = ws.cell(r, c), ws.cell(r + 1, c)
            destino.value = origen.value
            destino._style = copy(origen._style)
        ws.row_dimensions[r + 1].height = ws.row_dimensions[r].height
    for c in range(1, maxc + 1):
        ws.cell(fila, c).value = None
    for fila_celdas in ws.iter_rows():
        for celda in fila_celdas:
            celda.value = _mapear_refs(celda.value, lambda n: n + 1 if n >= fila else n)
    for m, _ in fusionadas:
        mc = CellRange(m)
        ws.merge_cells(start_row=mc.min_row + 1, start_column=mc.min_col, end_row=mc.max_row + 1, end_column=mc.max_col)


def fila_como(ws, modelo, nueva, ncols):
    """Copia estilo y fórmulas de la fila `modelo` a la fila `nueva`, apuntando las fórmulas a la propia fila."""
    for c in range(1, ncols + 1):
        origen, destino = ws.cell(modelo, c), ws.cell(nueva, c)
        destino._style = copy(origen._style)
        destino.value = _mapear_refs(origen.value, lambda n: nueva if n == modelo else n)
    if ws.row_dimensions[modelo].height:
        ws.row_dimensions[nueva].height = ws.row_dimensions[modelo].height


def ampliar_rangos(ws, hasta):
    """Alarga las validaciones y los formatos condicionales que terminaban en la fila 200."""
    for dv in ws.data_validations.dataValidation:
        dv.sqref = MultiCellRange(re.sub(r"(\d+)$", str(hasta), str(dv.sqref)))
    nuevo = ConditionalFormattingList()
    for cf in ws.conditional_formatting:
        for regla in cf.rules:
            nuevo.add(re.sub(r"([A-Z]+\d+:[A-Z]+)(\d+)$", lambda m: f"{m.group(1)}{hasta}", str(cf.sqref)), regla)
    ws.conditional_formatting = nuevo


def portada(wb, quitar_cubre=None, nuevo_cubre=None, completo=None):
    ws = wb["Portada"]
    ws["B7"] = "0.9"
    ws["B8"] = ws["B8"].value.replace(" y ronda 2 de HU-15 con los criterios de aceptación actualizados",
                                       ", ronda 2 de HU-15 con los criterios de aceptación actualizados y ronda 1 de HU-23 (PP-426)")
    if nuevo_cubre:
        texto = ws["B5"].value
        if quitar_cubre and quitar_cubre in texto:
            texto = texto.replace(quitar_cubre, nuevo_cubre)
        else:
            texto = texto.rstrip() + " " + nuevo_cubre
        ws["B5"] = texto
    wb.calculation.fullCalcOnLoad = True


def v(a, b):
    return QA / a / f"Pangea_{b}_v0.8.xlsx", QA / a / f"Pangea_{b}_v0.9.xlsx"


# ================================ Casos ================================
src, dst = v("02_Casos_de_Prueba", "Casos_de_Prueba")
wb = openpyxl.load_workbook(src)
ws = wb["Casos de Prueba"]
r = vacia(ws)
assert r == ID0 + 1, r
for k, c in enumerate(CASOS):
    req, tipo, prio, rol, pre, pasos, datos, esp, obt, estado, defecto, test, ev = c
    fila = [f"CP-{ID0 + k}", HU, req, tipo, prio, rol, pre, pasos, datos, esp, obt, estado, defecto, f"EV-CP-{ID0 + k}", "QA", FECHA, test, L if test.startswith(T) else LE, COMMIT]
    estilo(ws, r - 1, r + k, 19)
    for j, val in enumerate(fila, 1):
        ws.cell(r + k, j, val)
ampliar_rangos(ws, 1000)
wr = wb["Regresión"]
rr = vacia(wr)
RG = [
 ("RG-22", "Humo", "Suite pytest de QA de HU-23: listado, orden, aislamiento, búsqueda, abrir panel y errores", HU, "RQ-HU23-03", "Alta", "Los 28 casos de API (CP-222 a CP-249)", "Flujo principal de la HU por API", "Cada ronda", "DEF-05", "qa/03_Evidencias/HU23/test_hu23_qa.py", "—", "Fallido", FECHA, "QA", "26 aprobadas y 2 fallidas por DEF-05 (comodines % y _ en la búsqueda).", None, "EV-HU23-INF-01", None),
 ("RG-23", "Humo", "Flujo UI de HU-23: listado, orden, búsqueda, abrir panel y mensaje sin paneles", HU, "RQ-HU23-02", "Alta", "Los 12 recorridos de Playwright (CP-250 a CP-261) con 3 cuentas", "Flujo principal de la HU en pantalla", "Cada ronda", "DEF-05", "qa/playwright_hu23/hu23.spec.mjs", "—", "Fallido", FECHA, "QA", "11 aprobadas y 1 fallida por DEF-05 (el «%» devuelve todos los paneles).", None, "EV-HU23-INF-03", None),
 ("RG-24", "Regresión", "Suite existente de paneles (listar, crear, editar, eliminar, ubicaciones y widgets)", HU, "RQ-HU23-01", "Media", "55 pruebas de tests/routers/test_paneles.py", "La HU no cambió código; confirma que las otras funciones de paneles siguen estables", "Cada ronda", "—", "tests/routers/test_paneles.py", "—", "Aprobado", FECHA, "QA", "55 aprobadas.", None, "EV-HU23-INF-02", None),
 ("RG-25", "Reprueba", "Búsqueda sin comodines (% y _)", HU, "RQ-HU23-03", "Media", "CP-237, CP-238 y CP-261 pasan con la corrección", "Reprueba DEF-05", "Al corregir DEF-05", "DEF-05", "qa/03_Evidencias/HU23/test_hu23_qa.py (test_ca3_busqueda_con_comodin_porcentaje, test_ca3_busqueda_con_guion_bajo) y qa/playwright_hu23/hu23.spec.mjs", "Fallido", "Pendiente", "—", "—", "Se ejecuta cuando Dev suba la corrección de DEF-05.", None, "EV-CP-237, EV-CP-238, EV-CP-261", None),
]
for k, fila in enumerate(RG):
    estilo(wr, rr - 1, rr + k, 19)
    for j, val in enumerate(fila, 1):
        wr.cell(rr + k, j, val)
rs = wb["Resumen"]
# 1) los rangos de los casos terminaban en la fila 200 y ya había 221 casos: se alargan a 1000
for fila_celdas in rs.iter_rows():
    for celda in fila_celdas:
        if isinstance(celda.value, str) and celda.value.startswith("=") and "'Casos de Prueba'!" in celda.value:
            celda.value = re.sub(r"(\$?[A-Z]+\$?)200\b", r"\g<1>1000", celda.value)
# 2) una fila nueva en «Resultado por historia»
fila_hu = buscar(rs, "HU-15") + 1
insertar_fila(rs, fila_hu)
fila_como(rs, fila_hu - 1, fila_hu, 8)
rs.cell(fila_hu, 1, HU)
portada(wb, None, f"HU-23 Listar paneles (ronda 1: {N} casos, {N_OK} aprobados y {len(FALLIDOS)} fallidos por DEF-05); CP-{ID0} a CP-{ULT}. Los rangos de las fórmulas, las listas desplegables y los colores de la hoja Casos de Prueba se alargaron de la fila 200 a la 1000, porque la hoja ya tenía 221 casos.")
wb.save(dst)
print("casos ok", N, N_OK)

# ============================== Evidencias ==============================
src, dst = v("03_Evidencias", "Registro_de_Evidencias")
wb = openpyxl.load_workbook(src)
ws = wb["Registro"]
r = vacia(ws)
filas = []
for k, c in enumerate(CASOS):
    tipo, nombre, que = c[12]
    kb, h = sha(nombre)
    porque = c[8] if c[9] == "Fallido" else ""
    filas.append((f"EV-CP-{ID0 + k}", f"CP-{ID0 + k}", HU, tipo, que, nombre, UBIC, "QA", f"{FECHA} {HORA}", kb, h, COMMIT, "Adjuntada", c[9], porque))
EXTRA = [
 ("EV-HU23-INF-01", "EV-HU23-INF-04", "Informe HTML", "Informe completo de pytest de HU-23: 26 aprobadas y 2 fallidas (DEF-05)", PYT),
 ("EV-HU23-INF-02", "EV-HU23-INF-06", "Informe HTML", "Informe de regresión: test_paneles.py, 55 aprobadas", "pytest_regresion.html"),
 ("EV-HU23-INF-03", "EV-HU23-INF-05", "Informe HTML", "Informe de Playwright de HU-23: 11 aprobadas y 1 fallida (DEF-05)", PW),
 ("EV-HU23-INF-04", "EV-HU23-INF-01", "Captura", "Captura del informe pytest de HU-23 (extracto: primeras 10 filas)", "EV-HU23-INF-04_captura-informe-pytest.png"),
 ("EV-HU23-INF-05", "EV-HU23-INF-03", "Captura", "Captura del informe de Playwright (12 pruebas)", "EV-HU23-INF-05_captura-informe-playwright.png"),
 ("EV-HU23-INF-06", "EV-HU23-INF-02", "Captura", "Captura de la regresión (extracto: primeras 10 filas de 55)", "EV-HU23-INF-06_captura-informe-regresion-extracto.png"),
 ("EV-HU23-E2E-04", "CP-256", "Captura", "Pantalla del flujo: el panel nuevo aparece primero en el listado, con su proyecto", "EV-HU23-E2E-04_panel-nuevo-primero.png"),
]
for ide, caso, tipo, que, nombre in EXTRA:
    kb, h = sha(nombre)
    filas.append((ide, caso, HU, tipo, que, nombre, UBIC, "QA", f"{FECHA} {HORA}", kb, h, COMMIT, "Adjuntada", "Informativo" if "INF" in ide else "Aprobado", ""))
for k, f in enumerate(filas):
    estilo(ws, r - 1, r + k, 15)
    for j, val in enumerate(f, 1):
        ws.cell(r + k, j, val)
N_EVID = len(filas)
portada(wb, "HT-30.2 y HU-15 del tablero PP.", "HT-30.2, HU-15 y HU-23 del tablero PP.")
wb.save(dst)
print("evidencias ok", N_EVID)

# ============================== Defectos ==============================
src, dst = v("04_Defectos", "Registro_de_Defectos")
wb = openpyxl.load_workbook(src)
wd = wb["Defectos"]
rd = vacia(wd)
assert rd == 6, rd
estilo(wd, rd - 1, rd, 19)
DEF = ("DEF-05", "La búsqueda del listado de paneles trata «%» y «_» como comodines: «%» devuelve todos los paneles", HU, "RQ-HU23-03", "CP-237, CP-238, CP-261", "Baja", "Baja", "Local",
       "1. Iniciar sesión como Cliente Final con 2 o más paneles. 2. Abrir Tableros personalizables. 3. Escribir «%» (o «_») en «Buscar por nombre de panel...». 4. O por API: GET /paneles?busqueda=%25.",
       "Ningún panel coincide: el nombre de un panel solo admite letras, números y espacios y ninguno contiene «%» ni «_» (CA3: el listado muestra únicamente los paneles que coinciden).",
       "El listado devuelve todos los paneles propios (10 de 10 en pangea_e2e y 2 de 2 en pytest). No hay fuga de datos de otros usuarios; el listado muestra de más.",
       "pytest_hu23.html (EV-CP-237, EV-CP-238) y playwright/index.html con EV-CP-261 (EV-HU23-E2E-07)", "QA", FECHA, "Jareth (autor del código de paneles; PP-211)", "Nuevo", None,
       "Causa: listar_paneles (backend/app/routers/panel.py) arma el patrón con f\"%{busqueda.lower()}%\" y lo pasa a .like() sin escapar; PostgreSQL interpreta % y _ como comodines. Solución: escapar la barra invertida, el % y el _ del texto buscado antes de armar el patrón y declarar el carácter de escape en .like(patron, escape=...). Severidad Baja: relacionada con CA3 pero sin pérdida ni fuga de datos; pre-defecto que deja PP-211 En curso.",
       "RG-25 (pendiente)")
for j, val in enumerate(DEF, 1):
    wd.cell(rd, j, val)
ws = wb["Observaciones"]
r = vacia(ws)
OBS = [
 ("OBS-33", "CP-231", HU, "PP-211: el detalle de la HU dice que cada usuario solo ve sus paneles y que no se comparten en v1.0, pero el producto trae las acciones «Compartir con empresa» y «Hacer privado» (commit 68e3089). Si el dueño comparte un panel, otro usuario de la misma sede con acceso a sus ubicaciones lo ve en su listado y lo abre (solo lectura). Por defecto el panel es privado y los casos de aislamiento pasan.", "El PO decide si compartir con la empresa queda como alcance adicional (otra HU) o si se retira hasta una versión posterior.", "QA", FECHA, "Abierta", "Decisión del PO", "Media", "PO", None, None, None),
 ("OBS-34", "CP-259", HU, "PP-210: cuando el usuario tiene un proyecto activo y no tiene paneles, la pantalla muestra «Aún no hay paneles para <proyecto>» y no el texto «Aún no tienes paneles creados» que fija el detalle de la HU. Sin proyecto activo, que es el caso probado, el texto es el literal. Revisado leyendo Paneles.tsx; no se ejecutó con un proyecto activo.", "El PO confirma si el mensaje por proyecto es aceptable o si se debe usar siempre el texto literal.", "QA", FECHA, "Abierta", "Decisión del PO", "Baja", "PO", None, None, None),
]
for k, f_ in enumerate(OBS):
    estilo(ws, r - 1, r + k, 14)
    for j, val in enumerate(f_, 1):
        ws.cell(r + k, j, val)
wh = wb["Historial de rondas"]
rh = vacia(wh)
fila = ("1", HU, FECHA, COMMIT, str(N), str(N_OK), str(len(FALLIDOS)), "0", "1", "0", "2", str(N_EVID),
        f"Primera ronda de HU-23 (PP-426): {N - 12} de API con pytest (26 aprobadas y 2 fallidas) y 12 de UI con Playwright (11 aprobadas y 1 fallida); regresión de paneles 55 de 55. "
        "1 defecto menor (DEF-05, comodines % y _ en la búsqueda) y 2 observaciones para el PO (OBS-33 paneles compartidos y OBS-34 mensaje con proyecto activo).")
estilo(wh, rh - 1, rh, 13)
for j, val in enumerate(fila, 1):
    wh.cell(rh, j, val)
rs = wb["Resumen"]
fila_hu = buscar(rs, "HU-34") + 1
insertar_fila(rs, fila_hu)
fila_como(rs, fila_hu - 1, fila_hu, 3)
rs.cell(fila_hu, 1, HU)
portada(wb, "HT-30.2 y HU-15, con el historial de rondas.", "HT-30.2, HU-15 y HU-23, con el historial de rondas.")
wb.save(dst)
print("defectos ok")

# ================================ RTM ================================
src, dst = v("05_Matriz_Trazabilidad_RTM", "Matriz_Trazabilidad_RTM")
wb = openpyxl.load_workbook(src)
ws = wb["RTM"]
r_nueva = vacia(ws)
por_req = {}
for k, c in enumerate(CASOS):
    por_req.setdefault(c[0], []).append(f"CP-{ID0 + k}")
OBS_RQ = {"RQ-HU23-02": "—", "RQ-HU23-03": "—", "RQ-HU23-04": "OBS-33", "RQ-HU23-06": "OBS-34", "RQ-HU23-07": "OBS-18"}
DEF_RQ = {"RQ-HU23-03": "DEF-05"}
REG_RQ = {"RQ-HU23-01": "RG-24", "RQ-HU23-02": "RG-23", "RQ-HU23-03": "RG-22, RG-23, RG-25", "RQ-HU23-04": "RG-22, RG-23", "RQ-HU23-05": "RG-22, RG-23", "RQ-HU23-06": "RG-23", "RQ-HU23-07": "RG-22"}
for rid, (txt, back) in REQ.items():
    modelo = r_nueva - 1
    estilo(ws, modelo, r_nueva, 13)
    for col in (8, 9):
        ws.cell(r_nueva, col).value = _mapear_refs(ws.cell(modelo, col).value, lambda n: r_nueva if n == modelo else n)
    casos = por_req[rid]
    estados = [ESTADOS[x] for x in casos]
    ok = estados.count("Aprobado")
    estado = "Aprobado" if ok == len(estados) else ("Fallido" if "Fallido" in estados else "Parcial")
    ws.cell(r_nueva, 1, rid); ws.cell(r_nueva, 2, txt)
    ws.cell(r_nueva, 3, "HU-23 — criterios de aceptación y detalles de la conversación")
    ws.cell(r_nueva, 4, HU); ws.cell(r_nueva, 5, back); ws.cell(r_nueva, 6, "Alta")
    ws.cell(r_nueva, 7, ", ".join(casos)); ws.cell(r_nueva, 10, estado)
    ws.cell(r_nueva, 11, DEF_RQ.get(rid, "—")); ws.cell(r_nueva, 12, OBS_RQ.get(rid, "—")); ws.cell(r_nueva, 13, REG_RQ[rid])
    r_nueva += 1
hist = wb["Historias"]
fh = vacia(hist)
assert fh == 8, fh
for col, val in enumerate((HU, HU, "Listar paneles", "Tableros personalizables", "En curso", "Listo", "Listo", ", ".join(REQ)), 1):
    hist.cell(fh, col, val)
hist.cell(fh, 17, "DEF-05 (menor, PP-211): la búsqueda trata «%» y «_» como comodines y devuelve todos los paneles; reprueba RG-25. PP-210 y PP-212 quedan en Listo. Decisiones del PO, que no son defectos: OBS-33 (paneles compartidos con la empresa frente a «no se comparten en v1.0») y OBS-34 (mensaje con proyecto activo).")
hist.cell(fh, 18, "Probado sobre f9b939a (qa-elliot): el código del listado (routers/panel.py: GET /paneles y GET /paneles/{id}; pages/Paneles.tsx) es de Jareth y ya está en dev (68e3089); la HU no agregó commits propios con PP-210, PP-211 ni PP-212.")
wf = wb["Fuente casos"]
rf = vacia(wf)
for k, c in enumerate(CASOS):
    estilo(wf, rf - 1, rf + k, 3)
    wf.cell(rf + k, 1, f"CP-{ID0 + k}"); wf.cell(rf + k, 2, HU); wf.cell(rf + k, 3, c[9])
wdef = wb["Fuente defectos"]
rfd = vacia(wdef)
estilo(wdef, rfd - 1, rfd, 3)
wdef.cell(rfd, 1, "DEF-05"); wdef.cell(rfd, 2, HU); wdef.cell(rfd, 3, "Nuevo")
portada(wb, "HT-30.2 y HU-15 del tablero PP", "HT-30.2, HU-15 y HU-23 del tablero PP")
wb.save(dst)
print("rtm ok")
