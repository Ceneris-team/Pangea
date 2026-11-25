"""
HU 05 - Conectar datalogger vía FTP
HT-05 CA1 - Cada archivo .dat recibido por FTP genera un job en la cola
sin bloquear la recepción de nuevos archivos.

Solo cubre prtcl='FTP' (polling: conectar, listar, detectar nuevos). El
protocolo 'TCP' de cnxn_ftp es un mecanismo distinto (el datalogger empuja
datos por socket) que no se puede sondear de la misma forma; queda fuera
de esta pieza.
"""

import ftplib
import hashlib
import io
import logging

from app.security.ftp_crypto import decrypt_credential

logger = logging.getLogger(__name__)

EXTENSION_DAT = ".dat"


class ArchivoRemoto(str):
    def __new__(cls, nombre, version=None):
        archivo = super().__new__(cls, nombre)
        archivo.version = version
        return archivo


def listar_archivos_dat(cnxn) -> list[str]:
    """Se conecta a la conexión FTP y devuelve los nombres de archivo .dat
    en rt_rmt. cnxn es una instancia de app.models.ConexionFTP con
    prtcl='FTP'. Levanta ftplib.all_errors si la conexión falla -el
    llamador decide si eso dispara un reintento de Celery-."""
    password = decrypt_credential(cnxn.crdncl_cfrd)

    with ftplib.FTP() as ftp:
        ftp.connect(host=cnxn.hst, port=cnxn.prt, timeout=30)
        ftp.login(user=cnxn.usr_ftp, passwd=password)
        ftp.cwd(cnxn.rt_rmt)
        try:
            entradas = list(ftp.mlsd(facts=["type", "size", "modify"]))
        except ftplib.error_perm:
            entradas = []
            for nombre in ftp.nlst():
                if not nombre.lower().endswith(EXTENSION_DAT):
                    continue
                hechos = {}
                try:
                    ftp.voidcmd("TYPE I")
                    hechos["size"] = str(ftp.size(nombre))
                    hechos["modify"] = ftp.sendcmd(f"MDTM {nombre}")[4:]
                except ftplib.error_perm:
                    pass
                entradas.append((nombre, hechos))
    return [
        ArchivoRemoto(
            nombre,
            (
                hashlib.sha256(
                    f"{hechos.get('size', '')}:{hechos.get('modify', '')}".encode()
                ).hexdigest()
                if hechos.get("size") or hechos.get("modify")
                else None
            ),
        )
        for nombre, hechos in entradas
        if nombre.lower().endswith(EXTENSION_DAT) and hechos.get("type", "file") == "file"
    ]


def descargar_archivo_dat(cnxn, nombre_archivo: str, encoding: str = "utf-8") -> str:
    """Descarga un .dat puntual de rt_rmt y devuelve su contenido como
    texto (PP-97 trabaja sobre texto, no sobre bytes). Igual que
    listar_archivos_dat, levanta ftplib.all_errors si la conexión falla
    -el llamador (Celery task) decide si eso dispara reintento-."""
    return descargar_bytes_dat(cnxn, nombre_archivo).decode(encoding)


def descargar_bytes_dat(cnxn, nombre_archivo: str) -> bytes:
    password = decrypt_credential(cnxn.crdncl_cfrd)
    buffer = io.BytesIO()

    with ftplib.FTP() as ftp:
        ftp.connect(host=cnxn.hst, port=cnxn.prt, timeout=30)
        ftp.login(user=cnxn.usr_ftp, passwd=password)
        ftp.cwd(cnxn.rt_rmt)
        ftp.retrbinary(f"RETR {nombre_archivo}", buffer.write)

    return buffer.getvalue()
