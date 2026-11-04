"""PP-417: casos adicionales de listado sobre PostgreSQL local."""
import pytest
from app.main import app
from app.security.dependencies import get_current_user
from tests.routers.test_alarmas import client, escenario, crear_alarma

@pytest.mark.parametrize('parametros', [{'pagina': 0}, {'por_pagina': 0}, {'por_pagina': 101}])
def test_paginacion_invalida(client, escenario, parametros):
    assert client.get('/alarmas', params=parametros).status_code == 422

def test_segunda_pagina_sin_duplicados(client, db_session, escenario):
    for i in range(13):
        crear_alarma(db_session, escenario, f'QA {i:02}')
    primera = client.get('/alarmas').json()
    segunda = client.get('/alarmas', params={'pagina': 2}).json()
    assert len(primera['items']) == 10 and len(segunda['items']) == 3
    assert not {a['id_alrm'] for a in primera['items']} & {a['id_alrm'] for a in segunda['items']}
    assert primera['total'] == segunda['total'] == 13

def test_busqueda_sin_coincidencias(client, db_session, escenario):
    crear_alarma(db_session, escenario, 'Nivel alto')
    assert client.get('/alarmas', params={'busqueda': 'inexistente'}).json()['items'] == []

def test_filtro_no_elimina_datos(client, db_session, escenario):
    crear_alarma(db_session, escenario, 'Nivel alto')
    assert client.get('/alarmas', params={'estado': 'Inactiva'}).json()['total'] == 0
    assert client.get('/alarmas').json()['total'] == 1

def test_sesion_ausente(client):
    app.dependency_overrides.pop(get_current_user, None)
    assert client.get('/alarmas').status_code == 401
