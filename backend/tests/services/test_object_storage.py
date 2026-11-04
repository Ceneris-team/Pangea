"""Tests del cliente de Object Storage (HT-06). Se mockea el cliente boto3;
no se toca ningún bucket real. Cubre los helpers que agregó PP-127 (CA3) para
archivar el .dat crudo: esta_configurado, clave_dat y subir_contenido."""

import datetime as dt
from unittest.mock import MagicMock

from app.services import object_storage


def test_esta_configurado_true_con_bucket(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "pangea-storage-prod")
    assert object_storage.esta_configurado() is True


def test_esta_configurado_false_sin_bucket(monkeypatch):
    monkeypatch.delenv("OBJECT_STORAGE_BUCKET", raising=False)
    assert object_storage.esta_configurado() is False


def test_clave_dat_particiona_por_conexion_y_periodo():
    clave = object_storage.clave_dat(7, "H_2026.dat", fecha=dt.date(2026, 3, 9))
    assert clave == "datos-crudos/cnxn-7/2026/03/H_2026.dat"


def test_subir_contenido_usa_put_object_sin_archivo_temporal(monkeypatch):
    cliente = MagicMock()
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "mi-bucket")
    monkeypatch.setattr(object_storage, "cliente_s3", lambda: cliente)

    object_storage.subir_contenido(
        b"datos crudos", "datos-crudos/cnxn-1/2026/03/x.dat", content_type="text/plain"
    )

    cliente.put_object.assert_called_once_with(
        Bucket="mi-bucket",
        Key="datos-crudos/cnxn-1/2026/03/x.dat",
        Body=b"datos crudos",
        ContentType="text/plain",
    )
