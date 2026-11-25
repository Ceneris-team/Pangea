"""HU31 completa: API, original, mapeo real, outbox y recuperaciones."""

import datetime as dt
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.database import get_db
from app.main import app
from app.models import (
    ArchivoIngesta,
    IntentoProcesamiento,
    MapeoColumna,
    ResultadoCalculo,
    Telemetria,
    TrabajoCalculo,
)
from app.security.dependencies import get_current_user
from app.services.ingesta.originales import conservar_original
from app.services.ingesta.reprocesos import solicitar
from app.tasks import ingesta, reprocesos
from tests.routers.test_alarmas import dar_suscripcion_vigente
from tests.routers.test_mediciones import (
    crear_conexion,
    crear_dispositivo,
    crear_parametro,
    crear_ubicacion,
    mapear_parametro,
)


@pytest.fixture()
def entorno(db_session, fabrica, monkeypatch):
    db = db_session
    rol = fabrica.rol("Técnico CENERIS")
    usuario = fabrica.usuario(rol=rol)
    sede = fabrica.sede()
    dar_suscripcion_vigente(db, sede)
    proyecto = crear_ubicacion(db, sede)
    conexion = crear_conexion(db, sede)
    equipo = crear_dispositivo(db, proyecto, conexion)
    parametro = crear_parametro(db, "Nivel", "m")
    formato = mapear_parametro(db, equipo, parametro)
    fecha = dt.datetime.now(dt.timezone.utc).replace(microsecond=0) - dt.timedelta(hours=1)
    archivo = ArchivoIngesta(
        id_cnxn=conexion.id_cnxn,
        id_dspstv=equipo.id_dspstv,
        nmbr_archv="H_original.dat",
        estd="Fallido",
        mnsj_errr="Mapeo pendiente",
    )
    db.add(archivo)
    db.flush()
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "")
    conservar_original(archivo, f"Fecha,Nivel\n{fecha:%Y-%m-%d %H:%M:%S},12.5\n".encode())
    db.commit()
    identidad = {
        "sub": str(usuario.id_usr),
        "rol": rol.nmbr,
        "scope": "global",
        "cliente_id": sede.id_clnt,
        "proyecto_id": proyecto.id_ubccn,
    }
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: identidad
    for modulo in (reprocesos, ingesta):
        monkeypatch.setattr(modulo, "SessionLocal", lambda: db)
        monkeypatch.setattr(modulo, "invalidar_por_lectura", lambda **kwargs: None)
    monkeypatch.setattr(
        "app.services.ingesta.persistencia.invalidar_por_lectura", lambda **kwargs: None
    )
    monkeypatch.setattr(ingesta, "_publicar_eventos_mapa", lambda *args: None)
    with patch.object(db, "close"):
        try:
            yield dict(
                db=db,
                client=TestClient(app),
                usuario=usuario,
                identidad=identidad,
                sede=sede,
                proyecto=proyecto,
                conexion=conexion,
                equipo=equipo,
                parametro=parametro,
                formato=formato,
                archivo=archivo,
                fecha=fecha,
            )
        finally:
            app.dependency_overrides.clear()


def pedir(e, archivo=None):
    archivo = archivo or e["archivo"]
    respuesta = e["client"].post(f"/ingesta/cola/{archivo.id_archv}/reintentar")
    assert respuesta.status_code == 200, respuesta.text
    return (
        e["db"]
        .query(IntentoProcesamiento)
        .filter_by(id_archv=archivo.id_archv, rsltd="Pendiente")
        .one()
    )


def ejecutar(e, intento):
    return reprocesos.procesar_reproceso(e["archivo"].id_archv, intento.id_intnt)


