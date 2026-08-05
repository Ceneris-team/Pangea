"""
HT-08: gestión de las particiones mensuales de tlmtr.

tlmtr está particionada por RANGE sobre fch_hr (ver
app.models.telemetria.Telemetria). Postgres NO crea las particiones solo:
si llega una fila cuya fch_hr no cae en ninguna partición existente, el
INSERT falla. Este módulo centraliza el cálculo de nombres/rangos y el
CREATE idempotente, para que la migración inicial y el job de Celery Beat
(app.tasks.particiones) usen exactamente la misma lógica y no diverjan.

Convención de nombres: tlmtr_YYYY_MM, con rango [primer día del mes,
primer día del mes siguiente), que es como las creó la migración
eadc512979fc.
"""
import datetime as dt
import logging
import re

logger = logging.getLogger(__name__)

TABLA_PADRE = "tlmtr"

# SQLSTATE que devuelve Postgres cuando una fila no cae en ninguna
# partición. Llega como psycopg2.errors.CheckViolation; se compara por
# código y no por el texto del mensaje, que depende del locale del
# servidor.
SQLSTATE_SIN_PARTICION = "23514"
_MENSAJE_SIN_PARTICION = "no partition of relation"


class ParticionInexistenteError(Exception):
    """No existe partición de tlmtr para la fecha de la lectura.

    HT-08 CA4: este caso no debe salir como un traceback crudo de
    Postgres. Se traduce a esta excepción de dominio, con la fecha
    concreta y qué hacer al respecto, para que el llamador la clasifique
    como error de datos NO reintentable (reintentar no crea la
    partición)."""


def es_error_de_particion_faltante(exc: Exception) -> bool:
    """True si `exc` es el fallo de Postgres por falta de partición.

    Se usa sobre la excepción de SQLAlchemy/psycopg2 tal como llega del
    INSERT. Comprueba el SQLSTATE 23514 y, para no confundirlo con
    cualquier otro CHECK constraint de la tabla, que el mensaje sea el de
    partición faltante."""
    codigo = getattr(getattr(exc, "orig", exc), "pgcode", None)
    if codigo != SQLSTATE_SIN_PARTICION:
        return False
    return _MENSAJE_SIN_PARTICION in str(exc).lower()

# Se valida el nombre antes de interpolarlo en el DDL. Los valores vienen
# de nuestro propio cálculo de fechas -no de entrada de usuario-, pero el
# nombre de tabla no se puede pasar como parámetro ligado en un CREATE, y
# una regresión que meta algo raro aquí no debe poder inyectar SQL.
_PATRON_PARTICION = re.compile(r"^tlmtr_\d{4}_\d{2}$")


def primer_dia_del_mes(fecha: dt.date) -> dt.date:
    return fecha.replace(day=1)


def mes_siguiente(fecha: dt.date) -> dt.date:
    """Primer día del mes siguiente al de `fecha`."""
    if fecha.month == 12:
        return dt.date(fecha.year + 1, 1, 1)
    return dt.date(fecha.year, fecha.month + 1, 1)


def nombre_particion(fecha: dt.date) -> str:
    return f"{TABLA_PADRE}_{fecha.year:04d}_{fecha.month:02d}"


def rango_particion(fecha: dt.date) -> tuple:
    """Devuelve (desde, hasta) del mes de `fecha`; `hasta` es exclusivo."""
    desde = primer_dia_del_mes(fecha)
    return desde, mes_siguiente(desde)


def sql_crear_particion(fecha: dt.date) -> str:
    """DDL idempotente para la partición del mes de `fecha`.

    IF NOT EXISTS hace que re-ejecutar la migración o que el job corra dos
    veces el mismo mes no falle ni duplique nada (requisito de HT-08)."""
    nombre = nombre_particion(fecha)
    if not _PATRON_PARTICION.match(nombre):
        raise ValueError(f"nombre de partición inesperado: {nombre!r}")
    desde, hasta = rango_particion(fecha)
    return (
        f"CREATE TABLE IF NOT EXISTS {nombre} PARTITION OF {TABLA_PADRE} "
        f"FOR VALUES FROM ('{desde.isoformat()}') TO ('{hasta.isoformat()}')"
    )


def meses_a_cubrir(desde: dt.date, cantidad: int) -> list:
    """Lista de primeros-de-mes empezando en el mes de `desde`."""
    if cantidad < 1:
        raise ValueError("cantidad debe ser >= 1")
    meses = [primer_dia_del_mes(desde)]
    for _ in range(cantidad - 1):
        meses.append(mes_siguiente(meses[-1]))
    return meses


def particiones_existentes(conexion) -> set:
    """Nombres de las particiones mensuales de tlmtr ya creadas.

    `conexion` es una Connection de SQLAlchemy (o el bind de una sesión):
    sirve tanto desde Alembic (op.get_bind()) como desde el job."""
    from sqlalchemy import text

    filas = conexion.execute(text(
        "SELECT tablename FROM pg_tables "
        "WHERE tablename ~ '^tlmtr_[0-9]{4}_[0-9]{2}$'"
    )).all()
    return {fila[0] for fila in filas}


def asegurar_particiones(conexion, desde: dt.date, cantidad: int) -> list:
    """Crea las particiones de `cantidad` meses a partir de `desde`.

    Idempotente: solo emite DDL para las que faltan y devuelve la lista de
    nombres efectivamente creados (vacía si ya estaban todas)."""
    from sqlalchemy import text

    existentes = particiones_existentes(conexion)
    creadas = []
    for mes in meses_a_cubrir(desde, cantidad):
        nombre = nombre_particion(mes)
        if nombre in existentes:
            continue
        conexion.execute(text(sql_crear_particion(mes)))
        creadas.append(nombre)
        logger.info("Partición creada: %s", nombre)
    return creadas
