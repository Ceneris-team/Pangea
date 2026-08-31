"""
HU 17 CA3 - WebSocket de telemetría en vivo.

Cubre el control de acceso del canal (que es donde un error se paga caro:
un WebSocket mal autenticado filtraría telemetría de ubicaciones ajenas
en tiempo real) y el contrato del mensaje que viaja por Redis.

El camino completo "worker publica -> navegador recibe" se verifica
end-to-end contra el stack real levantado con docker-compose, no acá:
requiere Redis, un worker de Celery y un navegador, y montar eso en
pytest daría un test lento y frágil que probaría sobre todo el arnés.
Ver el resumen de verificación de HU 17.
"""

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import PermisoUbicacion, Ubicacion
from app.models.suscripcion import PermisoUsuarioSede
from app.security.jwt_auth import create_access_token
from app.services.mapa.eventos import CANAL_PREFIJO, canal_de_ubicacion, construir_evento

POLIGONO_DUMMY = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


class TestAutenticacionDelCanal:
    def test_sin_token_cierra_con_1008(self, client):
        """El navegador no puede mandar headers en new WebSocket(), así
        que el token va por query param; sin él, no se abre el canal."""
        with client.websocket_connect("/mapa-cliente/ws") as ws:
            mensaje = ws.receive()
        assert mensaje["type"] == "websocket.close"
        assert mensaje["code"] == 1008

    def test_token_invalido_cierra_con_1008(self, client):
        with client.websocket_connect("/mapa-cliente/ws?token=esto-no-es-un-jwt") as ws:
            mensaje = ws.receive()
        assert mensaje["type"] == "websocket.close"
        assert mensaje["code"] == 1008

    def test_token_valido_sin_permiso_sobre_tableros_cierra_con_1008(
        self, client, db_session, fabrica
    ):
        """Un JWT válido no alcanza: el módulo "Tableros" se exige igual
        que en el endpoint REST."""
        rol = fabrica.rol("Cliente Final")
        usuario = fabrica.usuario(rol=rol)
        sede = fabrica.sede()
        # Sin fila en prms_usr_sd para "Tableros".

        token = create_access_token(
            user_id=usuario.id_usr, sede_id=sede.id_sd, scope="por_sede", rol="Cliente Final"
        )

        with client.websocket_connect(f"/mapa-cliente/ws?token={token}") as ws:
            mensaje = ws.receive()
        assert mensaje["type"] == "websocket.close"
        assert mensaje["code"] == 1008


class TestUsuarioSinUbicaciones:
    """Regresión: un Cliente Final SIN ubicaciones asignadas (sin filas en
    prms_ubccn) no debe tumbar la conexión.

    Apareció en producción y no en local: acá los tests siempre creaban el
    usuario CON una ubicación asignada, así que el camino de
    "ids_permitidas vacío" nunca se ejecutaba. El bug era que el bucle
    llamaba a pubsub.get_message() sobre un PubSub sin ningún canal
    suscrito, y redis lanza RuntimeError("pubsub connection not set: did
    you forget to call subscribe()?"), cerrando el WebSocket con un 1006
    (cierre anormal) apenas conectaba.

    Es justo el estado de un cliente recién dado de alta, así que era el
    primer usuario real el que se lo encontraba.
    """

    def test_conexion_sobrevive_sin_ubicaciones_asignadas(
        self, client, db_session, fabrica, monkeypatch
    ):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        db_session.add(
            PermisoUsuarioSede(
                id_usr=usuario.id_usr,
                id_sd=sede.id_sd,
                id_rl=rol.id_rl,
                mdl="Tableros",
                nvl="Lectura",
            )
        )
        db_session.flush()
        # Sin filas en prms_ubccn a propósito: ese es el caso bajo prueba.

        token = create_access_token(
            user_id=usuario.id_usr, sede_id=sede.id_sd, scope="por_sede", rol="Cliente Final"
        )

        # El ping normal tarda 25s; se acorta para que el test no espere.
        monkeypatch.setattr("app.routers.mapa_cliente.SEGUNDOS_ENTRE_PINGS", 0.2)

        # El endpoint WebSocket abre su PROPIA sesión con SessionLocal() (no
        # usa la dependencia get_db, que es de HTTP), así que no ve las filas
        # de esta transacción de test -que nunca se confirma-. Se apunta la
        # consulta de permisos a la sesión del test y se fuerza el caso bajo
        # prueba: usuario válido, cero ubicaciones asignadas.
        monkeypatch.setattr(
            "app.routers.mapa_cliente.tiene_permiso", lambda *a, **k: True
        )
        monkeypatch.setattr(
            "app.routers.mapa_cliente.ubicaciones_permitidas", lambda *a, **k: []
        )

        with client.websocket_connect(f"/mapa-cliente/ws?token={token}") as ws:
            # Antes del arreglo esto era un 1006 inmediato; ahora tiene que
            # llegar un ping y la conexión seguir viva.
            mensaje = ws.receive_json()

        assert mensaje == {"tipo": "ping"}


