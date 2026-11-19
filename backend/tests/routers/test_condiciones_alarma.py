"""
HU 29 - Establecer condiciones de la alarma (PP-74). PP-229: guardar la
condición asociada a la alarma.

Regla de v1.0 (Diccionario de Datos Pangea 4.0, CONDICION_ALARMA): "una
condición por alarma, modelo flexible (HT-13)". La tabla admite varias
filas; la API exige exactamente una en el alta, en el PATCH y en
PUT /alarmas/{id}/condicion ("ACTUALIZAR": reemplaza, no agrega).

Corre contra la Postgres real de test (ver conftest.py). Reutiliza el
escenario de tests/routers/test_alarmas.py.
"""

from datetime import datetime, timezone

import pytest

from app.models import Alarma, CondicionAlarma, PermisoUbicacion, Suscripcion
from app.models.alarma import EstadoAlarma
from app.models.suscripcion import PermisoUsuarioSede
from tests.routers import test_alarmas as base

# Mismos fixtures y ayudas que test_alarmas.py (pytest los busca por nombre
# en este módulo).
client = base.client
escenario = base.escenario
crear_alarma = base.crear_alarma
cuerpo_valido = base.cuerpo_valido

MENSAJE_UNA = "exactamente una condición"


def detalle_422(resp):
    """Texto de los errores 422 de Pydantic (lista) o de HTTPException."""
    detalle = resp.json()["detail"]
    if isinstance(detalle, list):
        return " | ".join(e["msg"] for e in detalle)
    return detalle


def condiciones_en_bd(db, id_alarma):
    return [
        (c.oprdr, float(c.vlr_umbrl))
        for c in db.query(CondicionAlarma)
        .filter_by(id_alrm=id_alarma)
        .order_by(CondicionAlarma.id_cndcn)
        .all()
    ]


def crear_por_api(client, escenario, **extra):
    resp = client.post("/alarmas", json=cuerpo_valido(escenario, **extra))
    assert resp.status_code == 201, resp.text
    return resp.json()["alarma"]["id_alrm"]


# --- Alta: exactamente una condición ------------------------------------------------


class TestAltaUnaCondicion:
    def test_sin_condicion_es_422(self, client, escenario):
        resp = client.post("/alarmas", json=cuerpo_valido(escenario, condiciones=[]))
        assert resp.status_code == 422
        assert MENSAJE_UNA in detalle_422(resp)

    def test_omitir_el_campo_es_el_mismo_422(self, client, escenario):
        cuerpo = cuerpo_valido(escenario)
        del cuerpo["condiciones"]
        resp = client.post("/alarmas", json=cuerpo)
        assert resp.status_code == 422
        assert MENSAJE_UNA in detalle_422(resp)

    def test_dos_condiciones_es_422_y_no_crea_nada(self, client, db_session, escenario):
        resp = client.post(
            "/alarmas",
            json=cuerpo_valido(
                escenario,
                condiciones=[{"oprdr": ">", "vlr_umbrl": 30}, {"oprdr": "<", "vlr_umbrl": 5}],
            ),
        )
        assert resp.status_code == 422
        assert MENSAJE_UNA in detalle_422(resp)
        assert db_session.query(Alarma).filter_by(nmbr="Crecida del río").count() == 0

    def test_una_condicion_se_guarda_y_se_muestra(self, client, db_session, escenario):
        resp = client.post(
            "/alarmas",
            json=cuerpo_valido(escenario, condiciones=[{"oprdr": "<=", "vlr_umbrl": 0.25}]),
        )
        assert resp.status_code == 201
        alarma = resp.json()["alarma"]
        assert alarma["condicion"].startswith("<= 0.25")
        assert condiciones_en_bd(db_session, alarma["id_alrm"]) == [("<=", 0.25)]


# --- Valor umbral ------------------------------------------------------------------


@pytest.mark.parametrize(
    "umbral, fragmento",
    [
        (None, "obligatorio"),
        ("", "obligatorio"),
        ("abc", "debe ser un número"),
        (True, "obligatorio"),
        ("NaN", "finito"),
        ("Infinity", "finito"),
        (10000000000, "entre"),
        (-10000000000, "entre"),
        (1.23456, "hasta 4 decimales"),
        ([1], "debe ser un número"),
    ],
)
def test_umbral_invalido_con_mensaje_en_espanol(client, escenario, umbral, fragmento):
    resp = client.post(
        "/alarmas", json=cuerpo_valido(escenario, condiciones=[{"oprdr": ">", "vlr_umbrl": umbral}])
    )
    assert resp.status_code == 422
    assert fragmento in detalle_422(resp)


