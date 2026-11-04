"""
QA - PP-414 HU-21 CA-06: mapa en vivo con servidor, Redis y espera reales (sin mocks).

Requiere la API de dev en 127.0.0.1:8021 sobre pangea_e2e_hu21 y haber ejecutado seed_hu21.py.
Cada prueba vuelve a sembrar los datos y mide el tiempo real hasta el cierre del WebSocket.
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import redis
import websockets

BASE = "http://127.0.0.1:8021"
WS = "ws://127.0.0.1:8021/mapa-cliente/ws"
CANAL = "pangea:mapa:ubicacion:"  # app/services/mapa/eventos.py
REDIS_EVENTOS = "redis://localhost:6379/4"
CLAVE = os.environ.get("QA_CLAVE", "Pangea2026")  # contraseña del seed
SEED = Path(__file__).resolve().parents[2] / "playwright_hu21" / "seed_hu21.py"
LIMITE = 25.0  # segundos del criterio
MARGEN = 2.0  # tolerancia de medición
CF, LECTOR = "cf@hu21.pangea-dev.com", "lector2@hu21.pangea-dev.com"
ADMIN_EMPRESA, ADMIN = "admin-a@hu21.pangea-dev.com", "admin@pangea-dev.com"


@pytest.fixture()
def ids():
    entorno = {**os.environ, "PYTHONPATH": ".",
               "DATABASE_URL": "postgresql+psycopg2://postgres:postgres@localhost:55432/pangea_e2e_hu21"}
    salida = subprocess.run([sys.executable, str(SEED)], capture_output=True, text=True, check=True, env=entorno)
    return json.loads(salida.stdout.strip().splitlines()[-1])


def sesion(correo):
    subprocess.run("docker exec pangea-redis-1 redis-cli -n 1 FLUSHDB", shell=True, check=True, capture_output=True)
    r = httpx.post(f"{BASE}/auth/login", json={"correo": correo, "contrasena": CLAVE})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def publicar(id_ubccn):
    cliente = redis.Redis.from_url(REDIS_EVENTOS)
    try:
        return cliente.publish(f"{CANAL}{id_ubccn}", json.dumps({"id_ubccn": id_ubccn, "qa": "hu21"}))
    finally:
        cliente.close()


def asignar_anterior(cabeceras, id_usr, proyectos):
    r = httpx.put(f"{BASE}/usuarios/{id_usr}/permisos-ubicaciones",
                  json={"ubicacion_ids": proyectos}, headers=cabeceras)
    assert r.status_code == 200, r.text


def editar_miembro(cabeceras, cliente, miembro, rol, estado, proyectos):
    r = httpx.patch(f"{BASE}/empresas/{cliente}/usuarios/{miembro}",
                    json={"rol": rol, "estado": estado, "proyecto_ids": proyectos}, headers=cabeceras)
    assert r.status_code == 200, r.text


async def abrir(cabeceras):
    ticket = httpx.post(f"{BASE}/auth/ws-ticket", headers=cabeceras).json()["ticket"]
    socket = await websockets.connect(f"{WS}?ticket={ticket}")
    await asyncio.sleep(1.0)  # deja que el servidor termine de suscribirse
    return socket


async def esperar_cierre(socket, limite):
    """Devuelve (mensajes recibidos, código, motivo, segundos hasta el cierre)."""
    inicio, recibidos = time.monotonic(), []
    try:
        while True:
            restante = limite - (time.monotonic() - inicio)
            recibidos.append(json.loads(await asyncio.wait_for(socket.recv(), restante)))
    except websockets.ConnectionClosed as cierre:
        return recibidos, cierre.rcvd.code, cierre.rcvd.reason, time.monotonic() - inicio
    except TimeoutError:
        return recibidos, None, None, time.monotonic() - inicio


def lecturas(recibidos):
    return [m for m in recibidos if m.get("tipo") == "lectura"]


def test_ca06_control_sin_cambios_el_evento_autorizado_si_llega(ids):
    async def caso():
        socket = await abrir(sesion(CF))
        assert publicar(ids["p1"]) >= 1
        mensaje = json.loads(await asyncio.wait_for(socket.recv(), 5))
        while mensaje["tipo"] == "ping":  # el servidor saluda con un ping al suscribirse
            mensaje = json.loads(await asyncio.wait_for(socket.recv(), 5))
        await socket.close()
        return mensaje

    mensaje = asyncio.run(caso())
    assert mensaje["tipo"] == "lectura" and mensaje["evento"]["id_ubccn"] == ids["p1"]


def test_ca06_evento_posterior_a_la_revocacion_no_se_entrega_y_cierra(ids):
    admin = sesion(ADMIN)

    async def caso():
        socket = await abrir(sesion(CF))
        asignar_anterior(admin, ids["cf"], [ids["p2"]])
        assert publicar(ids["p1"]) >= 1
        return await esperar_cierre(socket, 5)

    recibidos, codigo, motivo, _ = asyncio.run(caso())
    assert lecturas(recibidos) == []
    assert (codigo, motivo) == (1008, "Los proyectos disponibles cambiaron")


def test_ca06_sin_eventos_la_revocacion_anterior_cierra_en_25s_como_maximo(ids):
    admin = sesion(ADMIN)

    async def caso():
        socket = await abrir(sesion(CF))
        asignar_anterior(admin, ids["cf"], [ids["p2"]])
        return await esperar_cierre(socket, LIMITE + MARGEN + 3)

    recibidos, codigo, _, segundos = asyncio.run(caso())
    assert lecturas(recibidos) == [] and codigo == 1008
    assert segundos <= LIMITE + MARGEN, segundos


def test_ca06_peor_caso_revocar_justo_tras_un_ping_cierra_en_25s(ids):
    admin = sesion(ADMIN_EMPRESA)

    async def caso():
        socket = await abrir(sesion(LECTOR))
        assert json.loads(await asyncio.wait_for(socket.recv(), LIMITE + MARGEN))["tipo"] == "ping"
        editar_miembro(admin, ids["a"], ids["m_lector2"], "Lector", "Activo", [ids["p1"]])
        return await esperar_cierre(socket, LIMITE + MARGEN + 3)

    _, codigo, _, segundos = asyncio.run(caso())
    assert codigo == 1008
    assert segundos <= LIMITE + MARGEN, segundos


def test_ca06_desactivar_membresia_cierra_la_conexion(ids):
    admin = sesion(ADMIN_EMPRESA)

    async def caso():
        socket = await abrir(sesion(LECTOR))
        editar_miembro(admin, ids["a"], ids["m_lector2"], "Lector", "Inactivo", [ids["p1"], ids["p2"]])
        assert publicar(ids["p1"]) >= 1
        return await esperar_cierre(socket, 5)

    recibidos, codigo, motivo, _ = asyncio.run(caso())
    assert lecturas(recibidos) == []
    assert (codigo, motivo) == (1008, "El acceso cambió")


def test_ca06_nueva_asignacion_tambien_restablece_el_contexto(ids):
    admin = sesion(ADMIN)

    async def caso():
        socket = await abrir(sesion(CF))
        asignar_anterior(admin, ids["cf"], [ids["p1"], ids["p2"]])
        assert publicar(ids["p1"]) >= 1
        return await esperar_cierre(socket, 5)

    _, codigo, motivo, _ = asyncio.run(caso())
    assert (codigo, motivo) == (1008, "Los proyectos disponibles cambiaron")


def test_ca06_conexion_sin_proyectos_detecta_la_nueva_asignacion_en_25s(ids):
    admin = sesion(ADMIN)
    asignar_anterior(admin, ids["cf"], [])

    async def caso():
        socket = await abrir(sesion(CF))
        asignar_anterior(admin, ids["cf"], [ids["p1"]])
        return await esperar_cierre(socket, LIMITE + MARGEN + 3)

    _, codigo, _, segundos = asyncio.run(caso())
    assert codigo == 1008
    assert segundos <= LIMITE + MARGEN, segundos
