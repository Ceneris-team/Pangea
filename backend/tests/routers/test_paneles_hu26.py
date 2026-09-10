"""
HU26 - Añadir ubicaciones al panel.

  CA1  "Añadir ubicaciones" muestra el listado de ubicaciones disponibles
       asignadas a mi cuenta (HU21) que todavía no están en el panel
  CA2  "AGREGAR AL PANEL" asocia las seleccionadas y muestra el MSG
       "Ubicaciones añadidas correctamente"
  CA3  cada ubicación añadida aparece con su nombre y los últimos valores
       de telemetría disponibles
  CA4  "Quitar" retira la ubicación del panel y muestra el MSG
       "Ubicación retirada del panel"

Reusa los helpers y el fixture de autenticación de test_paneles.py (HU23-
25, mismo router) en vez de duplicarlos: mismo Cliente Final con Edición
sobre "Tableros" que crea/edita/borra paneles ahí.

Corre contra la Postgres real de test (ver tests/conftest.py).
"""

import datetime as dt

import pytest

from app.main import app
from app.models import (
    ConexionFTP,
    Dispositivo,
    MapeoColumna,
    MapeoFormato,
    PanelUbicacion,
    Parametro,
    PermisoUbicacion,
    Telemetria,
    Ubicacion,
)
from app.security.dependencies import get_current_user
from tests.routers.test_paneles import (
    agregar_permiso,
    client,  # noqa: F401 -reexportado como fixture
    cliente_con_edicion_tableros,
    crear_panel,
    crear_ubicacion,
    usuario_jwt,
)

__all__ = ["cliente_con_edicion_tableros", "client"]


def asignar_ubicacion(db, usuario_db, ubicacion):
    db.add(PermisoUbicacion(id_usr=usuario_db.id_usr, id_ubccn=ubicacion.id_ubccn))
    db.flush()


@pytest.fixture()
def escenario(db_session, cliente_con_edicion_tableros):
    """El Cliente Final de test_paneles.py, con DOS ubicaciones asignadas
    (HU21) y un panel propio ya creado."""
    usuario, sede = cliente_con_edicion_tableros
    ubicacion_a = crear_ubicacion(db_session, sede, nombre="Estación A")
    ubicacion_b = crear_ubicacion(db_session, sede, nombre="Estación B")
    asignar_ubicacion(db_session, usuario, ubicacion_a)
    asignar_ubicacion(db_session, usuario, ubicacion_b)
    panel = crear_panel(db_session, usuario, sede, "Mi panel")

    return {
        "usuario": usuario,
        "sede": sede,
        "ubicacion_a": ubicacion_a,
        "ubicacion_b": ubicacion_b,
        "panel": panel,
    }


class TestCA1ListadoDisponibles:
    def test_solo_muestra_las_asignadas_y_no_las_ya_agregadas(self, client, escenario):
        id_pnl = escenario["panel"].id_pnl
        client.post(
            f"/paneles/{id_pnl}/ubicaciones",
            json={"ids_ubccn": [escenario["ubicacion_a"].id_ubccn]},
        )

        resp = client.get(f"/paneles/{id_pnl}/ubicaciones-disponibles")
        assert resp.status_code == 200
        assert [u["nmbr"] for u in resp.json()["items"]] == ["Estación B"]

    def test_ubicacion_no_asignada_no_aparece(self, client, db_session, escenario):
        crear_ubicacion(db_session, escenario["sede"], nombre="Estación Ajena")

        resp = client.get(f"/paneles/{escenario['panel'].id_pnl}/ubicaciones-disponibles")
        nombres = {u["nmbr"] for u in resp.json()["items"]}
        assert nombres == {"Estación A", "Estación B"}

    def test_panel_ajeno_da_404(self, client, db_session, escenario, fabrica):
        rol = fabrica.rol("Cliente Final")
        otro = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, otro, escenario["sede"], "Tableros", "Edición", rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            otro, rol.nmbr, sede_id=escenario["sede"].id_sd
        )

        resp = client.get(f"/paneles/{escenario['panel'].id_pnl}/ubicaciones-disponibles")
        assert resp.status_code == 404