@pytest.mark.parametrize(
    "umbral, guardado",
    [
        (0, 0.0),
        (-12.5, -12.5),
        ("30", 30.0),
        (" 7.25 ", 7.25),
        (1.2345, 1.2345),
        (9999999999.9999, 9999999999.9999),
        (-9999999999.9999, -9999999999.9999),
    ],
)
def test_umbral_valido_en_los_limites(client, db_session, escenario, umbral, guardado):
    id_alarma = crear_por_api(client, escenario, condiciones=[{"oprdr": "=", "vlr_umbrl": umbral}])
    assert condiciones_en_bd(db_session, id_alarma) == [("=", guardado)]


@pytest.mark.parametrize("operador", [">", "<", ">=", "<=", "="])
def test_acepta_los_cinco_operadores(client, db_session, escenario, operador):
    id_alarma = crear_por_api(
        client, escenario, condiciones=[{"oprdr": f" {operador} ", "vlr_umbrl": 1}]
    )
    assert condiciones_en_bd(db_session, id_alarma) == [(operador, 1.0)]


@pytest.mark.parametrize("operador", ["!=", "=>", "", None, 5])
def test_operador_invalido(client, escenario, operador):
    resp = client.post(
        "/alarmas", json=cuerpo_valido(escenario, condiciones=[{"oprdr": operador, "vlr_umbrl": 1}])
    )
    assert resp.status_code == 422
    assert "El operador debe ser uno de" in detalle_422(resp)


# --- Ver y ACTUALIZAR la condición -------------------------------------------------


class TestVerCondicion:
    def test_devuelve_la_condicion_con_parametro_y_unidad(self, client, escenario):
        id_alarma = crear_por_api(client, escenario, condiciones=[{"oprdr": ">", "vlr_umbrl": 3.5}])
        resp = client.get(f"/alarmas/{id_alarma}/condicion")
        assert resp.status_code == 200
        cuerpo = resp.json()
        assert cuerpo["oprdr"] == ">" and cuerpo["vlr_umbrl"] == 3.5
        assert cuerpo["parametro"] == escenario["parametro"].nmbr
        assert cuerpo["unidad"] == (escenario["parametro"].undd or "")
        assert cuerpo["condicion"].startswith("> 3.5")
        assert cuerpo["condiciones_guardadas"] == 1

    def test_alarma_sin_condicion(self, client, db_session, escenario):
        alarma = crear_alarma(db_session, escenario, "Sin regla", condicion=None)
        cuerpo = client.get(f"/alarmas/{alarma.id_alrm}/condicion").json()
        assert cuerpo["oprdr"] is None and cuerpo["condicion"] is None
        assert cuerpo["condiciones_guardadas"] == 0

    def test_alarma_antigua_con_dos_condiciones_se_lee(self, client, db_session, escenario):
        alarma = crear_alarma(db_session, escenario, "Antigua", condicion=(">", 30))
        db_session.add(CondicionAlarma(id_alrm=alarma.id_alrm, oprdr="<", vlr_umbrl=5))
        db_session.flush()
        cuerpo = client.get(f"/alarmas/{alarma.id_alrm}/condicion").json()
        assert cuerpo["oprdr"] == ">" and cuerpo["condiciones_guardadas"] == 2

    def test_alarma_ajena_o_inexistente_es_404(self, client, db_session, escenario, fabrica):
        otro = fabrica.usuario()
        ajena = crear_alarma(db_session, escenario, "Ajena", usuario=otro)
        assert client.get(f"/alarmas/{ajena.id_alrm}/condicion").status_code == 404
        assert client.get("/alarmas/999999/condicion").status_code == 404


