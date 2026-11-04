"""PP-410 (HT Modelo de datos comercial multi-sede y vencimientos) ronda 1: amplía los libros QA de v0.11 a v0.12.

Ejecutar desde backend/: venv/Scripts/python.exe qa/playwright_pp410/generar_documentos_qa.py
"""
import hashlib
import re
import time
from copy import copy
from pathlib import Path

import openpyxl
from openpyxl.formula import Tokenizer
from openpyxl.formula.tokenizer import Token
from openpyxl.worksheet.cell_range import CellRange

QA = Path(__file__).resolve().parents[1]
EVD = QA / "03_Evidencias" / "PP-410"
FECHA = "04/11/2026"
HORA = time.strftime("%H:%M")
COMMIT = "a8d6b35 (qa/correcciones sobre dev + PP-47)"
UBIC = "backend/qa/03_Evidencias/PP-410/"
T = "qa/03_Evidencias/PP-410/test_pp410_qa.py::"
L = "Local (Postgres 16 en Docker, puerto 55432; PLAN_LIMITS_REQUIRE_SUBSCRIPTION=false)"
ID0 = 303
HU = "PP-47"
PYT = "pytest_pp410.html"
OK = "Aprobada en pytest: el resultado coincide con el esperado."

R1, R2, R3, R4, R5, R6, R7, R8 = (f"RQ-PP47-0{i}" for i in range(1, 9))


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


def portada(wb, hu_nuevas=None):
    ws = wb["Portada"]
    ws["B7"] = "0.12"
    ws["B8"] = ws["B8"].value.rstrip() + ", ronda 1 de PP-47 (PP-410, 04/11/2026)"
    if hu_nuevas:
        ws["B5"] = ws["B5"].value.rstrip().rstrip(".") + f"; {hu_nuevas}."
    wb.calculation.fullCalcOnLoad = True


def v(a, b):
    return QA / a / f"Pangea_{b}_v0.11.xlsx", QA / a / f"Pangea_{b}_v0.12.xlsx"


def fila_pytest(test):
    return ("Fila de informe", PYT, f"Fila de {test[:70]} en el informe de pytest")