def test_solicitud_durable_historial_y_doble_clic(entorno):
    e = entorno
    intento = pedir(e)
    assert intento.id_usr == e["usuario"].id_usr and intento.fch_inicio is None
    assert intento.proximo_envio is not None
    r = e["client"].post(f"/ingesta/cola/{e['archivo'].id_archv}/reintentar")
    assert r.status_code == 409
    historial = e["client"].get(f"/ingesta/cola/{e['archivo'].id_archv}/intentos").json()
    assert len(historial) == 1 and historial[0]["rsltd"] == "Pendiente"
    assert historial[0]["usuario_nombre"] == e["usuario"].nmbr_cmplt


def test_mensaje_automatico_tardio_no_sustituye_solicitud_manual(entorno):
    e = entorno
    intento = pedir(e)
    assert ingesta.procesar_archivo_dat(e["archivo"].id_archv)["estado"] == "Pendiente"
    assert intento.rsltd == "Pendiente" and intento.fch_inicio is None
    e["archivo"].contenido_original = None
    e["db"].commit()
    assert ejecutar(e, intento)["estado"] == "Fallido"
    assert ingesta.procesar_archivo_dat(e["archivo"].id_archv)["estado"] == "Fallido"
    assert e["db"].query(IntentoProcesamiento).count() == 1


def test_usa_mapeo_corregido_y_original_aunque_ftp_cambie(entorno, monkeypatch):
    e = entorno
    intento = pedir(e)
    nuevo = crear_parametro(e["db"], "Nivel corregido", "m")
    columna = e["db"].query(MapeoColumna).filter_by(id_mp=e["formato"].id_mp).one()
    columna.id_prmtr = nuevo.id_prmtr
    e["db"].commit()
    monkeypatch.setattr(
        ingesta, "descargar_bytes_dat", lambda *args: pytest.fail("No debe consultar FTP")
    )
    assert ejecutar(e, intento)["estado"] == "Exitoso"
    lectura = e["db"].query(Telemetria).one()
    assert lectura.id_prmtr == nuevo.id_prmtr and float(lectura.vlr) == 12.5
    assert lectura.id_dspstv == e["equipo"].id_dspstv and lectura.fch_hr == e["fecha"]
    assert intento.fch_intnt <= intento.fch_inicio <= intento.fch_fin
    assert intento.registros_guardados == 1
    assert ejecutar(e, intento)["estado"] == "descartado"
    assert e["db"].query(Telemetria).count() == 1


@pytest.mark.parametrize(
    "problema", ["sin_original", "integridad", "utf8", "sin_mapeo", "origen_ambiguo"]
)
def test_fallos_no_transitorios_conservan_original_y_motivo(entorno, monkeypatch, problema):
    e = entorno
    archivo = e["archivo"]
    if problema == "sin_original":
        archivo.contenido_original = None
    elif problema == "integridad":
        archivo.contenido_original = b"modificado"
    elif problema == "utf8":
        archivo.sha256 = None
        conservar_original(archivo, b"\xff\xfe")
    elif problema == "sin_mapeo":
        e["formato"].estd = "Inactivo"
    else:
        archivo.id_dspstv = None
        e["identidad"]["proyecto_id"] = None
        # Dos equipos históricos en la conexión: no atribuir al reemplazo.
        e["equipo"].estd = "Inactivo"
        e["db"].flush()
        crear_dispositivo(e["db"], e["proyecto"], e["conexion"], nombre="Reemplazo")
    e["db"].commit()
    original = archivo.contenido_original
    intento = pedir(e)
    monkeypatch.setattr(
        ingesta, "descargar_bytes_dat", lambda *args: pytest.fail("No sustituir original")
    )
    assert ejecutar(e, intento)["estado"] == "Fallido"
    assert intento.rsltd == "Fallido" and intento.mnsj_errr and intento.fch_fin
    assert archivo.contenido_original == original
    assert e["db"].query(Telemetria).count() == 0
    assert e["db"].query(IntentoProcesamiento).count() == 1


