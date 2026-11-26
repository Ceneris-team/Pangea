"""HU37: log por evento, permisos, origen histórico, fechas y retención real."""

import datetime as dt
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.models import ArchivoIngesta, IntentoProcesamiento, LogIngesta, PermisoUsuarioSede
from app.services.ingesta.log import capturar_origen, mensaje_seguro
from app.tasks import ingesta, log_ingesta, reprocesos
from tests.routers.test_mediciones import crear_ubicacion
from tests.routers.test_reprocesos import ejecutar, pedir
from tests.routers.test_reprocesos import entorno as entorno  # noqa: F401


def evento(e, resultado="Fallido", mensaje="Falta configurar la columna", **datos):
    ingesta._registrar_intento(
        e["db"],
        e["archivo"].id_archv,
        resultado,
        mensaje,
        None,
        datos.pop("inicio", dt.datetime.now(dt.timezone.utc)),
        **datos,
    )
    e["db"].commit()
    return e["db"].query(LogIngesta).order_by(LogIngesta.id_evento.desc()).first()


def test_fallo_y_reproceso_exitoso_conservan_eventos_y_diagnostico_completo(entorno):
    e = entorno
    fallo = evento(e, mensaje="Diagnóstico largo: " + "dato inválido; " * 100)
    intento = pedir(e)
    assert ejecutar(e, intento)["estado"] == "Exitoso"
    r = e["client"].get("/ingesta/log")
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["total"] == 2 and datos["por_pagina"] == 20
    assert [fila["resultado"] for fila in datos["items"]] == ["Procesado", "Fallido"]
    detalle = e["client"].get(f"/ingesta/log/{fallo.id_evento}").json()
    assert len(detalle["mensaje"]) > 500
    assert len(detalle["historial"]) == 2
    assert detalle["registros_procesados"] is None
    exito = datos["items"][0]
    assert exito["registros_procesados"] == 1 and exito["registros_rechazados"] == 0
    assert exito["inicio"] <= exito["fin"] and exito["recepcion"]


def test_procesamiento_inicial_real_y_entrega_duplicada(entorno):
    e = entorno
    e["archivo"].estd = "Pendiente"
    e["db"].commit()
    assert ingesta.procesar_archivo_dat(e["archivo"].id_archv)["estado"] == "Exitoso"
    assert ingesta.procesar_archivo_dat(e["archivo"].id_archv)["estado"] == "Exitoso"
    filas = e["db"].query(LogIngesta).all()
    assert len(filas) == 1 and filas[0].origen == "Automático"


def test_filtros_combinados_fechas_inclusivas_en_zona_y_nombre_literal(entorno):
    e = entorno
    dia = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=2)
    inicio = dt.datetime.combine(dia, dt.time(5), dt.timezone.utc)  # Medianoche en Lima
    e["archivo"].nmbr_archv = "H_100%_nivel.dat"
    e["db"].commit()
    primero = evento(e, inicio=inicio)
    ultimo = evento(e, inicio=inicio + dt.timedelta(days=1, microseconds=-1))
    evento(e, inicio=inicio + dt.timedelta(days=1))
    evento(e, "Exitoso", inicio=inicio + dt.timedelta(hours=3))
    consulta = dict(
        nombre="100%_",
        resultado="Fallido",
        fecha_inicio=str(dia),
        fecha_fin=str(dia),
        zona_horaria="America/Lima",
        id_cnxn=e["conexion"].id_cnxn,
        id_dspstv=e["equipo"].id_dspstv,
    )
    r = e["client"].get("/ingesta/log", params=consulta)
    assert r.status_code == 200, r.text
    assert [f["id_evento"] for f in r.json()["items"]] == [ultimo.id_evento, primero.id_evento]
    assert e["client"].get("/ingesta/log", params={"nombre": "100X"}).json()["total"] == 0


@pytest.mark.parametrize(
    "params",
    [
        {"fecha_inicio": "2026-11-20", "fecha_fin": "2026-11-19"},
        {"fecha_inicio": "fecha-inválida"},
        {"zona_horaria": "Inexistente"},
        {"resultado": "Procesando"},
        {"pagina": 0},
        {"por_pagina": 101},
    ],
)
def test_validaciones(entorno, params):
    assert entorno["client"].get("/ingesta/log", params=params).status_code == 422


