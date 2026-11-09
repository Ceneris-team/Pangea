"""Aprovisiona o comprueba SES y genera los registros DNS requeridos.

python scripts/configurar_ses.py --domain example.com --region us-east-1 --apply
python scripts/configurar_ses.py --domain example.com --hosted-zone-id Z... --apply-dns
python scripts/configurar_ses.py --domain example.com --check

Sin --apply / --apply-dns solo consulta. Nunca envía correos.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv


def politicas_iam(
    account_id,
    domain,
    region,
    remitente,
    hosted_zone_id=None,
    test_recipient=None,
    configuration_sets=(),
):
    identidad = f"arn:aws:ses:{region}:{account_id}:identity/{domain}"
    identidad_correo = f"arn:aws:ses:{region}:{account_id}:identity/{remitente}"
    envio = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "EnviarNotificacionesPangea",
                "Effect": "Allow",
                "Action": "ses:SendEmail",
                "Resource": [identidad, identidad_correo],
                "Condition": {"StringEquals": {"ses:FromAddress": remitente}},
            }
        ],
    }
    if test_recipient:
        # En sandbox SES también autoriza el recurso de la identidad destinataria.
        envio["Statement"][0]["Resource"].append(
            f"arn:aws:ses:{region}:{account_id}:identity/{test_recipient}"
        )
        envio["Statement"][0]["Condition"]["ForAllValues:StringEquals"] = {
            "ses:Recipients": [test_recipient]
        }
    for nombre in sorted(set(configuration_sets)):
        envio["Statement"][0]["Resource"].append(
            f"arn:aws:ses:{region}:{account_id}:configuration-set/{nombre}"
        )
    configuracion = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ConsultarEstadoSES",
                "Effect": "Allow",
                "Action": ["ses:GetAccount", "ses:ListEmailIdentities"],
                "Resource": "*",
            },
            {
                "Sid": "ConfigurarDominioPangea",
                "Effect": "Allow",
                "Action": [
                    "ses:CreateEmailIdentity",
                    "ses:GetEmailIdentity",
                    "ses:PutEmailIdentityDkimAttributes",
                    "ses:PutEmailIdentityMailFromAttributes",
                ],
                "Resource": [identidad, identidad_correo],
            },
            {
                "Sid": "LocalizarZonaDNS",
                "Effect": "Allow",
                "Action": "route53:ListHostedZones",
                "Resource": "*",
            },
            {
                "Sid": "ConsultarZonaDNS",
                "Effect": "Allow",
                "Action": "route53:GetHostedZone",
                "Resource": f"arn:aws:route53:::hostedzone/{hosted_zone_id or '*'}",
            },
            {
                "Sid": "PublicarAutenticacionCorreo",
                "Effect": "Allow",
                "Action": "route53:ChangeResourceRecordSets",
                "Resource": f"arn:aws:route53:::hostedzone/{hosted_zone_id or '*'}",
                "Condition": {
                    "ForAllValues:StringLike": {
                        "route53:ChangeResourceRecordSetsNormalizedRecordNames": [
                            f"*._domainkey.{domain}",
                            f"avisos.{domain}",
                        ]
                    },
                    "ForAllValues:StringEquals": {
                        "route53:ChangeResourceRecordSetsRecordTypes": ["CNAME", "MX", "TXT"],
                        "route53:ChangeResourceRecordSetsActions": ["CREATE", "UPSERT"],
                    },
                },
            },
        ],
    }
    if hosted_zone_id is None:
        # DNS externo (por ejemplo GoDaddy): no pedir permisos Route53.
        configuracion["Statement"] = configuracion["Statement"][:2]
    return {"ses-envio.json": envio, "ses-configuracion.json": configuracion}


def registros_dns(domain, region, tokens):
    mail_from = f"avisos.{domain}"
    return [
        {
            "Name": f"{token}._domainkey.{domain}",
            "Type": "CNAME",
            "TTL": 300,
            "ResourceRecords": [{"Value": f"{token}.dkim.amazonses.com"}],
        }
        for token in tokens
    ] + [
        {
            "Name": mail_from,
            "Type": "MX",
            "TTL": 300,
            "ResourceRecords": [{"Value": f"10 feedback-smtp.{region}.amazonses.com"}],
        },
        {
            "Name": mail_from,
            "Type": "TXT",
            "TTL": 300,
            "ResourceRecords": [{"Value": '"v=spf1 include:amazonses.com ~all"'}],
        },
    ]


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--from-email", default=os.environ.get("SES_FROM_EMAIL"))
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE"))
    parser.add_argument(
        "--test-recipient",
        default=os.environ.get("SES_TEST_RECIPIENT"),
        help="Autorizar únicamente este destinatario en la política de pruebas",
    )
    parser.add_argument("--iam-dir", type=Path, help="Guardar políticas IAM sin modificar AWS")
    parser.add_argument(
        "--configuration-set",
        action="append",
        default=[],
        help="Configuration set adicional que debe autorizar la política de envío",
    )
    parser.add_argument("--region", default=os.environ.get("SES_REGION", "us-east-1"))
    parser.add_argument("--apply", action="store_true", help="Crear identidad y MAIL FROM")
    parser.add_argument("--hosted-zone-id")
    parser.add_argument("--apply-dns", action="store_true", help="Publicar registros en Route53")
    parser.add_argument(
        "--check", action="store_true", help="Exit 2 si la cuenta o DNS no están listos"
    )
    args = parser.parse_args()
    domain = args.domain.strip().lower().rstrip(".")
    from email_validator import validate_email

    validate_email(f"notificaciones@{domain}", check_deliverability=False)
    remitente = str(
        validate_email(
            args.from_email or f"notificaciones@{domain}", check_deliverability=False
        ).normalized
    )
    if remitente.rsplit("@", 1)[1] != domain:
        parser.error("El remitente debe pertenecer al dominio indicado")
    destino_prueba = (
        str(validate_email(args.test_recipient, check_deliverability=False).normalized)
        if args.test_recipient
        else None
    )
    session = boto3.Session(profile_name=args.profile)
    if args.iam_dir:
        cuenta_id = session.client(
            "sts", config=Config(connect_timeout=5, read_timeout=15)
        ).get_caller_identity()["Account"]
        conjuntos = set(args.configuration_set)
        explicito = os.environ.get("SES_CONFIGURATION_SET", "").strip()
        if explicito:
            conjuntos.add(explicito)
        consulta = session.client(
            "sesv2",
            region_name=args.region,
            config=Config(connect_timeout=5, read_timeout=15),
        )
        for nombre in dict.fromkeys((domain, remitente)):
            try:
                identidad_actual = consulta.get_email_identity(EmailIdentity=nombre)
            except ClientError as exc:
                codigo = exc.response.get("Error", {}).get("Code", "")
                if codigo == "NotFoundException":
                    continue
                if codigo in {"AccessDenied", "AccessDeniedException"}:
                    print(
                        f"Aviso: sin permiso para consultar la configuración de {nombre}; "
                        "si tiene un configuration set, indíquelo con --configuration-set.",
                        file=sys.stderr,
                    )
                    continue
                raise
            predeterminado = identidad_actual.get("ConfigurationSetName")
            if predeterminado:
                conjuntos.add(predeterminado)
        args.iam_dir.mkdir(parents=True, exist_ok=True)
        for nombre, contenido in politicas_iam(
            cuenta_id,
            domain,
            args.region,
            remitente,
            args.hosted_zone_id,
            destino_prueba,
            configuration_sets=conjuntos,
        ).items():
            archivo = args.iam_dir / nombre
            archivo.write_text(json.dumps(contenido, indent=2) + "\n", encoding="utf-8")
            print(f"Política IAM preparada: {archivo}")
        return 0
    ses = session.client(
        "sesv2", region_name=args.region, config=Config(connect_timeout=5, read_timeout=15)
    )
    if args.apply:
        try:
            ses.create_email_identity(
                EmailIdentity=domain, DkimSigningAttributes={"NextSigningKeyLength": "RSA_2048_BIT"}
            )
        except ses.exceptions.AlreadyExistsException:
            pass
        ses.put_email_identity_dkim_attributes(EmailIdentity=domain, SigningEnabled=True)
        ses.put_email_identity_mail_from_attributes(
            EmailIdentity=domain,
            MailFromDomain=f"avisos.{domain}",
            BehaviorOnMxFailure="REJECT_MESSAGE",
        )
    identidad = ses.get_email_identity(EmailIdentity=domain)
    cuenta = ses.get_account()
    dkim = identidad.get("DkimAttributes", {})
    mail_from = identidad.get("MailFromAttributes", {})
    registros = registros_dns(domain, args.region, dkim.get("Tokens", []))
    if args.apply_dns:
        if not args.hosted_zone_id:
            parser.error("--apply-dns requiere --hosted-zone-id")
        route53 = session.client("route53", config=Config(connect_timeout=5, read_timeout=15))
        zona = route53.get_hosted_zone(Id=args.hosted_zone_id)["HostedZone"]["Name"].rstrip(".")
        if domain != zona and not domain.endswith(f".{zona}"):
            parser.error("La zona DNS no contiene el dominio indicado")
        if not dkim.get("Tokens"):
            parser.error("La identidad no tiene tokens DKIM; usar --apply primero")
        route53.change_resource_record_sets(
            HostedZoneId=args.hosted_zone_id,
            ChangeBatch={
                "Comment": "Pangea HT-14 SES DKIM y MAIL FROM",
                "Changes": [{"Action": "UPSERT", "ResourceRecordSet": r} for r in registros],
            },
        )
    listo = all(
        (
            identidad.get("VerifiedForSendingStatus"),
            dkim.get("SigningEnabled"),
            dkim.get("Status") == "SUCCESS",
            mail_from.get("MailFromDomainStatus") == "SUCCESS",
            cuenta.get("SendingEnabled"),
            cuenta.get("ProductionAccessEnabled"),
        )
    )
    print(
        json.dumps(
            {
                "dominio": domain,
                "region": args.region,
                "listo": bool(listo),
                "verificado": identidad.get("VerifiedForSendingStatus"),
                "dkim": dkim.get("Status"),
                "mail_from": mail_from.get("MailFromDomainStatus"),
                "envio_habilitado": cuenta.get("SendingEnabled"),
                "acceso_produccion": cuenta.get("ProductionAccessEnabled"),
                "dns": registros,
                "configuracion": {
                    "SES_REGION": args.region,
                    "SES_FROM_EMAIL": remitente,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 2 if args.check and not listo else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BotoCoreError, ClientError) as exc:
        # No imprimir credenciales, cabeceras ni mensajes completos del proveedor.
        codigo = (
            exc.response.get("Error", {}).get("Code", type(exc).__name__)
            if isinstance(exc, ClientError)
            else type(exc).__name__
        )
        print(f"No se pudo completar la configuración SES: {codigo}", file=sys.stderr)
        sys.exit(1)