def test_broker_caido_y_mensaje_perdido_se_recuperan_sin_perder_autor(entorno, monkeypatch):
    e = entorno
    intento = pedir(e)

    def fallar(**kwargs):
        raise ConnectionError("Broker interrumpido")

    monkeypatch.setattr(reprocesos.procesar_reproceso, "apply_async", fallar)
    assert reprocesos.despachar_pendientes()["pendientes_recuperables"] == 1
    assert intento.rsltd == "Pendiente" and e["archivo"].estd == "Pendiente"
    assert intento.id_usr == e["usuario"].id_usr
    enviados = []
    monkeypatch.setattr(
        reprocesos.procesar_reproceso, "apply_async", lambda **kwargs: enviados.append(kwargs)
    )
    intento.proximo_envio = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
    e["db"].commit()
    assert reprocesos.despachar_pendientes()["publicados"] == 1
    assert enviados[0]["kwargs"] == {
        "id_archv": e["archivo"].id_archv,
        "id_intnt": intento.id_intnt,
    }
    assert ejecutar(e, intento)["estado"] == "Exitoso"


def test_worker_interrumpido_conserva_historial_y_recupera_trabajo(entorno):
    e = entorno
    intento = pedir(e)
    intento.rsltd = "Procesando"
    intento.fch_inicio = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=16)
    e["archivo"].estd = "Procesando"
    e["db"].commit()
    reprocesos.despachar_pendientes()
    siguiente = e["db"].query(IntentoProcesamiento).filter_by(rsltd="Pendiente").one()
    assert intento.rsltd == "Fallido" and "interrumpida" in intento.mnsj_errr
    assert siguiente.id_intento_anterior == intento.id_intnt
    assert siguiente.id_usr == intento.id_usr and siguiente.reintentos == 1
    # Una entrega tardía del worker viejo ya no puede modificar el archivo.
    assert ejecutar(e, intento)["estado"] == "descartado"
    assert ejecutar(e, siguiente)["estado"] == "Exitoso"


def test_reintentos_transitorios_limitados_preservan_cada_error(entorno, monkeypatch):
    e = entorno
    intento = pedir(e)

    def no_disponible(*args):
        raise TimeoutError("Almacén temporalmente inaccesible")

    monkeypatch.setattr(reprocesos, "leer_original", no_disponible)
    for numero in range(6):
        ejecutar(e, intento)
        assert intento.rsltd == "Fallido" and intento.fch_fin and "inaccesible" in intento.mnsj_errr
        if numero < 5:
            intento = e["db"].query(IntentoProcesamiento).filter_by(rsltd="Pendiente").one()
            assert intento.reintentos == numero + 1 and intento.id_usr == e["usuario"].id_usr
    assert e["archivo"].estd == "Fallido"
    assert e["db"].query(IntentoProcesamiento).count() == 6


@pytest.mark.parametrize("rol", ["Cliente Final", "Administrador Comercial", "Usuario Empresa"])
def test_rechaza_otros_roles_aunque_tengan_edicion(entorno, rol):
    e = entorno
    e["identidad"].update(rol=rol, _entorno_resuelto=True, rol_empresa="Administrador")
    # Forzar permiso de módulo concedido para aislar la restricción de rol.
    with patch("app.security.permisos.permiso_del_entorno", return_value=True):
        for url in (
            f"/ingesta/cola/{e['archivo'].id_archv}/reintentar",
            "/ingesta/cola/reintentar-fallidos",
        ):
            assert e["client"].post(url).status_code == 403
    assert e["archivo"].estd == "Fallido"
    assert e["db"].query(IntentoProcesamiento).count() == 0