# (requisito, tipo, prioridad, rol, precondición, pasos, esperado, test)
BASE = [
 (R1, "Funcional", "Crítica", "Administrador Comercial", "Cliente con 3 sedes y un plan con límites", "1. Crear cliente y 3 sedes. 2. Asignar el plan por PUT /comercial/clientes/{id}/suscripcion. 3. Contar sedes y contratos.", "El cliente tiene 3 sedes y un solo contrato (sin contratos separados por sede).", "test_ca1_cliente_con_tres_sedes_comparte_un_solo_contrato"),
 (R1, "Funcional", "Alta", "Sistema", "Modelos Cliente, Sede y Suscripcion", "1. Inspeccionar las columnas de la tabla sd. 2. Inspeccionar la FK de sscrpcn.", "Sede no guarda datos comerciales; el plan cuelga del Cliente.", "test_ca1_sede_no_guarda_datos_comerciales_y_cliente_es_la_raiz"),
 (R1, "Funcional", "Media", "Administrador Comercial", "Dos clientes con sedes y un plan del catálogo", "1. Asignar el mismo plan a dos clientes. 2. Comparar sus contratos.", "El plan es un catálogo reutilizable; cada cliente tiene su propio contrato.", "test_ca1_cada_cliente_tiene_su_propio_plan_aunque_comparta_catalogo"),
 (R2, "Funcional", "Alta", "Administrador Comercial", "Plan nuevo", "1. POST /comercial/planes. 2. PUT .../limites con ubicaciones, dispositivos y usuarios.", "Los límites se guardan y se devuelven.", "test_hu43_plan_guarda_limites_de_ubicaciones_dispositivos_y_usuarios"),
 (R2, "Funcional", "Crítica", "Administrador Comercial", "Plan nuevo", "1. PUT .../limites enviando sedes=2.", "El plan guarda y devuelve el máximo de sedes (PP-319).", "test_hu43_plan_guarda_limite_maximo_de_sedes"),
 (R2, "Negativa", "Media", "Administrador Comercial", "Plan nuevo", "1. PUT .../limites con sedes=-1.", "422: el límite de sedes no puede ser negativo.", "test_hu43_limite_de_sedes_negativo_se_rechaza"),
 (R2, "Negativa", "Media", "Administrador Comercial", "Plan nuevo", "1. PUT .../limites con ubicaciones=-1.", "422: los límites no pueden ser negativos.", "test_hu43_limites_negativos_se_rechazan"),
 (R2, "Negativa", "Alta", "Administrador Comercial", "Plan sin límites configurados", "1. Asignar el plan a un cliente.", "409: configura los límites antes de asignar el plan.", "test_hu45_no_se_asigna_plan_sin_limites_configurados"),
 (R3, "Funcional", "Crítica", "Administrador Comercial", "Cliente con 2 sedes y plan con máximo de 2", "1. POST /comercial/clientes/{id}/sedes.", "409 con «Has alcanzado el límite de tu plan…» y la sede no se crea.", "test_ca2_nueva_sede_sobre_el_limite_del_plan_se_rechaza"),
 (R3, "Límite", "Crítica", "Administrador Comercial", "Cliente con 1 sede y plan con máximo de 3", "1. Crear sede 2 y sede 3. 2. Intentar la sede 4.", "Las sedes 2 y 3 se crean (201) y la 4 se rechaza (409).", "test_ca2_sede_dentro_del_limite_se_crea_y_la_ultima_permitida_tambien"),
 (R3, "Límite", "Alta", "Administrador Comercial", "Cliente con 4 sedes y plan con máximo 0", "1. Crear una sede más.", "Límite 0 significa sin tope: 201.", "test_ca2_limite_cero_significa_sin_tope"),
 (R3, "Seguridad", "Alta", "Administrador Comercial", "Otro cliente con 3 sedes", "1. Crear la primera sede del cliente con máximo 1. 2. Intentar otra.", "Las sedes de otro cliente no cuentan: 201 y luego 409.", "test_ca2_las_sedes_de_otro_cliente_no_cuentan"),
 (R3, "Funcional", "Media", "Administrador Comercial", "Cliente al tope de su plan", "1. Rechazar sede. 2. Asignar un plan con más sedes. 3. Crear la sede.", "Tras reasignar a un plan mayor la sede se crea.", "test_ca2_subir_el_limite_del_plan_permite_nuevas_sedes_tras_reasignar"),
 (R3, "Negativa", "Alta", "Administrador Comercial / Cliente Final", "Cliente sin plan, cliente inexistente, nombre en blanco, rol sin permiso", "1. POST .../sedes en cada situación.", "409 sin plan, 404 cliente inexistente, 422 nombre en blanco y 403 para un rol no comercial.", "test_ca2_alta_de_sede_cliente_sin_plan_inexistente_rol_y_nombre"),
 (R3, "Negativa", "Alta", "Administrador Comercial", "Contrato vencido", "1. Marcar el contrato como Vencida. 2. Crear una sede.", "409: sin plan vigente no se agregan sedes.", "test_ca2_plan_vencido_no_permite_nuevas_sedes"),
 (R3, "Regresión", "Media", "Administrador Comercial", "Contrato sin la clave «sedes» en sus límites", "1. Quitar «sedes» de las condiciones. 2. Crear una sede.", "Un contrato anterior a PP-319 no bloquea (201).", "test_ca2_contrato_anterior_sin_limite_de_sedes_no_bloquea"),
 (R3, "Funcional", "Media", "Sistema", "Cliente con plan vigente", "1. comprobar_cupo con el recurso ubicaciones.", "El mecanismo de cupo existente sigue funcionando.", "test_ca2_el_limite_de_ubicaciones_si_se_aplica_con_409"),
 (R3, "Negativa", "Alta", "Sistema", "Cliente sin plan y PLAN_LIMITS_REQUIRE_SUBSCRIPTION=true", "1. comprobar_cupo.", "409: un cliente sin plan vigente no puede crecer.", "test_ca2_cliente_sin_plan_vigente_no_puede_crecer"),
 (R4, "Funcional", "Crítica", "Sistema", "Configuración de Celery Beat", "1. Leer beat_schedule.", "La tarea corre cada día a las 00:30.", "test_ca3_beat_programa_la_tarea_todos_los_dias"),
 (R4, "Funcional", "Crítica", "Sistema", "Contrato con renovación vencida ayer y sin cobro", "1. Ejecutar vencer_suscripciones_sin_cobro.", "El contrato pasa a Vencida y se encola el aviso.", "test_ca3_plan_con_renovacion_pasada_sin_cobro_pasa_a_vencida_y_avisa"),
 (R5, "Funcional", "Crítica", "Sistema", "Un Administrador Comercial activo y un Administrador", "1. Ejecutar notificar_suscripciones_vencidas.", "El correo llega solo al Administrador Comercial activo.", "test_ca3_aviso_llega_solo_al_administrador_comercial_activo"),
 (R4, "Funcional", "Alta", "Sistema", "Contrato vencido con un cobro registrado", "1. Ejecutar vencer_sin_cobro.", "El contrato con cobro no se marca vencido.", "test_ca3_plan_con_cobro_registrado_no_se_vence"),
 (R4, "Límite", "Alta", "Sistema", "Contrato vencido ayer", "1. Ejecutar la tarea dos veces el mismo día.", "La segunda corrida no vuelve a avisar.", "test_ca3_dos_corridas_el_mismo_dia_no_duplican_el_aviso"),
 (R4, "Límite", "Alta", "Sistema", "Contratos que vencen hoy y dentro de 15 días", "1. Ejecutar la tarea.", "No se tocan: el último día todavía es vigente.", "test_ca3_plan_vigente_o_en_su_ultimo_dia_no_se_toca"),
 (R5, "Negativa", "Media", "Sistema", "Sin contratos vencidos", "1. Notificar con lista vacía.", "No se envía ningún correo.", "test_ca3_sin_vencidas_no_se_envia_correo"),
 (R6, "Funcional", "Crítica", "Administrador Comercial", "Cliente con plan", "1. Registrar 3 cobros. 2. Listar el historial.", "Los 3 cobros se conservan y el primero no cambia.", "test_ca4_tres_cobros_se_conservan_y_el_primero_no_cambia"),
 (R6, "Límite", "Alta", "Administrador Comercial", "Cliente con plan", "1. Registrar dos cobros idénticos.", "Quedan dos registros distintos.", "test_ca4_dos_cobros_identicos_son_dos_registros"),
 (R6, "Funcional", "Alta", "Administrador Comercial", "Cliente con plan", "1. Registrar un cobro. 2. Leer su contrato.", "El cobro queda ligado al período contratado (contrato).", "test_ca4_cobro_queda_ligado_al_periodo_contratado_y_el_nuevo_no_lo_mueve"),
 (R6, "Seguridad", "Crítica", "Administrador Comercial", "Cobro registrado", "1. PUT, PATCH y DELETE sobre .../cobros/{id}.", "404 o 405: la API no permite editar ni borrar cobros.", "test_ca4_la_api_no_permite_editar_ni_borrar_un_cobro"),
 (R6, "Negativa", "Alta", "Administrador Comercial", "Cliente con plan", "1. Registrar cobros con monto 0, negativo, texto, 3 decimales, fecha futura, fecha mal escrita y método inválido.", "422 en cada caso y no se guarda nada.", "test_ca4_cobros_invalidos_se_rechazan_y_no_se_guardan"),
 (R6, "Negativa", "Media", "Administrador Comercial", "Cliente inexistente y cliente sin plan", "1. Registrar un cobro en cada caso.", "404 y 409.", "test_ca4_cobro_a_cliente_inexistente_o_sin_plan"),
 (R6, "Seguridad", "Crítica", "Administrador", "Cliente cualquiera", "1. Registrar un cobro con rol Administrador.", "403: solo el Administrador Comercial registra cobros.", "test_ca4_solo_el_administrador_comercial_registra_cobros"),
 (R7, "Funcional", "Crítica", "Administrador Comercial", "Clientes con vencimiento a 90, 5 y -3 días", "1. GET /comercial/vencimientos con rango todos, vencidos, 7 y 30.", "Cada filtro devuelve los clientes que le corresponden.", "test_ca5_la_tabla_muestra_vigentes_proximos_y_vencidos_y_filtra_por_rango"),
 (R7, "E2E", "Crítica", "Administrador Comercial", "Contrato vencido ayer", "1. Ejecutar vencer_sin_cobro. 2. Consultar rango=vencidos.", "El plan marcado por la tarea sigue en el filtro con estado Vencida.", "test_ca5_un_plan_vencido_por_la_tarea_sigue_en_el_filtro_vencidos"),
 (R7, "Seguridad", "Alta", "Administrador Comercial / Administrador", "Rol sin permiso y rango inventado", "1. GET con rango=cualquiera. 2. GET con rol Administrador.", "422 y 403.", "test_ca5_rango_invalido_y_acceso_restringido"),
 (R7, "Negativa", "Media", "Administrador Comercial", "Cliente sin plan", "1. Consultar vencimientos.", "El cliente sin plan no aparece.", "test_ca5_clientes_sin_plan_no_aparecen_en_vencimientos"),
 (R8, "Funcional", "Media", "Sistema", "Archivo backend/docs/modelo-comercial-er.md", "1. Leer el documento. 2. Buscar el diagrama y las relaciones.", "Documenta Cliente-Sede, Plan-Límites, Cliente-Contrato y Contrato-Cobro, y describe mx_sds como en uso.", "test_pp322_el_diagrama_er_documenta_cliente_sede_plan_limites_contrato_y_cobro"),
]
CASOS = []
for req, tipo, prio, rol, pre, pasos, esp, test in BASE:
    CASOS.append((req, tipo, prio, rol, pre, pasos, "Datos generados por la propia prueba", esp, OK, "Aprobado", "—", T + test, fila_pytest(test)))
