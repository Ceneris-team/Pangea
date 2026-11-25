import base64
import datetime as dt
import io
import os
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from app.services import almacen_respaldos as almacen
from app.services import cifrado_respaldos as cifrado
from app.services import respaldos
from app.services import vigilancia_respaldos as vigilancia
from app.services.restauracion_respaldos import validar_destino

UTC = dt.timezone.utc


@pytest.fixture(autouse=True)
def configuracion(monkeypatch, tmp_path):
    for nombre, valor in {
        "BACKUP_ENCRYPTION_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        "BACKUP_KEY_ID": "v1",
        "BACKUP_PREVIOUS_KEYS": "{}",
        "BACKUP_PREFIX": "respaldos/",
        "BACKUP_ENVIRONMENT": "pruebas",
        "BACKUP_RETENTION_DAYS": "56",
        "BACKUP_MAX_COPIES": "8",
        "BACKUP_MANUAL_MAX_COPIES": "2",
        "BACKUP_MONITOR_ENABLED": "true",
        "BACKUP_MONITOR_START_AT": "2026-01-01T00:00:00+00:00",
        "BACKUP_ALERT_RECIPIENTS": "equipo@example.com",
        "BACKUP_MONITOR_STATE_DIR": str(tmp_path / "monitor"),
    }.items():
        monkeypatch.setenv(nombre, valor)


def cifrar(tmp_path, contenido=b"PGDMP" + os.urandom(2 * 1024 * 1024)):
    origen = tmp_path / "respaldo.enc"
    with origen.open("wb") as salida:
        cifrado.cifrar_stream(io.BytesIO(contenido), salida)
    return origen, contenido


def test_cifrado_real_por_bloques_y_recuperacion(tmp_path):
    origen, datos = cifrar(tmp_path)
    assert b"PGDMP" not in origen.read_bytes()
    destino = tmp_path / "restaurado.dump"
    cabecera = cifrado.descifrar_archivo(origen, destino)
    assert cabecera["cifrado"] == "AES-256-GCM"
    assert destino.read_bytes() == datos


@pytest.mark.parametrize("alteracion", ["clave", "contenido", "cabecera", "truncado"])
def test_rechaza_alteracion_y_no_deja_dump(tmp_path, monkeypatch, alteracion):
    origen, _ = cifrar(tmp_path)
    datos = bytearray(origen.read_bytes())
    if alteracion == "clave":
        monkeypatch.setenv(
            "BACKUP_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
        )
    elif alteracion == "truncado":
        datos = datos[:-50]
    else:
        datos[60 if alteracion == "cabecera" else -100] ^= 1
    origen.write_bytes(datos)
    destino = tmp_path / "fallido.dump"
    with pytest.raises(cifrado.CifradoRespaldoError):
        cifrado.descifrar_archivo(origen, destino)
    assert not destino.exists()


def test_no_elimina_destino_preexistente_aunque_cabecera_invalida(tmp_path):
    origen = tmp_path / "invalido"
    origen.write_bytes(b"invalido")
    destino = tmp_path / "existente"
    destino.write_bytes(b"conservar")
    with pytest.raises(ValueError):
        cifrado.descifrar_archivo(origen, destino)
    assert destino.read_bytes() == b"conservar"


def test_rotacion_recupera_con_clave_anterior(tmp_path, monkeypatch):
    import json

    origen, datos = cifrar(tmp_path)
    anterior = os.environ["BACKUP_ENCRYPTION_KEY"]
    monkeypatch.setenv("BACKUP_KEY_ID", "v2")
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("BACKUP_PREVIOUS_KEYS", json.dumps({"v1": anterior}))
    destino = tmp_path / "rotado"
    cifrado.descifrar_archivo(origen, destino)
    assert destino.read_bytes() == datos


def test_password_codificada_ipv6_no_aparece_en_argumentos():
    url, clave = respaldos._separar_credenciales("postgresql://u:p%40ss%3Aword@[::1]:5433/db")
    assert url == "postgresql://u@[::1]:5433/db"
    assert clave == "p@ss:word"
    assert respaldos._url_libpq("postgresql+psycopg2://u@host/db") == "postgresql://u@host/db"


@pytest.mark.parametrize("prefijo", ["", "datos-crudos/", "respaldos/../", "respaldos//"])
def test_rechaza_prefijos_peligrosos(monkeypatch, prefijo):
    monkeypatch.setenv("BACKUP_PREFIX", prefijo)
    with pytest.raises(ValueError):
        almacen.prefijo()


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u@produccion/pangea_restore_demo",
        "postgresql://u@localhost/pangea_dev",
        "postgresql://u@localhost/pangea_restore_demo?hostaddr=1.2.3.4",
    ],
)
def test_restaura_solo_local_nueva(url):
    with pytest.raises(ValueError):
        validar_destino(url)


