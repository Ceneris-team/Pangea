"""
HU 30 - Configurar notificaciones (PP-75). PP-232: activar el canal de
correo con destinatarios.

  CA1  el panel muestra los canales disponibles y los destinatarios
  CA2  activar el canal y GUARDAR persiste y devuelve
       "Notificaciones configuradas correctamente"
  CA4  desactivar el canal y GUARDAR hace que deje de notificar

El canal es alrm.cnl_crr_actv (migración a75n20261119). Corre contra la
Postgres real de test (ver conftest.py).
"""

from datetime import datetime, timezone
from decimal import Decimal

from app.models import DestinatarioAlarma, NotificacionEnviada, Suscripcion
from app.models.alarma import Alarma, EstadoAlarma
from app.models.suscripcion import PermisoUsuarioSede
from app.routers.alarmas import MENSAJE_NOTIFICACIONES
from tests.routers import test_alarmas as base
from tests.services import test_notificaciones_ses as ses

client = base.client
escenario = base.escenario
crear_alarma = base.crear_alarma
cuerpo_valido = base.cuerpo_valido
caso = ses.caso
aislar_destinatario_pruebas = ses.aislar_destinatario_pruebas


def crear_por_api(client, escenario, **extra):
    resp = client.post("/alarmas", json=cuerpo_valido(escenario, **extra))
    assert resp.status_code == 201, resp.text
    return resp.json()["alarma"]["id_alrm"]


def correos(db, id_alarma):
    return sorted(
        d.crr for d in db.query(DestinatarioAlarma).filter_by(id_alrm=id_alarma, cnl="email").all()
    )


class TestCA1Panel:
    def test_muestra_canales_y_destinatarios(self, client, escenario):
        id_alarma = crear_por_api(
            client, escenario, destinatarios=["ops@example.com", "jefe@example.com"]
        )
        resp = client.get(f"/alarmas/{id_alarma}/notificaciones")
        assert resp.status_code == 200
        panel = resp.json()
        assert panel["canal_email_activo"] is True
        assert [(c["canal"], c["disponible"], c["activo"]) for c in panel["canales"]] == [
            ("email", True, True),
            ("telegram", False, False),
        ]
        assert [d["correo"] for d in panel["destinatarios"]] == [
            "jefe@example.com",
            "ops@example.com",
        ]
        assert panel["correo_cuenta"] == escenario["usuario"].crr.lower()

    def test_alarma_nueva_queda_con_el_canal_activo(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario)
        assert db_session.get(Alarma, id_alarma).cnl_crr_actv is True

    def test_otro_autor_es_visible_y_otro_proyecto_o_inexistente_es_404(
        self, client, db_session, escenario, fabrica
    ):
        ajena = crear_alarma(db_session, escenario, "Ajena", usuario=fabrica.usuario())
        assert client.get(f"/alarmas/{ajena.id_alrm}/notificaciones").status_code == 200
        fuera = base.crear_ubicacion(db_session, escenario["sede"], "Proyecto no asignado")
        ajena.id_ubccn = fuera.id_ubccn
        db_session.flush()
        assert client.get(f"/alarmas/{ajena.id_alrm}/notificaciones").status_code == 404
        assert client.get("/alarmas/999999/notificaciones").status_code == 404


class TestCA2Activar:
    def test_activar_sin_destinatarios_agrega_el_correo_de_la_cuenta(
        self, client, db_session, escenario
    ):
        id_alarma = crear_por_api(client, escenario)
        client.put(f"/alarmas/{id_alarma}/notificaciones", json={"canal_email_activo": False})
        assert correos(db_session, id_alarma) == []

        resp = client.put(f"/alarmas/{id_alarma}/notificaciones", json={"canal_email_activo": True})
        assert resp.status_code == 200
        assert resp.json()["mensaje"] == MENSAJE_NOTIFICACIONES
        assert resp.json()["notificaciones"]["canal_email_activo"] is True
        assert correos(db_session, id_alarma) == [escenario["usuario"].crr.lower()]

    def test_activar_con_destinatarios_no_agrega_la_cuenta(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario, destinatarios=["ops@example.com"])
        client.put(f"/alarmas/{id_alarma}/notificaciones", json={"canal_email_activo": False})
        client.put(f"/alarmas/{id_alarma}/notificaciones", json={"canal_email_activo": True})
        assert correos(db_session, id_alarma) == ["ops@example.com"]

    def test_guardar_dos_veces_es_idempotente(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario)
        for _ in range(2):
            resp = client.put(
                f"/alarmas/{id_alarma}/notificaciones", json={"canal_email_activo": True}
            )
            assert resp.status_code == 200
        assert correos(db_session, id_alarma) == [escenario["usuario"].crr.lower()]

    def test_valor_no_booleano_es_422(self, client, escenario):
        id_alarma = crear_por_api(client, escenario)
        for cuerpo in ({"canal_email_activo": "si"}, {"canal_email_activo": 1}, {}):
            resp = client.put(f"/alarmas/{id_alarma}/notificaciones", json=cuerpo)
            assert resp.status_code == 422, cuerpo