class TestContratoDelEvento:
    """La forma del mensaje la definen productor (worker de Celery) y
    consumidor (WebSocket) por separado; si se desincroniza, el marcador
    deja de actualizarse en silencio. Estos tests la fijan."""

    def test_canal_es_por_ubicacion(self):
        """El filtro de HU 21 se aplica en la SUSCRIPCIÓN: un canal por
        ubicación, no uno global que haya que filtrar al repartir."""
        assert canal_de_ubicacion(7) == f"{CANAL_PREFIJO}7"
        assert canal_de_ubicacion(7) != canal_de_ubicacion(8)

    def test_evento_trae_lo_que_el_marcador_necesita(self):
        """CA3: parámetro, valor y fecha/hora. Nada más - no viaja el
        archivo .dat ni la fila entera de tlmtr."""
        cuando = dt.datetime(2026, 8, 26, 15, 30, tzinfo=dt.timezone.utc)
        evento = construir_evento(
            id_ubccn=3, nombre_parametro="Temperatura", unidad="°C", valor=25.5, fecha_hora=cuando
        )
        assert evento == {
            "id_ubccn": 3,
            "parametro": "Temperatura",
            "unidad": "°C",
            "valor": 25.5,
            "fch_hr": "2026-08-26T15:30:00+00:00",
        }

    def test_evento_es_serializable_a_json(self):
        """Viaja por Redis como JSON: un Decimal de tlmtr reventaría
        json.dumps si no se convirtiera antes."""
        from decimal import Decimal

        evento = construir_evento(
            id_ubccn=1,
            nombre_parametro="Temperatura",
            unidad="°C",
            valor=Decimal("25.5000"),
            fecha_hora=dt.datetime.now(dt.timezone.utc),
        )
        assert json.loads(json.dumps(evento))["valor"] == 25.5

    def test_evento_de_texto_viaja_sin_convertir(self):
        """Un evento de evnt_txt ("Puerta Abierta") no es convertible a
        float; se manda tal cual para que el panel lo muestre igual."""
        evento = construir_evento(
            id_ubccn=1,
            nombre_parametro="MensajeP",
            unidad="-",
            valor="Puerta Abierta",
            fecha_hora=dt.datetime.now(dt.timezone.utc),
        )
        assert evento["valor"] == "Puerta Abierta"
        assert json.loads(json.dumps(evento))["valor"] == "Puerta Abierta"


class TestPublicacionDesdeLaIngesta:
    """HU17 CA3: el punto donde procesar_archivo_dat avisa al mapa."""

    def test_no_publica_si_no_hubo_lecturas(self, db_session):
        """Un archivo sin filas guardadas no debe generar tráfico."""
        from unittest.mock import patch

        from app.services.ingesta.persistencia import ResultadoPersistencia
        from app.tasks.ingesta import _publicar_eventos_mapa

        resultado = ResultadoPersistencia(
            guardadas=0, omitidas_sin_valor=0, omitidas_parametro_desconocido=[]
        )
        with patch("app.tasks.ingesta.publicar_lecturas") as publicar:
            _publicar_eventos_mapa(db_session, resultado)
        publicar.assert_not_called()

    def test_publica_el_ultimo_valor_de_cada_parametro(self, db_session, fabrica):
        """No una publicación por fila del .dat: solo el último valor de
        cada parámetro, que es lo único que el marcador muestra."""
        from unittest.mock import patch

        from app.models import Parametro
        from app.services.ingesta.persistencia import ResultadoPersistencia
        from app.tasks.ingesta import _publicar_eventos_mapa

        db_session.add(Parametro(nmbr="Temperatura HU17 WS", undd="°C", tipo_dato="numerico"))
        db_session.flush()

        ahora = dt.datetime.now(dt.timezone.utc)
        resultado = ResultadoPersistencia(
            guardadas=3,
            omitidas_sin_valor=0,
            omitidas_parametro_desconocido=[],
            ultimos_por_parametro={"Temperatura HU17 WS": (25.5, ahora)},
            id_ubccn=42,
        )

        with patch("app.tasks.ingesta.publicar_lecturas") as publicar:
            _publicar_eventos_mapa(db_session, resultado)

        publicar.assert_called_once()
        (eventos,) = publicar.call_args[0]
        assert len(eventos) == 1
        assert eventos[0]["id_ubccn"] == 42
        assert eventos[0]["parametro"] == "Temperatura HU17 WS"
        assert eventos[0]["valor"] == 25.5
        # La unidad se resuelve desde prmtr para que el panel la muestre.
        assert eventos[0]["unidad"] == "°C"