def test_masivo_respeta_proyecto_y_filtros_en_todas_las_paginas(entorno):
    e = entorno
    db = e["db"]
    for i in range(12):
        db.add(
            ArchivoIngesta(
                id_cnxn=e["conexion"].id_cnxn,
                id_dspstv=e["equipo"].id_dspstv,
                nmbr_archv=f"H_{i}.dat",
                estd="Fallido",
            )
        )
    otro = crear_ubicacion(db, e["sede"], "Otro proyecto en la misma sede")
    cnxn = crear_conexion(db, e["sede"], "Otro origen")
    equipo = crear_dispositivo(db, otro, cnxn, "Otro equipo")
    ajeno = ArchivoIngesta(
        id_cnxn=cnxn.id_cnxn, id_dspstv=equipo.id_dspstv, nmbr_archv="H_ajeno.dat", estd="Fallido"
    )
    db.add(ajeno)
    db.commit()
    filtros = {
        "estado": "Fallido",
        "id_cnxn": e["conexion"].id_cnxn,
        "id_dspstv": e["equipo"].id_dspstv,
    }
    listado = e["client"].get("/ingesta/cola", params=filtros).json()
    assert listado["fallidos"] == 13 and len(listado["items"]) == 10
    assert e["client"].post("/ingesta/cola/reintentar-fallidos", params=filtros).json() == {
        "reencolados": 13
    }
    assert ajeno.estd == "Fallido"
    assert e["client"].post(f"/ingesta/cola/{ajeno.id_archv}/reintentar").status_code == 403
    assert e["client"].get(f"/ingesta/cola/{ajeno.id_archv}").status_code == 403
    assert e["client"].get("/ingesta/metricas").json()["total"] == 13
    assert e["client"].post("/ingesta/cola/reintentar-fallidos", params=filtros).json() == {
        "reencolados": 0
    }


def test_indice_impide_dos_solicitudes_activas(entorno):
    e = entorno
    pedir(e)
    with pytest.raises(IntegrityError):
        with e["db"].begin_nested():
            solicitar(e["db"], e["archivo"], e["usuario"].id_usr)
            e["db"].flush()


def test_fallo_al_guardar_no_cambia_estado_ni_crea_solicitud(entorno, monkeypatch):
    e = entorno

    def fallar():
        e["db"].rollback()
        raise OperationalError("COMMIT", {}, RuntimeError("Base no disponible"))

    monkeypatch.setattr(e["db"], "commit", fallar)
    respuesta = e["client"].post(f"/ingesta/cola/{e['archivo'].id_archv}/reintentar")
    assert respuesta.status_code == 503 and "No se pudo guardar" in respuesta.json()["detail"]
    assert e["archivo"].estd == "Fallido"
    assert e["db"].query(IntentoProcesamiento).count() == 0


def test_rol_runtime_puede_despachar_y_ejecutar(entorno):
    e = entorno
    pedir(e)

    def rol_runtime(session, transaction, connection):
        connection.exec_driver_sql("SET LOCAL ROLE pangea_app")

    event.listen(e["db"], "after_begin", rol_runtime)
    try:
        intento = e["db"].query(IntentoProcesamiento).one()
        assert ejecutar(e, intento)["estado"] == "Exitoso"
    finally:
        event.remove(e["db"], "after_begin", rol_runtime)
        e["db"].execute(text("RESET ROLE"))


def test_recupera_solo_faltantes_sin_reevaluar_lecturas_existentes(entorno, monkeypatch):
    e = entorno
    fecha = e["fecha"]
    archivo = e["archivo"]
    archivo.sha256 = None
    conservar_original(
        archivo,
        (
            f"Fecha,Nivel\n{fecha:%Y-%m-%d %H:%M:%S},99\n"
            f"{fecha + dt.timedelta(minutes=1):%Y-%m-%d %H:%M:%S},15\n"
        ).encode(),
    )
    existente = Telemetria(
        id_dspstv=e["equipo"].id_dspstv,
        id_sd=e["sede"].id_sd,
        id_prmtr=e["parametro"].id_prmtr,
        fch_hr=fecha,
        vlr=12.5,
    )
    e["db"].add(existente)
    e["db"].commit()
    evaluaciones = []
    monkeypatch.setattr(
        "app.services.ingesta.persistencia.evaluar_alarmas",
        lambda db, **kwargs: evaluaciones.extend(kwargs["lecturas"]),
    )
    intento = pedir(e)
    assert ejecutar(e, intento)["guardadas"] == 1
    assert float(existente.vlr) == 12.5
    assert e["db"].query(Telemetria).count() == 2
    assert len(evaluaciones) == 1 and evaluaciones[0].valor == 15
    # Incluso otro reproceso explícito del mismo original no crea efectos duplicados.
    archivo.estd = "Fallido"
    e["db"].commit()
    siguiente = pedir(e)
    assert ejecutar(e, siguiente)["guardadas"] == 0
    assert e["db"].query(Telemetria).count() == 2 and len(evaluaciones) == 1