N = len(CASOS)
ULT = ID0 + N - 1
N_OK = N

REQ = {
    R1: ("Un Cliente puede tener una o más Sedes bajo un mismo Plan de Suscripción, sin contratos separados por sede (HU44).", "PP-317 / PP-318"),
    R2: ("El catálogo de planes parametriza límites de sedes, ubicaciones, dispositivos y usuarios y se asigna al cliente con límites válidos (HU42, HU43, HU45).", "PP-317 / PP-318 / PP-319"),
    R3: ("El sistema rechaza la creación de una sede que excede el límite del plan vigente del cliente (HU43).", "PP-319"),
    R4: ("Un plan cuya renovación pasó sin cobro cambia solo a «vencido», una vez, con Celery Beat cada día.", "PP-320"),
    R5: ("El vencimiento automático genera una notificación al Administrador Comercial (HT-14).", "PP-321"),
    R6: ("El historial de cobros del cliente conserva todos los pagos; un cobro nuevo no elimina ni sobrescribe los anteriores (HU46).", "PP-317 / PP-318"),
    R7: ("HU47 permite filtrar los planes por vencimiento con los datos de la tarea programada.", "PP-320"),
    R8: ("Se documenta el diagrama entidad-relación del modelo comercial.", "PP-322"),
}
ESTADOS = {f"CP-{ID0 + k}": c[9] for k, c in enumerate(CASOS)}
IDX = {c[11].split("::")[1]: k for k, c in enumerate(CASOS)}


