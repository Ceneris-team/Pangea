"""La solicitud y el estado del archivo se confirman en la misma transacción.

Cada ejecución tiene su fila; un fallo transitorio conserva el intento terminado
y crea el siguiente. El despachador puede repetir mensajes sin repetir trabajo.
"""

import datetime as dt

from app.models import IntentoProcesamiento

MAX_REINTENTOS = 5


def ahora():
    return dt.datetime.now(dt.timezone.utc)


def solicitar(db, archivo, id_usr, *, anterior=None, demora=0):
    from app.services.ingesta.log import capturar_origen

    capturar_origen(db, archivo)
    intento = IntentoProcesamiento(
        id_archv=archivo.id_archv,
        id_usr=id_usr,
        rsltd="Pendiente",
        fch_intnt=ahora(),
        proximo_envio=ahora() + dt.timedelta(seconds=demora),
        reintentos=anterior.reintentos + 1 if anterior else 0,
        id_intento_anterior=anterior.id_intnt if anterior else None,
    )
    archivo.estd = "Pendiente"
    archivo.fch_prcsd = None
    archivo.rgstrs_prcsds = None
    # El motivo anterior permanece visible hasta que este intento termine.
    db.add(intento)
    return intento


def finalizar(intento, resultado, mensaje=None, registros=None, *, db, archivo, rechazados=None):
    intento.rsltd = resultado
    intento.mnsj_errr = mensaje[:500] if mensaje else None
    intento.fch_fin = ahora()
    intento.proximo_envio = None
    intento.registros_guardados = registros
    from app.services.ingesta.log import registrar_evento

    registrar_evento(db, archivo, intento, mensaje, rechazados=rechazados, origen="Reproceso")
