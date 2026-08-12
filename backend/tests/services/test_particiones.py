"""
HT-08: tests del particionamiento de tlmtr (app.services.particiones,
app.services.ingesta.persistencia).

Corren contra la Postgres real de test (ver tests/conftest.py): CREATE
TABLE ... PARTITION OF es DDL específico de Postgres que SQLite no puede
compilar, y estos tests validan justamente ese DDL (idempotencia,
reparación de huecos, y que un INSERT fuera de rango no reviente crudo).

Los tests de asegurar_particiones usan fechas lejanas en el futuro
(2031+) para no pisar el rango que la migración a7f31c4b9e02 y el job de
Beat ya mantienen creado alrededor de la fecha real de hoy.
"""

import datetime as dt

import pytest
from sqlalchemy import text

from app.models.mapeo_dispositivo import Dispositivo, Parametro
from app.models.ubicacion_conexion import ConexionFTP, Ubicacion
from app.services.ingesta.persistencia import guardar_lecturas
from app.services.ingesta.validador import LecturaValidada
from app.services.particiones import (
    ParticionInexistenteError,
    asegurar_particiones,
    es_error_de_particion_faltante,
    mes_siguiente,
    meses_a_cubrir,
    nombre_particion,
    particiones_existentes,
    primer_dia_del_mes,
    rango_particion,
    sql_crear_particion,
)

# ---------------------------------------------------------------------
# Cálculo de nombres/rangos: funciones puras, sin BD.
# ---------------------------------------------------------------------


def test_nombre_particion_formatea_anio_mes():
    assert nombre_particion(dt.date(2026, 8, 7)) == "tlmtr_2026_08"
    assert nombre_particion(dt.date(2027, 1, 1)) == "tlmtr_2027_01"


def test_primer_dia_del_mes():
    assert primer_dia_del_mes(dt.date(2026, 8, 17)) == dt.date(2026, 8, 1)


def test_mes_siguiente_cruza_anio():
    assert mes_siguiente(dt.date(2026, 12, 5)) == dt.date(2027, 1, 1)
    assert mes_siguiente(dt.date(2026, 3, 1)) == dt.date(2026, 4, 1)


def test_rango_particion_es_medio_abierto():
    desde, hasta = rango_particion(dt.date(2026, 8, 17))
    assert (desde, hasta) == (dt.date(2026, 8, 1), dt.date(2026, 9, 1))


def test_meses_a_cubrir_genera_secuencia_consecutiva_cruzando_anio():
    meses = meses_a_cubrir(dt.date(2026, 11, 20), 3)
    assert meses == [dt.date(2026, 11, 1), dt.date(2026, 12, 1), dt.date(2027, 1, 1)]


def test_meses_a_cubrir_rechaza_cantidad_invalida():
    with pytest.raises(ValueError):
        meses_a_cubrir(dt.date(2026, 1, 1), 0)


def test_sql_crear_particion_es_if_not_exists_y_rango_correcto():
    ddl = sql_crear_particion(dt.date(2026, 9, 15))
    assert "CREATE TABLE IF NOT EXISTS tlmtr_2026_09 PARTITION OF tlmtr" in ddl
    assert "FROM ('2026-09-01') TO ('2026-10-01')" in ddl


# ---------------------------------------------------------------------
# es_error_de_particion_faltante: no debe confundirse con otro CHECK
# constraint que también use el SQLSTATE 23514.
# ---------------------------------------------------------------------


class _ExcepcionOrigFalsa(Exception):
    def __init__(self, pgcode, mensaje):
        super().__init__(mensaje)
        self.pgcode = pgcode


def test_reconoce_error_de_particion_faltante():
    exc = Exception('no partition of relation "tlmtr" found for row')
    exc.orig = _ExcepcionOrigFalsa("23514", "no partition of relation")
    assert es_error_de_particion_faltante(exc) is True


def test_no_confunde_otro_check_constraint_con_mismo_sqlstate():
    exc = Exception('new row for relation "dspstv" violates check constraint "dspstv_lttd_check"')
    exc.orig = _ExcepcionOrigFalsa("23514", "violates check constraint")
    assert es_error_de_particion_faltante(exc) is False


def test_no_confunde_otro_sqlstate():
    exc = Exception("duplicate key value violates unique constraint")
    exc.orig = _ExcepcionOrigFalsa("23505", "duplicate key")
    assert es_error_de_particion_faltante(exc) is False


# ---------------------------------------------------------------------
# asegurar_particiones contra Postgres real: idempotencia y reparación
# de huecos (lo que corre a diario el job de Celery Beat).
# ---------------------------------------------------------------------