def test_paginacion_20_sin_perder_resultado_y_orden_estable(entorno):
    e = entorno
    instante = dt.datetime.now(dt.timezone.utc)
    for _ in range(22):
        evento(e, inicio=instante)
    a = e["client"].get("/ingesta/log", params={"resultado": "Fallido"}).json()
    b = e["client"].get("/ingesta/log", params={"resultado": "Fallido", "pagina": 2}).json()
    assert a["total"] == b["total"] == 22
    assert len(a["items"]) == 20 and len(b["items"]) == 2
    ids = [f["id_evento"] for f in a["items"] + b["items"]]
    assert len(set(ids)) == 22 and ids == sorted(ids, reverse=True)


def test_origen_no_cambia_al_renombrar_o_trasladar_equipo(entorno):
    e = entorno
    fila = evento(e)
    original = fila.datalogger
    proyecto_original = fila.proyecto
    e["equipo"].nmbr = "Nombre cambiado"
    destino = crear_ubicacion(e["db"], e["sede"], nombre="Proyecto destino")
    e["equipo"].id_ubccn = destino.id_ubccn
    e["db"].commit()
    r = e["client"].get(f"/ingesta/log/{fila.id_evento}")
    assert r.status_code == 200, r.text
    assert r.json()["datalogger"] == original and r.json()["proyecto"] == proyecto_original
    e["identidad"]["proyecto_id"] = destino.id_ubccn
    assert e["client"].get("/ingesta/log").json()["total"] == 0
    assert e["client"].get(f"/ingesta/log/{fila.id_evento}").status_code == 404


def test_origen_se_captura_antes_del_primer_procesamiento(entorno):
    e = entorno
    origen = capturar_origen(e["db"], e["archivo"]).copy()
    e["db"].commit()
    e["equipo"].nmbr = "Equipo renombrado después de recibir el archivo"
    e["db"].commit()
    fila = evento(e)
    assert fila.datalogger == origen["datalogger"]
    assert fila.id_ubccn == origen["id_ubccn"]


def test_error_de_difusion_no_crea_un_falso_fallo_de_ingesta(entorno, monkeypatch):
    e = entorno
    e["archivo"].estd = "Pendiente"
    e["db"].commit()
    monkeypatch.setattr(
        ingesta,
        "_publicar_eventos_mapa",
        lambda *args: (_ for _ in ()).throw(RuntimeError("Sin difusión")),
    )
    assert ingesta.procesar_archivo_dat(e["archivo"].id_archv)["estado"] == "Exitoso"
    assert [f.resultado for f in e["db"].query(LogIngesta).all()] == ["Exitoso"]


@pytest.mark.parametrize("rol", ["Cliente Final", "Usuario Empresa", "Administrador Comercial"])
def test_otros_roles_no_consultan_ni_listado_ni_filtros_ni_detalle(entorno, rol):
    e = entorno
    fila = evento(e)
    e["identidad"]["rol"] = rol
    for ruta in ("/ingesta/log", "/ingesta/log/dataloggers", f"/ingesta/log/{fila.id_evento}"):
        assert e["client"].get(ruta).status_code == 403


def test_aislamiento_empresa_proyecto_sede_y_permiso_lectura(entorno, fabrica):
    e = entorno
    fila = evento(e)
    otra = fabrica.sede()
    e["db"].commit()
    e["identidad"].update(cliente_id=otra.id_clnt, proyecto_id=None)
    assert e["client"].get("/ingesta/log").json()["total"] == 0
    assert e["client"].get("/ingesta/log/dataloggers").json()["items"] == []
    assert e["client"].get(f"/ingesta/log/{fila.id_evento}").status_code == 404
    e["identidad"].update(scope="por_sede", sede_id=e["sede"].id_sd, cliente_id=None)
    assert e["client"].get("/ingesta/log").status_code == 403
    e["db"].add(
        PermisoUsuarioSede(
            id_usr=e["usuario"].id_usr,
            id_sd=e["sede"].id_sd,
            id_rl=e["usuario"].id_rl,
            mdl="Ingesta",
            nvl="Lectura",
        )
    )
    e["db"].commit()
    assert e["client"].get("/ingesta/log").json()["total"] == 1
    e["identidad"]["sede_id"] = otra.id_sd
    assert e["client"].get("/ingesta/log").status_code == 403