class TestCA2AgregarAlPanel:
    def test_agrega_las_seleccionadas_y_muestra_el_mensaje(self, client, db_session, escenario):
        id_pnl = escenario["panel"].id_pnl

        resp = client.post(
            f"/paneles/{id_pnl}/ubicaciones",
            json={
                "ids_ubccn": [
                    escenario["ubicacion_a"].id_ubccn,
                    escenario["ubicacion_b"].id_ubccn,
                ]
            },
        )
        assert resp.status_code == 200
        cuerpo = resp.json()
        assert cuerpo["mensaje"] == "Ubicaciones añadidas correctamente"
        assert {u["nmbr"] for u in cuerpo["panel"]["ubicaciones"]} == {"Estación A", "Estación B"}

        filas = db_session.query(PanelUbicacion).filter(PanelUbicacion.id_pnl == id_pnl).all()
        assert len(filas) == 2

    def test_una_misma_ubicacion_no_se_puede_agregar_dos_veces(self, client, escenario):
        id_pnl = escenario["panel"].id_pnl
        client.post(
            f"/paneles/{id_pnl}/ubicaciones",
            json={"ids_ubccn": [escenario["ubicacion_a"].id_ubccn]},
        )

        resp = client.post(
            f"/paneles/{id_pnl}/ubicaciones",
            json={"ids_ubccn": [escenario["ubicacion_a"].id_ubccn]},
        )
        assert resp.status_code == 422

    def test_ubicacion_no_asignada_da_403(self, client, db_session, escenario):
        ajena = crear_ubicacion(db_session, escenario["sede"], nombre="Estación Ajena")

        resp = client.post(
            f"/paneles/{escenario['panel'].id_pnl}/ubicaciones",
            json={"ids_ubccn": [ajena.id_ubccn]},
        )
        assert resp.status_code == 403

    def test_lista_vacia_es_rechazada(self, client, escenario):
        resp = client.post(
            f"/paneles/{escenario['panel'].id_pnl}/ubicaciones", json={"ids_ubccn": []}
        )
        assert resp.status_code == 422

    def test_panel_ajeno_da_404(self, client, db_session, escenario, fabrica):
        rol = fabrica.rol("Cliente Final")
        otro = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, otro, escenario["sede"], "Tableros", "Edición", rol)
        asignar_ubicacion(db_session, otro, escenario["ubicacion_a"])
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            otro, rol.nmbr, sede_id=escenario["sede"].id_sd
        )

        resp = client.post(
            f"/paneles/{escenario['panel'].id_pnl}/ubicaciones",
            json={"ids_ubccn": [escenario["ubicacion_a"].id_ubccn]},
        )
        assert resp.status_code == 404

    def test_otro_rol_con_edicion_no_puede_agregar(self, client, db_session, escenario, fabrica):
        """Mismo criterio que crear_panel/actualizar_panel: Edición sobre
        'Tableros' no alcanza, hace falta ser Cliente Final."""
        rol_tecnico = fabrica.rol("Técnico CENERIS")
        tecnico = fabrica.usuario(rol=rol_tecnico)
        agregar_permiso(db_session, tecnico, escenario["sede"], "Tableros", "Edición", rol_tecnico)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            tecnico, rol_tecnico.nmbr, sede_id=escenario["sede"].id_sd, scope="global"
        )

        resp = client.post(
            f"/paneles/{escenario['panel'].id_pnl}/ubicaciones",
            json={"ids_ubccn": [escenario["ubicacion_a"].id_ubccn]},
        )
        assert resp.status_code == 403


