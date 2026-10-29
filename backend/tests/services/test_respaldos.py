"""Tests del respaldo extendido (HT-06, PP-129).

No tocan Postgres ni un bucket real: la lógica pura se prueba directo y la
orquestación mockea pg_dump/openssl (generar_respaldo_cifrado) y el cliente de
Object Storage. Así corren sin infraestructura, igual que un test unitario."""

import datetime as dt
import os

import pytest

from app.services import respaldos


def test_url_libpq_quita_sufijo_driver():
    assert (
        respaldos._url_libpq("postgresql+psycopg2://u:p@host:5432/db")
        == "postgresql://u:p@host:5432/db"
    )


def test_url_libpq_deja_igual_una_url_ya_libpq():
    assert respaldos._url_libpq("postgresql://u:p@host/db") == "postgresql://u:p@host/db"


def test_clave_respaldo_incluye_prefijo_y_fecha(monkeypatch):
    monkeypatch.delenv("BACKUP_PREFIX", raising=False)
    assert respaldos.clave_respaldo(dt.date(2026, 3, 9)) == "respaldos/pangea-2026-03-09.sql.gz.enc"


def test_clave_respaldo_respeta_prefijo_configurado(monkeypatch):
    monkeypatch.setenv("BACKUP_PREFIX", "backups/pangea/")
    assert respaldos.clave_respaldo(dt.date(2026, 3, 9)) == "backups/pangea/pangea-2026-03-09.sql.gz.enc"


def test_expirados_solo_marca_los_mas_viejos_que_el_limite():
    limite = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    objetos = [
        {"Key": "respaldos/viejo.enc", "LastModified": dt.datetime(2025, 6, 1, tzinfo=dt.timezone.utc)},
        {"Key": "respaldos/nuevo.enc", "LastModified": dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)},
        {"Key": "respaldos/sin-fecha.enc"},
    ]
    assert respaldos._expirados(objetos, limite) == ["respaldos/viejo.enc"]


def test_aplicar_retencion_borra_los_expirados(monkeypatch):
    monkeypatch.delenv("BACKUP_PREFIX", raising=False)
    monkeypatch.setenv("BACKUP_RETENTION_DAYS", "365")
    hoy = dt.date(2026, 1, 1)
    objetos = [
        {"Key": "respaldos/viejo.enc", "LastModified": dt.datetime(2024, 12, 1, tzinfo=dt.timezone.utc)},
        {"Key": "respaldos/reciente.enc", "LastModified": dt.datetime(2025, 12, 20, tzinfo=dt.timezone.utc)},
    ]
    borrados = []
    monkeypatch.setattr(respaldos.object_storage, "listar", lambda prefijo: objetos)
    monkeypatch.setattr(respaldos.object_storage, "eliminar", lambda claves: borrados.extend(claves))

    resultado = respaldos.aplicar_retencion(hoy)

    assert resultado == ["respaldos/viejo.enc"]
    assert borrados == ["respaldos/viejo.enc"]


def test_generar_respaldo_cifrado_exige_llave(monkeypatch, tmp_path):
    monkeypatch.delenv("BACKUP_ENCRYPTION_KEY", raising=False)
    with pytest.raises(respaldos.RespaldoError, match="BACKUP_ENCRYPTION_KEY"):
        respaldos.generar_respaldo_cifrado(str(tmp_path / "x.enc"))


def test_ejecutar_respaldo_sube_y_limpia_el_temporal(monkeypatch):
    monkeypatch.delenv("BACKUP_PREFIX", raising=False)
    rutas_generadas = []

    def fake_generar(ruta):
        with open(ruta, "wb") as f:
            f.write(b"dump-cifrado")
        rutas_generadas.append(ruta)

    subidos = []
    monkeypatch.setattr(respaldos, "generar_respaldo_cifrado", fake_generar)
    monkeypatch.setattr(
        respaldos.object_storage, "subir_archivo", lambda ruta, clave: subidos.append((ruta, clave))
    )
    monkeypatch.setattr(respaldos.object_storage, "listar", lambda prefijo: [])
    monkeypatch.setattr(respaldos.object_storage, "eliminar", lambda claves: None)

    resultado = respaldos.ejecutar_respaldo(dt.date(2026, 3, 9))

    assert resultado["clave"] == "respaldos/pangea-2026-03-09.sql.gz.enc"
    assert resultado["bytes"] == len(b"dump-cifrado")
    assert resultado["borrados_por_retencion"] == 0
    # El temporal se subió y después se borró: no queda nada en disco.
    assert subidos[0][1] == "respaldos/pangea-2026-03-09.sql.gz.enc"
    assert not os.path.exists(rutas_generadas[0])


def test_ejecutar_respaldo_borra_el_temporal_aunque_falle_la_subida(monkeypatch):
    rutas_generadas = []

    def fake_generar(ruta):
        with open(ruta, "wb") as f:
            f.write(b"x")
        rutas_generadas.append(ruta)

    def falla_subida(ruta, clave):
        raise RuntimeError("bucket caido")

    monkeypatch.setattr(respaldos, "generar_respaldo_cifrado", fake_generar)
    monkeypatch.setattr(respaldos.object_storage, "subir_archivo", falla_subida)

    with pytest.raises(RuntimeError, match="bucket caido"):
        respaldos.ejecutar_respaldo(dt.date(2026, 3, 9))

    assert not os.path.exists(rutas_generadas[0])