def test_retencion_8_semanas_sin_desplazarlas_con_manuales(monkeypatch):
    hoy = dt.datetime(2026, 11, 9, tzinfo=UTC)
    copias = []
    for i in range(10):
        fecha = hoy - dt.timedelta(weeks=i)
        copias.append(
            {
                "estado": "Exitoso",
                "tipo": "semanal",
                "semana": fecha.strftime("%G-W%V"),
                "clave": almacen.prefijo() + f"{i}.dump.enc",
                "finalizado": fecha.isoformat(),
            }
        )
    for i in range(4):
        copias.append(
            {
                "estado": "Exitoso",
                "tipo": "manual",
                "clave": almacen.prefijo() + f"manual{i}.dump.enc",
                "finalizado": (hoy - dt.timedelta(minutes=i)).isoformat(),
            }
        )
    # Un reintento de la ultima semana no ocupa otra plaza semanal.
    copias.append(
        {
            **copias[0],
            "clave": almacen.prefijo() + "duplicado.dump.enc",
            "finalizado": (hoy - dt.timedelta(seconds=1)).isoformat(),
        }
    )
    manifiestos = {info["clave"] + ".json": info for info in copias}
    monkeypatch.setattr(almacen, "listar", lambda: [{"Key": clave} for clave in manifiestos])
    monkeypatch.setattr(almacen, "leer_json", lambda clave: manifiestos[clave])
    borrados = []
    monkeypatch.setattr(almacen, "eliminar", borrados.extend)
    resultado = respaldos.aplicar_retencion(hoy.date())
    assert set(resultado) == {
        almacen.prefijo() + nombre
        for nombre in [
            "8.dump.enc",
            "9.dump.enc",
            "manual2.dump.enc",
            "manual3.dump.enc",
            "duplicado.dump.enc",
        ]
    }
    assert len(borrados) == 10


def test_retencion_purga_antiguo_aunque_no_llegue_a_8(monkeypatch):
    clave = almacen.prefijo() + "viejo.dump.enc"
    monkeypatch.setattr(almacen, "listar", lambda: [{"Key": clave + ".json"}])
    monkeypatch.setattr(
        almacen,
        "leer_json",
        lambda _: {
            "estado": "Exitoso",
            "tipo": "semanal",
            "semana": "2024-W01",
            "clave": clave,
            "finalizado": "2024-01-01T00:00:00+00:00",
        },
    )
    eliminados = []
    monkeypatch.setattr(almacen, "eliminar", eliminados.extend)
    assert respaldos.aplicar_retencion(dt.date(2026, 11, 9)) == [clave]


def test_eliminar_borra_versiones_y_marcadores_solo_objeto_exacto(monkeypatch):
    cliente = MagicMock()
    cliente.get_bucket_versioning.return_value = {"Status": "Enabled"}
    clave = almacen.prefijo() + "viejo.dump.enc"
    cliente.get_paginator.return_value.paginate.return_value = [
        {
            "Versions": [
                {"Key": clave, "VersionId": "a"},
                {"Key": clave + ".ajeno", "VersionId": "b"},
            ],
            "DeleteMarkers": [{"Key": clave, "VersionId": "c"}],
        }
    ]
    cliente.delete_objects.return_value = {}
    monkeypatch.setattr(almacen.object_storage, "cliente_s3", lambda: cliente)
    monkeypatch.setenv("BACKUP_BUCKET", "bucket")
    almacen.eliminar([clave])
    assert cliente.delete_objects.call_args.kwargs["Delete"]["Objects"] == [
        {"Key": clave, "VersionId": "a"},
        {"Key": clave, "VersionId": "c"},
    ]


def test_watchdog_detecta_beat_caido_sin_consultar_bd(monkeypatch):
    monkeypatch.setattr(almacen, "leer_json", lambda _: None)
    alertas = []
    monkeypatch.setattr(vigilancia, "emitir_alerta", lambda evento, mensaje: alertas.append(evento))
    assert (
        vigilancia.comprobar_respaldo(dt.datetime(2026, 11, 8, 12, tzinfo=UTC))["estado"]
        == "Alerta"
    )
    assert alertas == ["ausente-2026-11-08"]


def test_watchdog_respeta_ventana_y_solo_exito_semanal(monkeypatch):
    monkeypatch.setattr(almacen, "leer_json", lambda _: None)
    assert (
        vigilancia.comprobar_respaldo(dt.datetime(2026, 11, 8, 9, tzinfo=UTC))["estado"]
        == "Correcto"
    )


def test_watchdog_no_alerta_por_semanas_anteriores_a_activacion(monkeypatch):
    monkeypatch.setenv("BACKUP_MONITOR_START_AT", "2026-11-09T00:00:00+00:00")
    monkeypatch.setattr(almacen, "leer_json", lambda _: None)
    assert (
        vigilancia.comprobar_respaldo(dt.datetime(2026, 11, 9, 12, tzinfo=UTC))["estado"]
        == "Correcto"
    )


