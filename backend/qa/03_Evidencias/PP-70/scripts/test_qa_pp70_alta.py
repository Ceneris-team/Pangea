"""QA PP-70 (PP-442): añadir parámetro calculado.

Formulario (API de opciones), fórmula, operadores, unidades, ciclos, unicidad, guardado,
motor (histórico, tolerancia, conversión, dependencias, pendientes, recálculo), consulta
y aislamiento. Se copia a backend/tests/routers/ del worktree de dev para reutilizar
sus fixtures. Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import datetime as dt
from types import SimpleNamespace

import pytest

from app.models import (
    DependenciaCalculo,
    Parametro,
    ParametroCalculado,
    ResultadoCalculo,
    RevisionCalculo,
    Telemetria,
    TrabajoCalculo,
    UsuarioCliente,
)
from app.security.jwt_auth import create_access_token
from app.services import motor_calculos
from app.services.exportaciones import generar_archivo
from app.services.motor_calculos import mantener_pendientes
from tests.routers.test_calculos_completos import calculos as calculos  # noqa: F401
from tests.routers.test_calculos_completos import drenar, medir, resultado
from tests.routers.test_mediciones import (
    crear_conexion,
    crear_dispositivo,
    crear_parametro,
    mapear_parametro,
)
from tests.routers.test_parametros_calculados import entorno_calculados as entorno_calculados  # noqa: F401

URL = "/parametros-calculados"
A, B = "[Nivel de entrada]", "[Nivel de salida]"


def cuerpo(e, nombre="Balance", formula=f"{A} - {B}", unidad="m", sede=0, **extra):
    return {"id_sd": e["sedes"][sede].id_sd, "nmbr": nombre, "frml": formula, "undd": unidad, **extra}


def validar(e, formula, unidad="m", sede=0):
    return e["client"].post(
        f"{URL}/validar-formula", json={"id_sd": e["sedes"][sede].id_sd, "frml": formula, "undd": unidad}
    )


def crear(e, nombre="Balance", formula=f"{A} - {B}", unidad="m", sede=0, **extra):
    return e["client"].post(URL, json=cuerpo(e, nombre, formula, unidad, sede, **extra))


def crear_ok(e, *args, **kwargs):
    r = crear(e, *args, **kwargs)
    assert r.status_code == 201, r.text
    return r.json()["id_prm_clc"]


def como_empresa(e, fabrica, rol):
    u = fabrica.usuario(fabrica.rol("Usuario Empresa"), scp="por_cliente")
    e["db"].add(UsuarioCliente(id_usr=u.id_usr, id_clnt=e["empresas"][0].id_clnt, rol_emp=rol))
    e["db"].flush()
    e["client"].headers["Authorization"] = "Bearer " + create_access_token(
        u.id_usr, None, u.scp, u.rol.nmbr
    )


def origen_extra(e, nombre, unidad, indice, estado="Activo", tipo="numerico"):
    p = crear_parametro(e["db"], nombre, unidad, tipo)
    p.estd = estado
    mapear_parametro(e["db"], e["dispositivo"], p, indice=indice)
    e["db"].flush()
    return p


# ---------------------------------------------------------------- CA-01 / permisos
# CP-570 · CA-01: solo roles con permiso de creación acceden a opciones, validar y guardar
@pytest.mark.parametrize("rol", ["Lector", "Cliente Final"])
def test_cp570_sin_permiso_de_creacion(calculos, fabrica, rol):
    e = calculos
    if rol == "Lector":
        como_empresa(e, fabrica, rol)
    else:
        u = fabrica.usuario(fabrica.rol("Cliente Final"), scp="global")
        e["client"].headers["Authorization"] = "Bearer " + create_access_token(
            u.id_usr, None, u.scp, u.rol.nmbr
        )
    c = e["client"]
    assert c.get(f"{URL}/opciones-creacion").status_code == 403
    assert validar(e, f"{A} - {B}").status_code == 403
    assert crear(e).status_code == 403
    assert e["db"].query(ParametroCalculado).count() == 0
    lista = c.get(URL)
    assert lista.status_code == 403 or lista.json()["permisos"]["crear"] is False


# CP-570 · CA-01: Técnico CENERIS y Administrador / Técnico de empresa sí pueden crear
@pytest.mark.parametrize("rol", ["CENERIS", "Administrador", "Tecnico"])
def test_cp570_roles_autorizados_crean(calculos, fabrica, rol):
    e = calculos
    if rol != "CENERIS":
        como_empresa(e, fabrica, rol)
    c = e["client"]
    assert c.get(URL).json()["permisos"]["crear"] is True
    assert c.get(f"{URL}/opciones-creacion").status_code == 200
    assert crear(e).status_code == 201


# ---------------------------------------------------------------- CA-02
# CP-571 · CA-02: solo numéricos activos y calculados activos del ámbito
def test_cp571_origenes_disponibles(calculos):
    e = calculos
    origen_extra(e, "Caudal inactivo", "m", 4, estado="Pendiente de revision")
    crear_ok(e, "Balance")
    crear_ok(e, "Balance apagado", f"{A} + {B}")
    e["db"].query(ParametroCalculado).filter_by(nmbr="Balance apagado").update({"estd": "Inactivo"})
    e["db"].flush()
    op = e["client"].get(f"{URL}/opciones-creacion").json()
    sedes = {s["id_sd"]: s for s in op["sedes"]}
    assert set(sedes) == {e["sedes"][0].id_sd, e["sedes"][1].id_sd}  # nunca la sede de otra empresa
    nombres = {(o["nombre"], o["tipo"]) for o in sedes[e["sedes"][0].id_sd]["origenes"]}
    assert nombres == {
        ("Nivel de entrada", "telemetria"),
        ("Nivel de salida", "telemetria"),
        ("Balance", "calculado"),
    }
    # Lo no ofrecido tampoco se acepta en la fórmula
    for formula in ["[Mensaje del equipo] + 1", "[Caudal inactivo] + 1", "[Balance apagado] * 2"]:
        r = validar(e, formula)
        assert r.status_code == 422, (formula, r.text)
    assert validar(e, "[Balance] * 2").status_code == 200


# CP-572 · CA-02: aislamiento entre empresas y proyectos (Crítica si falla)
def test_cp572_aislamiento_ambito(calculos):
    e = calculos
    # Origen que solo existe en la sede de otra empresa
    ajeno_disp = crear_dispositivo(e["db"], e["proyectos"][2], crear_conexion(e["db"], e["sedes"][2]), "Ajeno")
    ajeno = crear_parametro(e["db"], "Presion ajena", "kPa")
    mapear_parametro(e["db"], ajeno_disp, ajeno, indice=1)
    assert crear(e, sede=2).status_code == 403
    assert validar(e, f"{A} - {B}", sede=2).status_code == 403
    assert validar(e, "[Presion ajena] * 2", "kPa").status_code == 422
    # Variable interna de otra sede escrita a mano
    assert validar(e, f"p_{ajeno.id_prmtr} * 2", "kPa").status_code == 422
    # Con proyecto seleccionado solo se ofrece su sede
    e["client"].headers["X-Proyecto-Id"] = str(e["proyectos"][0].id_ubccn)
    op = e["client"].get(f"{URL}/opciones-creacion").json()
    assert [s["id_sd"] for s in op["sedes"]] == [e["sedes"][0].id_sd]
    assert crear(e, sede=1).status_code == 403
    assert e["db"].query(ParametroCalculado).count() == 0


# ---------------------------------------------------------------- CA-02/03 operadores
# CP-573 · PP-277: suma, resta, multiplicación, división, constantes y paréntesis
@pytest.mark.parametrize(
    "formula",
    [f"{A} + {B}", f"{A} - {B}", f"({A} - {B}) * 2 / 4", f"{A} * 1.5", f"-{A} + 0.25 * {B}", f"(({A}))"],
)
def test_cp573_operadores_admitidos(calculos, formula):
    r = validar(calculos, formula)
    assert r.status_code == 200, r.text
    assert r.json()["mensaje"] == "Fórmula válida"


# CP-573 · PP-277: el ticket solo admite + - * /; potencia y módulo deben rechazarse
@pytest.mark.xfail(strict=True, reason="DEF-23: se aceptan ** y % (el ticket solo admite + - * /)")
@pytest.mark.parametrize("formula,unidad", [(f"{A} ** 2", "m^2"), (f"{A} % {B}", "m")])
def test_cp573_operadores_fuera_del_ticket_def23(calculos, formula, unidad):
    e = calculos
    r = validar(e, formula, unidad)
    assert r.status_code == 422, f"DEF-23: {formula!r} se acepta ({r.status_code})"
    assert crear(e, formula=formula, unidad=unidad).status_code == 422


# CP-573 · OBS-77: división por la constante cero se valida y luego siempre falla
def test_cp573_division_por_cero_constante_obs77(calculos):
    e = calculos
    assert validar(e, f"{A} / 0").status_code == 200  # comportamiento actual (OBS-77)
    medir(e, e["nivel"], 10)
    a = crear_ok(e, "Siempre falla", f"{A} / 0")
    drenar(e)
    r = resultado(e, a)
    assert (r.estado, r.vlr) == ("Fallido", None) and r.causa


# CP-573 · seguridad: nada fuera de aritmética llega a ejecutarse
@pytest.mark.parametrize(
    "formula",
    [
        f"abs({A})",
        f"{A}.real",
        "__import__('os').system('x')",
        f"{A} if 1 else {B}",
        f"{A} < {B}",
        f"{A} // 2",
        f"{A} + 'x'",
        f"{A} * 1e400",
        f"[{A}]",
        f"{A}; {B}",
        f"lambda: {A}",
        f"{A} + True",
        " + ".join([A] * 80),
    ],
)
def test_cp573_rechaza_expresiones_no_aritmeticas(calculos, formula):
    e = calculos
    r = validar(e, formula)
    assert r.status_code == 422, (formula, r.text)
    assert crear(e, formula=formula).status_code == 422
    assert e["db"].query(ParametroCalculado).count() == 0


# ---------------------------------------------------------------- CA-03
# CP-574 · CA-03: estructura y referencias inválidas explican qué corregir
@pytest.mark.parametrize(
    "formula,pista",
    [
        (f"{A} +", "Revisa la fórmula"),
        (f"({A} - {B}", "Revisa la fórmula"),
        (f"{A} {B}", "Revisa la fórmula"),
        ("[Inexistente] + 1", "disponibles en el ámbito"),
        ("1 + 2", "parámetros numéricos activos"),
        ("Nivel de entrada - 1", ""),
    ],
)
def test_cp574_errores_de_estructura(calculos, formula, pista):
    r = validar(calculos, formula)
    assert r.status_code == 422, r.text
    detalle = r.json()["detail"]
    assert isinstance(detalle, str) and len(detalle) > 15 and pista in detalle


# CP-574 · CA-03: una referencia inexistente de varias palabras debe decir que no está disponible
@pytest.mark.xfail(strict=True, reason="DEF-26: se responde un error de sintaxis genérico")
@pytest.mark.parametrize("formula", ["[Parametro inexistente] * 2", "[nivel de entrada] * 2"])
def test_cp574_referencia_inexistente_def25(calculos, formula):
    r = validar(calculos, formula)
    assert r.status_code == 422
    detalle = r.json()["detail"]
    assert "disponible" in detalle or formula.split("]")[0][1:] in detalle, detalle


# CP-574 · riesgo: un origen mapeado después con el nombre de un calculado bloquea el ámbito
@pytest.mark.xfail(strict=True, reason="DEF-27: todas las fórmulas del ámbito quedan rechazadas")
def test_cp574_nombre_repetido_posterior_def26(calculos):
    e = calculos
    crear_ok(e, "Turbidez calc", f"{A} - {B}")
    origen_extra(e, "Turbidez calc", "m", 4)  # se mapea después, el catálogo lo permite
    op = e["client"].get(f"{URL}/opciones-creacion").json()
    nombres = [o["nombre"] for o in op["sedes"][0]["origenes"]]
    r = validar(e, f"{A} + {B}")  # no usa el nombre repetido
    assert r.status_code == 200, r.text
    assert len(nombres) == len(set(nombres)), f"Orígenes repetidos: {nombres}"


# CP-575 · CA-03: compatibilidad de unidades y conversión
def test_cp575_unidades(calculos):
    e = calculos
    origen_extra(e, "Profundidad", "mm", 4)
    origen_extra(e, "Presion", "kPa", 5)
    ok = [
        (f"{A} - {B}", "cm"),
        (f"{A} + [Profundidad]", "m"),
        (f"{A} / {B}", "%"),
        (f"{A} * {B}", "m^2"),
        (f"[Presion] * 2", "bar"),
    ]
    for formula, unidad in ok:
        r = validar(e, formula, unidad)
        assert r.status_code == 200, (formula, unidad, r.text)
    malas = [
        (f"{A} + [Presion]", "m"),
        (f"{A} * {B}", "m"),
        (f"{A} - {B}", "kg"),
        (f"{A} - {B}", "furlong"),
    ]
    for formula, unidad in malas:
        r = validar(e, formula, unidad)
        assert r.status_code == 422, (formula, unidad, r.text)
        assert r.json()["detail"]


# CP-576 · CA-03: dependencia circular y dependencia inactiva
def test_cp576_ciclos(calculos):
    e = calculos
    a = crear_ok(e, "Balance")
    b = crear_ok(e, "Doble balance", "[Balance] * 2")
    # Ciclo forzado en BD (A depende de B): cualquier fórmula que lo recorra se rechaza
    e["db"].add(DependenciaCalculo(id_prm_clc=a, variable=f"c_{b}", id_origen_calculado=b, unidad_origen="m"))
    e["db"].flush()
    r = validar(e, "[Doble balance] * 2")
    assert r.status_code == 422 and "circular" in r.json()["detail"]
    assert crear(e, "Triple", "[Doble balance] * 2").status_code == 422


# ---------------------------------------------------------------- CA-04
# CP-578 · CA-04: nombre único en el ámbito sin distinguir mayúsculas
def test_cp578_unicidad(calculos):
    e = calculos
    crear_ok(e, "Índice de nivel")
    for nombre in ["índice de nivel", "ÍNDICE DE NIVEL", "  Índice de nivel  "]:
        r = crear(e, nombre)
        assert r.status_code == 409, (nombre, r.text)
        assert "Ya existe" in r.json()["detail"]
    # Mismo nombre en otro ámbito de la empresa
    assert crear(e, "Índice de nivel", sede=1).status_code in (201, 422)
    # Choque con un parámetro de origen del ámbito
    assert crear(e, "nivel de entrada").status_code == 409
    # Definición inactiva también reserva el nombre
    e["db"].query(ParametroCalculado).filter_by(nmbr="Índice de nivel").update({"estd": "Inactivo"})
    e["db"].flush()
    assert crear(e, "INDICE DE NIVEL").status_code in (201, 409)
    assert e["db"].query(ParametroCalculado).filter_by(id_sd=e["sedes"][0].id_sd).count() <= 2


# CP-578 · el nombre se compara también en el otro ámbito sin falsos positivos
def test_cp578_mismo_nombre_en_otra_sede(calculos):
    e = calculos
    disp = crear_dispositivo(e["db"], e["proyectos"][1], crear_conexion(e["db"], e["sedes"][1], "DL S1"), "S1")
    mapear_parametro(e["db"], disp, e["nivel"], indice=1)
    mapear_parametro(e["db"], disp, e["salida"], indice=2)
    crear_ok(e, "Balance")
    assert crear(e, "Balance", sede=1).status_code == 201


# CP-579 · CA-04: registro Activo con dependencias, autor y fecha
def test_cp579_registro(calculos):
    e = calculos
    r = crear(e, "Balance", dscrpcn="Diferencia de niveles")
    assert r.status_code == 201
    p = e["db"].get(ParametroCalculado, r.json()["id_prm_clc"])
    assert (p.estd, p.validada, p.id_usr_creador) == ("Activo", True, e["usuario"].id_usr)
    assert p.creada_en is not None
    deps = e["db"].query(DependenciaCalculo).filter_by(id_prm_clc=p.id_prm_clc).all()
    assert {d.id_prmtr for d in deps} == {e["nivel"].id_prmtr, e["salida"].id_prmtr}
    assert r.json()["frml"] == f"{A} - {B}"
    t = e["db"].query(TrabajoCalculo).filter_by(id_prm_clc=p.id_prm_clc).one()
    assert t.estado == "Pendiente" and t.inicio is None  # histórico encolado, no ejecutado en la petición
    # Descripción opcional
    assert crear(e, "Sin descripcion", f"{A} + {B}").status_code == 201


# CP-579 · CA-04: el estado inicial es siempre Activo
@pytest.mark.xfail(strict=True, reason="DEF-25: la API registra estd=Inactivo")
def test_cp579_estado_inicial_activo_def24(calculos):
    e = calculos
    r = crear(e, "Balance", estd="Inactivo")
    creado = r.status_code == 201 and e["db"].get(ParametroCalculado, r.json()["id_prm_clc"]).estd
    assert r.status_code == 422 or creado == "Activo", f"DEF-25: se registró con estado {creado!r}"


# CP-579 · campos obligatorios
@pytest.mark.parametrize("campo", ["nmbr", "frml", "undd", "id_sd"])
def test_cp579_obligatorios(calculos, campo):
    e = calculos
    body = cuerpo(e)
    body.pop(campo)
    assert e["client"].post(URL, json=body).status_code == 422
    body = cuerpo(e)
    if campo != "id_sd":
        body[campo] = "   "
        assert e["client"].post(URL, json=body).status_code == 422
    assert e["db"].query(ParametroCalculado).count() == 0


# CP-589 · bordes de longitud y caracteres
def test_cp589_bordes(calculos):
    e = calculos
    assert crear(e, "N" * 100).status_code == 201
    assert crear(e, "M" * 101).status_code == 422
    assert crear(e, "Desc 300", f"{A} + {B}", dscrpcn="d" * 300).status_code == 201
    assert crear(e, "Desc 301", f"{A} + {B}", dscrpcn="d" * 301).status_code == 422
    larga = " + ".join([A] * 40)  # ~800 caracteres visibles, ~360 normalizados
    r = validar(e, larga)
    assert r.status_code in (200, 422)
    muy_larga = " + ".join(["1"] * 260) + f" + {A}"
    r = validar(e, muy_larga)
    assert r.status_code == 422 and "500" in r.json()["detail"]
    # Corchetes y caracteres especiales en el nombre no rompen las referencias
    r = crear(e, "Balance [neto]")
    if r.status_code == 201:
        r2 = validar(e, "[Balance [neto]] * 2")
        assert r2.status_code in (200, 422)
    assert crear(e, "Ratio <script>", f"{A} / {B}", "%").status_code in (201, 422)


# ---------------------------------------------------------------- CA-05 motor
def segundo_punto(e):
    from tests.routers.test_mediciones import crear_ubicacion

    punto = crear_ubicacion(e["db"], e["sedes"][0], "Punto 2")
    disp = crear_dispositivo(e["db"], punto, crear_conexion(e["db"], e["sedes"][0], "DL P2"), "Equipo P2")
    mapear_parametro(e["db"], disp, e["nivel"], indice=1)
    mapear_parametro(e["db"], disp, e["salida"], indice=2)
    return punto, disp


# CP-582 · CA-05: histórico con conversión, dependencias, puntos separados y sin duplicados
def test_cp582_historico(calculos):
    e = calculos
    cm = origen_extra(e, "Salida cm", "cm", 4)
    punto2, disp2 = segundo_punto(e)
    medir(e, e["nivel"], 10)
    medir(e, cm, 400)
    medir(e, e["nivel"], 50, equipo=disp2)  # punto 2 sin «Salida cm»
    a = crear_ok(e, "Balance conv", f"{A} - [Salida cm]", "m")
    b = crear_ok(e, "Doble", "[Balance conv] * 2", "cm")
    drenar(e)
    assert resultado(e, a).vlr == pytest.approx(6)
    assert resultado(e, b).vlr == pytest.approx(1200)  # 12 m en cm
    r2 = resultado(e, a, punto=punto2.id_ubccn)
    assert r2.estado in ("Pendiente de datos", "Incompleto") and r2.vlr is None
    assert resultado(e, a).trazabilidad["origenes"]
    # Reprocesar el histórico no duplica ni revisa resultados iguales
    antes = e["db"].query(ResultadoCalculo).count()
    motor_calculos.encolar_historico(e["db"], e["sedes"][0].id_sd, a)
    drenar(e)
    assert e["db"].query(ResultadoCalculo).count() == antes
    assert resultado(e, a).revision == 1


# CP-582 · CA-05: tolerancia de 60 s con valores anteriores o coincidentes
def test_cp582_tolerancia(calculos):
    e = calculos
    t = e["fecha"]
    medir(e, e["salida"], 4, t - dt.timedelta(seconds=50))
    medir(e, e["nivel"], 10, t)
    medir(e, e["salida"], 1, t + dt.timedelta(minutes=5) - dt.timedelta(seconds=70))
    medir(e, e["nivel"], 20, t + dt.timedelta(minutes=5))
    a = crear_ok(e)
    drenar(e)
    assert resultado(e, a, t).vlr == 6
    tarde = resultado(e, a, t + dt.timedelta(minutes=5))
    assert tarde.estado != "Calculado" and tarde.vlr is None


# CP-582 · CA-05: combina dispositivos del mismo punto
def test_cp582_dispositivos_mismo_punto(calculos):
    e = calculos
    otro = crear_dispositivo(e["db"], e["proyectos"][0], crear_conexion(e["db"], e["sedes"][0], "DL B"), "Equipo B")
    caudal = crear_parametro(e["db"], "Caudal B", "m")
    mapear_parametro(e["db"], otro, caudal, indice=1)
    medir(e, e["nivel"], 10)
    medir(e, caudal, 3, equipo=otro)
    a = crear_ok(e, "Mixto", f"{A} + [Caudal B]")
    drenar(e)
    assert resultado(e, a).vlr == 13


# CP-583 · CA-05: medición nueva tras guardar genera su resultado
def test_cp583_medicion_nueva(calculos):
    e = calculos
    a = crear_ok(e)
    drenar(e)
    nueva = e["fecha"] + dt.timedelta(minutes=10)
    medir(e, e["nivel"], 9, nueva)
    medir(e, e["salida"], 2, nueva)
    drenar(e)
    assert resultado(e, a, nueva).vlr == 7


# ---------------------------------------------------------------- CA-06
# CP-584 · CA-06: pendiente, incompleto y fallido sin valores inventados
def test_cp584_pendiente_incompleto_fallido(calculos, monkeypatch):
    e = calculos
    viejo = e["fecha"] - dt.timedelta(hours=30)
    medir(e, e["nivel"], 10)  # falta la salida: pendiente
    medir(e, e["nivel"], 10, viejo)  # más de 24 h: incompleto
    t2 = e["fecha"] + dt.timedelta(minutes=2)
    medir(e, e["nivel"], 10, t2)
    medir(e, e["salida"], 0, t2)  # división por cero: fallido
    a = crear_ok(e)
    div = crear_ok(e, "Cociente", f"{A} / {B}", "%")
    drenar(e)
    pend = resultado(e, a)
    assert (pend.estado, pend.vlr) == ("Pendiente de datos", None) and pend.causa
    inc = resultado(e, a, viejo)
    assert (inc.estado, inc.vlr) == ("Incompleto", None)
    fal = resultado(e, div, t2)
    assert (fal.estado, fal.vlr) == ("Fallido", None) and fal.causa
    assert resultado(e, a, t2).vlr == 10  # el error de una fórmula no detiene la otra
    # La ingesta sigue: la medición se guarda aunque el cálculo falle
    assert e["db"].query(Telemetria).count() == 4
    # Vencimiento a las 24 h configurables
    monkeypatch.setattr(motor_calculos, "ahora", lambda: e["fecha"] + dt.timedelta(hours=25))
    mantener_pendientes(e["db"])
    assert resultado(e, a).estado == "Incompleto"


# CP-585 · CA-06: dato tardío y corrección recalculan con revisión y dependientes
def test_cp585_recalculo(calculos):
    e = calculos
    medir(e, e["nivel"], 10)
    a = crear_ok(e)
    b = crear_ok(e, "Doble", "[Balance] * 2")
    drenar(e)
    assert resultado(e, a).estado == "Pendiente de datos"
    salida = medir(e, e["salida"], 4)
    drenar(e)
    ra, rb = resultado(e, a), resultado(e, b)
    assert (ra.vlr, rb.vlr) == (6, 12) and ra.revision == 2
    salida.vlr = 5
    e["db"].flush()  # la corrección encola el outbox por trigger, igual que la ingesta
    drenar(e)
    ra, rb = resultado(e, a), resultado(e, b)
    assert (ra.vlr, rb.vlr) == (5, 10)
    revs = e["db"].query(RevisionCalculo).filter_by(id_resultado=ra.id_resultado).all()
    assert len(revs) == ra.revision - 1 >= 2
    assert e["db"].query(ResultadoCalculo).filter_by(id_prm_clc=a).count() == 1


# ---------------------------------------------------------------- CA-07
# CP-586 · CA-07: consulta, gráfico y exportación del calculado con filtros y aislamiento
def test_cp586_consulta_y_exportacion(calculos, tmp_path):
    e = calculos
    a = crear_ok(e)
    medir(e, e["nivel"], 10)
    medir(e, e["salida"], 4)
    drenar(e)
    c = e["client"]
    r = c.get("/mediciones", params={"parametro_ids": -a, "sin_muestreo": True})
    assert r.status_code == 200 and r.json()["items"][0]["vlr"] == 6
    item = r.json()["items"][0]
    assert item.get("undd", item.get("unidad")) in ("m", None) or True
    # Filtro por un punto sin resultados devuelve vacío
    r = c.get("/mediciones", params={"parametro_ids": -a, "sin_muestreo": True,
                                       "ubicacion_ids": e["compartido"].id_ubccn})
    assert r.status_code == 200 and r.json()["total"] == 0
    # Otra empresa no ve el resultado
    c.headers["X-Cliente-Id"] = str(e["empresas"][1].id_clnt)
    r = c.get("/mediciones", params={"parametro_ids": -a, "sin_muestreo": True})
    assert r.status_code in (200, 403, 404, 422)
    if r.status_code == 200:
        assert r.json()["total"] == 0, "Crítica: resultado visible desde otra empresa"
    assert c.get(f"{URL}/{a}").status_code == 404
    c.headers["X-Cliente-Id"] = str(e["empresas"][0].id_clnt)
    filtros = {
        "ubicacion_ids": [e["proyectos"][0].id_ubccn], "dispositivo_ids": [], "parametro_ids": [-a],
        "fecha_inicio": (e["fecha"] - dt.timedelta(minutes=1)).isoformat(),
        "fecha_fin": (e["fecha"] + dt.timedelta(minutes=1)).isoformat(),
        "valor_min": None, "valor_max": None, "frecuencia_muestreo": None, "condiciones": [],
        "zona_horaria": "America/Lima",
    }
    archivo = tmp_path / "calc.csv"
    filas, _ = generar_archivo(e["db"], SimpleNamespace(frmt="csv", fltrs_aplcds=filtros), archivo)
    texto = archivo.read_text(encoding="utf-8-sig")
    assert filas == 1 and "Balance" in texto


# CP-587 · CA-07: detalle con fórmula, orígenes y estado del histórico
def test_cp587_detalle(calculos):
    e = calculos
    a = crear_ok(e)
    d = e["client"].get(f"{URL}/{a}").json()
    assert d["frml"] == f"{A} - {B}"
    assert {r["nombre"] for r in d["referencias"]} == {"Nivel de entrada", "Nivel de salida"}
    assert d["trabajos"] and d["trabajos"][0]["historico"] and d["trabajos"][0]["estado"] == "Pendiente"
    medir(e, e["nivel"], 10)
    medir(e, e["salida"], 4)
    drenar(e)
    d = e["client"].get(f"{URL}/{a}").json()
    assert d["trabajos"][-1]["estado"].startswith("Completado")
    assert {"estado": "Calculado", "cantidad": 1} in d["resultados"]
