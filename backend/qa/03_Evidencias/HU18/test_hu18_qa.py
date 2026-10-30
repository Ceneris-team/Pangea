"""
QA - HU18 Desactivar dispositivo (PP-189 acción con confirmación, PP-190
polling FTP, PP-191 historial de telemetría, PP-413 validación QA).

Ejecutar desde backend/ con la BD de test migrada:
    TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/pangea_test \
    venv/Scripts/python.exe -m pytest qa/03_Evidencias/HU18/test_hu18_qa.py \
        --html=qa/03_Evidencias/HU18/pytest_hu18.html --self-contained-html
"""

import datetime as dt
from unittest.mock import patch

import pytest

from app.main import app
from app.models import ArchivoIngesta, Dispositivo, Parametro, Telemetria, Usuario
from app.models.suscripcion import LimitePlan, PlanSuscripcion, Suscripcion
from app.security.dependencies import get_current_user
from app.tasks import ingesta as tareas_ingesta

# Fixtures y helpers del propio proyecto (mismo patrón que los tests de HU10/HU18).
from tests.conftest import _engine, db_session, fabrica  # noqa: F401
from tests.routers.test_dispositivos import (  # noqa: F401
    agregar_permiso,
    client,
    preparar_dispositivo,
    tecnico_editor,
    tecnico_lector,
    usuario_jwt,
)

MSG = "Dispositivo desactivado correctamente"


def con_suscripcion_vigente(db, sede):
    """Empresa con contrato Vigente y límites (si no, exigir_operacion da 409)."""
    plan = PlanSuscripcion(nmbr=f"Plan QA HU18 {sede.id_sd}", prc_mnsl=100)
    db.add(plan)
    db.flush()
    db.add(LimitePlan(id_pln=plan.id_pln, mx_sds=1, mx_ubccns=10, mx_dspstvs=10, mx_usrs=10))
    hoy = dt.date.today()
    db.add(
        Suscripcion(
            id_clnt=sede.id_clnt,
            id_pln=plan.id_pln,
            fch_inc=hoy - dt.timedelta(days=1),
            fch_vncmnt=hoy + dt.timedelta(days=30),
            estd="Activa",
        )
    )
    db.flush()


@pytest.fixture()
def operativo(db_session, tecnico_editor):
    """Técnico con Edición en una sede cuya empresa tiene suscripción vigente."""
    sede, rol = tecnico_editor
    con_suscripcion_vigente(db_session, sede)
    # Para consultar telemetría (PP-191) también necesita Lectura sobre Tableros.
    id_usr = int(app.dependency_overrides[get_current_user]()["sub"])
    usuario = db_session.get(Usuario, id_usr)
    agregar_permiso(db_session, usuario, sede, "Tableros", "Lectura", rol)
    return sede, rol


def sondear(db_session, nombres=("H_2026-10-28_00-00-00.dat",)):
    """Ejecuta el sondeo real de Celery contra la BD de test; el listado FTP
    se simula (test_integracion_ftp_real.py usa un FTP verdadero)."""
    with (
        patch.object(tareas_ingesta, "SessionLocal", return_value=db_session),
        patch.object(tareas_ingesta, "listar_archivos_dat", return_value=list(nombres)) as listar,
        patch.object(tareas_ingesta.procesar_archivo_dat, "delay"),
        patch.object(db_session, "close"),
    ):
        resultado = tareas_ingesta.sondear_conexiones_ftp()
    return resultado, listar


# --------------------------- CA1 / CA2 : API (PP-189) -----------------------