def test_asegurar_particiones_es_idempotente(db_session):
    conexion = db_session.connection()
    hoy = dt.date(2031, 3, 10)

    creadas_1 = asegurar_particiones(conexion, hoy, 2)
    assert creadas_1 == [nombre_particion(hoy), nombre_particion(mes_siguiente(hoy))]

    creadas_2 = asegurar_particiones(conexion, hoy, 2)
    assert creadas_2 == [], "correr dos veces no debe duplicar ni fallar"

    existentes = particiones_existentes(conexion)
    assert nombre_particion(hoy) in existentes
    assert nombre_particion(mes_siguiente(hoy)) in existentes


def test_asegurar_particiones_repara_huecos(db_session):
    conexion = db_session.connection()
    hoy = dt.date(2032, 5, 1)

    asegurar_particiones(conexion, hoy, 3)
    hueco = nombre_particion(mes_siguiente(hoy))  # mes intermedio de los 3
    conexion.execute(text(f"DROP TABLE {hueco}"))
    assert hueco not in particiones_existentes(conexion)

    creadas = asegurar_particiones(conexion, hoy, 3)
    assert creadas == [hueco]
    assert hueco in particiones_existentes(conexion)


# ---------------------------------------------------------------------
# CA4: insertar una lectura con fecha fuera de las particiones
# existentes no revienta con el traceback crudo de Postgres.
# ---------------------------------------------------------------------


@pytest.fixture()
def dispositivo_de_prueba(db_session, fabrica):
    """DEC-09: el dispositivo ya no necesita un MapeoFormato para crearse
    (columna dspstv.id_mp eliminada); estos tests de particionamiento no
    ejercitan el mapeo, así que no hace falta crear uno."""
    sede = fabrica.sede()
    ubicacion = Ubicacion(
        id_sd=sede.id_sd,
        nmbr="Ubicación HT-08",
        lttd=4.6,
        lngtd=-74.0,
        plgn_gjsn={},
    )
    conexion_ftp = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr="FTP HT-08",
        hst="host",
        usr_ftp="u",
        rt_rmt="/",
        crdncl_cfrd="x",
    )
    db_session.add_all([ubicacion, conexion_ftp])
    db_session.flush()
    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn,
        id_cnxn=conexion_ftp.id_cnxn,
        nmbr="Dispositivo HT-08",
        mrc="Marca HT-08",
        lttd=4.6,
        lngtd=-74.0,
    )
    db_session.add(dispositivo)
    db_session.flush()
    return dispositivo


@pytest.fixture()
def parametro_de_prueba(db_session):
    parametro = Parametro(nmbr="Temperatura HT-08", undd="C")
    db_session.add(parametro)
    db_session.flush()
    return parametro


def test_guardar_lecturas_en_particion_existente_las_persiste(
    db_session, dispositivo_de_prueba, parametro_de_prueba
):
    lectura = LecturaValidada(
        fecha_hora=dt.datetime(2026, 8, 7, 10, tzinfo=dt.timezone.utc),
        id_cnxn=dispositivo_de_prueba.id_cnxn,
        parametro=parametro_de_prueba.nmbr,
        valor=25.5,
        numero_fila=1,
    )
    resultado = guardar_lecturas(db_session, [lectura], dispositivo_de_prueba, id_archv=None)
    assert resultado.guardadas == 1


def test_guardar_lecturas_fuera_de_particion_no_revienta_crudo(
    db_session, dispositivo_de_prueba, parametro_de_prueba
):
    """CA4: el INSERT sin partición no debe propagar el IntegrityError
    crudo de Postgres; debe traducirse a ParticionInexistenteError con
    el rango de fechas concreto."""
    lectura = LecturaValidada(
        fecha_hora=dt.datetime(2019, 3, 1, 10, tzinfo=dt.timezone.utc),
        id_cnxn=dispositivo_de_prueba.id_cnxn,
        parametro=parametro_de_prueba.nmbr,
        valor=25.5,
        numero_fila=1,
    )
    with pytest.raises(ParticionInexistenteError, match="2019-03-01"):
        guardar_lecturas(db_session, [lectura], dispositivo_de_prueba, id_archv=999)


def test_guardar_lecturas_omite_valores_vacios_sin_tocar_particiones(
    db_session, dispositivo_de_prueba, parametro_de_prueba
):
    """Una lectura sin valor (None) no genera INSERT en tlmtr, así que
    una fecha sin partición para esa fila no debe fallar: nunca llega a
    intentarse el INSERT."""
    lectura = LecturaValidada(
        fecha_hora=dt.datetime(2019, 3, 1, 10, tzinfo=dt.timezone.utc),
        id_cnxn=dispositivo_de_prueba.id_cnxn,
        parametro=parametro_de_prueba.nmbr,
        valor=None,
        numero_fila=1,
    )
    resultado = guardar_lecturas(db_session, [lectura], dispositivo_de_prueba, id_archv=None)
    assert resultado.guardadas == 0
    assert resultado.omitidas_sin_valor == 1