def cp(test_parcial):
    return f"CP-{ID0 + next(k for t, k in IDX.items() if test_parcial in t)}"


# ================================ Casos ================================
src, dst = v("02_Casos_de_Prueba", "Casos_de_Prueba")
wb = openpyxl.load_workbook(src)
ws = wb["Casos de Prueba"]
r = vacia(ws)
assert r == ID0 + 1, r
for k, c in enumerate(CASOS):
    req, tipo, prio, rol, pre, pasos, datos, esp, obt, estado, defecto, test, ev = c
    fila = [f"CP-{ID0 + k}", HU, req, tipo, prio, rol, pre, pasos, datos, esp, obt, estado, defecto, f"EV-CP-{ID0 + k}", "QA", FECHA, test, L, COMMIT]
    estilo(ws, r - 1, r + k, 19)
    for j, val in enumerate(fila, 1):
        ws.cell(r + k, j, val)
wr = wb["Regresión"]
rr = vacia(wr, ini=3)
RG = [
 ("RG-29", "Humo", "Suite pytest de QA de PP-47: multi-sede, límites, vencimiento, cobros, vencimientos y diagrama ER", HU, R3, "Alta", f"Los {N} casos de pytest (CP-{ID0} a CP-{ULT})", "Flujo principal de la HT", "Cada ronda", "—", "qa/03_Evidencias/PP-410/test_pp410_qa.py", "—", "Aprobado", FECHA, "QA", "45 aprobadas.", "Sprint 1", "EV-PP410-INF-01", None),
 ("RG-30", "Regresión", "Suites existentes de comercial, contratos, cobros, límites, ubicaciones, solicitudes y empresas", HU, R2, "Media", "159 pruebas de tests/services y tests/routers", "PP-319 tocó contratos.py, limites_plan.py, comercial.py y ubicaciones.py", "Cada ronda", "—", "tests/services/test_vencimientos.py, test_limites_plan.py; tests/routers/test_comercial.py, test_contratos.py, test_registrar_cobro.py, test_ubicaciones.py, test_solicitudes_suscripcion.py, test_empresas.py", "—", "Aprobado", FECHA, "QA", "159 aprobadas.", "Sprint 1", "EV-PP410-INF-02", None),
 ("RG-31", "Regresión", "Consultar vencimientos HU47 (tests/routers/test_vencimientos.py)", HU, R7, "Media", "23 pruebas", "El filtro de vencimientos lee los contratos que la tarea marca como Vencida", "Cada ronda", "—", "tests/routers/test_vencimientos.py", "—", "Aprobado", FECHA, "QA", "23 aprobadas.", "Sprint 1", "EV-PP410-INF-03", None),
 ("RG-32", "Regresión", "Suite completa del backend (excepto la de carga)", HU, R3, "Alta", "1 020 pruebas de backend/tests", "PP-319 cambia el contrato de límites que usan varios módulos", "Cada ronda", "—", "backend/tests (completo)", "—", "Aprobado", FECHA, "QA", "1 020 aprobadas en 7 min 3 s, sobre db86ba8 (el commit siguiente solo cambia documentación).", "Sprint 1", "—", None),
]
for k, fila in enumerate(RG):
    estilo(wr, rr - 1, rr + k, 19)
    for j, val in enumerate(fila, 1):
        wr.cell(rr + k, j, val)