def test_alerta_directa_deduplica_y_reintenta_si_ses_falla(monkeypatch):
    envios = []

    def enviar(*args):
        envios.append(args)
        if len(envios) == 1:
            raise ConnectionError()
        return "ses-id"

    monkeypatch.setattr(vigilancia, "enviar_ses", enviar)
    with pytest.raises(ConnectionError):
        vigilancia.emitir_alerta("incidente", "mensaje")
    assert vigilancia.emitir_alerta("incidente", "mensaje")[0]["resultado"] == "Enviado"
    assert vigilancia.emitir_alerta("incidente", "mensaje")[0]["resultado"] == "YaAlertado"
    assert len(envios) == 2


def test_tarea_reintenta_y_alerta_ante_fallo(monkeypatch):
    from celery.exceptions import Retry

    from app.tasks import respaldos as tarea

    monkeypatch.setenv("BACKUP_ENABLED", "true")
    monkeypatch.setattr(
        tarea, "ejecutar_respaldo", lambda: (_ for _ in ()).throw(ConnectionError())
    )
    alertas = []
    monkeypatch.setattr(tarea, "emitir_alerta", lambda *args: alertas.append(args))
    with pytest.raises(Retry):
        tarea.respaldo_semanal.apply(throw=True)
    assert alertas


def test_ejecutar_limpia_temporal_y_no_retiene_si_subida_falla(monkeypatch):
    conn = MagicMock()
    rutas = []
    eliminados = []

    @contextmanager
    def bloqueo():
        yield conn

    monkeypatch.setattr(respaldos, "bloqueo_respaldo", bloqueo)
    monkeypatch.setattr(respaldos, "inventario", lambda _: {})
    monkeypatch.setattr(almacen, "guardar_json", lambda *args: None)

    def generar(ruta, snapshot):
        ruta.write_bytes(b"cifrado")
        rutas.append(ruta)

    monkeypatch.setattr(respaldos, "generar_respaldo_cifrado", generar)
    monkeypatch.setattr(almacen, "subir", lambda *args: (_ for _ in ()).throw(ConnectionError()))
    monkeypatch.setattr(respaldos, "aplicar_retencion", lambda *args: eliminados.append(True))
    with pytest.raises(ConnectionError):
        respaldos.ejecutar_respaldo()
    assert rutas and not rutas[0].exists() and not eliminados


def test_fallo_retencion_no_publica_un_ciclo_exitoso(monkeypatch):
    conn = MagicMock()
    conn.scalar.return_value = "snapshot"
    conn.execute.return_value.scalars.return_value.all.return_value = ["revision"]

    @contextmanager
    def bloqueo():
        yield conn

    monkeypatch.setattr(respaldos, "bloqueo_respaldo", bloqueo)
    monkeypatch.setattr(respaldos, "inventario", lambda _: {})
    monkeypatch.setattr(
        respaldos, "generar_respaldo_cifrado", lambda ruta, _: ruta.write_bytes(b"cifrado")
    )
    monkeypatch.setattr(almacen, "subir", lambda *args: None)
    guardados = []
    monkeypatch.setattr(
        almacen, "guardar_json", lambda clave, info: guardados.append((clave, dict(info)))
    )

    def fallo(*args):
        raise ConnectionError()

    monkeypatch.setattr(respaldos, "aplicar_retencion", fallo)
    with pytest.raises(ConnectionError):
        respaldos.ejecutar_respaldo()
    assert guardados[-1][1]["estado"] == "Fallido"
    assert not any("ultimo-exito-semanal" in clave for clave, _ in guardados)


def test_custodia_cifra_y_recupera_claves_sin_mostrarlas():
    from scripts.custodiar_claves_respaldos import exportar, importar

    datos = {"BACKUP_ENCRYPTION_KEY": os.environ["BACKUP_ENCRYPTION_KEY"]}
    password = "frase-larga-de-prueba-solo-para-test"
    paquete = exportar(datos, password)
    assert datos["BACKUP_ENCRYPTION_KEY"].encode() not in paquete
    assert importar(paquete, password) == datos
    from cryptography.exceptions import InvalidTag

    with pytest.raises(InvalidTag):
        importar(paquete, "frase-incorrecta-de-prueba")


def test_worker_aislado_no_programa_trabajos_de_otras_versiones():
    import json
    import subprocess
    import sys
    from pathlib import Path

    codigo = """
import json
from app.core.celery_respaldos import celery_app
print(json.dumps({'cola':celery_app.conf.task_default_queue,
 'modulos':celery_app.conf.include,
 'tareas':[e['task'] for e in celery_app.conf.beat_schedule.values()]}))
"""
    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    config = json.loads(resultado.stdout.strip().splitlines()[-1])
    assert config == {
        "cola": "respaldos",
        "modulos": ["app.tasks.respaldos"],
        "tareas": ["app.tasks.respaldos.respaldo_semanal"],
    }