class TestDesactivarCA2:
    def test_cp_desactivar_activo_cambia_estado_y_mensaje(self, client, db_session, operativo):
        sede, _ = operativo
        d = preparar_dispositivo(db_session, sede)
        resp = client.delete(f"/dispositivos/{d.id_dspstv}")
        assert resp.status_code == 200
        assert resp.json()["mensaje"] == MSG
        db_session.refresh(d)
        assert d.estd == "Inactivo"

    def test_cp_no_elimina_la_fila(self, client, db_session, operativo):
        sede, _ = operativo
        d = preparar_dispositivo(db_session, sede)
        client.delete(f"/dispositivos/{d.id_dspstv}")
        assert db_session.get(Dispositivo, d.id_dspstv) is not None

    def test_cp_desactivar_ya_inactivo_409(self, client, db_session, operativo):
        sede, _ = operativo
        d = preparar_dispositivo(db_session, sede, estado="Inactivo")
        resp = client.delete(f"/dispositivos/{d.id_dspstv}")
        assert resp.status_code == 409
        assert "ya está inactivo" in resp.json()["detail"]

    def test_cp_desactivar_inexistente_404(self, client, operativo):
        assert client.delete("/dispositivos/999999").status_code == 404

    def test_cp_empresa_sin_suscripcion_vigente_409(self, client, db_session, tecnico_editor):
        """OBS: la regla comercial (exigir_operacion) bloquea la desactivación."""
        sede, _ = tecnico_editor
        d = preparar_dispositivo(db_session, sede)
        resp = client.delete(f"/dispositivos/{d.id_dspstv}")
        assert resp.status_code == 409
        assert "modo consulta" in resp.json()["detail"]
        db_session.refresh(d)
        assert d.estd == "Activo"


# --------------------------- CA3 : listado y Reactivar ----------------------


class TestListadoYReactivarCA3:
    def test_cp_listado_muestra_inactivo_y_filtra_por_estado(self, client, db_session, operativo):
        sede, _ = operativo
        d = preparar_dispositivo(db_session, sede, nombre="DESACT-01")
        preparar_dispositivo(db_session, sede, nombre="ACTIVO-02")
        client.delete(f"/dispositivos/{d.id_dspstv}")
        items = {i["nmbr"]: i["estd"] for i in client.get("/dispositivos").json()["items"]}
        assert items == {"DESACT-01": "Inactivo", "ACTIVO-02": "Activo"}
        solo = client.get("/dispositivos", params={"estado": "Inactivo"}).json()["items"]
        assert [i["nmbr"] for i in solo] == ["DESACT-01"]

    def test_cp_reactivar_vuelve_a_activo(self, client, db_session, operativo):
        sede, _ = operativo
        d = preparar_dispositivo(db_session, sede)
        client.delete(f"/dispositivos/{d.id_dspstv}")
        resp = client.post(f"/dispositivos/{d.id_dspstv}/reactivar")
        assert resp.status_code == 200
        db_session.refresh(d)
        assert d.estd == "Activo"

    def test_cp_reactivar_activo_409(self, client, db_session, operativo):
        sede, _ = operativo
        d = preparar_dispositivo(db_session, sede)
        assert client.post(f"/dispositivos/{d.id_dspstv}/reactivar").status_code == 409


# --------------------------- PP-190 : polling FTP ---------------------------


class TestPollingFTPPP190:
    def test_cp_control_dispositivo_activo_si_se_sondea(self, db_session, operativo):
        sede, _ = operativo
        d = preparar_dispositivo(db_session, sede)
        resultado, listar = sondear(db_session)
        assert listar.called
        assert resultado["encolados"] == 1
        assert db_session.query(ArchivoIngesta).filter_by(id_cnxn=d.id_cnxn).count() == 1

    def test_cp_dispositivo_desactivado_no_se_sondea(self, client, db_session, operativo):
        sede, _ = operativo
        d = preparar_dispositivo(db_session, sede)
        assert client.delete(f"/dispositivos/{d.id_dspstv}").status_code == 200
        resultado, listar = sondear(db_session)
        assert not listar.called, "el sondeo sigue conectándose al FTP del dispositivo desactivado"
        assert resultado["encolados"] == 0
        assert db_session.query(ArchivoIngesta).filter_by(id_cnxn=d.id_cnxn).count() == 0

    def test_cp_desactivar_uno_no_detiene_a_otro(self, client, db_session, operativo):
        sede, _ = operativo
        a = preparar_dispositivo(db_session, sede, nombre="A")
        b = preparar_dispositivo(db_session, sede, nombre="B")
        client.delete(f"/dispositivos/{a.id_dspstv}")
        sondear(db_session)
        assert db_session.query(ArchivoIngesta).filter_by(id_cnxn=b.id_cnxn).count() == 1

    def test_cp_reactivar_reanuda_el_sondeo(self, client, db_session, operativo):
        sede, _ = operativo
        d = preparar_dispositivo(db_session, sede)
        client.delete(f"/dispositivos/{d.id_dspstv}")
        client.post(f"/dispositivos/{d.id_dspstv}/reactivar")
        resultado, _ = sondear(db_session)
        assert resultado["encolados"] == 1


