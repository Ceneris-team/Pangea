"""
Mitigación de R-05 (RAID del proyecto) - tickets de un solo uso para
autenticar el WebSocket de HU17. Ver security/ws_tickets.py y el
docstring de _autenticar_websocket en routers/mapa_cliente.py.

Corre contra el Redis real (DB 6, propia -ver el módulo bajo prueba-) y
se salta sola si no está levantado, mismo criterio que
tests/routers/test_cache_ht10.py para HT-10.
"""

import time

import pytest

from app.security import ws_tickets


def _hay_redis() -> bool:
    try:
        ws_tickets._cliente().ping()
        return True
    except Exception:
        return False


requiere_redis = pytest.mark.skipif(
    not _hay_redis(), reason="Requiere Redis levantado (docker compose up redis)"
)


@requiere_redis
class TestEmitirYCanjearTicket:
    def test_el_ticket_canjeado_devuelve_el_jwt_asociado(self):
        jwt_de_prueba = "un-jwt-cualquiera.para.este-test"
        ticket = ws_tickets.emitir_ticket(jwt_de_prueba)

        assert ws_tickets.canjear_ticket(ticket) == jwt_de_prueba

    def test_uso_unico_real_el_segundo_canje_falla(self):
        """No alcanza con que el ticket "sea de vida corta": reusarlo un
        instante después del primer canje debe fallar igual. Es lo que
        distingue esto de simplemente poner un TTL corto."""
        ticket = ws_tickets.emitir_ticket("otro-jwt-de-prueba")

        assert ws_tickets.canjear_ticket(ticket) is not None
        assert ws_tickets.canjear_ticket(ticket) is None

    def test_ticket_inexistente_devuelve_none(self):
        assert ws_tickets.canjear_ticket("esto-nunca-se-emitio") is None

    def test_ticket_vacio_o_none_devuelve_none(self):
        assert ws_tickets.canjear_ticket("") is None
        assert ws_tickets.canjear_ticket(None) is None

    def test_dos_tickets_del_mismo_jwt_son_distintos(self):
        """Cada llamada genera un ticket propio (secrets.token_urlsafe),
        no una función determinística del JWT: dos pestañas abriendo el
        mapa a la vez no deben pisarse el ticket una a la otra."""
        jwt_de_prueba = "mismo-jwt-dos-tickets"
        primero = ws_tickets.emitir_ticket(jwt_de_prueba)
        segundo = ws_tickets.emitir_ticket(jwt_de_prueba)

        assert primero != segundo
        assert ws_tickets.canjear_ticket(primero) == jwt_de_prueba
        assert ws_tickets.canjear_ticket(segundo) == jwt_de_prueba

    def test_ticket_expira_solo_pasado_el_ttl(self, monkeypatch):
        """El TTL es la red de seguridad si el ticket nunca se canjea
        -pestaña cerrada antes de que el WS llegue a conectar-. Se baja el
        TTL a 1s en vez de esperar los 45s reales de producción."""
        monkeypatch.setattr(ws_tickets, "TTL_SEGUNDOS", 1)
        ticket = ws_tickets.emitir_ticket("jwt-de-vida-corta")

        time.sleep(1.5)

        assert ws_tickets.canjear_ticket(ticket) is None