rs = wb["Resumen"]
fila_hu = buscar(rs, "HU-28") + 1
insertar_fila(rs, fila_hu)
fila_como(rs, fila_hu - 1, fila_hu, 8)
rs.cell(fila_hu, 1, HU)
portada(wb, f"PP-47 Modelo de datos comercial multi-sede y vencimientos (ronda 1: {N} casos, {N_OK} aprobados; CP-{ID0} a CP-{ULT})")
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
    filas.append((f"EV-CP-{ID0 + k}", f"CP-{ID0 + k}", HU, tipo, que, nombre, UBIC, "QA", f"{FECHA} {HORA}", kb, h, COMMIT, "Adjuntada", c[9], ""))
EXTRA = [
 ("EV-PP410-INF-01", f"CP-{ID0}", "Informe HTML", f"Informe completo de pytest de PP-47: {N} aprobadas", PYT),
 ("EV-PP410-INF-02", "RG-30", "Informe HTML", "Informe de regresión: 159 aprobadas", "pytest_regresion.html"),
 ("EV-PP410-INF-03", "RG-31", "Informe HTML", "Informe de regresión de HU47: 23 aprobadas", "pytest_regresion_hu47.html"),
 ("EV-PP410-INF-04", f"CP-{ID0}", "Captura", "Captura del informe pytest de PP-47 (extracto: primeras 10 filas)", "EV-PP410-INF-01_captura-informe-pytest.png"),
 ("EV-PP410-INF-05", "RG-30", "Captura", "Captura de la regresión (extracto: primeras 10 filas de 159)", "EV-PP410-INF-02_captura-informe-regresion-extracto.png"),
 ("EV-PP410-INF-06", "RG-31", "Captura", "Captura de la regresión de HU47 (extracto: primeras 10 filas de 23)", "EV-PP410-INF-03_captura-informe-regresion-hu47-extracto.png"),
]
for ide, caso, tipo, que, nombre in EXTRA:
    kb, h = sha(nombre)
    filas.append((ide, caso, HU, tipo, que, nombre, UBIC, "QA", f"{FECHA} {HORA}", kb, h, COMMIT, "Adjuntada", "Informativo", ""))
