"""HU38: API, outbox real, histórico, correcciones y consumo del resultado."""

import datetime as dt
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from app.models import (
    DependenciaCalculo,
    ParametroCalculado,
    ResultadoCalculo,
    RevisionCalculo,
    SerieCalculada,
    Telemetria,
    TrabajoCalculo,
    UsuarioCliente,
)
from app.security.jwt_auth import create_access_token
from app.services.exportaciones import generar_archivo
from app.services.motor_calculos import mantener_pendientes, procesar_lote
from tests.routers.test_mediciones import crear_conexion, crear_dispositivo, mapear_parametro
from tests.routers.test_parametros_calculados import entorno_calculados as entorno_calculados
from tests.routers.test_parametros_calculados import preparar_origenes


@pytest.fixture()
def calculos(entorno_calculados, monkeypatch):
    e = entorno_calculados
    from app.services.cache import consultas

    monkeypatch.setattr(consultas, "obtener", lambda *args, **kwargs: None)
    monkeypatch.setattr(consultas, "guardar", lambda *args, **kwargs: None)
    e["nivel"], e["salida"], e["dispositivo"] = preparar_origenes(e)
    e["fecha"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0) - dt.timedelta(hours=1)
    return e


def crear(e, nombre="Balance", formula="[Nivel de entrada] - [Nivel de salida]", unidad="m"):
    r = e["client"].post(
        "/parametros-calculados",
        json={
            "id_sd": e["sedes"][0].id_sd,
            "nmbr": nombre,
            "frml": formula,
            "undd": unidad,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id_prm_clc"]


def medir(e, p, valor, fecha=None, equipo=None):
    equipo = equipo or e["dispositivo"]
    r = Telemetria(
        id_dspstv=equipo.id_dspstv,
        id_sd=e["sedes"][0].id_sd,
        id_prmtr=p.id_prmtr,
        fch_hr=fecha or e["fecha"],
        vlr=valor,
    )
    e["db"].add(r)
    e["db"].flush()
    return r


def drenar(e):
    for _ in range(100):
        t = (
            e["db"]
            .query(TrabajoCalculo)
            .filter(TrabajoCalculo.estado.in_(["Pendiente", "En curso"]))
            .order_by(TrabajoCalculo.id_trabajo)
            .first()
        )
        if not t:
            return
        procesar_lote(e["db"], t)
    pytest.fail("La cola no terminó")


def resultado(e, id_, fecha=None, punto=None):
    return (
        e["db"]
        .query(ResultadoCalculo)
        .filter_by(
            id_prm_clc=id_, id_ubccn=punto or e["proyectos"][0].id_ubccn, fch_hr=fecha or e["fecha"]
        )
        .one()
    )


def test_validar_unidades_y_registro_con_autor(calculos):
    e = calculos
    body = {
        "id_sd": e["sedes"][0].id_sd,
        "frml": "[Nivel de entrada] / [Nivel de salida]",
        "undd": "%",
    }
    r = e["client"].post("/parametros-calculados/validar-formula", json=body)
    assert r.status_code == 200 and r.json()["mensaje"] == "Fórmula válida"
    assert (
        e["client"]
        .post("/parametros-calculados/validar-formula", json={**body, "undd": "kg"})
        .status_code
        == 422
    )
    id_ = crear(e)
    p = e["db"].get(ParametroCalculado, id_)
    assert p.validada and p.id_usr_creador == e["usuario"].id_usr and p.creada_en
    assert e["db"].query(DependenciaCalculo).filter_by(id_prm_clc=id_).count() == 2
    assert e["db"].query(TrabajoCalculo).filter_by(id_prm_clc=id_).one().estado == "Pendiente"


def test_historico_antes_de_crear_y_dependencias(calculos):
    e = calculos
    medir(e, e["nivel"], 10)
    medir(e, e["salida"], 4)
    primero = crear(e)
    segundo = crear(e, "Doble balance", "[Balance] * 2")
    drenar(e)
    assert resultado(e, primero).vlr == 6
    assert resultado(e, segundo).vlr == 12
    assert resultado(e, segundo).trazabilidad["origenes"][f"c_{primero}"]["revision"] == 1
    assert e["db"].query(SerieCalculada).count() == 2


def test_outbox_nuevas_correcciones_borrado_y_reintento_idempotente(calculos):
    e = calculos
    id_ = crear(e)
    drenar(e)
    medir(e, e["nivel"], 10)
    origen = medir(e, e["salida"], 4)
    assert e["db"].query(TrabajoCalculo).filter(TrabajoCalculo.inicio.isnot(None)).count() > 0
    drenar(e)
    r = resultado(e, id_)
    assert r.vlr == 6 and r.revision == 1
    origen.vlr = 5
    e["db"].flush()
    drenar(e)
    assert r.vlr == 5 and r.revision == 2
    assert (
        e["db"]
        .query(RevisionCalculo)
        .filter_by(id_resultado=r.id_resultado)
        .one()
        .anterior["valor"]
        == 6
    )
    e["db"].delete(origen)
    e["db"].flush()
    drenar(e)
    assert r.vlr is None and r.estado == "Pendiente de datos"
    e["db"].add(TrabajoCalculo(id_sd=e["sedes"][0].id_sd))
    e["db"].flush()
    drenar(e)
    assert r.revision == 3 and e["db"].query(ResultadoCalculo).count() == 1


def test_pendiente_vence_y_dato_tardio_recupera(calculos, monkeypatch):
    e = calculos
    id_ = crear(e)
    medir(e, e["nivel"], 10)
    drenar(e)
    r = resultado(e, id_)
    assert r.estado == "Pendiente de datos" and r.vlr is None
    import app.services.motor_calculos as motor

    monkeypatch.setattr(motor, "ahora", lambda: e["fecha"] + dt.timedelta(hours=25))
    mantener_pendientes(e["db"])
    assert r.estado == "Incompleto"
    medir(e, e["salida"], 3)
    drenar(e)
    assert r.estado == "Calculado" and r.vlr == 7


def test_tolerancia_no_usa_datos_futuros_y_configuracion(calculos):
    e = calculos
    id_ = crear(e)
    medir(e, e["nivel"], 10)
    medir(e, e["salida"], 4, e["fecha"] + dt.timedelta(seconds=30))
    drenar(e)
    assert e["db"].query(ResultadoCalculo).filter_by(id_prm_clc=id_).count() == 1
    assert resultado(e, id_, e["fecha"] + dt.timedelta(seconds=30)).vlr == 6
    r = e["client"].put(
        f"/parametros-calculados/configuracion/{e['sedes'][0].id_sd}",
        json={"tolerancia_segundos": 10, "espera_horas": 48},
    )
    assert r.status_code == 200, r.text
    drenar(e)
    assert resultado(e, id_, e["fecha"] + dt.timedelta(seconds=30)).estado == "Pendiente de datos"


def test_error_division_no_afecta_otras_formulas(calculos):
    e = calculos
    valido = crear(e)
    invalido = crear(e, "Cociente", "[Nivel de entrada] / [Nivel de salida]", "1")
    medir(e, e["nivel"], 10)
    medir(e, e["salida"], 0)
    drenar(e)
    assert resultado(e, valido).vlr == 10
    assert resultado(e, invalido).estado == "Fallido"
    assert "cero" in resultado(e, invalido).causa


def test_diferentes_dispositivos_mismo_punto_y_aislamiento(calculos):
    e = calculos
    id_ = crear(e)
    otro = crear_dispositivo(
        e["db"], e["proyectos"][0], crear_conexion(e["db"], e["sedes"][0], "Otro"), nombre="Otro"
    )
    mapear_parametro(e["db"], otro, e["salida"], indice=1)
    medir(e, e["nivel"], 10)
    medir(e, e["salida"], 3, equipo=otro)
    ajeno = crear_dispositivo(
        e["db"], e["compartido"], crear_conexion(e["db"], e["sedes"][0], "Ajeno"), nombre="Ajeno"
    )
    medir(e, e["nivel"], 100, equipo=ajeno)
    drenar(e)
    assert resultado(e, id_).vlr == 7
    assert resultado(e, id_, punto=e["compartido"].id_ubccn).estado == "Pendiente de datos"


def test_rechaza_origen_ambiguo_sin_elegir_dispositivo_arbitrario(calculos):
    e = calculos
    id_ = crear(e)
    otro = crear_dispositivo(
        e["db"], e["proyectos"][0], crear_conexion(e["db"], e["sedes"][0], "Otro"), nombre="Otro"
    )
    medir(e, e["nivel"], 10)
    medir(e, e["nivel"], 20, equipo=otro)
    medir(e, e["salida"], 3)
    drenar(e)
    assert (
        resultado(e, id_).estado == "Fallido" and "varios dispositivos" in resultado(e, id_).causa
    )


def test_deteccion_de_ciclos_en_dependencias(calculos):
    e = calculos
    a = crear(e)
    b = crear(e, "Doble", "[Balance] * 2")
    e["db"].add(
        DependenciaCalculo(
            id_prm_clc=a, variable=f"c_{b}", id_origen_calculado=b, unidad_origen="m"
        )
    )
    e["db"].flush()
    r = e["client"].post(
        "/parametros-calculados/validar-formula",
        json={"id_sd": e["sedes"][0].id_sd, "frml": "[Doble] * 3", "undd": "m"},
    )
    assert r.status_code == 422 and "circular" in r.text


def test_consulta_cursor_grafico_exportacion_y_traza(calculos, tmp_path):
    e = calculos
    id_ = crear(e)
    medir(e, e["nivel"], 10)
    medir(e, e["salida"], 4)
    drenar(e)
    catalogo = e["client"].get("/mediciones/parametros")
    assert any(p["id_prmtr"] == -id_ for p in catalogo.json()["items"])
    r = e["client"].get("/mediciones", params={"parametro_ids": -id_, "sin_muestreo": True})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1 and r.json()["items"][0]["vlr"] == 6
    assert r.json()["items"][0]["id_calculado"] == id_
    r = e["client"].get("/mediciones", params={"por_pagina": 1, "sin_muestreo": True})
    ids, cursores = [], set()
    while True:
        assert r.status_code == 200, r.text
        ids.extend((i["id_prmtr"], i["id_registro"]) for i in r.json()["items"])
        cursor = r.json()["next_cursor"]
        if not cursor:
            break
        assert cursor not in cursores
        cursores.add(cursor)
        r = e["client"].get(
            "/mediciones", params={"por_pagina": 1, "sin_muestreo": True, "cursor": cursor}
        )
    assert len(ids) == len(set(ids)) == 3
    serie = e["db"].query(SerieCalculada).filter_by(id_prm_clc=id_).one()
    r = e["client"].get(
        f"/mediciones/series/{-serie.id_serie}",
        params={
            "fecha_inicio": (e["fecha"] - dt.timedelta(minutes=1)).isoformat(),
            "fecha_fin": (e["fecha"] + dt.timedelta(minutes=1)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["vlr"] == 6 and r.json()["resumen"]["promedio"] == 6
    filtros = {
        "ubicacion_ids": [e["proyectos"][0].id_ubccn],
        "dispositivo_ids": [],
        "parametro_ids": [-id_],
        "fecha_inicio": (e["fecha"] - dt.timedelta(minutes=1)).isoformat(),
        "fecha_fin": (e["fecha"] + dt.timedelta(minutes=1)).isoformat(),
        "valor_min": None,
        "valor_max": None,
        "frecuencia_muestreo": None,
        "condiciones": [],
        "zona_horaria": "America/Lima",
    }
    for formato in ("csv", "xlsx"):
        archivo = tmp_path / f"calculados.{formato}"
        filas, _ = generar_archivo(
            e["db"], SimpleNamespace(frmt=formato, fltrs_aplcds=filtros), archivo
        )
        assert filas == 1 and archivo.stat().st_size > 0
    assert "Balance" in (tmp_path / "calculados.csv").read_text(encoding="utf-8-sig")
    r = e["client"].get(f"/mediciones/calculados/{id_}/resultados")
    assert r.status_code == 200 and r.json()["items"][0]["trazabilidad"]["origenes"]


def test_lectores_autorizados_consultan_pero_no_crean(calculos, fabrica):
    e = calculos
    id_ = crear(e)
    medir(e, e["nivel"], 10)
    medir(e, e["salida"], 4)
    drenar(e)
    usuario = fabrica.usuario(fabrica.rol("Usuario Empresa"), scp="por_cliente")
    miembro = UsuarioCliente(
        id_usr=usuario.id_usr, id_clnt=e["empresas"][0].id_clnt, rol_emp="Lector"
    )
    e["db"].add(miembro)
    e["db"].flush()
    from app.models import UsuarioProyecto

    e["db"].add(UsuarioProyecto(id_mmb=miembro.id_mmb, id_ubccn=e["proyectos"][0].id_ubccn))
    e["db"].flush()
    e["client"].headers["Authorization"] = "Bearer " + create_access_token(
        usuario.id_usr, None, usuario.scp, usuario.rol.nmbr
    )
    assert e["client"].get(f"/mediciones/calculados/{id_}").status_code == 200
    assert e["client"].get(f"/mediciones/calculados/{id_}/resultados").json()["total"] == 1
    assert (
        e["client"]
        .post(
            "/parametros-calculados/validar-formula",
            json={"id_sd": e["sedes"][0].id_sd, "frml": "[Balance]", "undd": "m"},
        )
        .status_code
        == 403
    )
    e["client"].headers["X-Cliente-Id"] = str(e["empresas"][1].id_clnt)
    assert e["client"].get(f"/mediciones/calculados/{id_}/resultados").status_code == 403


def test_lotes_reanudables_y_reintento(calculos, monkeypatch):
    e = calculos
    import app.services.motor_calculos as motor

    monkeypatch.setattr(motor, "LOTE", 2)
    id_ = crear(e)
    for i in range(5):
        medir(e, e["nivel"], i + 10, e["fecha"] + dt.timedelta(minutes=i))
        medir(e, e["salida"], 2, e["fecha"] + dt.timedelta(minutes=i))
    t = e["db"].query(TrabajoCalculo).filter_by(id_prm_clc=id_).one()
    procesar_lote(e["db"], t)
    assert t.estado == "En curso" and t.procesados == 2 and t.cursor
    t.estado = "Fallido"
    e["db"].flush()
    r = e["client"].post(f"/parametros-calculados/trabajos/{t.id_trabajo}/reintentar")
    assert r.status_code == 200
    drenar(e)
    assert e["db"].query(ResultadoCalculo).filter_by(id_prm_clc=id_).count() == 5
    assert all(r.revision == 1 for r in e["db"].query(ResultadoCalculo))


@pytest.mark.parametrize("desfase", [0, -30])
def test_celery_procesa_outbox_real(calculos, monkeypatch, desfase):
    e = calculos
    from celery import Celery
    from celery.contrib.testing.worker import start_worker

    import app.tasks.calculos as tareas

    id_ = crear(e)
    medir(e, e["nivel"], 10)
    medir(e, e["salida"], 3, e["fecha"] + dt.timedelta(seconds=desfase))
    monkeypatch.setattr(tareas, "SessionLocal", lambda: nullcontext(e["db"]))
    monkeypatch.setattr(tareas, "invalidar_resultados", lambda *args: None)
    monkeypatch.setenv("CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "cache+memory://")
    # Aplicación independiente para no reutilizar conexiones/productores del
    # broker operativo que otros módulos hayan inicializado al importarse.
    prueba = Celery(
        "hu38_prueba", broker="memory://", backend="cache+memory://", set_as_current=False
    )
    nombre = "app.tasks.calculos.procesar_pendientes"
    prueba.task(name=nombre)(tareas.procesar_pendientes.run)
    try:
        with start_worker(
            prueba,
            pool="solo",
            queues=["hu38_prueba"],
            perform_ping_check=False,
            shutdown_timeout=10,
        ):
            prueba.send_task(nombre, queue="hu38_prueba").get(timeout=10)
        assert resultado(e, id_).vlr == 7
        assert (
            e["db"]
            .query(TrabajoCalculo)
            .filter(TrabajoCalculo.estado.in_(["Pendiente", "En curso", "Fallido"]))
            .count()
            == 0
        )
    finally:
        prueba.close()


def test_correccion_propaga_dependencias_y_revisiones(calculos):
    e = calculos
    a = crear(e)
    b = crear(e, "Doble balance", "[Balance] * 2")
    medir(e, e["nivel"], 10)
    origen = medir(e, e["salida"], 3)
    drenar(e)
    assert resultado(e, b).vlr == 14
    origen.vlr = 5
    e["db"].flush()
    drenar(e)
    assert resultado(e, a).vlr == 5 and resultado(e, b).vlr == 10
    assert resultado(e, b).revision == 2


def test_filtros_avanzados_y_exportacion_de_fuente_calculada(calculos, tmp_path):
    e = calculos
    id_ = crear(e)
    medir(e, e["nivel"], 10)
    medir(e, e["salida"], 3)
    drenar(e)
    import json

    from app.schemas_exportaciones import ExportacionCrear
    from app.services.exportaciones import validar_solicitud

    regla = [{"parametro_id": -id_, "minimo": "8", "modo": "dentro"}]
    punto = e["proyectos"][0].id_ubccn
    params = {"parametro_ids": -id_, "dispositivo_ids": -punto, "condiciones": json.dumps(regla)}
    r = e["client"].get("/mediciones", params=params)
    assert r.status_code == 200 and r.json()["total"] == 0, r.text
    regla[0]["minimo"] = "6"
    r = e["client"].get("/mediciones", params={**params, "condiciones": json.dumps(regla)})
    assert r.status_code == 200 and r.json()["total"] == 1, r.text
    body = ExportacionCrear(
        fecha_inicio=e["fecha"] - dt.timedelta(minutes=1),
        fecha_fin=e["fecha"] + dt.timedelta(minutes=1),
        ubicacion_ids=[punto],
        dispositivo_ids=[-punto],
        parametro_ids=[-id_],
        condiciones=regla,
    )
    usuario = {
        "sub": str(e["usuario"].id_usr),
        "scope": "global",
        "rol": "Técnico CENERIS",
        "cliente_id": e["empresas"][0].id_clnt,
    }
    filtros = validar_solicitud(e["db"], usuario, body)
    filtros["zona_horaria"] = "America/Lima"
    assert (
        generar_archivo(
            e["db"], SimpleNamespace(frmt="csv", fltrs_aplcds=filtros), tmp_path / "filtrado.csv"
        )[0]
        == 1
    )


def test_diferencia_termica_como_dependencia(calculos):
    e = calculos
    e["nivel"].undd = e["salida"].undd = "°C"
    e["db"].flush()
    a = crear(e, "Diferencia térmica", unidad="°C")
    b = crear(e, "Diferencia doble", "[Diferencia térmica] * 2", "°C")
    medir(e, e["nivel"], 30)
    medir(e, e["salida"], 20)
    drenar(e)
    assert resultado(e, a).vlr == pytest.approx(10)
    assert resultado(e, b).vlr == pytest.approx(20)


def test_cambio_unidad_origen_invalida_resultado_y_conserva_revision(calculos):
    e = calculos
    id_ = crear(e)
    medir(e, e["nivel"], 10)
    medir(e, e["salida"], 3)
    drenar(e)
    e["nivel"].undd = "cm"
    e["db"].flush()
    drenar(e)
    r = resultado(e, id_)
    assert r.estado == "Fallido" and r.vlr is None and "unidad" in r.causa
    assert r.revision == 2


def test_motor_y_outbox_funcionan_con_rol_de_ejecucion(calculos):
    from sqlalchemy import text

    e = calculos
    id_ = crear(e)
    e["db"].execute(text("SET LOCAL ROLE pangea_app"))
    try:
        medir(e, e["nivel"], 10)
        origen = medir(e, e["salida"], 3)
        drenar(e)
        assert resultado(e, id_).vlr == 7
        origen.vlr = 5
        e["db"].flush()
        drenar(e)
        assert resultado(e, id_).vlr == 5 and resultado(e, id_).revision == 2
        assert (
            not e["db"]
            .execute(
                text(
                    "SELECT has_table_privilege(current_user, 'clcl_revision', 'UPDATE,DELETE,TRUNCATE')"
                )
            )
            .scalar()
        )
    finally:
        e["db"].execute(text("RESET ROLE"))