class TestCA4Desactivar:
    def test_desactivar_conserva_los_destinatarios(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario, destinatarios=["ops@example.com"])
        resp = client.put(
            f"/alarmas/{id_alarma}/notificaciones", json={"canal_email_activo": False}
        )
        assert resp.status_code == 200
        assert resp.json()["mensaje"] == MENSAJE_NOTIFICACIONES
        panel = resp.json()["notificaciones"]
        assert panel["canal_email_activo"] is False
        assert panel["canales"][0]["activo"] is False
        assert [d["correo"] for d in panel["destinatarios"]] == ["ops@example.com"]
        assert db_session.get(Alarma, id_alarma).cnl_crr_actv is False

    def test_reactivar_reinicia_la_evaluacion(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario, destinatarios=["ops@example.com"])
        client.put(f"/alarmas/{id_alarma}/notificaciones", json={"canal_email_activo": False})
        db_session.add(
            EstadoAlarma(
                id_alrm=id_alarma,
                id_dspstv=escenario["dispositivo"].id_dspstv,
                en_alarma=True,
                ultima_fecha=datetime(2026, 11, 19, tzinfo=timezone.utc),
            )
        )
        db_session.flush()
        client.put(f"/alarmas/{id_alarma}/notificaciones", json={"canal_email_activo": True})
        estado = db_session.query(EstadoAlarma).filter_by(id_alrm=id_alarma).one()
        db_session.refresh(estado)
        assert estado.en_alarma is False


class TestPermisos:
    def test_solo_lectura_ve_pero_no_guarda(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario)
        db_session.query(PermisoUsuarioSede).filter_by(
            id_usr=escenario["usuario"].id_usr, mdl="Alarmas"
        ).update({"nvl": "Lectura"})
        db_session.flush()
        assert client.get(f"/alarmas/{id_alarma}/notificaciones").status_code == 200
        resp = client.put(
            f"/alarmas/{id_alarma}/notificaciones", json={"canal_email_activo": False}
        )
        assert resp.status_code == 403
        assert db_session.get(Alarma, id_alarma).cnl_crr_actv is True

    def test_modo_consulta_no_guarda(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario)
        db_session.query(Suscripcion).filter_by(id_clnt=escenario["sede"].id_clnt).update(
            {"estd": "Cancelada"}
        )
        db_session.flush()
        resp = client.put(
            f"/alarmas/{id_alarma}/notificaciones", json={"canal_email_activo": False}
        )
        assert resp.status_code == 409

    def test_alarma_de_otro_proyecto_no_se_modifica(self, client, db_session, escenario, fabrica):
        ajena = crear_alarma(db_session, escenario, "Ajena", usuario=fabrica.usuario())
        assert client.get(f"/alarmas/{ajena.id_alrm}/notificaciones").status_code == 200
        fuera = base.crear_ubicacion(db_session, escenario["sede"], "Proyecto no asignado")
        ajena.id_ubccn = fuera.id_ubccn
        db_session.flush()
        resp = client.put(
            f"/alarmas/{ajena.id_alrm}/notificaciones", json={"canal_email_activo": False}
        )
        assert resp.status_code == 404
        db_session.refresh(ajena)
        assert ajena.cnl_crr_actv is True


# --- CA4 en la evaluación: con el canal apagado no se envía nada -------------


def avisos(db):
    return db.query(NotificacionEnviada).filter_by(tipo="alarma_activada").count()


def test_canal_apagado_no_notifica_pero_registra_el_estado(db_session, caso):
    caso["alarma"].cnl_crr_actv = False
    db_session.flush()
    ses.evaluar(db_session, caso, [Decimal("35")])
    assert avisos(db_session) == 0
    assert db_session.query(EstadoAlarma).one().en_alarma is True


def test_canal_encendido_notifica_a_todos_los_destinatarios(db_session, caso):
    ses.evaluar(db_session, caso, [Decimal("35")])
    assert avisos(db_session) == 2
