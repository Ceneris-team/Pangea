from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.services.exportaciones_storage import AlmacenExportaciones


@pytest.fixture()
def almacen():
    client = MagicMock()
    client.get_bucket_acl.return_value = {"Grants": []}
    client.get_bucket_policy_status.return_value = {"PolicyStatus": {"IsPublic": False}}
    with patch("app.services.exportaciones_storage.boto3.client", return_value=client):
        yield AlmacenExportaciones("privado"), client


def test_no_sube_a_bucket_con_politica_publica(almacen, tmp_path):
    storage, client = almacen
    client.get_bucket_policy_status.return_value = {"PolicyStatus": {"IsPublic": True}}
    with pytest.raises(RuntimeError, match="pública"):
        storage.subir(tmp_path / "no-importa.csv", "archivo.csv", "csv")
    client.put_object.assert_not_called()


@pytest.mark.parametrize("grupo", ["AllUsers", "AuthenticatedUsers"])
def test_no_sube_a_bucket_con_acl_publica(almacen, grupo):
    storage, client = almacen
    client.get_bucket_acl.return_value = {
        "Grants": [{"Grantee": {"URI": "http://acs.amazonaws.com/groups/global/" + grupo}}]
    }
    with pytest.raises(RuntimeError, match="privado"):
        storage.verificar_privado()


def test_preserva_version_para_eliminacion_real(almacen):
    storage, client = almacen
    storage.eliminar("exportaciones/1/a.csv", "version-1")
    client.delete_object.assert_called_once_with(
        Bucket="privado", Key="exportaciones/1/a.csv", VersionId="version-1"
    )


def test_bucket_sin_politica_no_implica_publico(almacen):
    storage, client = almacen
    client.get_bucket_policy_status.side_effect = ClientError(
        {"Error": {"Code": "NoSuchBucketPolicy"}}, "GetBucketPolicyStatus"
    )
    storage.verificar_privado()


def test_no_asume_privacidad_si_no_puede_verificarla(almacen):
    storage, client = almacen
    client.get_bucket_policy_status.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied"}}, "GetBucketPolicyStatus"
    )
    with pytest.raises(ClientError):
        storage.verificar_privado()


def test_limpieza_versionada_no_toca_otras_exportaciones(almacen):
    storage, client = almacen
    client.get_bucket_versioning.return_value = {"Status": "Enabled"}
    client.get_paginator.return_value.paginate.return_value = [
        {
            "Versions": [
                {"Key": "exportaciones/a.csv", "VersionId": "1"},
                {"Key": "exportaciones/a.csv", "VersionId": "2"},
                {"Key": "exportaciones/a.csv-otro", "VersionId": "3"},
            ],
            "DeleteMarkers": [{"Key": "exportaciones/a.csv", "VersionId": "4"}],
        }
    ]
    client.delete_objects.return_value = {}
    storage.eliminar("exportaciones/a.csv")
    assert client.delete_objects.call_args.kwargs["Delete"]["Objects"] == [
        {"Key": "exportaciones/a.csv", "VersionId": "1"},
        {"Key": "exportaciones/a.csv", "VersionId": "2"},
        {"Key": "exportaciones/a.csv", "VersionId": "4"},
    ]


def test_no_confirma_borrado_si_s3_informa_errores_parciales(almacen):
    storage, client = almacen
    client.get_bucket_versioning.return_value = {"Status": "Enabled"}
    client.get_paginator.return_value.paginate.return_value = [
        {"Versions": [{"Key": "a.csv", "VersionId": "1"}]}
    ]
    client.delete_objects.return_value = {"Errors": [{"Code": "AccessDenied"}]}
    with pytest.raises(RuntimeError):
        storage.eliminar("a.csv")
