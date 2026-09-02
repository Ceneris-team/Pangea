"""
HU50 CA4/CA5/CA6 - endpoints de columnas pendientes de asignación:

  GET  /mapeos/columnas-pendientes             listado (para el badge/popover)
  GET  /mapeos/columnas-pendientes/conteo      versión barata, solo el número
  POST /mapeos/columnas-pendientes/{id}/resolver   asigna un parámetro
  POST /mapeos/columnas-pendientes/{id}/ignorar    descarta la columna

Reutiliza los fixtures/helpers de test_mapeos.py (client, tecnico_editor,
crear_dispositivo) para no duplicar el boilerplate de sede/dispositivo.
"""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import MapeoColumna, MapeoColumnaPendiente, MapeoFormato, Parametro
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
    """Mismo fixture que test_mapeos.py: Técnico CENERIS con permiso de
    Edición sobre Ingesta en su sede, ya autenticado."""
    rol = fabrica.rol("Técnico CENERIS")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Ingesta", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )
    return sede, rol


@pytest.fixture()
def parametros(db_session):
    creados = []
    for nombre, unidad in [
        ("Temperatura HU50", "°C"),
        ("pH HU50", "pH"),
    ]:
        parametro = Parametro(nmbr=nombre, undd=unidad, dscrpcn="parámetro creado por los tests")
        db_session.add(parametro)
        creados.append(parametro)
    db_session.flush()
    return creados


def crear_pendiente(db_session, formato, indc_clmn=0, nombre="ColumnaSinMatch", estd="Pendiente"):
    pendiente = MapeoColumnaPendiente(
        id_mp=formato.id_mp,
        indc_clmn=indc_clmn,
        nmbr_clmn_orgn=nombre,
        estd=estd,
    )
    db_session.add(pendiente)
    db_session.flush()
    return pendiente


def crear_formato(db_session, dispositivo, tp_trm="Q"):
    formato = MapeoFormato(
        id_dspstv=dispositivo.id_dspstv,
        tp_trm=tp_trm,
        orgn_crcn="Automatico",
        dlmtdr=",",
        fl_inc_dts=2,
        frmt_fch="%Y-%m-%d %H:%M:%S",
    )
    db_session.add(formato)
    db_session.flush()
    return formato