class TestActualizarCondicion:
    def test_reemplaza_la_condicion(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario, condiciones=[{"oprdr": ">", "vlr_umbrl": 3.5}])
        resp = client.put(f"/alarmas/{id_alarma}/condicion", json={"oprdr": "<", "vlr_umbrl": 1.25})
        assert resp.status_code == 200
        assert resp.json()["mensaje"] == "Condición actualizada correctamente"
        assert resp.json()["condicion"]["condicion"].startswith("< 1.25")
        assert condiciones_en_bd(db_session, id_alarma) == [("<", 1.25)]

    def test_alarma_antigua_queda_con_una(self, client, db_session, escenario):
        alarma = crear_alarma(db_session, escenario, "Antigua", condicion=(">", 30))
        db_session.add(CondicionAlarma(id_alrm=alarma.id_alrm, oprdr="<", vlr_umbrl=5))
        db_session.flush()
        resp = client.put(
            f"/alarmas/{alarma.id_alrm}/condicion", json={"oprdr": ">=", "vlr_umbrl": 28}
        )
        assert resp.status_code == 200
        assert condiciones_en_bd(db_session, alarma.id_alrm) == [(">=", 28.0)]
        assert resp.json()["condicion"]["condiciones_guardadas"] == 1

    def test_misma_condicion_no_cambia_nada(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario, condiciones=[{"oprdr": ">", "vlr_umbrl": 3.5}])
        antes = db_session.query(CondicionAlarma).filter_by(id_alrm=id_alarma).one().id_cndcn
        resp = client.put(
            f"/alarmas/{id_alarma}/condicion", json={"oprdr": ">", "vlr_umbrl": "3.50"}
        )
        assert resp.status_code == 200
        assert resp.json()["mensaje"] == "La condición no tuvo cambios"
        assert (
            db_session.query(CondicionAlarma).filter_by(id_alrm=id_alarma).one().id_cndcn == antes
        )

    def test_cambiar_la_condicion_reinicia_la_evaluacion(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario, condiciones=[{"oprdr": ">", "vlr_umbrl": 3.5}])
        db_session.add(
            EstadoAlarma(
                id_alrm=id_alarma,
                id_dspstv=escenario["dispositivo"].id_dspstv,
                en_alarma=True,
                ultima_fecha=datetime(2026, 11, 19, tzinfo=timezone.utc),
            )
        )
        db_session.flush()
        client.put(f"/alarmas/{id_alarma}/condicion", json={"oprdr": ">", "vlr_umbrl": 10})
        estado = db_session.query(EstadoAlarma).filter_by(id_alrm=id_alarma).one()
        db_session.refresh(estado)
        assert estado.en_alarma is False

    def test_condicion_invalida_no_toca_la_guardada(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario, condiciones=[{"oprdr": ">", "vlr_umbrl": 3.5}])
        resp = client.put(f"/alarmas/{id_alarma}/condicion", json={"oprdr": ">", "vlr_umbrl": "x"})
        assert resp.status_code == 422
        assert condiciones_en_bd(db_session, id_alarma) == [(">", 3.5)]

    def test_alarma_ajena_es_404(self, client, db_session, escenario, fabrica):
        ajena = crear_alarma(db_session, escenario, "Ajena", usuario=fabrica.usuario())
        resp = client.put(
            f"/alarmas/{ajena.id_alrm}/condicion", json={"oprdr": ">", "vlr_umbrl": 1}
        )
        assert resp.status_code == 404
        assert condiciones_en_bd(db_session, ajena.id_alrm) == [(">", 3.5)]

    def test_sin_ubicacion_asignada_es_404(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario)
        db_session.query(PermisoUbicacion).filter_by(id_usr=escenario["usuario"].id_usr).delete()
        db_session.flush()
        resp = client.put(f"/alarmas/{id_alarma}/condicion", json={"oprdr": ">", "vlr_umbrl": 1})
        assert resp.status_code == 404

    def test_solo_lectura_no_puede_actualizar(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario)
        db_session.query(PermisoUsuarioSede).filter_by(
            id_usr=escenario["usuario"].id_usr, mdl="Alarmas"
        ).update({"nvl": "Lectura"})
        db_session.flush()
        assert client.get(f"/alarmas/{id_alarma}/condicion").status_code == 200
        resp = client.put(f"/alarmas/{id_alarma}/condicion", json={"oprdr": ">", "vlr_umbrl": 1})
        assert resp.status_code == 403
        assert condiciones_en_bd(db_session, id_alarma) == [(">", 3.5)]

    def test_modo_consulta_no_puede_actualizar(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario)
        db_session.query(Suscripcion).filter_by(id_clnt=escenario["sede"].id_clnt).update(
            {"estd": "Cancelada"}
        )
        db_session.flush()
        resp = client.put(f"/alarmas/{id_alarma}/condicion", json={"oprdr": ">", "vlr_umbrl": 1})
        assert resp.status_code == 409
        assert condiciones_en_bd(db_session, id_alarma) == [(">", 3.5)]


# --- PATCH general: la misma regla ------------------------------------------------


class TestPatchMismaRegla:
    def test_patch_con_dos_condiciones_es_422(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario)
        resp = client.patch(
            f"/alarmas/{id_alarma}",
            json={"condiciones": [{"oprdr": ">", "vlr_umbrl": 1}, {"oprdr": "<", "vlr_umbrl": 0}]},
        )
        assert resp.status_code == 422
        assert MENSAJE_UNA in detalle_422(resp)
        assert condiciones_en_bd(db_session, id_alarma) == [(">", 3.5)]

    def test_patch_con_lista_vacia_es_422(self, client, escenario):
        id_alarma = crear_por_api(client, escenario)
        resp = client.patch(f"/alarmas/{id_alarma}", json={"condiciones": []})
        assert resp.status_code == 422

    def test_patch_solo_estado_conserva_la_condicion(self, client, db_session, escenario):
        id_alarma = crear_por_api(client, escenario)
        resp = client.patch(f"/alarmas/{id_alarma}", json={"estado": "Inactiva"})
        assert resp.status_code == 200 and resp.json()["estado"] == "Inactiva"
        assert condiciones_en_bd(db_session, id_alarma) == [(">", 3.5)]
