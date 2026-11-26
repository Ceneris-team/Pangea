"""QA PP-69 (PP-441): listar parámetros calculados.

Casos API de listado, paginación, orden, detalle, vacío, permisos y solo lectura.
Se copia a backend/tests/routers/ del worktree de dev para reutilizar sus fixtures.
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import pytest

from app.models import ParametroCalculado, ResultadoCalculo, TrabajoCalculo, UsuarioCliente
from app.security.jwt_auth import create_access_token
from tests.routers.test_parametros_calculados import definir, preparar_origenes
from tests.routers.test_parametros_calculados import entorno_calculados as entorno_calculados  # noqa: F401

URL = "/parametros-calculados"


def listar(c, **params):
    r = c.get(URL, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def nombres(c, **params):
    return [p["nmbr"] for p in listar(c, **params)["items"]]


def como_empresa(e, fabrica, rol):
    u = fabrica.usuario(fabrica.rol("Usuario Empresa"), scp="por_cliente")
    e["db"].add(UsuarioCliente(id_usr=u.id_usr, id_clnt=e["empresas"][0].id_clnt, rol_emp=rol))
    e["db"].flush()
    e["client"].headers["Authorization"] = "Bearer " + create_access_token(
        u.id_usr, None, u.scp, u.rol.nmbr
    )


# CP-554 · CA-01: roles autorizados acceden; Lector de empresa no
@pytest.mark.parametrize(
    "rol,esperado", [("CENERIS", 200), ("Administrador", 200), ("Tecnico", 200), ("Lector", 403)]
)
def test_cp554_roles_autorizados(entorno_calculados, fabrica, rol, esperado):
    e = entorno_calculados
    p = definir(e["db"], e["sedes"][0], "Caudal neto")
    if rol != "CENERIS":
        como_empresa(e, fabrica, rol)
    c = e["client"]
    assert c.get(URL).status_code == esperado
    assert c.get(f"{URL}/{p.id_prm_clc}").status_code == esperado


# CP-555 · CA-01: solo las definiciones de la empresa y el proyecto seleccionados
def test_cp555_aislamiento_empresa_y_proyecto(entorno_calculados):
    e = entorno_calculados
    c = e["client"]
    propio = definir(e["db"], e["sedes"][0], "Propio sede 0")
    misma_empresa = definir(e["db"], e["sedes"][1], "Propio sede 1")
    ajeno = definir(e["db"], e["sedes"][2], "Ajeno empresa 2")
    lista = listar(c)
    assert sorted(p["nmbr"] for p in lista["items"]) == ["Propio sede 0", "Propio sede 1"]
    assert lista["total"] == 2
    assert lista["contexto"]["empresa"] == e["empresas"][0].rzn_scl
    assert c.get(f"{URL}/{ajeno.id_prm_clc}").status_code == 404
    # Con proyecto seleccionado se acota a la sede del proyecto
    c.headers["X-Proyecto-Id"] = str(e["proyectos"][0].id_ubccn)
    lista = listar(c)
    assert [p["nmbr"] for p in lista["items"]] == ["Propio sede 0"]
    assert lista["contexto"]["proyecto"] == "Proyecto 0"
    assert c.get(f"{URL}/{misma_empresa.id_prm_clc}").status_code == 404
    assert c.get(f"{URL}/{propio.id_prm_clc}").status_code == 200
    # Proyecto de otra empresa con la empresa 0 seleccionada
    c.headers["X-Proyecto-Id"] = str(e["proyectos"][2].id_ubccn)
    assert c.get(URL).status_code == 403


# CP-556 · CA-02: cada fila trae nombre, fórmula, unidad, estado y ámbito
def test_cp556_columnas_y_ambito(entorno_calculados):
    e = entorno_calculados
    definir(e["db"], e["sedes"][0], "Caudal neto", "Activo", "m3/s")
    item = listar(e["client"])["items"][0]
    assert (item["nmbr"], item["undd"], item["estd"]) == ("Caudal neto", "m3/s", "Activo")
    assert item["frml"]
    assert item["empresa_nombre"] == e["empresas"][0].rzn_scl
    assert e["sedes"][0].nmbr in item["ambito"]


# CP-557 · CA-02/CA-04: la fórmula extensa llega completa al detalle
def test_cp557_formula_extensa_completa_en_detalle(entorno_calculados):
    e = entorno_calculados
    nivel, salida, _ = preparar_origenes(e)
    larga = " + ".join([f"p_{nivel.id_prmtr} * {i}" for i in range(1, 31)]) + f" - p_{salida.id_prmtr}"
    assert 250 < len(larga) <= 500  # la columna frml es varchar(500)
    p = definir(e["db"], e["sedes"][0], "Fórmula larga")
    p.frml = larga
    e["db"].flush()
    d = e["client"].get(f"{URL}/{p.id_prm_clc}").json()
    assert d["frml"].count("*") == 30 and "Nivel de salida" in d["frml"], d["frml"]


# CP-558 · CA-03: 10 por página, total y página actual, sin omitir ni duplicar
def test_cp558_paginacion_completa(entorno_calculados):
    e = entorno_calculados
    for i in range(23):
        definir(e["db"], e["sedes"][i % 2], f"Parámetro {i:02d}", "Activo" if i % 3 else "Inactivo")
    vistos = []
    for pagina, cantidad in [(1, 10), (2, 10), (3, 3)]:
        r = listar(e["client"], pagina=pagina)
        assert (r["total"], r["pagina"], r["por_pagina"]) == (23, pagina, 10)
        assert len(r["items"]) == cantidad
        vistos += [p["id_prm_clc"] for p in r["items"]]
    assert len(vistos) == len(set(vistos)) == 23
    # Por defecto (sin por_pagina) también son 10
    assert len(e["client"].get(URL).json()["items"]) == 10


# CP-559 · CA-03: orden por nombre estable (iguales por id, mayúsculas y acentos)
def test_cp559_orden_estable(entorno_calculados):
    e = entorno_calculados
    # El nombre es único por sede: los iguales se reparten entre las dos sedes de la empresa
    for i, n in enumerate(["Zeta", "caudal", "Árbol", "Caudal", "abeto", "Caudal", "éter", "nube", "Ñandú", "Éxito"]):
        definir(e["db"], e["sedes"][1 if i == 5 else 0], n)
    orden = [(p["nmbr"], p["id_prm_clc"]) for p in listar(e["client"], por_pagina=20)["items"]]
    print("ORDEN_OBTENIDO", [n for n, _ in orden])
    # Repetir la consulta devuelve el mismo orden
    assert orden == [(p["nmbr"], p["id_prm_clc"]) for p in listar(e["client"], por_pagina=20)["items"]]
    # Los nombres iguales se desempatan por id
    iguales = [i for n, i in orden if n.lower() == "caudal"]
    assert iguales == sorted(iguales)
    # Orden alfabético: el acento no manda la palabra al final
    obtenido = [n.lower() for n, _ in orden if n != "Ñandú"]
    esperado = ["abeto", "árbol", "caudal", "caudal", "caudal", "éter", "éxito", "nube", "zeta"]
    assert obtenido == esperado
    # OBS-74: en español la ñ va después de la n; la collation en_US de la base la trata como n
    nombres_orden = [n for n, _ in orden]
    print("OBS74_N_ANTES_QUE_NUBE", nombres_orden.index("Ñandú") < nombres_orden.index("nube"))


# CP-560 · CA-03: límites de paginación
def test_cp560_limites_paginacion(entorno_calculados):
    e = entorno_calculados
    c = e["client"]
    for i in range(12):
        definir(e["db"], e["sedes"][0], f"P{i:02d}")
    assert c.get(URL, params={"pagina": 0}).status_code == 422
    assert c.get(URL, params={"por_pagina": 101}).status_code == 422
    assert c.get(URL, params={"pagina": "x"}).status_code == 422
    fuera = listar(c, pagina=9)
    print("PAGINA_FUERA", fuera["total"], fuera["pagina"], len(fuera["items"]))
    assert fuera["total"] == 12 and fuera["items"] == []


# CP-561 · CA-04: detalle con descripción, referencias con nombre, unidad, estado y ámbito
def test_cp561_detalle_completo(entorno_calculados):
    e = entorno_calculados
    nivel, salida, _ = preparar_origenes(e)
    p = definir(e["db"], e["sedes"][0], "Caudal neto", "Inactivo", "m")
    p.frml = f"p_{nivel.id_prmtr} - p_{salida.id_prmtr}"
    sin = definir(e["db"], e["sedes"][0], "Sin descripción")
    sin.dscrpcn = None
    e["db"].flush()
    c = e["client"]
    d = c.get(f"{URL}/{p.id_prm_clc}").json()
    assert (d["nmbr"], d["undd"], d["estd"]) == ("Caudal neto", "m", "Inactivo")
    assert d["dscrpcn"] == "Diferencia entre mediciones"
    assert e["sedes"][0].nmbr in d["ambito"]
    refs = {r["nombre"] for r in d["referencias"]}
    assert refs == {"Nivel de entrada", "Nivel de salida"}, d["referencias"]
    assert "Nivel de entrada" in d["frml"] and "p_" not in d["frml"], d["frml"]
    assert c.get(f"{URL}/{sin.id_prm_clc}").json()["dscrpcn"] is None
    assert c.get(f"{URL}/999999").status_code == 404


# CP-562 / CP-563 · CA-05: vacío; permiso de crear según el rol
@pytest.mark.parametrize("rol,crear", [("Administrador", True), ("CENERIS", True)])
def test_cp562_vacio_con_permiso_de_crear(entorno_calculados, fabrica, rol, crear):
    e = entorno_calculados
    preparar_origenes(e)
    if rol != "CENERIS":
        como_empresa(e, fabrica, rol)
    r = listar(e["client"])
    assert (r["total"], r["items"]) == (0, [])
    assert r["permisos"]["crear"] is crear


# CP-566 · Conversación: Activo e Inactivo se listan sin filtro
def test_cp566_ambos_estados_al_inicio(entorno_calculados):
    e = entorno_calculados
    definir(e["db"], e["sedes"][0], "Activo uno", "Activo")
    definir(e["db"], e["sedes"][0], "Inactivo uno", "Inactivo")
    assert {p["estd"] for p in listar(e["client"])["items"]} == {"Activo", "Inactivo"}


# CP-567 · Conversación: listar y ver detalle no modifica ni ejecuta fórmulas
def test_cp567_consultar_no_modifica(entorno_calculados):
    e = entorno_calculados
    db = e["db"]
    nivel, salida, _ = preparar_origenes(e)
    p = definir(db, e["sedes"][0], "Caudal neto")
    p.frml = f"p_{nivel.id_prmtr} - p_{salida.id_prmtr}"
    db.flush()

    def foto():
        db.expire_all()
        q = db.get(ParametroCalculado, p.id_prm_clc)
        return (
            q.nmbr, q.frml, q.undd, q.estd, q.dscrpcn,
            db.query(TrabajoCalculo).count(), db.query(ResultadoCalculo).count(),
            db.query(ParametroCalculado).count(),
        )

    antes = foto()
    c = e["client"]
    for _ in range(3):
        listar(c)
        listar(c, pagina=2)
        assert c.get(f"{URL}/{p.id_prm_clc}").status_code == 200
    assert foto() == antes