class TestListarColumnasPendientes:
    def test_lista_solo_las_pendientes(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        formato = crear_formato(db_session, dispositivo)
        crear_pendiente(db_session, formato, indc_clmn=0, nombre="Pendiente1")
        crear_pendiente(db_session, formato, indc_clmn=1, nombre="YaResuelta", estd="Resuelta")
        crear_pendiente(db_session, formato, indc_clmn=2, nombre="Ignorada1", estd="Ignorada")

        resp = client.get("/mapeos/columnas-pendientes")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["nmbr_clmn_orgn"] == "Pendiente1"
        assert items[0]["dispositivo_nombre"] == dispositivo.nmbr
        assert items[0]["tp_trm"] == "Q"

    def test_filtro_por_dispositivo(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        disp_a = crear_dispositivo(db_session, sede, nombre="DispA-pendientes")
        disp_b = crear_dispositivo(db_session, sede, nombre="DispB-pendientes")
        formato_a = crear_formato(db_session, disp_a, tp_trm="A")
        formato_b = crear_formato(db_session, disp_b, tp_trm="B")
        crear_pendiente(db_session, formato_a, nombre="DeA")
        crear_pendiente(db_session, formato_b, nombre="DeB")

        resp = client.get(f"/mapeos/columnas-pendientes?id_dspstv={disp_a.id_dspstv}")
        items = resp.json()
        assert len(items) == 1
        assert items[0]["nmbr_clmn_orgn"] == "DeA"

    def test_usuario_de_otra_sede_no_ve_pendientes_ajenas(self, client, db_session, tecnico_editor, fabrica):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        formato = crear_formato(db_session, dispositivo)
        crear_pendiente(db_session, formato)

        otro_rol = fabrica.rol("Administrador")
        otra_sede = fabrica.sede()
        otro_usuario = fabrica.usuario(rol=otro_rol)
        agregar_permiso(db_session, otro_usuario, otra_sede, "Ingesta", "Lectura", otro_rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            otro_usuario, otro_rol.nmbr, sede_id=otra_sede.id_sd
        )

        resp = client.get("/mapeos/columnas-pendientes")
        assert resp.json() == []


class TestContarColumnasPendientes:
    def test_conteo_coincide_con_el_listado(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        formato = crear_formato(db_session, dispositivo)
        crear_pendiente(db_session, formato, indc_clmn=0, nombre="Uno")
        crear_pendiente(db_session, formato, indc_clmn=1, nombre="Dos")

        resp = client.get("/mapeos/columnas-pendientes/conteo")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_conteo_cero_sin_pendientes(self, client, db_session, tecnico_editor):
        resp = client.get("/mapeos/columnas-pendientes/conteo")
        assert resp.json()["total"] == 0


class TestResolverColumnaPendiente:
    def test_resuelve_y_crea_la_columna_real(self, client, db_session, tecnico_editor, parametros):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        formato = crear_formato(db_session, dispositivo)
        pendiente = crear_pendiente(db_session, formato, indc_clmn=3, nombre="ColX")

        resp = client.post(
            f"/mapeos/columnas-pendientes/{pendiente.id_mp_cl_pnd}/resolver",
            json={"id_prmtr": parametros[0].id_prmtr},
        )
        assert resp.status_code == 200

        db_session.refresh(pendiente)
        assert pendiente.estd == "Resuelta"
        assert pendiente.fch_resolucion is not None
        assert pendiente.id_usr_resolvio is not None

        columna = (
            db_session.query(MapeoColumna)
            .filter(MapeoColumna.id_mp == formato.id_mp, MapeoColumna.indc_clmn == 3)
            .first()
        )
        assert columna is not None
        assert columna.id_prmtr == parametros[0].id_prmtr

        # CA4: ya no debe aparecer en el listado de pendientes.
        assert client.get("/mapeos/columnas-pendientes/conteo").json()["total"] == 0

    def test_pendiente_inexistente_devuelve_404(self, client, tecnico_editor, parametros):
        resp = client.post(
            "/mapeos/columnas-pendientes/999999/resolver",
            json={"id_prmtr": parametros[0].id_prmtr},
        )
        assert resp.status_code == 404

    def test_ya_resuelta_devuelve_409(self, client, db_session, tecnico_editor, parametros):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        formato = crear_formato(db_session, dispositivo)
        pendiente = crear_pendiente(db_session, formato, estd="Resuelta")

        resp = client.post(
            f"/mapeos/columnas-pendientes/{pendiente.id_mp_cl_pnd}/resolver",
            json={"id_prmtr": parametros[0].id_prmtr},
        )
        assert resp.status_code == 409

    def test_parametro_inexistente_devuelve_422(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        formato = crear_formato(db_session, dispositivo)
        pendiente = crear_pendiente(db_session, formato)

        resp = client.post(
            f"/mapeos/columnas-pendientes/{pendiente.id_mp_cl_pnd}/resolver",
            json={"id_prmtr": 999999},
        )
        assert resp.status_code == 422

    def test_indice_ya_ocupado_devuelve_409(self, client, db_session, tecnico_editor, parametros):
        """Carrera con el PUT genérico de mapeos: alguien ya asignó ese
        índice por otra vía mientras la pendiente seguía abierta."""
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        formato = crear_formato(db_session, dispositivo)
        pendiente = crear_pendiente(db_session, formato, indc_clmn=0)
        db_session.add(
            MapeoColumna(id_mp=formato.id_mp, indc_clmn=0, id_prmtr=parametros[0].id_prmtr)
        )
        db_session.flush()

        resp = client.post(
            f"/mapeos/columnas-pendientes/{pendiente.id_mp_cl_pnd}/resolver",
            json={"id_prmtr": parametros[1].id_prmtr},
        )
        assert resp.status_code == 409

    def test_usuario_de_otra_sede_no_puede_resolver(
        self, client, db_session, tecnico_editor, parametros, fabrica
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        formato = crear_formato(db_session, dispositivo)
        pendiente = crear_pendiente(db_session, formato)

        otro_rol = fabrica.rol("Administrador")
        otra_sede = fabrica.sede()
        otro_usuario = fabrica.usuario(rol=otro_rol)
        agregar_permiso(db_session, otro_usuario, otra_sede, "Ingesta", "Edición", otro_rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            otro_usuario, otro_rol.nmbr, sede_id=otra_sede.id_sd
        )

        resp = client.post(
            f"/mapeos/columnas-pendientes/{pendiente.id_mp_cl_pnd}/resolver",
            json={"id_prmtr": parametros[0].id_prmtr},
        )
        assert resp.status_code == 403

    def test_denegado_con_permiso_de_solo_lectura(self, client, db_session, fabrica, parametros):
        rol = fabrica.rol("Técnico CENERIS")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Ingesta", "Lectura", rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )
        dispositivo = crear_dispositivo(db_session, sede)
        formato = crear_formato(db_session, dispositivo)
        pendiente = crear_pendiente(db_session, formato)

        resp = client.post(
            f"/mapeos/columnas-pendientes/{pendiente.id_mp_cl_pnd}/resolver",
            json={"id_prmtr": parametros[0].id_prmtr},
        )
        assert resp.status_code == 403


class TestIgnorarColumnaPendiente:
    def test_ignora_sin_crear_columna(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        formato = crear_formato(db_session, dispositivo)
        pendiente = crear_pendiente(db_session, formato, indc_clmn=7)

        resp = client.post(f"/mapeos/columnas-pendientes/{pendiente.id_mp_cl_pnd}/ignorar")
        assert resp.status_code == 200

        db_session.refresh(pendiente)
        assert pendiente.estd == "Ignorada"
        assert (
            db_session.query(MapeoColumna)
            .filter(MapeoColumna.id_mp == formato.id_mp, MapeoColumna.indc_clmn == 7)
            .count()
            == 0
        )
        assert client.get("/mapeos/columnas-pendientes/conteo").json()["total"] == 0

    def test_ya_ignorada_devuelve_409(self, client, db_session, tecnico_editor):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        formato = crear_formato(db_session, dispositivo)
        pendiente = crear_pendiente(db_session, formato, estd="Ignorada")

        resp = client.post(f"/mapeos/columnas-pendientes/{pendiente.id_mp_cl_pnd}/ignorar")
        assert resp.status_code == 409

    def test_pendiente_inexistente_devuelve_404(self, client, tecnico_editor):
        resp = client.post("/mapeos/columnas-pendientes/999999/ignorar")
        assert resp.status_code == 404
