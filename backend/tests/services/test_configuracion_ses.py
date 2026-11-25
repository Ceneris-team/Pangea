from scripts.configurar_ses import politicas_iam, registros_dns


def test_politica_envio_limita_identidad_y_remitente():
    politica = politicas_iam(
        "123456789012", "example.com", "us-east-1", "notificaciones@example.com"
    )["ses-envio.json"]
    regla = politica["Statement"][0]
    assert regla["Action"] == "ses:SendEmail"
    assert "*" not in regla["Resource"]
    assert regla["Condition"]["StringEquals"]["ses:FromAddress"] == "notificaciones@example.com"


def test_dns_externo_no_requiere_permisos_route53():
    politica = politicas_iam(
        "123456789012", "example.com", "us-east-1", "notificaciones@example.com"
    )["ses-configuracion.json"]
    acciones = [a for r in politica["Statement"] for a in r["Action"]]
    assert all(not a.startswith("route53:") for a in acciones)


def test_politica_dns_no_modifica_mx_principal_del_dominio():
    politica = politicas_iam(
        "123456789012", "example.com", "us-east-1", "notificaciones@example.com", "Z123"
    )["ses-configuracion.json"]
    regla = next(r for r in politica["Statement"] if r["Sid"] == "PublicarAutenticacionCorreo")
    assert regla["Resource"] == "arn:aws:route53:::hostedzone/Z123"
    permitidos = regla["Condition"]["ForAllValues:StringLike"][
        "route53:ChangeResourceRecordSetsNormalizedRecordNames"
    ]
    assert "example.com" not in permitidos
    assert "avisos.example.com" in permitidos
    assert regla["Condition"]["ForAllValues:StringEquals"][
        "route53:ChangeResourceRecordSetsActions"
    ] == ["CREATE", "UPSERT"]


def test_dns_agrega_dkim_y_mail_from_sin_alterar_el_correo_existente():
    registros = registros_dns("example.com", "us-east-1", ["token1", "token2", "token3"])
    assert len(registros) == 5
    assert all(r["Name"] != "example.com" for r in registros)
    assert [r for r in registros if r["Type"] == "MX"][0]["Name"] == "avisos.example.com"