def test_retencion_oculta_y_depura_solo_log_sin_borrar_archivos_o_intentos(entorno, monkeypatch):
    e = entorno
    viejo = evento(e, inicio=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=91))
    reciente = evento(e)
    assert e["client"].get("/ingesta/log").json()["total"] == 1
    assert e["client"].get(f"/ingesta/log/{viejo.id_evento}").status_code == 404
    detalle = e["client"].get(f"/ingesta/log/{reciente.id_evento}").json()
    assert len(detalle["historial"]) == 1
    monkeypatch.setattr(log_ingesta, "SessionLocal", lambda: e["db"])
    with patch.object(e["db"], "__exit__"):
        assert log_ingesta.depurar()["eliminados"] == 1
    assert e["db"].query(LogIngesta).count() == 1
    assert e["db"].query(IntentoProcesamiento).count() == 2
    assert e["db"].query(ArchivoIngesta).count() == 1


def test_carga_manual_exitosa_y_fallida_dejan_log(entorno):
    e = entorno
    for valor, esperado in [("23.5", 201), ("invalido", 422)]:
        contenido = f"Fecha,Nivel\n{e['fecha']:%Y-%m-%d %H:%M:%S},{valor}\n"
        r = e["client"].post(
            f"/dispositivos/{e['equipo'].id_dspstv}/carga-archivo",
            files={"archivo": ("H_manual.dat", contenido, "text/plain")},
        )
        assert r.status_code == esperado, r.text
    filas = e["db"].query(LogIngesta).order_by(LogIngesta.id_evento).all()
    assert [f.resultado for f in filas] == ["Exitoso", "Fallido"]
    assert all(f.origen == "Carga manual" for f in filas)
    assert filas[1].registros_rechazados == 1 and "no es numérico" in filas[1].mensaje


def test_reproceso_transitorio_y_posterior_exito_quedan_separados(entorno, monkeypatch):
    e = entorno
    intento = pedir(e)
    leer = reprocesos.leer_original
    monkeypatch.setattr(
        reprocesos,
        "leer_original",
        lambda *args: (_ for _ in ()).throw(TimeoutError("Red no disponible")),
    )
    assert ejecutar(e, intento)["estado"] == "Pendiente"
    siguiente = e["db"].query(IntentoProcesamiento).filter_by(rsltd="Pendiente").one()
    monkeypatch.setattr(reprocesos, "leer_original", leer)
    assert ejecutar(e, siguiente)["estado"] == "Exitoso"
    assert e["client"].get("/ingesta/log").json()["total"] == 2


def test_credenciales_ocultas_y_rol_runtime_puede_insertar_sin_editar(entorno):
    e = entorno
    fila = evento(
        e,
        mensaje="Fallo ftp://tecnico:secreto@equipo password=privado token='oculto valor' "
        + "x" * 700,
    )
    assert "secreto" not in fila.mensaje and "privado" not in fila.mensaje
    r = e["client"].get(f"/ingesta/log/{fila.id_evento}")
    assert "secreto" not in r.text and len(r.json()["mensaje"]) > 500
    assert (
        mensaje_seguro("[SQL: INSERT x] [parameters: sensibles]")
        == "Error al guardar los datos. Requiere revisión técnica."
    )
    for permiso, esperado in [
        ("SELECT", True),
        ("INSERT", True),
        ("DELETE", True),
        ("UPDATE", False),
    ]:
        assert (
            e["db"]
            .execute(
                text("SELECT has_table_privilege('pangea_app','log_ingesta',:p)"), {"p": permiso}
            )
            .scalar()
            == esperado
        )
