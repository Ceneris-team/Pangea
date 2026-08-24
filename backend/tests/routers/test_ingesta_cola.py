"""
HU09 - Monitorear cola de procesamiento: tests de CA1 (listado paginado),
CA2 (filtro por estado) y CA3 (detalle). No cubre /ingesta/metricas
(HT-05 CA3), que ya tiene tests propios y no se toca en esta HU.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (
    ArchivoIngesta,
    ConexionFTP,
    Dispositivo,
    EventoTexto,
    Parametro,
    Telemetria,
    Ubicacion,
)
from app.models.suscripcion import PermisoUsuarioSede
from app.security.dependencies import get_current_user

POLIGONO_DUMMY = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}


def usuario_jwt(usuario_db, rol_nombre, sede_id=None, scope="por_sede"):
    return {"sub": str(usuario_db.id_usr), "sede_id": sede_id, "scope": scope, "rol": rol_nombre}


def agregar_permiso(db, usuario_db, sede_db, modulo, nivel, rol_db):
    db.add(
        PermisoUsuarioSede(
            id_usr=usuario_db.id_usr, id_sd=sede_db.id_sd, id_rl=rol_db.id_rl, mdl=modulo, nvl=nivel
        )
    )
    db.flush()


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def tecnico_lector(db_session, fabrica):
    """Técnico CENERIS con permiso de Lectura sobre Ingesta en su sede."""
    rol = fabrica.rol("Técnico CENERIS")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Ingesta", "Lectura", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )
    return sede, rol


def crear_conexion(db_session, sede, nombre="Datalogger Estacion A"):
    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr=nombre,
        prtcl="FTP",
        hst="127.0.0.1",
        prt=21,
        usr_ftp="usr",
        crdncl_cfrd="cifrado-de-prueba",
        rt_rmt="/data",
        frcnc_mnts=1,
        estd="Activa",
    )
    db_session.add(conexion)
    db_session.flush()
    return conexion


def crear_archivo(db_session, conexion, nombre="H_ejemplo.dat", estd="Pendiente", **overrides):
    archivo = ArchivoIngesta(id_cnxn=conexion.id_cnxn, nmbr_archv=nombre, estd=estd, **overrides)
    db_session.add(archivo)
    db_session.flush()
    return archivo


def crear_dispositivo(db_session, sede, conexion, nombre="CR1000-01", estd="Activo"):
    """Cadena completa (Ubicacion + Dispositivo) para poder resolver
    dspstv.nmbr como nombre del datalogger (ver _mapa_dataloggers en
    routers/ingesta.py).

    DEC-09: ya no crea un MapeoFormato -no hace falta para resolver el
    nombre del datalogger en la cola- ni pasa id_mp al Dispositivo (columna
    eliminada)."""
    ubicacion = Ubicacion(
        id_sd=sede.id_sd,
        nmbr="Ubicacion de prueba",
        lttd=0,
        lngtd=0,
        plgn_gjsn=POLIGONO_DUMMY,
    )
    db_session.add(ubicacion)
    db_session.flush()

    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn,
        id_cnxn=conexion.id_cnxn,
        nmbr=nombre,
        mrc="Campbell",
        lttd=0,
        lngtd=0,
        estd=estd,
    )
    db_session.add(dispositivo)
    db_session.flush()
    return dispositivo


class TestListarColaIngesta:
    """CA1: tabla paginada, 10 registros por defecto, orden fch_dtccn desc."""

    def test_devuelve_los_archivos_de_la_sede(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede)
        crear_archivo(db_session, conexion, nombre="H_uno.dat")
        crear_archivo(db_session, conexion, nombre="H_dos.dat")

        resp = client.get("/ingesta/cola")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["por_pagina"] == 10
        nombres = [item["nmbr_archv"] for item in body["items"]]
        assert set(nombres) == {"H_uno.dat", "H_dos.dat"}

    def test_por_defecto_pagina_de_10(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede)
        for i in range(15):
            crear_archivo(db_session, conexion, nombre=f"H_{i}.dat")

        resp = client.get("/ingesta/cola")
        body = resp.json()
        assert body["total"] == 15
        assert len(body["items"]) == 10

    def test_orden_descendente_por_fecha_de_recepcion(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede)
        ahora = dt.datetime.now(dt.timezone.utc)
        crear_archivo(
            db_session, conexion, nombre="H_viejo.dat", fch_dtccn=ahora - dt.timedelta(hours=2)
        )
        crear_archivo(db_session, conexion, nombre="H_nuevo.dat", fch_dtccn=ahora)

        resp = client.get("/ingesta/cola")
        nombres = [item["nmbr_archv"] for item in resp.json()["items"]]
        assert nombres == ["H_nuevo.dat", "H_viejo.dat"]

    def test_datalogger_de_origen_usa_nombre_de_la_conexion_por_defecto(
        self, client, db_session, tecnico_lector
    ):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede, nombre="FTP Estacion Norte")
        crear_archivo(db_session, conexion)

        resp = client.get("/ingesta/cola")
        assert resp.json()["items"][0]["datalogger_nombre"] == "FTP Estacion Norte"

    def test_datalogger_de_origen_prefiere_el_nombre_del_dispositivo(
        self, client, db_session, tecnico_lector
    ):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede, nombre="FTP Estacion Norte")
        crear_dispositivo(db_session, sede, conexion, nombre="CR1000-Norte")
        crear_archivo(db_session, conexion)

        resp = client.get("/ingesta/cola")
        assert resp.json()["items"][0]["datalogger_nombre"] == "CR1000-Norte"

    def test_usuario_de_otra_sede_no_ve_archivos_ajenos(
        self, client, db_session, tecnico_lector, fabrica
    ):
        sede, _ = tecnico_lector
        crear_archivo(db_session, crear_conexion(db_session, sede))

        otra_sede = fabrica.sede()
        crear_archivo(db_session, crear_conexion(db_session, otra_sede, nombre="Otra conexion"))

        resp = client.get("/ingesta/cola")
        assert resp.json()["total"] == 1

    def test_denegado_sin_permiso(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )
        assert client.get("/ingesta/cola").status_code == 403


class TestFiltroPorEstado:
    """CA2: filtro por estado en el lenguaje de negocio de la HU."""

    def test_filtra_en_espera(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede)
        crear_archivo(db_session, conexion, nombre="H_pendiente.dat", estd="Pendiente")
        crear_archivo(db_session, conexion, nombre="H_exitoso.dat", estd="Exitoso")

        resp = client.get("/ingesta/cola", params={"estado": "En espera"})
        items = resp.json()["items"]
        assert [i["nmbr_archv"] for i in items] == ["H_pendiente.dat"]
        assert items[0]["estado"] == "En espera"

    def test_filtra_procesado(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede)
        crear_archivo(db_session, conexion, nombre="H_pendiente.dat", estd="Pendiente")
        crear_archivo(db_session, conexion, nombre="H_exitoso.dat", estd="Exitoso")

        resp = client.get("/ingesta/cola", params={"estado": "Procesado"})
        items = resp.json()["items"]
        assert [i["nmbr_archv"] for i in items] == ["H_exitoso.dat"]
        assert items[0]["estado"] == "Procesado"

    def test_filtra_fallido(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede)
        crear_archivo(db_session, conexion, nombre="H_fallido.dat", estd="Fallido")
        crear_archivo(db_session, conexion, nombre="H_exitoso.dat", estd="Exitoso")

        resp = client.get("/ingesta/cola", params={"estado": "Fallido"})
        assert [i["nmbr_archv"] for i in resp.json()["items"]] == ["H_fallido.dat"]

    def test_estado_invalido_devuelve_422(self, client, tecnico_lector):
        resp = client.get("/ingesta/cola", params={"estado": "Pendiente"})
        assert resp.status_code == 422

    def test_estado_no_reconocido_devuelve_422(self, client, tecnico_lector):
        resp = client.get("/ingesta/cola", params={"estado": "no-existe"})
        assert resp.status_code == 422


class TestDetalleArchivoIngesta:
    """CA3: fecha de recepción, fecha de procesamiento, registros
    procesados y mensaje de resultado."""

    def test_devuelve_el_detalle_de_un_archivo_exitoso(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede)
        ahora = dt.datetime.now(dt.timezone.utc)
        archivo = crear_archivo(
            db_session,
            conexion,
            estd="Exitoso",
            fch_prcsd=ahora,
            rgstrs_prcsds=120,
        )

        resp = client.get(f"/ingesta/cola/{archivo.id_archv}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["estado"] == "Procesado"
        assert body["rgstrs_prcsds"] == 120
        assert body["mnsj_errr"] is None

    def test_devuelve_el_mensaje_de_error_de_un_archivo_fallido(
        self, client, db_session, tecnico_lector
    ):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede)
        archivo = crear_archivo(
            db_session,
            conexion,
            estd="Fallido",
            mnsj_errr="dispositivo no resoluble",
        )

        resp = client.get(f"/ingesta/cola/{archivo.id_archv}")
        body = resp.json()
        assert body["estado"] == "Fallido"
        assert body["mnsj_errr"] == "dispositivo no resoluble"

    def test_archivo_inexistente_devuelve_404(self, client, tecnico_lector):
        assert client.get("/ingesta/cola/999999").status_code == 404

    def test_usuario_de_otra_sede_no_ve_el_detalle(
        self, client, db_session, tecnico_lector, fabrica
    ):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede)
        archivo = crear_archivo(db_session, conexion)

        otro_rol = fabrica.rol("Administrador")
        otra_sede = fabrica.sede()
        otro_usuario = fabrica.usuario(rol=otro_rol)
        agregar_permiso(db_session, otro_usuario, otra_sede, "Ingesta", "Lectura", otro_rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            otro_usuario, otro_rol.nmbr, sede_id=otra_sede.id_sd
        )

        assert client.get(f"/ingesta/cola/{archivo.id_archv}").status_code == 403

    def test_denegado_sin_permiso(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )
        assert client.get("/ingesta/cola/1").status_code == 403


def crear_parametro(db_session, nombre, unidad="u", tipo_dato="numerico"):
    parametro = Parametro(nmbr=nombre, undd=unidad, tipo_dato=tipo_dato)
    db_session.add(parametro)
    db_session.flush()
    return parametro


def crear_medicion(db_session, dispositivo, parametro, sede, archivo, valor=10.0, fecha=None):
    medicion = Telemetria(
        fch_hr=fecha or dt.datetime.now(dt.timezone.utc),
        id_dspstv=dispositivo.id_dspstv,
        id_prmtr=parametro.id_prmtr,
        id_sd=sede.id_sd,
        vlr=valor,
        id_archv=archivo.id_archv,
    )
    db_session.add(medicion)
    db_session.flush()
    return medicion


def crear_evento_texto(db_session, dispositivo, parametro, sede, archivo, valor="Puerta Abierta", fecha=None):
    evento = EventoTexto(
        fch_hr=fecha or dt.datetime.now(dt.timezone.utc),
        id_dspstv=dispositivo.id_dspstv,
        id_prmtr=parametro.id_prmtr,
        id_sd=sede.id_sd,
        vlr=valor,
        id_archv=archivo.id_archv,
    )
    db_session.add(evento)
    db_session.flush()
    return evento


class TestRegistrosArchivoIngesta:
    """Vista previa de lo que un archivo procesado escribió en tlmtr/evnt_txt."""

    def test_devuelve_mediciones_y_eventos_del_archivo(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede)
        dispositivo = crear_dispositivo(db_session, sede, conexion)
        archivo = crear_archivo(db_session, conexion, estd="Exitoso", rgstrs_prcsds=2)
        parametro_num = crear_parametro(db_session, "Nivel de napa", unidad="m")
        parametro_txt = crear_parametro(db_session, "MensajeP", unidad="-", tipo_dato="texto")

        crear_medicion(db_session, dispositivo, parametro_num, sede, archivo, valor=12.5)
        crear_evento_texto(db_session, dispositivo, parametro_txt, sede, archivo, valor="Puerta Abierta")

        resp = client.get(f"/ingesta/cola/{archivo.id_archv}/registros")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["mostrados"] == 2
        valores = {item["parametro_nombre"]: item["vlr"] for item in body["items"]}
        assert valores["Nivel de napa"] == "12.5000"
        assert valores["MensajeP"] == "Puerta Abierta"

    def test_archivo_sin_registros_devuelve_total_cero(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede)
        archivo = crear_archivo(db_session, conexion, estd="Exitoso", rgstrs_prcsds=0)

        resp = client.get(f"/ingesta/cola/{archivo.id_archv}/registros")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_no_mezcla_registros_de_otro_archivo(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede)
        dispositivo = crear_dispositivo(db_session, sede, conexion)
        parametro = crear_parametro(db_session, "Nivel de napa", unidad="m")

        archivo_1 = crear_archivo(db_session, conexion, nombre="H_1.dat", estd="Exitoso")
        archivo_2 = crear_archivo(db_session, conexion, nombre="H_2.dat", estd="Exitoso")
        crear_medicion(db_session, dispositivo, parametro, sede, archivo_1, valor=1)
        crear_medicion(db_session, dispositivo, parametro, sede, archivo_2, valor=2)

        resp = client.get(f"/ingesta/cola/{archivo_1.id_archv}/registros")
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["vlr"] == "1.0000"

    def test_archivo_inexistente_devuelve_404(self, client, tecnico_lector):
        assert client.get("/ingesta/cola/999999/registros").status_code == 404

    def test_usuario_de_otra_sede_no_ve_los_registros(self, client, db_session, tecnico_lector, fabrica):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede)
        archivo = crear_archivo(db_session, conexion, estd="Exitoso")

        otro_rol = fabrica.rol("Administrador")
        otra_sede = fabrica.sede()
        otro_usuario = fabrica.usuario(rol=otro_rol)
        agregar_permiso(db_session, otro_usuario, otra_sede, "Ingesta", "Lectura", otro_rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            otro_usuario, otro_rol.nmbr, sede_id=otra_sede.id_sd
        )

        assert client.get(f"/ingesta/cola/{archivo.id_archv}/registros").status_code == 403

    def test_denegado_sin_permiso(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )
        assert client.get("/ingesta/cola/1/registros").status_code == 403


@pytest.fixture()
def tecnico_editor(db_session, fabrica):
    """Técnico CENERIS con permiso de Edición sobre Ingesta en su sede -
    nivel que exige POST /ingesta/cola/{id}/reintentar, a diferencia de los
    GET de este módulo que solo piden Lectura."""
    rol = fabrica.rol("Técnico CENERIS")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Ingesta", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )
    return sede, rol


@pytest.fixture()
def reintentos_encolados(monkeypatch):
    """Spy sobre procesar_archivo_dat: lo que corresponde verificar acá es
    que el endpoint reencola la task con el id correcto, no que el
    pipeline corra de nuevo de punta a punta (eso ya lo cubren los tests
    de app/tasks/ingesta.py)."""
    llamadas = []

    class TaskFalsa:
        @staticmethod
        def delay(**kwargs):
            llamadas.append(kwargs)

    monkeypatch.setattr("app.routers.ingesta.procesar_archivo_dat", TaskFalsa)
    return llamadas


class TestReintentarArchivoIngesta:
    """HU31: reprocesamiento manual de un archivo Fallido."""

    def test_reencola_un_archivo_fallido(
        self, client, db_session, tecnico_editor, reintentos_encolados
    ):
        sede, _ = tecnico_editor
        conexion = crear_conexion(db_session, sede)
        archivo = crear_archivo(
            db_session,
            conexion,
            estd="Fallido",
            mnsj_errr="dispositivo no resoluble",
            rgstrs_prcsds=0,
        )

        resp = client.post(f"/ingesta/cola/{archivo.id_archv}/reintentar")
        assert resp.status_code == 200
        body = resp.json()
        assert body["estado"] == "En espera"
        assert body["mnsj_errr"] is None
        assert body["rgstrs_prcsds"] is None
        assert reintentos_encolados == [{"id_archv": archivo.id_archv}]

    def test_archivo_no_fallido_devuelve_409(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        conexion = crear_conexion(db_session, sede)
        archivo = crear_archivo(db_session, conexion, estd="Exitoso")

        resp = client.post(f"/ingesta/cola/{archivo.id_archv}/reintentar")
        assert resp.status_code == 409

    def test_archivo_inexistente_devuelve_404(self, client, tecnico_editor):
        assert client.post("/ingesta/cola/999999/reintentar").status_code == 404

    def test_usuario_de_otra_sede_no_puede_reintentar(
        self, client, db_session, tecnico_editor, fabrica
    ):
        sede, _ = tecnico_editor
        conexion = crear_conexion(db_session, sede)
        archivo = crear_archivo(db_session, conexion, estd="Fallido")

        otro_rol = fabrica.rol("Administrador")
        otra_sede = fabrica.sede()
        otro_usuario = fabrica.usuario(rol=otro_rol)
        agregar_permiso(db_session, otro_usuario, otra_sede, "Ingesta", "Edición", otro_rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            otro_usuario, otro_rol.nmbr, sede_id=otra_sede.id_sd
        )

        assert client.post(f"/ingesta/cola/{archivo.id_archv}/reintentar").status_code == 403

    def test_denegado_con_solo_permiso_de_lectura(self, client, db_session, tecnico_lector):
        sede, _ = tecnico_lector
        conexion = crear_conexion(db_session, sede)
        archivo = crear_archivo(db_session, conexion, estd="Fallido")

        assert client.post(f"/ingesta/cola/{archivo.id_archv}/reintentar").status_code == 403
