"""CLI operativa. Ejecucion: python -m scripts.gestionar_respaldos <comando>."""

import argparse
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description="Respaldos cifrados de Pangea")
    parser.add_argument("--env-file", type=Path, help="Configuracion privada de otro entorno")
    comandos = parser.add_subparsers(dest="comando", required=True)
    backup = comandos.add_parser("crear")
    backup.add_argument("--tipo", choices=["semanal", "manual"], default="manual")
    comandos.add_parser("vigilar")
    comandos.add_parser("listar")
    restore = comandos.add_parser("restaurar-local")
    restore.add_argument("clave", help="Clave S3 del respaldo dentro del entorno configurado")
    args = parser.parse_args()
    load_dotenv(args.env_file or Path(__file__).resolve().parents[2] / ".env")
    try:
        if args.comando == "crear":
            from app.services.respaldos import ejecutar_respaldo

            resultado = ejecutar_respaldo(tipo=args.tipo)
        elif args.comando == "vigilar":
            from app.services.vigilancia_respaldos import comprobar_respaldo

            resultado = comprobar_respaldo()
        elif args.comando == "listar":
            from app.services.almacen_respaldos import listar

            resultado = [
                {"clave": obj["Key"], "bytes": obj["Size"]}
                for obj in listar()
                if obj["Key"].endswith(".dump.enc")
            ]
        else:
            from app.services.restauracion_respaldos import restaurar_local

            resultado = restaurar_local(args.clave, os.environ["BACKUP_RESTORE_DATABASE_URL"])
        print(json.dumps(resultado, ensure_ascii=True))
        if args.comando == "vigilar" and resultado.get("estado") == "Alerta":
            raise SystemExit(2)
    except Exception as exc:
        # Las excepciones de SQLAlchemy/libpq pueden incluir secretos.
        logging.error("La operacion fallo. Codigo: %s", type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
