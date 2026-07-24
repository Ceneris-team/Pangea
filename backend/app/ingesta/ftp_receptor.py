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
import logging

from app.security.ftp_crypto import decrypt_credential

logger = logging.getLogger(__name__)

EXTENSION_DAT = ".dat"


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
        nombres = ftp.nlst()

    return [n for n in nombres if n.lower().endswith(EXTENSION_DAT)]