def _mapear_parametro_con_lectura(db_session, ubicacion, sede, valor=23.5):
    """Deja UNA lectura de telemetría reciente en `ubicacion`, para CA3."""
    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr=f"Conexion de {ubicacion.nmbr}",
        hst="127.0.0.1",
        usr_ftp="usr",
        rt_rmt="/data",
        crdncl_cfrd="cifrado-de-prueba",
    )
    db_session.add(conexion)
    db_session.flush()

    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn,
        id_cnxn=conexion.id_cnxn,
        nmbr=f"Datalogger {ubicacion.nmbr}",
        mrc="Campbell",
        lttd=0,
        lngtd=0,
    )
    db_session.add(dispositivo)
    db_session.flush()

    parametro = Parametro(
        nmbr=f"nivel_panel_hu26_{ubicacion.id_ubccn}", undd="m", tipo_dato="numerico"
    )
    db_session.add(parametro)
    db_session.flush()

    formato = MapeoFormato(
        id_dspstv=dispositivo.id_dspstv,
        tp_trm="H",
        dlmtdr=",",
        fl_inc_dts=1,
        frmt_fch="%Y-%m-%d %H:%M:%S",
        estd="Activo",
    )
    db_session.add(formato)
    db_session.flush()
    db_session.add(MapeoColumna(id_mp=formato.id_mp, indc_clmn=1, id_prmtr=parametro.id_prmtr))
    db_session.flush()

    db_session.add(
        Telemetria(
            fch_hr=dt.datetime.now(dt.timezone.utc),
            id_dspstv=dispositivo.id_dspstv,
            id_prmtr=parametro.id_prmtr,
            id_sd=sede.id_sd,
            vlr=valor,
        )
    )
    db_session.flush()
    return parametro


class TestCA3VistaConTelemetria:
    def test_ubicacion_agregada_aparece_con_su_ultimo_valor(self, client, db_session, escenario):
        _mapear_parametro_con_lectura(
            db_session, escenario["ubicacion_a"], escenario["sede"], valor=23.5
        )
        id_pnl = escenario["panel"].id_pnl
        client.post(
            f"/paneles/{id_pnl}/ubicaciones",
            json={"ids_ubccn": [escenario["ubicacion_a"].id_ubccn]},
        )

        resp = client.get(f"/paneles/{id_pnl}")
        assert resp.status_code == 200
        ubicacion = resp.json()["ubicaciones"][0]
        assert ubicacion["nmbr"] == "Estación A"
        assert len(ubicacion["parametros"]) == 1
        assert ubicacion["parametros"][0]["valor"] == 23.5

    def test_ubicacion_sin_telemetria_aparece_sin_parametros(self, client, escenario):
        id_pnl = escenario["panel"].id_pnl
        client.post(
            f"/paneles/{id_pnl}/ubicaciones",
            json={"ids_ubccn": [escenario["ubicacion_a"].id_ubccn]},
        )

        resp = client.get(f"/paneles/{id_pnl}")
        assert resp.json()["ubicaciones"][0]["parametros"] == []


class TestCA4QuitarUbicacion:
    def test_quitar_retira_del_panel_y_muestra_el_mensaje(self, client, db_session, escenario):
        id_pnl = escenario["panel"].id_pnl
        client.post(
            f"/paneles/{id_pnl}/ubicaciones",
            json={"ids_ubccn": [escenario["ubicacion_a"].id_ubccn]},
        )

        resp = client.delete(f"/paneles/{id_pnl}/ubicaciones/{escenario['ubicacion_a'].id_ubccn}")
        assert resp.status_code == 200
        assert resp.json()["mensaje"] == "Ubicación retirada del panel"
        assert resp.json()["panel"]["ubicaciones"] == []

        assert db_session.query(PanelUbicacion).filter(PanelUbicacion.id_pnl == id_pnl).count() == 0

    def test_quitar_no_borra_la_ubicacion_del_sistema(self, client, db_session, escenario):
        id_pnl = escenario["panel"].id_pnl
        client.post(
            f"/paneles/{id_pnl}/ubicaciones",
            json={"ids_ubccn": [escenario["ubicacion_a"].id_ubccn]},
        )
        client.delete(f"/paneles/{id_pnl}/ubicaciones/{escenario['ubicacion_a'].id_ubccn}")

        assert db_session.get(Ubicacion, escenario["ubicacion_a"].id_ubccn) is not None

    def test_quitar_ubicacion_que_no_esta_en_el_panel_da_404(self, client, escenario):
        resp = client.delete(
            f"/paneles/{escenario['panel'].id_pnl}/ubicaciones/{escenario['ubicacion_a'].id_ubccn}"
        )
        assert resp.status_code == 404
