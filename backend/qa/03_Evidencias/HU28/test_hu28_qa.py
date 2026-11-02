"""
QA HU-28 Crear alarma: casos propios de QA (CA, errores y bordes).
Reutiliza fixtures y helpers de tests/routers/test_alarmas.py (rama fabio).
Se copia a backend/tests/routers/ del worktree de fabio para ejecutarse.
"""
import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Alarma, CondicionAlarma
from tests.routers.test_alarmas import (  # noqa: F401
    client,
    cuerpo_valido,
    escenario,
    crear_parametro,
    crear_ubicacion,
    mapear_parametro,
    crear_dispositivo,
    crear_conexion,
)

NOMBRE_SQL = "'; DROP TABLE alrm;--"


class TestCA1Formulario:
    def test_CP01_parametros_sin_ubicacion_traen_los_de_ubicaciones_asignadas(self, client, escenario):
        r = client.get("/alarmas/parametros")
        assert r.status_code == 200
        ids = [p["id_prmtr"] for p in r.json()["items"]]
        assert escenario["parametro"].id_prmtr in ids

    def test_CP02_parametro_de_ubicacion_ajena_no_se_ofrece(self, client, db_session, escenario):
        ajena = crear_ubicacion(db_session, escenario["sede"], "Ajena QA")
        conexion = crear_conexion(db_session, escenario["sede"], "DL ajeno QA")
        disp = crear_dispositivo(db_session, ajena, conexion, "Disp ajeno QA")
        p = crear_parametro(db_session, "Param ajeno QA", "x")
        mapear_parametro(db_session, disp, p)
        ids = [i["id_prmtr"] for i in client.get("/alarmas/parametros").json()["items"]]
        assert p.id_prmtr not in ids

    def test_CP03_ubicacion_ajena_no_aparece_en_selector(self, client, db_session, escenario):
        ajena = crear_ubicacion(db_session, escenario["sede"], "Ajena selector QA")
        ids = [u["id_ubccn"] for u in client.get("/alarmas/ubicaciones").json()["items"]]
        assert ajena.id_ubccn not in ids
        assert escenario["ubicacion"].id_ubccn in ids


class TestCA3Guardar:
    def test_CP10_guardar_devuelve_201_mensaje_y_estado_activa(self, client, db_session, escenario):
        r = client.post("/alarmas", json=cuerpo_valido(escenario))
        assert r.status_code == 201
        assert r.json()["mensaje"] == "Alarma creada correctamente"
        a = db_session.query(Alarma).filter(Alarma.id_alrm == r.json()["alarma"]["id_alrm"]).one()
        assert a.estd == "Activa"

    def test_CP11_alarma_aparece_en_listado(self, client, escenario):
        client.post("/alarmas", json=cuerpo_valido(escenario, nmbr="Alarma listado QA"))
        items = client.get("/alarmas").json()["items"]
        assert any(i["nmbr"] == "Alarma listado QA" for i in items)

    def test_CP12_condicion_del_paso2_queda_guardada(self, client, db_session, escenario):
        r = client.post(
            "/alarmas", json=cuerpo_valido(escenario, condiciones=[{"oprdr": "<=", "vlr_umbrl": 1.25}])
        )
        c = (
            db_session.query(CondicionAlarma)
            .filter(CondicionAlarma.id_alrm == r.json()["alarma"]["id_alrm"])
            .all()
        )
        assert len(c) == 1 and c[0].oprdr == "<=" and float(c[0].vlr_umbrl) == 1.25

    def test_CP13_nombre_con_espacios_laterales_se_recorta(self, client, escenario):
        r = client.post("/alarmas", json=cuerpo_valido(escenario, nmbr="  Nivel alto  "))
        assert r.status_code == 201
        assert r.json()["alarma"]["nmbr"] == "Nivel alto"

    @pytest.mark.parametrize("op", [">", ">=", "<", "<=", "="])
    def test_CP14_todos_los_operadores_admitidos(self, client, escenario, op):
        r = client.post(
            "/alarmas", json=cuerpo_valido(escenario, condiciones=[{"oprdr": op, "vlr_umbrl": 2}])
        )
        assert r.status_code == 201

    @pytest.mark.xfail(reason="OBS-36: la API crea la alarma sin condiciones; decide el PO (HU-29)")
    def test_CP15_guardar_sin_condicion_es_rechazado(self, client, escenario):
        """CA3: 'he completado la configuración de condiciones'. Sin condición no debería crearse."""
        r = client.post("/alarmas", json=cuerpo_valido(escenario, condiciones=[]))
        assert r.status_code == 422


