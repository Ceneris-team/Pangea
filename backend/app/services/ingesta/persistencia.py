"""
PP-100 (HU06): persiste las lecturas ya validadas (PP-99) en tlmtr, la
tabla de telemetría que ya existe en el esquema (HT-08, ver
app.models.telemetria.Telemetria) - no se crea tabla nueva para mediciones
numéricas.

tlmtr.vlr es NOT NULL, así que las lecturas con valor vacío en origen
(LecturaValidada.valor is None) se consideran válidas semánticamente pero
no persistibles como medición numérica: se cuentan aparte y no generan
fila en tlmtr. Si en el futuro se necesita conservar "vacíos" como
lecturas reales, requiere volver nullable tlmtr.vlr (decisión de negocio,
fuera de alcance de PP-97..100).

Una LecturaValidada con valor de tipo str (prmtr.tipo_dato='texto', ver
validador.py) es un EVENTO, no una medición: va a evnt_txt en vez de
tlmtr -no se puede mezclar "23.5" con "Puerta Abierta" en la misma
columna Numeric-.
"""

import dataclasses
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.evento_texto import EventoTexto
from app.models.mapeo_dispositivo import Dispositivo, Parametro
from app.models.telemetria import Telemetria
from app.models.ubicacion_conexion import Ubicacion
from app.services.cache.invalidacion import invalidar_por_lectura
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
    # HU17 CA3: la lectura MÁS RECIENTE de cada parámetro dentro de este
    # archivo, como {nombre_parametro: (valor, fecha_hora)}, más la
    # ubicación a la que pertenecen. Es lo que la tarea de ingesta publica
    # al bus de eventos del mapa (ver app/services/mapa/eventos.py).
    #
    # Se calcula ACÁ, en el bucle que ya recorre las lecturas, y no con una
    # consulta posterior: un .dat trae decenas de filas del mismo parámetro
    # y al marcador solo le sirve la última. Volver a leerlas de tlmtr
    # después del commit sería una consulta extra por archivo para
    # recuperar un dato que esta función ya tuvo en la mano.
    ultimos_por_parametro: dict = dataclasses.field(default_factory=dict)
    id_ubccn: int | None = None
    # HT-10 CA2: la sede a la que pertenecen estas lecturas. Se devuelve
    # junto a id_ubccn porque la invalidación de caché necesita las dos
    # (una entrada de /mediciones se indexa por sede y una de
    # /mapa-cliente por ubicación). Sale de la ubicación del dispositivo,
    # que esta función ya tiene cargada: no cuesta ninguna consulta extra.
    id_sd: int | None = None


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
    """Inserta una fila por LecturaValidada: en tlmtr si el valor es
    numérico (medición), en evnt_txt si es texto (evento, prmtr.tipo_dato
    ='texto' -ver validador.py-). No hace commit -el llamador controla la
    transacción, igual que el resto de app.tasks.ingesta-."""
    parametros = _mapa_parametros(db)
    ubicacion = db.get(Ubicacion, dispositivo.id_ubccn)
    guardadas = 0
    omitidas_sin_valor = 0
    parametros_desconocidos = set()
    fechas_numericas = []
    # HU17 CA3: {nombre_parametro: (valor, fecha_hora)} con la lectura más
    # reciente de cada parámetro vista en este archivo.
    ultimos_por_parametro: dict = {}

    for lectura in lecturas:
        if lectura.valor is None:
            omitidas_sin_valor += 1
            continue

        id_prmtr = parametros.get(lectura.parametro)
        if id_prmtr is None:
            parametros_desconocidos.add(lectura.parametro)
            continue

        if isinstance(lectura.valor, str):
            db.add(
                EventoTexto(
                    fch_hr=lectura.fecha_hora,
                    id_dspstv=dispositivo.id_dspstv,
                    id_prmtr=id_prmtr,
                    id_sd=ubicacion.id_sd,
                    vlr=lectura.valor,
                    id_archv=id_archv,
                )
            )
        else:
            db.add(
                Telemetria(
                    fch_hr=lectura.fecha_hora,
                    id_dspstv=dispositivo.id_dspstv,
                    id_prmtr=id_prmtr,
                    id_sd=ubicacion.id_sd,
                    vlr=lectura.valor,
                    id_archv=id_archv,
                )
            )
            fechas_numericas.append(lectura.fecha_hora)
        guardadas += 1

        # HU17 CA3: se queda con la lectura más reciente de cada parámetro.
        # Las filas de un .dat no vienen necesariamente ordenadas por
        # fecha, así que se compara en vez de sobrescribir sin más.
        anterior = ultimos_por_parametro.get(lectura.parametro)
        if anterior is None or lectura.fecha_hora > anterior[1]:
            ultimos_por_parametro[lectura.parametro] = (lectura.valor, lectura.fecha_hora)

    # flush explícito para que el INSERT viaje a Postgres AQUÍ y no en el
    # commit del llamador: es la única forma de traducir el fallo por
    # partición faltante (HT-08 CA4) a un error de dominio con contexto
    # útil. Sin esto, el llamador recibiría un IntegrityError crudo desde
    # dentro de db.commit(), sin saber qué fecha lo causó. evnt_txt no
    # está particionada, así que solo tlmtr puede fallar por esta causa.
    if guardadas:
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            if fechas_numericas and es_error_de_particion_faltante(exc):
                fechas = sorted(fechas_numericas)
                rango = f"{fechas[0]:%Y-%m-%d} .. {fechas[-1]:%Y-%m-%d}"
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

    # HT-10 CA2: una lectura nueva invalida la caché de su sede y su
    # ubicación (invalidación DIRIGIDA, no un flush global: ver
    # services/cache/invalidacion.py).
    #
    # POR QUE ACA Y NO SOLO TRAS EL COMMIT DEL LLAMADOR: esta función no
    # commitea -la transacción la controla el llamador-, así que en rigor
    # se invalida un instante antes de que el dato sea visible. Se acepta
    # a propósito, y es seguro en este sentido: borrar de más solo puede
    # causar un MISS extra (se relee de Postgres), nunca servir un dato
    # viejo. El riesgo teórico contrario -que un request se cuele entre
    # esta invalidación y el commit y repueble con el estado anterior- lo
    # acota el TTL corto (<=45s, ver consultas.TTL_CORTO), y tasks/
    # ingesta.py invalida OTRA VEZ después del commit para cerrarlo.
    #
    # Va acá igualmente porque es el punto que garantiza que TODO camino
    # que persista lecturas por el pipeline invalide, incluso si mañana
    # aparece otro llamador de guardar_lecturas() que no sea la tarea de
    # Celery actual.
    if guardadas:
        invalidar_por_lectura(id_sd=ubicacion.id_sd, id_ubccn=dispositivo.id_ubccn)

    return ResultadoPersistencia(
        guardadas=guardadas,
        omitidas_sin_valor=omitidas_sin_valor,
        omitidas_parametro_desconocido=sorted(parametros_desconocidos),
        ultimos_por_parametro=ultimos_por_parametro,
        id_ubccn=dispositivo.id_ubccn,
        id_sd=ubicacion.id_sd,
    )
