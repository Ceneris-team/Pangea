"""
PP-100 (HU06): persiste las lecturas ya validadas (PP-99) en tlmtr, la
tabla de telemetría que ya existe en el esquema (HT-08, ver
app.models.telemetria.Telemetria) - no se crea tabla nueva.

tlmtr.vlr es NOT NULL, así que las lecturas con valor vacío en origen
(LecturaValidada.valor is None) se consideran válidas semánticamente pero
no persistibles como medición numérica: se cuentan aparte y no generan
fila en tlmtr. Si en el futuro se necesita conservar "vacíos" como
lecturas reales, requiere volver nullable tlmtr.vlr (decisión de negocio,
fuera de alcance de PP-97..100).
"""
import dataclasses
import datetime as dt
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.mapeo_dispositivo import Dispositivo, Parametro
from app.models.telemetria import Telemetria
from app.models.ubicacion_conexion import Ubicacion
from app.services.ingesta.validador import LecturaValidada
from app.services.particiones import (
    ParticionInexistenteError,
    es_error_de_particion_faltante,
)

logger = logging.getLogger(__name__)


class DispositivoNoResueltoError(Exception):
    """La conexión FTP no tiene exactamente un dispositivo activo asociado.

    Error de datos/configuración, no transitorio: no tiene sentido
    reintentar automáticamente (ver app.tasks.ingesta)."""


@dataclasses.dataclass
class ResultadoPersistencia:
    guardadas: int
    omitidas_sin_valor: int
    omitidas_parametro_desconocido: list  # nombres de parámetro sin fila en prmtr


def resolver_dispositivo(db: Session, id_cnxn: int) -> Dispositivo:
    """Un dispositivo activo por conexión FTP (ver decisión de producto:
    mientras PP-96 no defina soporte multi-dispositivo por conexión, se
    asume 1:1)."""
    dispositivos = (
        db.query(Dispositivo)
        .filter(Dispositivo.id_cnxn == id_cnxn, Dispositivo.estd == "Activo")
        .all()
    )
    if len(dispositivos) != 1:
        raise DispositivoNoResueltoError(
            f"cnxn_ftp id={id_cnxn} tiene {len(dispositivos)} dispositivos activos "
            "asociados (se esperaba exactamente 1)"
        )
    return dispositivos[0]


def _mapa_parametros(db: Session) -> dict:
    return {p.nmbr: p.id_prmtr for p in db.query(Parametro).all()}


def guardar_lecturas(
    db: Session,
    lecturas: list,
    dispositivo: Dispositivo,
    id_archv: int,
) -> ResultadoPersistencia:
    """Inserta en tlmtr una fila por LecturaValidada con valor numérico.
    No hace commit -el llamador controla la transacción, igual que el
    resto de app.tasks.ingesta-."""
    parametros = _mapa_parametros(db)
    ubicacion = db.get(Ubicacion, dispositivo.id_ubccn)
    guardadas = 0
    omitidas_sin_valor = 0
    parametros_desconocidos = set()

    for lectura in lecturas:
        if lectura.valor is None:
            omitidas_sin_valor += 1
            continue

        id_prmtr = parametros.get(lectura.parametro)
        if id_prmtr is None:
            parametros_desconocidos.add(lectura.parametro)
            continue

        db.add(Telemetria(
            fch_hr=lectura.fecha_hora,
            id_dspstv=dispositivo.id_dspstv,
            id_prmtr=id_prmtr,
            id_sd=ubicacion.id_sd,
            vlr=lectura.valor,
            id_archv=id_archv,
        ))
        guardadas += 1

    # flush explícito para que el INSERT viaje a Postgres AQUÍ y no en el
    # commit del llamador: es la única forma de traducir el fallo por
    # partición faltante (HT-08 CA4) a un error de dominio con contexto
    # útil. Sin esto, el llamador recibiría un IntegrityError crudo desde
    # dentro de db.commit(), sin saber qué fecha lo causó.
    if guardadas:
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            if es_error_de_particion_faltante(exc):
                fechas = sorted({
                    l.fecha_hora for l in lecturas if l.valor is not None
                })
                rango = (
                    f"{fechas[0]:%Y-%m-%d} .. {fechas[-1]:%Y-%m-%d}"
                    if fechas else "desconocido"
                )
                raise ParticionInexistenteError(
                    f"No existe partición de tlmtr para las lecturas del archivo "
                    f"id_archv={id_archv} (rango {rango}). El job "
                    f"app.tasks.particiones.asegurar_particiones_futuras crea las "
                    f"particiones futuras; si la fecha es muy antigua o muy lejana, "
                    f"revisa la configuración de fecha del datalogger."
                ) from exc
            raise

    if parametros_desconocidos:
        logger.warning(
            "Parámetros sin fila en prmtr, lecturas descartadas: %s",
            sorted(parametros_desconocidos),
        )

    return ResultadoPersistencia(
        guardadas=guardadas,
        omitidas_sin_valor=omitidas_sin_valor,
        omitidas_parametro_desconocido=sorted(parametros_desconocidos),
    )