# --------------------------- PP-191 : historial de telemetría ---------------


class TestHistorialPP191:
    def _con_telemetria(self, db_session, d, sede, n=3):
        p = Parametro(nmbr=f"QA-HU18-{d.id_dspstv}", undd="u", dscrpcn="qa", tipo_dato="numerico")
        db_session.add(p)
        db_session.flush()
        ahora = dt.datetime.now(dt.timezone.utc)
        for i in range(n):
            db_session.add(
                Telemetria(
                    fch_hr=ahora - dt.timedelta(minutes=i),
                    id_dspstv=d.id_dspstv,
                    id_prmtr=p.id_prmtr,
                    id_sd=sede.id_sd,
                    vlr=10 + i,
                )
            )
        db_session.flush()
        return p

    def test_cp_telemetria_previa_se_conserva(self, client, db_session, operativo):
        sede, _ = operativo
        d = preparar_dispositivo(db_session, sede)
        self._con_telemetria(db_session, d, sede)
        client.delete(f"/dispositivos/{d.id_dspstv}")
        assert db_session.query(Telemetria).filter_by(id_dspstv=d.id_dspstv).count() == 3

    def test_cp_telemetria_sigue_consultable_por_api(self, client, db_session, operativo):
        sede, _ = operativo
        d = preparar_dispositivo(db_session, sede)
        p = self._con_telemetria(db_session, d, sede)
        client.delete(f"/dispositivos/{d.id_dspstv}")
        resp = client.get(
            "/mediciones", params={"dispositivo_ids": d.id_dspstv, "parametro_ids": p.id_prmtr}
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["items"]) == 3


# --------------------------- Roles y seguridad ------------------------------


class TestRolesYSeguridad:
    def _como(self, db_session, fabrica, rol_nombre, nivel):
        rol = fabrica.rol(rol_nombre)
        sede = fabrica.sede()
        con_suscripcion_vigente(db_session, sede)
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Dispositivos", nivel, rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )
        return sede

    @pytest.mark.parametrize("rol", ["Técnico CENERIS", "Administrador"])
    def test_cp_roles_autorizados_pueden_desactivar(self, client, db_session, fabrica, rol):
        sede = self._como(db_session, fabrica, rol, "Edición")
        d = preparar_dispositivo(db_session, sede)
        assert client.delete(f"/dispositivos/{d.id_dspstv}").status_code == 200

    @pytest.mark.parametrize("rol", ["Técnico CENERIS", "Administrador"])
    def test_cp_solo_lectura_no_puede_desactivar(self, client, db_session, fabrica, rol):
        sede = self._como(db_session, fabrica, rol, "Lectura")
        d = preparar_dispositivo(db_session, sede)
        assert client.delete(f"/dispositivos/{d.id_dspstv}").status_code == 403
        db_session.refresh(d)
        assert d.estd == "Activo"

    def test_cp_cliente_final_no_puede_desactivar(self, client, db_session, fabrica):
        sede = self._como(db_session, fabrica, "Cliente Final", "Lectura")
        d = preparar_dispositivo(db_session, sede)
        assert client.delete(f"/dispositivos/{d.id_dspstv}").status_code == 403

    def test_cp_sin_sesion_401(self, client, db_session, fabrica):
        sede = fabrica.sede()
        d = preparar_dispositivo(db_session, sede)
        app.dependency_overrides.pop(get_current_user, None)
        assert client.delete(f"/dispositivos/{d.id_dspstv}").status_code == 401

    def test_cp_no_puede_desactivar_dispositivo_de_otra_sede(
        self, client, db_session, operativo, fabrica
    ):
        ajena = fabrica.sede()
        con_suscripcion_vigente(db_session, ajena)
        d = preparar_dispositivo(db_session, ajena)
        assert client.delete(f"/dispositivos/{d.id_dspstv}").status_code in (403, 404)