def test_lecturas_recuperadas_alimentan_consultas_y_calculos(entorno):
    from app.services.motor_calculos import procesar_lote

    e = entorno
    respuesta = e["client"].post(
        "/parametros-calculados",
        json={
            "id_sd": e["sede"].id_sd,
            "nmbr": "Doble nivel",
            "frml": "[Nivel] * 2",
            "undd": "m",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    id_calculo = respuesta.json()["id_prm_clc"]
    assert ejecutar(e, pedir(e))["estado"] == "Exitoso"
    for _ in range(10):
        trabajo = (
            e["db"]
            .query(TrabajoCalculo)
            .filter(TrabajoCalculo.estado.in_(("Pendiente", "En curso")))
            .first()
        )
        if not trabajo:
            break
        procesar_lote(e["db"], trabajo)
    resultado = e["db"].query(ResultadoCalculo).filter_by(id_prm_clc=id_calculo).one()
    assert float(resultado.vlr) == 25
    respuesta = e["client"].get(
        "/mediciones",
        params={"dispositivo_ids": e["equipo"].id_dspstv, "parametro_ids": e["parametro"].id_prmtr},
    )
    assert respuesta.status_code == 200 and respuesta.json()["total"] == 1, respuesta.text


def test_celery_ejecuta_solicitud_durable(entorno, monkeypatch):
    from celery import Celery
    from celery.contrib.testing.worker import start_worker

    e = entorno
    intento = pedir(e)
    prueba = Celery(
        "hu31_prueba", broker="memory://", backend="cache+memory://", set_as_current=False
    )
    nombre = "app.tasks.reprocesos.procesar_reproceso"
    prueba.task(name=nombre)(reprocesos.procesar_reproceso.run)
    try:
        with start_worker(
            prueba,
            pool="solo",
            queues=["hu31_prueba"],
            perform_ping_check=False,
            shutdown_timeout=10,
        ):
            respuesta = prueba.send_task(
                nombre,
                kwargs={"id_archv": e["archivo"].id_archv, "id_intnt": intento.id_intnt},
                queue="hu31_prueba",
            ).get(timeout=10)
            assert respuesta["estado"] == "Exitoso"
        e["db"].expire_all()
        assert intento.rsltd == "Exitoso" and e["db"].query(Telemetria).count() == 1
    finally:
        prueba.close()


def test_un_fallido_no_impide_el_siguiente_archivo_del_lote(entorno):
    e = entorno
    malo = ArchivoIngesta(
        id_cnxn=e["conexion"].id_cnxn,
        id_dspstv=e["equipo"].id_dspstv,
        nmbr_archv="H_sin_original.dat",
        estd="Fallido",
    )
    e["db"].add(malo)
    e["db"].commit()
    r = e["client"].post("/ingesta/cola/reintentar-fallidos")
    assert r.json()["reencolados"] == 2
    for intento in (
        e["db"]
        .query(IntentoProcesamiento)
        .filter_by(rsltd="Pendiente")
        .order_by(IntentoProcesamiento.id_archv.desc())
        .all()
    ):
        reprocesos.procesar_reproceso(intento.id_archv, intento.id_intnt)
    assert malo.estd == "Fallido" and e["archivo"].estd == "Exitoso"
