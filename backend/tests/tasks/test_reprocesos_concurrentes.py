"""Dos conexiones reales comprueban exclusión y rescate de un worker vivo."""

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from sqlalchemy import delete, update
from sqlalchemy.orm import sessionmaker

from app.models import (
    ArchivoIngesta,
    Cliente,
    ConexionFTP,
    Dispositivo,
    IntentoProcesamiento,
    MapeoColumna,
    MapeoFormato,
    Parametro,
    Sede,
    Telemetria,
    Ubicacion,
    Usuario,
)
from app.services.ingesta.originales import conservar_original
from app.services.ingesta.reprocesos import solicitar
from app.tasks import ingesta, reprocesos
from tests.conftest import Fabrica
from tests.routers.test_mediciones import (
    crear_conexion,
    crear_dispositivo,
    crear_parametro,
    crear_ubicacion,
    mapear_parametro,
)


def test_worker_vivo_no_se_duplica_ni_es_rescatado(_engine, monkeypatch):
    sesiones = sessionmaker(bind=_engine, expire_on_commit=False)
    db = sesiones()
    fabrica = Fabrica(db)
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=fabrica.rol("Técnico CENERIS"))
    punto = crear_ubicacion(db, sede)
    conexion = crear_conexion(db, sede)
    equipo = crear_dispositivo(db, punto, conexion)
    parametro = crear_parametro(db, "Nivel concurrencia", "m")
    formato = mapear_parametro(db, equipo, parametro)
    archivo = ArchivoIngesta(
        id_cnxn=conexion.id_cnxn,
        id_dspstv=equipo.id_dspstv,
        nmbr_archv="H_concurrencia.dat",
        estd="Fallido",
    )
    db.add(archivo)
    db.flush()
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "")
    fecha = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    conservar_original(archivo, f"Fecha,Nivel\n{fecha:%Y-%m-%d %H:%M:%S},8\n".encode())
    intento = solicitar(db, archivo, usuario.id_usr)
    db.commit()
    monkeypatch.setattr(reprocesos, "SessionLocal", sesiones)
    monkeypatch.setattr(reprocesos, "invalidar_por_lectura", lambda **kwargs: None)
    monkeypatch.setattr(
        "app.services.ingesta.persistencia.invalidar_por_lectura", lambda **kwargs: None
    )
    monkeypatch.setattr(ingesta, "_publicar_eventos_mapa", lambda *args: None)
    iniciado, liberar = Event(), Event()
    interpretar = ingesta.interpretar_y_guardar

    def pausado(*args, **kwargs):
        iniciado.set()
        assert liberar.wait(10), "El test no liberó el worker"
        return interpretar(*args, **kwargs)

    monkeypatch.setattr(ingesta, "interpretar_y_guardar", pausado)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            tarea = pool.submit(
                reprocesos.procesar_reproceso.run, archivo.id_archv, intento.id_intnt
            )
            assert iniciado.wait(10), "El worker no comenzó"
            try:
                db.execute(
                    update(IntentoProcesamiento)
                    .where(IntentoProcesamiento.id_intnt == intento.id_intnt)
                    .values(fch_inicio=fecha - dt.timedelta(minutes=16))
                )
                db.commit()
                assert (
                    reprocesos.procesar_reproceso(archivo.id_archv, intento.id_intnt)["estado"]
                    == "ocupado_o_inexistente"
                )
                assert reprocesos.despachar_pendientes()["publicados"] == 0
            finally:
                liberar.set()
            assert tarea.result(timeout=10)["estado"] == "Exitoso"
        db.expire_all()
        assert db.query(Telemetria).filter_by(id_archv=archivo.id_archv).count() == 1
        assert db.query(IntentoProcesamiento).filter_by(id_archv=archivo.id_archv).count() == 1
        assert db.get(ArchivoIngesta, archivo.id_archv).estd == "Exitoso"
    finally:
        liberar.set()
        db.rollback()
        for modelo, condicion in (
            (Telemetria, Telemetria.id_archv == archivo.id_archv),
            (IntentoProcesamiento, IntentoProcesamiento.id_archv == archivo.id_archv),
            (ArchivoIngesta, ArchivoIngesta.id_archv == archivo.id_archv),
            (MapeoColumna, MapeoColumna.id_mp == formato.id_mp),
            (MapeoFormato, MapeoFormato.id_mp == formato.id_mp),
            (Dispositivo, Dispositivo.id_dspstv == equipo.id_dspstv),
            (Parametro, Parametro.id_prmtr == parametro.id_prmtr),
            (ConexionFTP, ConexionFTP.id_cnxn == conexion.id_cnxn),
            (Ubicacion, Ubicacion.id_ubccn == punto.id_ubccn),
            (Sede, Sede.id_sd == sede.id_sd),
            (Cliente, Cliente.id_clnt == sede.id_clnt),
            (Usuario, Usuario.id_usr == usuario.id_usr),
        ):
            db.execute(delete(modelo).where(condicion))
        db.commit()
        db.close()
