"""Original inmutable por recepción, también disponible si desaparece del FTP."""

import hashlib

from app.models import Dispositivo
from app.services import object_storage
from app.services.ingesta.persistencia import DispositivoNoResueltoError


def dispositivo_del_archivo(db, archivo):
    if archivo.id_dspstv is None:
        # No atribuir archivos antiguos de una conexión reutilizada al nuevo equipo.
        equipos = db.query(Dispositivo).filter_by(id_cnxn=archivo.id_cnxn).all()
        if len(equipos) != 1:
            raise DispositivoNoResueltoError(
                "El archivo no tiene equipo de origen inequívoco; requiere revisión técnica"
            )
        archivo.id_dspstv = equipos[0].id_dspstv
    dispositivo = db.get(Dispositivo, archivo.id_dspstv)
    if dispositivo is None:
        raise DispositivoNoResueltoError("El equipo original del archivo no existe")
    return dispositivo


def conservar_original(archivo, datos):
    if archivo.sha256:
        return
    archivo.sha256 = hashlib.sha256(datos).hexdigest()
    if object_storage.esta_configurado():
        clave = (
            f"datos-crudos/cnxn-{archivo.id_cnxn}/archivo-{archivo.id_archv}/"
            f"{archivo.sha256}.dat"
        )
        object_storage.subir_contenido(datos, clave)
        archivo.clave_original = clave
    else:
        archivo.contenido_original = datos


def leer_original(archivo):
    if archivo.clave_original:
        datos = (
            object_storage.cliente_s3()
            .get_object(Bucket=object_storage.bucket(), Key=archivo.clave_original)["Body"]
            .read()
        )
    else:
        datos = archivo.contenido_original
    if datos is not None and hashlib.sha256(datos).hexdigest() != archivo.sha256:
        raise ValueError("La copia del archivo original no coincide con su huella")
    return datos
