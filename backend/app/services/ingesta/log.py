"""Historial de HU37. Se confirma junto con el resultado, nunca con otro commit."""

import datetime as dt
import re

from app.models import ConexionFTP, Dispositivo, LogIngesta, Ubicacion

DIAS_CONSERVACION = 90


def limite_conservacion():
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=DIAS_CONSERVACION)


def mensaje_seguro(mensaje):
    if not mensaje:
        return None
    texto = str(mensaje)
    # No publicar SQL ni los parámetros de conexión de errores del motor.
    if "[SQL:" in texto or "[parameters:" in texto:
        return "Error al guardar los datos. Requiere revisión técnica."
    texto = re.sub(r"(\w+://)[^\s/@]+(?::[^\s/@]*)?@", r"\1[oculto]@", texto)
    texto = re.sub(
        r"""(?i)((?:password|passwd|pwd|contraseña|clave|secret|token|api[_-]?key|credential|crdncl_cfrd|signature)[\w-]*["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;&]+)""",
        r"\1[oculto]",
        texto,
    )
    return re.sub(r"(?i)Bearer\s+\S+", "Bearer [oculto]", texto)


def capturar_origen(db, archivo):
    if archivo.origen_ingesta is not None:
        return archivo.origen_ingesta
    conexion = db.get(ConexionFTP, archivo.id_cnxn)
    equipo = db.get(Dispositivo, archivo.id_dspstv) if archivo.id_dspstv else None
    proyecto = db.get(Ubicacion, equipo.id_ubccn) if equipo else None
    archivo.origen_ingesta = dict(
        id_cnxn=archivo.id_cnxn,
        id_dspstv=archivo.id_dspstv,
        id_sd=conexion.id_sd,
        id_ubccn=proyecto.id_ubccn if proyecto else None,
        archivo=archivo.nmbr_archv,
        datalogger=equipo.nmbr if equipo else f"{conexion.nmbr} · equipo sin identificar",
        proyecto=proyecto.nmbr if proyecto else None,
    )
    return archivo.origen_ingesta


def registrar_evento(db, archivo, intento, mensaje=None, rechazados=None, origen=None):
    instantanea = capturar_origen(db, archivo)
    db.flush()
    if db.query(LogIngesta.id_evento).filter_by(id_intnt=intento.id_intnt).first():
        return
    db.add(
        LogIngesta(
            id_archv=archivo.id_archv,
            id_intnt=intento.id_intnt,
            **instantanea,
            fecha=intento.fch_inicio or intento.fch_intnt,
            recepcion=archivo.fch_dtccn,
            inicio=intento.fch_inicio,
            fin=intento.fch_fin,
            resultado=intento.rsltd,
            mensaje=mensaje_seguro(mensaje if mensaje is not None else intento.mnsj_errr),
            registros_procesados=intento.registros_guardados,
            registros_rechazados=rechazados,
            origen=origen or ("Reproceso" if intento.id_usr else "Automático"),
        )
    )