class TestErroresNombre:
    @pytest.mark.parametrize(
        "nombre", ["", "   ", None, "<script>alert(1)</script>", NOMBRE_SQL, "😀😀", "###"]
    )
    def test_CP20_nombres_invalidos_rechazados(self, client, escenario, nombre):
        r = client.post("/alarmas", json=cuerpo_valido(escenario, nmbr=nombre))
        assert r.status_code == 422

    def test_CP21_nombre_100_acepta_y_101_rechaza(self, client, escenario):
        assert client.post("/alarmas", json=cuerpo_valido(escenario, nmbr="B" * 100)).status_code == 201
        assert client.post("/alarmas", json=cuerpo_valido(escenario, nmbr="B" * 101)).status_code == 422

    def test_CP22_nombre_con_tildes_y_enie(self, client, escenario):
        assert (
            client.post("/alarmas", json=cuerpo_valido(escenario, nmbr="Caudal Ñandú 2 río")).status_code
            == 201
        )

    @pytest.mark.xfail(reason="OBS-35: el nombre admite signos ademas de alfanumericos; decide el PO")
    def test_CP23_nombre_con_signos_estrictamente_alfanumerico(self, client, escenario):
        """La HU dice 'texto alfanumérico'. El backend admite además . , ; : _ ( ) - / (ver OBS)."""
        r = client.post("/alarmas", json=cuerpo_valido(escenario, nmbr="Nivel (río) 1/2"))
        assert r.status_code == 422


class TestErroresCampos:
    def test_CP30_falta_parametro(self, client, escenario):
        c = cuerpo_valido(escenario)
        del c["id_prmtr"]
        assert client.post("/alarmas", json=c).status_code == 422

    def test_CP31_falta_ubicacion(self, client, escenario):
        c = cuerpo_valido(escenario)
        del c["id_ubccn"]
        assert client.post("/alarmas", json=c).status_code == 422

    def test_CP32_falta_nombre(self, client, escenario):
        c = cuerpo_valido(escenario)
        del c["nmbr"]
        assert client.post("/alarmas", json=c).status_code == 422

    def test_CP33_parametro_inexistente(self, client, escenario):
        assert client.post("/alarmas", json=cuerpo_valido(escenario, id_prmtr=99999999)).status_code == 422

    def test_CP34_ubicacion_inexistente_no_da_500(self, client, escenario):
        assert client.post("/alarmas", json=cuerpo_valido(escenario, id_ubccn=99999999)).status_code in (
            403,
            422,
        )

    def test_CP35_ubicacion_no_asignada_403(self, client, db_session, escenario):
        a = crear_ubicacion(db_session, escenario["sede"], "No asignada QA")
        assert client.post("/alarmas", json=cuerpo_valido(escenario, id_ubccn=a.id_ubccn)).status_code == 403

    def test_CP36_parametro_texto_no_monitoreable(self, client, db_session, escenario):
        p = crear_parametro(db_session, "Estado texto QA", "-", tipo_dato="texto")
        assert client.post("/alarmas", json=cuerpo_valido(escenario, id_prmtr=p.id_prmtr)).status_code == 422

    def test_CP37_umbral_no_numerico(self, client, escenario):
        r = client.post(
            "/alarmas", json=cuerpo_valido(escenario, condiciones=[{"oprdr": ">", "vlr_umbrl": "abc"}])
        )
        assert r.status_code == 422

    def test_CP38_operador_invalido(self, client, escenario):
        r = client.post(
            "/alarmas", json=cuerpo_valido(escenario, condiciones=[{"oprdr": "!=", "vlr_umbrl": 1}])
        )
        assert r.status_code == 422

    def test_CP39_tipos_incorrectos_en_ids(self, client, escenario):
        assert client.post("/alarmas", json=cuerpo_valido(escenario, id_prmtr="x")).status_code == 422


class TestAcceso:
    def test_CP40_sin_sesion_no_autorizado(self, db_session):
        app.dependency_overrides.clear()
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            c = TestClient(app)
            assert c.post("/alarmas", json={"nmbr": "x"}).status_code in (401, 403)
            assert c.get("/alarmas/ubicaciones").status_code in (401, 403)
            assert c.get("/alarmas/parametros").status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()


class TestCA4Cancelar:
    def test_CP50_cancelar_no_crea_registros(self, client, db_session, escenario):
        antes = db_session.query(Alarma).count()
        client.get("/alarmas/ubicaciones")
        client.get("/alarmas/parametros")
        assert db_session.query(Alarma).count() == antes

    def test_CP51_alta_rechazada_no_deja_alarma_huerfana(self, client, db_session, escenario):
        antes = db_session.query(Alarma).count()
        client.post(
            "/alarmas", json=cuerpo_valido(escenario, condiciones=[{"oprdr": "!=", "vlr_umbrl": 1}])
        )
        assert db_session.query(Alarma).count() == antes