for k, f in enumerate(filas):
    estilo(ws, r - 1, r + k, 15)
    for j, val in enumerate(f, 1):
        ws.cell(r + k, j, val)
N_EVID = len(filas)
portada(wb)
wb.save(dst)
print("evidencias ok", N_EVID)

# ============================== Defectos ==============================
src, dst = v("04_Defectos", "Registro_de_Defectos")
wb = openpyxl.load_workbook(src)
wp = wb["Pendientes de entrega"]
rp = vacia(wp)
estilo(wp, rp - 1, rp, 11)
PEN = ("PEN-07", "PP-319", HU, "Validar el límite de sedes según el plan vigente: el plan no guardaba el máximo de sedes y ninguna sede nueva se rechazaba (comprobar_cupo no conocía el recurso «sedes»).", "Dev (GA)", "En curso", "Entregada por QA en qa/correcciones (commit db86ba8); falta integrarla a dev", "Cuando se integre db86ba8", "Sí, hasta integrar db86ba8 y el resto de la rama feature/PP-47", "Hallazgo de QA en la ronda 1 de PP-47", "No es un defecto del producto. A pedido del usuario, QA implementó la entrega en qa/correcciones: sedes en PUT /planes/{id}/limites, POST /comercial/clientes/{id}/sedes y comprobar_cupo(..., «sedes»). Reprueba RG-29.")
for j, val in enumerate(PEN, 1):
    wp.cell(rp, j, val)
ws = wb["Observaciones"]
r = vacia(ws)
OBS = [
 ("OBS-42", cp("ca2_nueva_sede_sobre_el_limite"), HU, "PP-320 a PP-322 (commit ccfc588) están solo en origin/feature/PP-47-modelo-comercial, que va 27 commits atrás de dev; PP-319 (commit db86ba8 en qa/correcciones) tampoco está en dev. La HT no queda cerrada hasta integrarlas.", "Subir la rama (push), abrir el PR hacia dev y resolver conflictos con dev.", "QA", FECHA, "Abierta", "Integración", "Media", "Dev", None, None, None),
 ("OBS-43", cp("ca4_cobro_queda_ligado"), HU, "HU46 pide el cobro «vinculado a un período de facturación específico»; el modelo cbr cuelga del contrato (sscrpcn) y no tiene un campo de período propio. El contrato es el período contratado y cumple el criterio de no sobrescribir.", "El PO confirma si el contrato basta como período o se agrega un campo de período al cobro.", "QA", FECHA, "Abierta", "Decisión del PO", "Baja", "PO", None, None, None),
 ("OBS-44", cp("ca2_nueva_sede_sobre_el_limite"), HU, "El diagrama ER y la decisión del flujo multiempresa decían que «la sede es un detalle interno» y que mx_sds ya no se usa como cupo, lo que contradice el criterio de la HT («rechaza la creación de una sede que excede el límite»). QA siguió el criterio de la HT y actualizó el ER.", "El PO confirma que el límite de sedes sí es un requisito vigente.", "QA", FECHA, "Abierta", "Decisión del PO", "Media", "PO", None, None, None),
 ("OBS-45", cp("ca2_cliente_sin_plan_vigente"), HU, "El test existente tests/services/test_limites_plan.py::test_suscripcion_vencida_bloquea_altas falla con la configuración por defecto y pasa con PLAN_LIMITS_REQUIRE_SUBSCRIPTION=false: depende de una variable de entorno que no fija.", "Fijar la variable con monkeypatch dentro del test.", "QA", FECHA, "Abierta", "Mejora técnica", "Baja", "Dev", None, None, None),
 ("OBS-46", cp("ca5_la_tabla_muestra"), HU, "No se probó la pantalla de HU47 con Playwright ni el envío real del correo (HT-14 se verificó con el envío simulado); no hay pytest-cov instalado, así que no se midió cobertura.", "Probar la pantalla y el correo en el entorno desplegado cuando HT-14 use SES.", "QA", FECHA, "Abierta", "Alcance", "Baja", "QA", None, None, None),
]
for k, f_ in enumerate(OBS):
    estilo(ws, r - 1, r + k, 14)
    for j, val in enumerate(f_, 1):
        ws.cell(r + k, j, val)
