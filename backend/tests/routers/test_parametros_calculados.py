"""Listado calculado: búsqueda, estado, alcance y ausencia de mutaciones."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import ParametroCalculado, PermisoUsuarioSede, UsuarioCliente
from app.security.jwt_auth import create_access_token
from tests.routers.test_mediciones import (
    crear_conexion,
    crear_dispositivo,
    crear_parametro,
    crear_ubicacion,
    mapear_parametro,
)


def definir(db, sede, nombre, estado="Activo", unidad="m"):
    p = ParametroCalculado(
        id_sd=sede.id_sd,
        nmbr=nombre,
        estd=estado,
        undd=unidad,
        frml="nivel_entrada - nivel_salida",
        dscrpcn="Diferencia entre mediciones",
    )
    db.add(p)
    db.flush()
    return p


def preparar_origenes(e):
    db = e["db"]
    dispositivo = crear_dispositivo(db, e["proyectos"][0], crear_conexion(db, e["sedes"][0]))
    nivel = crear_parametro(db, "Nivel de entrada", "m")
    salida = crear_parametro(db, "Nivel de salida", "m")
    texto = crear_parametro(db, "Mensaje del equipo", "texto", "texto")
    for i, p in enumerate([nivel, salida, texto], 1):
        mapear_parametro(db, dispositivo, p, indice=i)
    return nivel, salida, dispositivo


@pytest.fixture()
def entorno_calculados(db_session, fabrica):
    db = db_session
    empresas = [fabrica.cliente(), fabrica.cliente()]
    sedes = [fabrica.sede(empresas[0]), fabrica.sede(empresas[0]), fabrica.sede(empresas[1])]
    proyectos = [crear_ubicacion(db, sede, f"Proyecto {i}") for i, sede in enumerate(sedes)]
    compartido = crear_ubicacion(db, sedes[0], "Proyecto compartido")
    usuario = fabrica.usuario(fabrica.rol("Técnico CENERIS"), scp="global")
    token = create_access_token(usuario.id_usr, None, usuario.scp, usuario.rol.nmbr)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            client.headers["Authorization"] = "Bearer " + token
            client.headers["X-Cliente-Id"] = str(empresas[0].id_clnt)
            yield {
                "client": client,
                "db": db,
                "empresas": empresas,
                "sedes": sedes,
                "proyectos": proyectos,
                "compartido": compartido,
                "usuario": usuario,
            }
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("busqueda", ["índice", "ÍNDICE", "  ÍnDiCe  "])
def test_busqueda_parcial_sin_distinguir_mayusculas_y_con_espacios(entorno_calculados, busqueda):
    e = entorno_calculados
    propio = definir(e["db"], e["sedes"][0], "Índice de calidad")
    definir(e["db"], e["sedes"][0], "Balance hídrico")
    definir(e["db"], e["sedes"][2], "Índice de otra empresa")
    resp = e["client"].get("/parametros-calculados", params={"q": busqueda})
    assert resp.status_code == 200, resp.text
    assert [p["id_prm_clc"] for p in resp.json()["items"]] == [propio.id_prm_clc]


def test_estados_y_combinacion_acumulativa(entorno_calculados):
    e = entorno_calculados
    for nombre, estado in [
        ("Nivel activo", "Activo"),
        ("Nivel inactivo", "Inactivo"),
        ("Balance", "Activo"),
    ]:
        definir(e["db"], e["sedes"][0], nombre, estado)
    client = e["client"]
    assert client.get("/parametros-calculados").json()["total"] == 3
    assert client.get("/parametros-calculados", params={"estado": "Activo"}).json()["total"] == 2
    assert client.get("/parametros-calculados", params={"estado": "Inactivo"}).json()["total"] == 1
    combinado = client.get(
        "/parametros-calculados", params={"q": "NIVEL", "estado": "Activo"}
    ).json()
    assert combinado["total"] == 1 and combinado["items"][0]["nmbr"] == "Nivel activo"
    assert client.get("/parametros-calculados", params={"q": "   "}).json()["total"] == 3


@pytest.mark.parametrize("texto", ["100%", "Etiqueta_", "' OR 1=1 --"])
def test_busqueda_literal_no_interpreta_comodines_ni_sql(entorno_calculados, texto):
    e = entorno_calculados
    for nombre in ["Ratio 100%", "Ratio 100x", "Etiqueta_1", "Etiquetax1"]:
        definir(e["db"], e["sedes"][0], nombre)
    data = e["client"].get("/parametros-calculados", params={"q": texto}).json()
    assert data["total"] == (0 if texto.startswith("'") else 1)


def test_paginacion_sobre_todo_el_resultado_y_orden_estable(entorno_calculados):
    e = entorno_calculados
    for i in range(36):
        definir(e["db"], e["sedes"][0], f"Medida {i:02}", "Activo" if i % 2 == 0 else "Inactivo")
    ids = []
    for pagina in range(1, 4):
        resp = e["client"].get(
            "/parametros-calculados",
            params={"q": "medida", "estado": "Inactivo", "por_pagina": 7, "pagina": pagina},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 18 and data["pagina"] == pagina
        assert all(p["estd"] == "Inactivo" for p in data["items"])
        ids.extend(p["id_prm_clc"] for p in data["items"])
    assert len(ids) == len(set(ids)) == 18
    repetida = (
        e["client"]
        .get(
            "/parametros-calculados", params={"q": "medida", "estado": "Inactivo", "por_pagina": 7}
        )
        .json()
    )
    assert [p["id_prm_clc"] for p in repetida["items"]] == ids[:7]


def test_contexto_empresa_proyecto_y_definiciones_compartidas(entorno_calculados):
    e = entorno_calculados
    definiciones = [definir(e["db"], sede, "Mismo nombre") for sede in e["sedes"]]
    client = e["client"]
    data = client.get("/parametros-calculados").json()
    assert {p["id_prm_clc"] for p in data["items"]} == {p.id_prm_clc for p in definiciones[:2]}
    assert data["contexto"]["empresa"] == e["empresas"][0].rzn_scl
    for proyecto in [e["proyectos"][0], e["compartido"]]:
        client.headers["X-Proyecto-Id"] = str(proyecto.id_ubccn)
        data = client.get("/parametros-calculados").json()
        assert [p["id_prm_clc"] for p in data["items"]] == [definiciones[0].id_prm_clc]
        assert data["contexto"]["proyecto"] == proyecto.nmbr
    client.headers["X-Proyecto-Id"] = str(e["proyectos"][1].id_ubccn)
    assert (
        client.get("/parametros-calculados").json()["items"][0]["id_prm_clc"]
        == definiciones[1].id_prm_clc
    )
    client.headers["X-Proyecto-Id"] = str(e["proyectos"][2].id_ubccn)
    assert client.get("/parametros-calculados").status_code == 403
    client.headers["X-Cliente-Id"] = str(e["empresas"][1].id_clnt)
    assert (
        client.get("/parametros-calculados").json()["items"][0]["id_prm_clc"]
        == definiciones[2].id_prm_clc
    )


@pytest.mark.parametrize("rol", ["Administrador", "Tecnico", "Lector"])
def test_membresia_empresarial_con_sesion_real(entorno_calculados, fabrica, rol):
    e = entorno_calculados
    nivel, _, _ = preparar_origenes(e)
    usuario = fabrica.usuario(fabrica.rol("Usuario Empresa"), scp="por_cliente")
    e["db"].add(
        UsuarioCliente(id_usr=usuario.id_usr, id_clnt=e["empresas"][0].id_clnt, rol_emp=rol)
    )
    propio = definir(e["db"], e["sedes"][0], "Propio")
    definir(e["db"], e["sedes"][2], "Ajeno")
    e["client"].headers["Authorization"] = "Bearer " + create_access_token(
        usuario.id_usr, None, usuario.scp, usuario.rol.nmbr
    )
    resp = e["client"].get("/parametros-calculados")
    assert resp.status_code == (403 if rol == "Lector" else 200)
    assert e["client"].get(f"/parametros-calculados/{propio.id_prm_clc}").status_code == (
        403 if rol == "Lector" else 200
    )
    assert e["client"].get("/parametros-calculados/opciones-creacion").status_code == (
        403 if rol == "Lector" else 200
    )
    if rol != "Lector":
        assert [p["nmbr"] for p in resp.json()["items"]] == ["Propio"]
        assert resp.json()["permisos"]["crear"]
    crear = e["client"].post(
        "/parametros-calculados",
        json={
            "id_sd": e["sedes"][0].id_sd,
            "nmbr": "Derivado",
            "frml": f"p_{nivel.id_prmtr} * 2",
            "undd": "m",
        },
    )
    assert crear.status_code == (403 if rol == "Lector" else 201), crear.text
    if rol != "Lector":
        e["client"].headers["X-Cliente-Id"] = str(e["empresas"][1].id_clnt)
        assert e["client"].get("/parametros-calculados").status_code == 403


@pytest.mark.parametrize("rol,con_permiso", [("Técnico CENERIS", False), ("Cliente Final", True)])
def test_exige_permiso_y_funcion_tecnica_para_cuentas_anteriores(
    entorno_calculados, fabrica, rol, con_permiso
):
    e = entorno_calculados
    usuario = fabrica.usuario(fabrica.rol(rol))
    if con_permiso:
        e["db"].add(
            PermisoUsuarioSede(
                id_usr=usuario.id_usr,
                id_sd=e["sedes"][0].id_sd,
                id_rl=usuario.id_rl,
                mdl="Ingesta",
                nvl="Lectura",
            )
        )
        e["db"].flush()
    client = e["client"]
    client.headers.clear()
    client.headers["Authorization"] = "Bearer " + create_access_token(
        usuario.id_usr, e["sedes"][0].id_sd, usuario.scp, usuario.rol.nmbr
    )
    assert client.get("/parametros-calculados").status_code == 403


def test_consultar_filtrar_y_limpiar_no_modifican_definiciones(entorno_calculados):
    e = entorno_calculados
    p = definir(e["db"], e["sedes"][0], "Balance", "Inactivo")
    antes = (p.nmbr, p.frml, p.undd, p.estd, p.id_sd)
    for params in [{"q": "balance"}, {"estado": "Activo"}, {}]:
        assert e["client"].get("/parametros-calculados", params=params).status_code == 200
    e["db"].refresh(p)
    assert (p.nmbr, p.frml, p.undd, p.estd, p.id_sd) == antes
    item = e["client"].get("/parametros-calculados").json()["items"][0]
    assert item["undd"] == "m" and item["dscrpcn"] == "Diferencia entre mediciones"
    assert item["empresa_nombre"] == e["empresas"][0].rzn_scl


@pytest.mark.parametrize(
    "params",
    [
        {"estado": "Pendiente"},
        {"estado": "Activo\x00"},
        {"pagina": 0},
        {"por_pagina": 101},
        {"q": "a" * 201},
    ],
)
def test_rechaza_filtros_invalidos(entorno_calculados, params):
    assert (
        entorno_calculados["client"].get("/parametros-calculados", params=params).status_code == 422
    )


@pytest.mark.parametrize("busqueda", ["caudal\x00", "\x00", "\tcaudal", "\n", "\x7f", "\x85"])
@pytest.mark.parametrize("estado", [None, "Activo"])
def test_busqueda_con_controles_devuelve_422_y_permite_consultar_despues(
    entorno_calculados, busqueda, estado
):
    e = entorno_calculados
    parametro = definir(e["db"], e["sedes"][0], "Caudal calculado")
    params = {"q": busqueda}
    if estado:
        params["estado"] = estado
    respuesta = e["client"].get("/parametros-calculados", params=params)
    assert respuesta.status_code == 422, respuesta.text
    error = respuesta.json()["detail"][0]
    assert error["loc"] == ["query", "q"]
    assert "caracteres de control" in error["msg"]
    valida = e["client"].get("/parametros-calculados", params={"q": "caudal", "estado": "Activo"})
    assert valida.status_code == 200
    assert [p["id_prm_clc"] for p in valida.json()["items"]] == [parametro.id_prm_clc]


def test_listado_vacio_y_sesion_obligatoria(entorno_calculados):
    client = entorno_calculados["client"]
    data = client.get("/parametros-calculados").json()
    assert data["items"] == [] and data["total"] == 0
    client.headers.clear()
    assert client.get("/parametros-calculados").status_code == 401


def test_diez_por_defecto_formula_y_ambito_compartido(entorno_calculados):
    e = entorno_calculados
    nivel, salida, _ = preparar_origenes(e)
    for i in range(23):
        p = definir(e["db"], e["sedes"][0], f"Balance {i:02}", "Inactivo" if i % 2 else "Activo")
        p.frml = f"p_{nivel.id_prmtr} - p_{salida.id_prmtr}"
    e["db"].flush()
    ids = []
    for pagina, cantidad in [(1, 10), (2, 10), (3, 3)]:
        data = e["client"].get("/parametros-calculados", params={"pagina": pagina}).json()
        assert data["por_pagina"] == 10 and data["total"] == 23
        assert len(data["items"]) == cantidad
        assert data["items"][0]["frml"] == "[Nivel de entrada] - [Nivel de salida]"
        assert "Compartido por los proyectos de" in data["items"][0]["ambito"]
        ids.extend(p["id_prm_clc"] for p in data["items"])
    assert len(set(ids)) == 23


def test_detalle_completo_aislado_y_referencia_antigua_sin_inventar(entorno_calculados):
    e = entorno_calculados
    nivel, salida, _ = preparar_origenes(e)
    p = definir(e["db"], e["sedes"][0], "Balance propio")
    p.frml = f"(p_{nivel.id_prmtr} - p_{salida.id_prmtr}) * 1.25"
    e["db"].flush()
    detalle = e["client"].get(f"/parametros-calculados/{p.id_prm_clc}").json()
    assert detalle["frml"] == "([Nivel de entrada] - [Nivel de salida]) * 1.25"
    assert [r["nombre"] for r in detalle["referencias"]] == ["Nivel de entrada", "Nivel de salida"]
    assert all(r["disponible"] for r in detalle["referencias"])
    ajeno = definir(e["db"], e["sedes"][2], "Ajeno")
    assert e["client"].get(f"/parametros-calculados/{ajeno.id_prm_clc}").status_code == 404
    assert e["client"].get("/parametros-calculados/99999999").status_code == 404
    p.frml = "nivel_entrada - nivel_salida"
    e["db"].flush()
    detalle = e["client"].get(f"/parametros-calculados/{p.id_prm_clc}").json()
    assert detalle["frml"] == p.frml
    assert all(not r["disponible"] and r["nombre"] is None for r in detalle["referencias"])
    # Una referencia canónica desaparecida del mapeo tampoco se vincula a otro parámetro.
    p.frml = "p_99999999 + 1"
    e["db"].flush()
    assert (
        not e["client"]
        .get(f"/parametros-calculados/{p.id_prm_clc}")
        .json()["referencias"][0]["disponible"]
    )


def test_registro_desde_listado_vacio_y_referencias_estables(entorno_calculados):
    e = entorno_calculados
    nivel, salida, _ = preparar_origenes(e)
    client = e["client"]
    client.headers["X-Proyecto-Id"] = str(e["proyectos"][0].id_ubccn)
    assert client.get("/parametros-calculados").json()["permisos"]["crear"]
    opciones = client.get("/parametros-calculados/opciones-creacion").json()["sedes"]
    assert len(opciones) == 1 and opciones[0]["id_sd"] == e["sedes"][0].id_sd
    assert {p["nombre"] for p in opciones[0]["origenes"]} == {nivel.nmbr, salida.nmbr}
    body = {
        "id_sd": e["sedes"][0].id_sd,
        "nmbr": "  Balance hídrico  ",
        "frml": "[Nivel de entrada] - [Nivel de salida]",
        "undd": "m",
        "estd": "Inactivo",
    }
    resp = client.post("/parametros-calculados", json=body)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["nmbr"] == "Balance hídrico" and data["estd"] == "Inactivo"
    guardado = e["db"].get(ParametroCalculado, data["id_prm_clc"])
    assert guardado.frml == f"p_{nivel.id_prmtr} - p_{salida.id_prmtr}"
    nivel.nmbr = "Nivel aguas arriba"
    e["db"].flush()
    assert (
        "[Nivel aguas arriba]"
        in client.get(f"/parametros-calculados/{guardado.id_prm_clc}").json()["frml"]
    )
    assert (
        client.post(
            "/parametros-calculados",
            json={**body, "nmbr": "BALANCE HÍDRICO", "frml": f"p_{nivel.id_prmtr}"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/parametros-calculados", json={**body, "id_sd": e["sedes"][1].id_sd}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/parametros-calculados", json={**body, "id_sd": e["sedes"][2].id_sd}
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "formula",
    [
        "[Ajeno] * 2",
        "1 + 2",
        "[Mensaje del equipo]",
        "[Nivel de entrada] +",
        "__import__('os').system('echo x')",
        "[Nivel de entrada].real",
        "[Nivel de entrada] + 1e999",
        "[Nivel de entrada] + True",
    ],
)
def test_registro_rechaza_formulas_no_soportadas_sin_persistir(entorno_calculados, formula):
    e = entorno_calculados
    preparar_origenes(e)
    resp = e["client"].post(
        "/parametros-calculados",
        json={"id_sd": e["sedes"][0].id_sd, "nmbr": "No guardar", "frml": formula, "undd": "m"},
    )
    assert resp.status_code == 422, resp.text
    assert e["db"].query(ParametroCalculado).count() == 0


def test_lectura_legacy_oculta_creacion_y_bloquea_mutacion(entorno_calculados, fabrica):
    e = entorno_calculados
    nivel, _, _ = preparar_origenes(e)
    usuario = fabrica.usuario(fabrica.rol("Técnico CENERIS"))
    e["db"].add(
        PermisoUsuarioSede(
            id_usr=usuario.id_usr,
            id_sd=e["sedes"][0].id_sd,
            id_rl=usuario.id_rl,
            mdl="Ingesta",
            nvl="Lectura",
        )
    )
    e["db"].flush()
    e["client"].headers.clear()
    e["client"].headers["Authorization"] = "Bearer " + create_access_token(
        usuario.id_usr, e["sedes"][0].id_sd, usuario.scp, usuario.rol.nmbr
    )
    p = definir(e["db"], e["sedes"][0], "Propio")
    assert not e["client"].get("/parametros-calculados").json()["permisos"]["crear"]
    assert e["client"].get(f"/parametros-calculados/{p.id_prm_clc}").status_code == 200
    assert e["client"].get("/parametros-calculados/opciones-creacion").status_code == 403
    assert (
        e["client"]
        .post(
            "/parametros-calculados",
            json={
                "id_sd": e["sedes"][0].id_sd,
                "nmbr": "Prohibido",
                "frml": f"p_{nivel.id_prmtr}",
                "undd": "m",
            },
        )
        .status_code
        == 403
    )
