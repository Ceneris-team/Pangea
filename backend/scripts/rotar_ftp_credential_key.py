"""
Script de uso ÚNICO (no forma parte de la app en runtime) para rotar
FTP_CREDENTIAL_KEY sin perder las credenciales ya cifradas en
cnxn_ftp.crdncl_cfrd (R-05 del RAID log).

`app/security/ftp_crypto.py` usa una sola Fernet global tomada de
FTP_CREDENTIAL_KEY: no sirve para una migración porque, en el momento de
migrar, unas filas están cifradas con la llave vieja y otras (si el
proceso se interrumpe) quedarían con la nueva. Por eso este script
instancia dos Fernet independientes -OLD y NEW- y nunca toca
ftp_crypto.py ni depende de cuál llave esté activa en el entorno.

Uso:
    # Dry-run (por defecto): no escribe nada, solo reporta.
    FTP_CREDENTIAL_KEY_OLD=... FTP_CREDENTIAL_KEY_NEW=... \\
        python -m scripts.rotar_ftp_credential_key

    # Aplicar de verdad (solo si el dry-run dio 0 fallos):
    FTP_CREDENTIAL_KEY_OLD=... FTP_CREDENTIAL_KEY_NEW=... \\
        python -m scripts.rotar_ftp_credential_key --aplicar

Después de --aplicar: actualizar FTP_CREDENTIAL_KEY en containers.json
(api, worker, beat) al valor NUEVO y recién ahí desplegar.
"""

import argparse
import os
import sys
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.ubicacion_conexion import ConexionFTP


@dataclass
class ResultadoRotacion:
    total: int
    migradas: int
    fallidas: int
    ids_fallidos: list[int]


def rotar_credenciales(
    db: Session, fernet_old: Fernet, fernet_new: Fernet, aplicar: bool
) -> ResultadoRotacion:
    """Función central, reutilizada por el CLI y por los tests.

    En dry-run (aplicar=False) solo descifra con `fernet_old` y cuenta
    éxitos/fallos, sin escribir nada. En modo aplicar, además re-cifra
    con `fernet_new`, actualiza cada fila y hace un único commit al
    final -si algo falla a mitad de camino, rollback completo para
    nunca dejar mezcladas filas viejas y nuevas.

    Nunca imprime ni retorna el valor cifrado o descifrado de ninguna
    credencial: solo ids_fallidos (id_cnxn) y conteos.
    """
    filas = db.query(ConexionFTP).all()
    migradas = 0
    fallidas = 0
    ids_fallidos: list[int] = []

    try:
        for fila in filas:
            try:
                credencial_plana = fernet_old.decrypt(fila.crdncl_cfrd.encode("utf-8"))
            except InvalidToken:
                fallidas += 1
                ids_fallidos.append(fila.id_cnxn)
                print(
                    f"  [FALLO] id_cnxn={fila.id_cnxn} nmbr={fila.nmbr!r}: "
                    "no se pudo descifrar con FTP_CREDENTIAL_KEY_OLD"
                )
                continue

            if aplicar:
                fila.crdncl_cfrd = fernet_new.encrypt(credencial_plana).decode("utf-8")

            migradas += 1

        if aplicar and fallidas == 0:
            db.commit()
        elif aplicar:
            db.rollback()
    except Exception:
        if aplicar:
            db.rollback()
        raise

    return ResultadoRotacion(
        total=len(filas), migradas=migradas, fallidas=fallidas, ids_fallidos=ids_fallidos
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rota FTP_CREDENTIAL_KEY re-cifrando cnxn_ftp.crdncl_cfrd."
    )
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Ejecuta la migración de verdad. Sin este flag, solo hace dry-run.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    key_old = os.environ.get("FTP_CREDENTIAL_KEY_OLD")
    key_new = os.environ.get("FTP_CREDENTIAL_KEY_NEW")

    if not key_old or not key_new:
        print(
            "ERROR: hacen falta las variables de entorno FTP_CREDENTIAL_KEY_OLD "
            "y FTP_CREDENTIAL_KEY_NEW (nunca uses FTP_CREDENTIAL_KEY sola aquí, "
            "para no depender de cuál está activa en el entorno).",
            file=sys.stderr,
        )
        return 1

    fernet_old = Fernet(key_old.encode("utf-8"))
    fernet_new = Fernet(key_new.encode("utf-8"))

    db = SessionLocal()
    try:
        if not args.aplicar:
            print("Modo DRY-RUN (no se escribe nada). Usa --aplicar para ejecutar de verdad.\n")
            resultado = rotar_credenciales(db, fernet_old, fernet_new, aplicar=False)
            print(
                f"\nTotal filas: {resultado.total} | "
                f"migrarían OK: {resultado.migradas} | "
                f"fallarían: {resultado.fallidas}"
            )
            if resultado.fallidas:
                print(
                    "\nHay filas que no se pudieron descifrar con FTP_CREDENTIAL_KEY_OLD. "
                    "No corras --aplicar hasta resolver esto (revisa que sea la llave "
                    "correcta)."
                )
                return 1
            return 0

        print("Modo APLICAR: primero se corre un dry-run de verificación...\n")
        verificacion = rotar_credenciales(db, fernet_old, fernet_new, aplicar=False)
        if verificacion.fallidas:
            print(
                f"\nABORTADO: {verificacion.fallidas} fila(s) no se pudieron descifrar con "
                "FTP_CREDENTIAL_KEY_OLD. No se modificó nada.",
                file=sys.stderr,
            )
            return 1

        print(f"Dry-run OK: {verificacion.total} fila(s) migrarían correctamente.\n")
        print("Re-cifrando y guardando en una sola transacción...\n")
        resultado = rotar_credenciales(db, fernet_old, fernet_new, aplicar=True)

        print(f"\nListo: {resultado.migradas} fila(s) re-cifradas con FTP_CREDENTIAL_KEY_NEW.")
        print(
            "\nActualiza FTP_CREDENTIAL_KEY en containers.json (api, worker, beat) "
            "al valor NUEVO y recién ahí despliega."
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
