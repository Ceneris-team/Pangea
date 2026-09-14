"""HU51 CA3/CA4/CA5 - endpoints del catálogo de parámetros:

  GET  /parametros?estd=Pendiente de revision  listado filtrado (CA3)
  POST /parametros/{id}/activar                revisar y activar   (CA4)
  POST /parametros/{id}/fusionar               fusionar con otro   (CA5)

Reutiliza los fixtures/helpers de test_mapeos.py, igual que
test_mapeos_columnas_pendientes.py.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (
    Alarma,
    MapeoColumna,
    MapeoFormato,
    Parametro,
    Telemetria,
)
from app.security.dependencies import get_current_user
from tests.routers.test_mapeos import agregar_permiso, crear_dispositivo, usuario_jwt


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def tecnico_editor(db_session, fabrica):
    rol = fabrica.rol("Técnico CENERIS")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Ingesta", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )
    return sede, rol


def crear_parametro_automatico(db_session, nombre="auto_hu51", tipo_dato="numerico"):
    """Simula lo que dejó el motor de ingesta al auto-crear (HU51 CA1)."""
    parametro = Parametro(
        nmbr=nombre,
        undd="-",
        dscrpcn="Parametro auto-creado (HU51)",
        tipo_dato=tipo_dato,
        estd="Pendiente de revision",
        orgn_crcn="Automatico",
    )
    db_session.add(parametro)
    db_session.flush()
    return parametro


class TestListadoCA3:
    def test_filtra_por_pendientes_de_revision(self, client, db_session, tecnico_editor):
        crear_parametro_automatico(db_session, "pendiente_hu51")
        db_session.add(Parametro(nmbr="activo_hu51", undd="m"))
        db_session.flush()

        resp = client.get("/parametros", params={"estd": "Pendiente de revision"})

        assert resp.status_code == 200
        nombres = [p["nmbr"] for p in resp.json()]
        assert "pendiente_hu51" in nombres
        assert "activo_hu51" not in nombres

    def test_expone_estado_y_origen(self, client, db_session, tecnico_editor):
        crear_parametro_automatico(db_session, "con_origen_hu51")

        resp = client.get("/parametros", params={"estd": "Pendiente de revision"})

        item = next(p for p in resp.json() if p["nmbr"] == "con_origen_hu51")
        assert item["estd"] == "Pendiente de revision"
        assert item["orgn_crcn"] == "Automatico"

    def test_los_fusionados_nunca_aparecen(self, client, db_session, tecnico_editor):
        """CA5: un fusionado no debe volver a aparecer en NINGÚN selector,
        ni siquiera pidiendo el listado completo sin filtro."""
        db_session.add(
            Parametro(nmbr="fusionado_listado_hu51", undd="m", estd="Fusionado")
        )
        db_session.flush()

        resp = client.get("/parametros")

        nombres = [p["nmbr"] for p in resp.json()]
        assert "fusionado_listado_hu51" not in nombres


class TestActivarCA4:
    def test_activar_cambia_estado_y_permite_editar_nombre_y_unidad(
        self, client, db_session, tecnico_editor
    ):
        parametro = crear_parametro_automatico(db_session, "Temp_cruda_hu51")

        resp = client.post(
            f"/parametros/{parametro.id_prmtr}/activar",
            json={"nmbr": "Temperatura ambiente", "undd": "°C"},
        )

        assert resp.status_code == 200, resp.text
        cuerpo = resp.json()
        assert cuerpo["nmbr"] == "Temperatura ambiente"
        assert cuerpo["undd"] == "°C"
        assert cuerpo["estd"] == "Activo"

    def test_orgn_crcn_se_mantiene_en_automatico_tras_activar(
        self, client, db_session, tecnico_editor
    ):
        """CA4, verificación explícita: orgn_crcn es HISTORIAL de origen.
        Que un humano lo revise y lo active no cambia el hecho de que lo
        creó el motor de ingesta; resetearlo a 'Manual' haría imposible
        auditar después qué parte del catálogo nació automáticamente."""
        parametro = crear_parametro_automatico(db_session, "mantiene_origen_hu51")

        resp = client.post(
            f"/parametros/{parametro.id_prmtr}/activar",
            json={"nmbr": "Nombre Revisado", "undd": "m"},
        )

        assert resp.status_code == 200
        assert resp.json()["orgn_crcn"] == "Automatico"
        db_session.refresh(parametro)
        assert parametro.orgn_crcn == "Automatico"
        assert parametro.estd == "Activo"

    def test_activar_con_nombre_ya_usado_devuelve_409(
        self, client, db_session, tecnico_editor
    ):
        db_session.add(Parametro(nmbr="ya_tomado_hu51", undd="m"))
        parametro = crear_parametro_automatico(db_session, "a_renombrar_hu51")
        db_session.flush()

        resp = client.post(
            f"/parametros/{parametro.id_prmtr}/activar",
            json={"nmbr": "ya_tomado_hu51"},
        )

        assert resp.status_code == 409
        assert "Fusionar" in resp.json()["detail"]

    def test_activar_inexistente_devuelve_404(self, client, tecnico_editor):
        resp = client.post("/parametros/99999999/activar", json={"undd": "m"})
        assert resp.status_code == 404

    def test_puede_corregir_el_tipo_de_dato(self, client, db_session, tecnico_editor):
        """El tipo se infiere de los datos al auto-crear, pero puede
        haberse inferido con una muestra poco representativa."""
        parametro = crear_parametro_automatico(
            db_session, "tipo_corregible_hu51", tipo_dato="texto"
        )

        resp = client.post(
            f"/parametros/{parametro.id_prmtr}/activar",
            json={"undd": "m", "tipo_dato": "numerico"},
        )

        assert resp.status_code == 200
        assert resp.json()["tipo_dato"] == "numerico"


class TestFusionarCA5:
    def _preparar_telemetria(self, db_session, fabrica_sede, parametro, cantidad=3):
        dispositivo = crear_dispositivo(db_session, fabrica_sede)
        formato = MapeoFormato(
            id_dspstv=dispositivo.id_dspstv,
            tp_trm="F",
            dlmtdr=",",
            dlmtdr_dcml=".",
            fl_inc_dts=1,
            frmt_fch="%Y-%m-%d %H:%M:%S",
            estd="Activo",
        )
        db_session.add(formato)
        db_session.flush()
        db_session.add(
            MapeoColumna(id_mp=formato.id_mp, indc_clmn=1, id_prmtr=parametro.id_prmtr)
        )
        base = dt.datetime(2026, 9, 2, 10, 0, tzinfo=dt.timezone.utc)
        for i in range(cantidad):
            db_session.add(
                Telemetria(
                    fch_hr=base + dt.timedelta(minutes=i),
                    id_dspstv=dispositivo.id_dspstv,
                    id_prmtr=parametro.id_prmtr,
                    id_sd=fabrica_sede.id_sd,
                    vlr=10 + i,
                )
            )
        db_session.flush()
        return dispositivo, formato

    def test_fusion_reasigna_telemetria_y_mapeos(self, client, db_session, tecnico_editor):
        """CA5: TODOS los registros históricos pasan al destino, y los
        mapeos también -para que los archivos FUTUROS vayan directo al
        destino sin recrear el pendiente-."""
        sede, _ = tecnico_editor
        origen = crear_parametro_automatico(db_session, "temp_dup_hu51")
        destino = Parametro(nmbr="temperatura_buena_hu51", undd="°C")
        db_session.add(destino)
        db_session.flush()
        _dispositivo, formato = self._preparar_telemetria(db_session, sede, origen, cantidad=3)

        resp = client.post(
            f"/parametros/{origen.id_prmtr}/fusionar",
            json={"id_prmtr_destino": destino.id_prmtr},
        )

        assert resp.status_code == 200, resp.text
        # Sin pérdida de datos: las 3 lecturas ahora son del destino.
        assert (
            db_session.query(Telemetria)
            .filter(Telemetria.id_prmtr == destino.id_prmtr)
            .count()
            == 3
        )
        assert (
            db_session.query(Telemetria)
            .filter(Telemetria.id_prmtr == origen.id_prmtr)
            .count()
            == 0
        )
        # Y el mapeo de columna también quedó apuntando al destino.
        columna = (
            db_session.query(MapeoColumna).filter(MapeoColumna.id_mp == formato.id_mp).one()
        )
        assert columna.id_prmtr == destino.id_prmtr

    def test_origen_queda_fusionado_y_no_reutilizable(
        self, client, db_session, tecnico_editor
    ):
        origen = crear_parametro_automatico(db_session, "a_fusionar_hu51")
        destino = Parametro(nmbr="destino_hu51", undd="m")
        db_session.add(destino)
        db_session.flush()

        client.post(
            f"/parametros/{origen.id_prmtr}/fusionar",
            json={"id_prmtr_destino": destino.id_prmtr},
        )

        db_session.refresh(origen)
        assert origen.estd == "Fusionado"
        assert origen.id_prmtr_fusionado_en == destino.id_prmtr
        # No aparece en el listado (ningún selector puede volver a usarlo).
        nombres = [p["nmbr"] for p in client.get("/parametros").json()]
        assert "a_fusionar_hu51" not in nombres

    def test_fusionar_dos_veces_devuelve_409(self, client, db_session, tecnico_editor):
        origen = crear_parametro_automatico(db_session, "doble_fusion_hu51")
        destino = Parametro(nmbr="destino_doble_hu51", undd="m")
        db_session.add(destino)
        db_session.flush()

        primera = client.post(
            f"/parametros/{origen.id_prmtr}/fusionar",
            json={"id_prmtr_destino": destino.id_prmtr},
        )
        assert primera.status_code == 200

        segunda = client.post(
            f"/parametros/{origen.id_prmtr}/fusionar",
            json={"id_prmtr_destino": destino.id_prmtr},
        )
        assert segunda.status_code == 409

    def test_no_se_puede_fusionar_consigo_mismo(self, client, db_session, tecnico_editor):
        parametro = crear_parametro_automatico(db_session, "solo_hu51")

        resp = client.post(
            f"/parametros/{parametro.id_prmtr}/fusionar",
            json={"id_prmtr_destino": parametro.id_prmtr},
        )

        assert resp.status_code == 422

    def test_destino_inexistente_devuelve_404(self, client, db_session, tecnico_editor):
        origen = crear_parametro_automatico(db_session, "sin_destino_hu51")

        resp = client.post(
            f"/parametros/{origen.id_prmtr}/fusionar",
            json={"id_prmtr_destino": 99999999},
        )

        assert resp.status_code == 404

    def test_no_se_puede_fusionar_contra_un_fusionado(
        self, client, db_session, tecnico_editor
    ):
        origen = crear_parametro_automatico(db_session, "origen_x_hu51")
        ya_fusionado = Parametro(nmbr="destino_muerto_hu51", undd="m", estd="Fusionado")
        db_session.add(ya_fusionado)
        db_session.flush()

        resp = client.post(
            f"/parametros/{origen.id_prmtr}/fusionar",
            json={"id_prmtr_destino": ya_fusionado.id_prmtr},
        )

        assert resp.status_code == 409

    def test_activar_un_fusionado_devuelve_409(self, client, db_session, tecnico_editor):
        """Un fusionado no debe poder revivir por la puerta de atrás."""
        fusionado = Parametro(nmbr="revivir_hu51", undd="m", estd="Fusionado")
        db_session.add(fusionado)
        db_session.flush()

        resp = client.post(
            f"/parametros/{fusionado.id_prmtr}/activar", json={"undd": "m"}
        )

        assert resp.status_code == 409
