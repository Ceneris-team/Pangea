"""
HU 17 - Ver datos en mapa (rol Cliente Final).

CA1: solo las ubicaciones ASIGNADAS al Cliente Final (HU 21, prms_ubccn).
CA2: último valor de cada parámetro + fecha/hora de la última lectura.

El punto crítico de la HU -y lo que estos tests cubren con más detalle-
es el AISLAMIENTO: que un Cliente Final no vea en el mapa una ubicación
que no le fue asignada, mismo criterio que ya valida test_mediciones.py
para HU 13. HU 17 es una pantalla distinta de HU 22 (vista de
Administrador), así que el filtro se verifica aparte y no se asume
heredado.

CA3 (WebSocket) se cubre en test_mapa_cliente_ws.py; CA4 es navegación
del frontend.

Corre contra la Postgres real de test (ver conftest.py).
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (
    ConexionFTP,
    Dispositivo,
    EventoTexto,
    Parametro,
    PermisoUbicacion,
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


def asignar_ubicacion(db, usuario_db, ubicacion):
    db.add(PermisoUbicacion(id_usr=usuario_db.id_usr, id_ubccn=ubicacion.id_ubccn))
    db.flush()


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def crear_ubicacion(db_session, sede, nombre, lttd=10, lngtd=-70):
    ubicacion = Ubicacion(
        id_sd=sede.id_sd, nmbr=nombre, lttd=lttd, lngtd=lngtd, plgn_gjsn=POLIGONO_DUMMY
    )
    db_session.add(ubicacion)
    db_session.flush()
    return ubicacion


def crear_dispositivo(db_session, ubicacion, sede, nombre="CR1000-HU17"):
    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr=f"Datalogger {nombre}",
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

    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn,
        id_cnxn=conexion.id_cnxn,
        nmbr=nombre,
        mrc="Campbell",
        lttd=0,
        lngtd=0,
        estd="Activo",
    )
    db_session.add(dispositivo)
    db_session.flush()
    return dispositivo


def crear_parametro(db_session, nombre, unidad="u", tipo_dato="numerico"):
    parametro = Parametro(
        nmbr=nombre, undd=unidad, dscrpcn="parámetro creado por los tests", tipo_dato=tipo_dato
    )
    db_session.add(parametro)
    db_session.flush()
    return parametro


def agregar_lectura(db_session, dispositivo, parametro, sede, valor, cuando):
    db_session.add(
        Telemetria(
            fch_hr=cuando,
            id_dspstv=dispositivo.id_dspstv,
            id_prmtr=parametro.id_prmtr,
            id_sd=sede.id_sd,
            vlr=valor,
        )
    )
    db_session.flush()


@pytest.fixture()
def escenario(db_session, fabrica):
    """Un Cliente Final con UNA ubicación asignada y otra que NO lo está."""
    rol = fabrica.rol("Cliente Final")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Tableros", "Lectura", rol)

    asignada = crear_ubicacion(db_session, sede, "Estacion Asignada")
    ajena = crear_ubicacion(db_session, sede, "Estacion Ajena")
    asignar_ubicacion(db_session, usuario, asignada)

    return {
        "usuario": usuario,
        "rol": rol,
        "sede": sede,
        "asignada": asignada,
        "ajena": ajena,
    }


class TestCA1FiltroDePermisos:
    def test_cliente_final_solo_ve_sus_ubicaciones(self, client, db_session, escenario):
        """CA1 + HU21: la ubicación no asignada NO aparece en el mapa."""
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            escenario["usuario"], "Cliente Final", escenario["sede"].id_sd
        )

        respuesta = client.get("/mapa-cliente")
        assert respuesta.status_code == 200

        nombres = [item["nmbr"] for item in respuesta.json()["items"]]
        assert "Estacion Asignada" in nombres
        assert "Estacion Ajena" not in nombres

    def test_marcador_trae_coordenadas(self, client, db_session, escenario):
        """CA1: "marcadores en las coordenadas de las ubicaciones"."""
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            escenario["usuario"], "Cliente Final", escenario["sede"].id_sd
        )

        item = next(
            i for i in client.get("/mapa-cliente").json()["items"] if i["nmbr"] == "Estacion Asignada"
        )
        assert item["lttd"] == 10
        assert item["lngtd"] == -70
        assert item["id_ubccn"] == escenario["asignada"].id_ubccn

    def test_sin_ubicaciones_asignadas_devuelve_lista_vacia(self, client, db_session, fabrica):
        """Un Cliente Final sin nada asignado ve un mapa vacío, no un 500
        ni todas las ubicaciones."""
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Tableros", "Lectura", rol)
        crear_ubicacion(db_session, sede, "Estacion De Otro")

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, "Cliente Final", sede.id_sd
        )

        respuesta = client.get("/mapa-cliente")
        assert respuesta.status_code == 200
        assert respuesta.json()["items"] == []

    def test_administrador_ve_todas(self, client, db_session, escenario, fabrica):
        """Mismo criterio que el resto de la app: Administrador no está
        limitado por prms_ubccn."""
        rol_admin = fabrica.rol("Administrador")
        admin = fabrica.usuario(rol=rol_admin, scp="global")
        agregar_permiso(db_session, admin, escenario["sede"], "Tableros", "Lectura", rol_admin)

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            admin, "Administrador", escenario["sede"].id_sd, scope="global"
        )

        nombres = [i["nmbr"] for i in client.get("/mapa-cliente").json()["items"]]
        assert "Estacion Asignada" in nombres
        assert "Estacion Ajena" in nombres

    def test_sin_permiso_sobre_tableros_es_403(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        # No se agrega permiso sobre "Tableros".

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, "Cliente Final", sede.id_sd
        )

        assert client.get("/mapa-cliente").status_code == 403


class TestCA2UltimoValorPorParametro:
    def test_devuelve_el_ultimo_valor_y_no_los_anteriores(self, client, db_session, escenario):
        """CA2: "el último valor de cada parámetro", no el histórico."""
        dispositivo = crear_dispositivo(db_session, escenario["asignada"], escenario["sede"])
        temperatura = crear_parametro(db_session, "temperatura", "°C")

        ahora = dt.datetime.now(dt.timezone.utc)
        agregar_lectura(db_session, dispositivo, temperatura, escenario["sede"], 10, ahora - dt.timedelta(hours=2))
        agregar_lectura(db_session, dispositivo, temperatura, escenario["sede"], 20, ahora - dt.timedelta(hours=1))
        agregar_lectura(db_session, dispositivo, temperatura, escenario["sede"], 25, ahora)

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            escenario["usuario"], "Cliente Final", escenario["sede"].id_sd
        )

        item = next(
            i for i in client.get("/mapa-cliente").json()["items"] if i["nmbr"] == "Estacion Asignada"
        )
        parametros = {p["parametro"]: p for p in item["parametros"]}
        assert parametros["temperatura"]["valor"] == 25
        assert parametros["temperatura"]["unidad"] == "°C"
        assert len(item["parametros"]) == 1

    def test_un_valor_por_cada_parametro(self, client, db_session, escenario):
        dispositivo = crear_dispositivo(db_session, escenario["asignada"], escenario["sede"])
        temperatura = crear_parametro(db_session, "temperatura", "°C")
        humedad = crear_parametro(db_session, "ph", "pH")

        ahora = dt.datetime.now(dt.timezone.utc)
        agregar_lectura(db_session, dispositivo, temperatura, escenario["sede"], 25, ahora)
        agregar_lectura(db_session, dispositivo, humedad, escenario["sede"], 7, ahora)

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            escenario["usuario"], "Cliente Final", escenario["sede"].id_sd
        )

        item = next(
            i for i in client.get("/mapa-cliente").json()["items"] if i["nmbr"] == "Estacion Asignada"
        )
        parametros = {p["parametro"]: p["valor"] for p in item["parametros"]}
        assert parametros == {"temperatura": 25, "ph": 7}

    def test_fecha_de_ultima_lectura_es_la_mas_reciente(self, client, db_session, escenario):
        """CA2: "la fecha/hora de la última lectura" de la estación."""
        dispositivo = crear_dispositivo(db_session, escenario["asignada"], escenario["sede"])
        temperatura = crear_parametro(db_session, "temperatura", "°C")
        humedad = crear_parametro(db_session, "ph", "pH")

        ahora = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        agregar_lectura(db_session, dispositivo, humedad, escenario["sede"], 7, ahora - dt.timedelta(hours=3))
        agregar_lectura(db_session, dispositivo, temperatura, escenario["sede"], 25, ahora)

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            escenario["usuario"], "Cliente Final", escenario["sede"].id_sd
        )

        item = next(
            i for i in client.get("/mapa-cliente").json()["items"] if i["nmbr"] == "Estacion Asignada"
        )
        assert item["ultima_lectura"].startswith(ahora.isoformat()[:19])

    def test_estacion_sin_lecturas_no_rompe(self, client, db_session, escenario):
        """Una ubicación recién creada aparece en el mapa igual, con el
        panel vacío: CA1 pide el marcador, no que haya datos."""
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            escenario["usuario"], "Cliente Final", escenario["sede"].id_sd
        )

        item = next(
            i for i in client.get("/mapa-cliente").json()["items"] if i["nmbr"] == "Estacion Asignada"
        )
        assert item["parametros"] == []
        assert item["ultima_lectura"] is None
        assert item["semaforo"] == "verde"

    def test_incluye_eventos_de_texto(self, client, db_session, escenario):
        """evnt_txt es tan "último valor de un parámetro" como tlmtr."""
        dispositivo = crear_dispositivo(db_session, escenario["asignada"], escenario["sede"])
        mensaje = crear_parametro(db_session, "mensaje_puerta", "-", tipo_dato="texto")

        db_session.add(
            EventoTexto(
                fch_hr=dt.datetime.now(dt.timezone.utc),
                id_dspstv=dispositivo.id_dspstv,
                id_prmtr=mensaje.id_prmtr,
                id_sd=escenario["sede"].id_sd,
                vlr="Puerta Abierta",
            )
        )
        db_session.flush()

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            escenario["usuario"], "Cliente Final", escenario["sede"].id_sd
        )

        item = next(
            i for i in client.get("/mapa-cliente").json()["items"] if i["nmbr"] == "Estacion Asignada"
        )
        parametros = {p["parametro"]: p["valor"] for p in item["parametros"]}
        assert parametros["mensaje_puerta"] == "Puerta Abierta"


class TestSemaforoEnElEndpoint:
    def test_valor_en_rango_pinta_verde(self, client, db_session, escenario):
        dispositivo = crear_dispositivo(db_session, escenario["asignada"], escenario["sede"])
        temperatura = crear_parametro(db_session, "temperatura", "°C")
        agregar_lectura(
            db_session, dispositivo, temperatura, escenario["sede"], 20, dt.datetime.now(dt.timezone.utc)
        )

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            escenario["usuario"], "Cliente Final", escenario["sede"].id_sd
        )

        item = next(
            i for i in client.get("/mapa-cliente").json()["items"] if i["nmbr"] == "Estacion Asignada"
        )
        assert item["semaforo"] == "verde"

    def test_valor_fuera_de_rango_pinta_rojo(self, client, db_session, escenario):
        """Con los umbrales TEMPORALES de HU 28 simulada: >32 °C es rojo."""
        dispositivo = crear_dispositivo(db_session, escenario["asignada"], escenario["sede"])
        temperatura = crear_parametro(db_session, "temperatura", "°C")
        agregar_lectura(
            db_session, dispositivo, temperatura, escenario["sede"], 35, dt.datetime.now(dt.timezone.utc)
        )

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            escenario["usuario"], "Cliente Final", escenario["sede"].id_sd
        )

        item = next(
            i for i in client.get("/mapa-cliente").json()["items"] if i["nmbr"] == "Estacion Asignada"
        )
        assert item["semaforo"] == "rojo"