wh = wb["Historial de rondas"]
rh = vacia(wh)
fila = ("1", HU, FECHA, COMMIT, str(N), str(N_OK), "0", "0", "0", "0", "5", str(N_EVID),
        f"Primera ronda de PP-47 (PP-410): {N} casos de pytest aprobados, regresión de 159 + 23 pruebas y suite completa de 1 020 pruebas sin fallos. PP-319 no estaba entregada (PEN-07); QA la implementó en qa/correcciones y se reprobó. 5 observaciones: OBS-42 integración, OBS-43 período del cobro, OBS-44 criterio de sedes, OBS-45 test dependiente del entorno y OBS-46 alcance.")
estilo(wh, rh - 1, rh, 13)
for j, val in enumerate(fila, 1):
    wh.cell(rh, j, val)
rs = wb["Resumen"]
fila_hu = buscar(rs, "HU-28") + 1
insertar_fila(rs, fila_hu)
fila_como(rs, fila_hu - 1, fila_hu, 3)
rs.cell(fila_hu, 1, HU)
portada(wb)
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
OBS_RQ = {R1: "—", R2: "OBS-44", R3: "OBS-44, OBS-42", R4: "OBS-42", R5: "OBS-42, OBS-46", R6: "OBS-43", R7: "OBS-46", R8: "OBS-44"}
REG_RQ = {R1: "RG-29", R2: "RG-29, RG-30", R3: "RG-29, RG-32", R4: "RG-29, RG-30", R5: "RG-29", R6: "RG-29, RG-30", R7: "RG-29, RG-31", R8: "RG-29"}
for rid, (txt, back) in REQ.items():
    modelo = r_nueva - 1
    estilo(ws, modelo, r_nueva, 13)
    for col in (8, 9):
        ws.cell(r_nueva, col).value = _mapear_refs(ws.cell(modelo, col).value, lambda n: r_nueva if n == modelo else n)
    casos = por_req[rid]
    ok = [ESTADOS[x] for x in casos].count("Aprobado")
    ws.cell(r_nueva, 1, rid); ws.cell(r_nueva, 2, txt)
    ws.cell(r_nueva, 3, "PP-47 — criterios de aceptación y detalles de la conversación técnica")
    ws.cell(r_nueva, 4, HU); ws.cell(r_nueva, 5, back); ws.cell(r_nueva, 6, "Alta")
    ws.cell(r_nueva, 7, ", ".join(casos)); ws.cell(r_nueva, 10, "Aprobado" if ok == len(casos) else "Parcial")
    ws.cell(r_nueva, 11, "—"); ws.cell(r_nueva, 12, OBS_RQ[rid]); ws.cell(r_nueva, 13, REG_RQ[rid])
    r_nueva += 1
hist = wb["Historias"]
fh = vacia(hist)
assert fh == 10, fh
for col, val in enumerate((HU, HU, "Modelo de datos comercial multi-sede y automatización de vencimientos", "Modelo comercial", "Listo", "Listo", "Listo", ", ".join(REQ)), 1):
    hist.cell(fh, col, val)
hist.cell(fh, 17, "Sin defectos del producto. PP-319 no estaba entregada (PEN-07): QA la implementó en qa/correcciones (db86ba8) y pasó. Pendiente de integración a dev: OBS-42. Decisiones del PO: OBS-43 (período del cobro) y OBS-44 (límite de sedes como requisito vigente).")
hist.cell(fh, 18, "Probado sobre dev + feature/PP-47-modelo-comercial (merge local b07660f) más qa/correcciones (db86ba8 y a8d6b35): PP-320 a PP-322 (ccfc588, Gean Pierre) no están en dev; PP-317 y PP-318 sí.")
wf = wb["Fuente casos"]
rf = vacia(wf)
for k, c in enumerate(CASOS):
    estilo(wf, rf - 1, rf + k, 3)
    wf.cell(rf + k, 1, f"CP-{ID0 + k}"); wf.cell(rf + k, 2, HU); wf.cell(rf + k, 3, c[9])
portada(wb)
wb.save(dst)
print("rtm ok")
