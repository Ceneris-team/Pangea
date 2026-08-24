from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)

from app.database import Base


class MapeoFormato(Base):
    """HU 06: mini-ETL por DISPOSITIVO (DEC-09).

    Un datalogger manda varios formatos distintos de archivo, con distinto
    número y significado de columnas, y por eso el formato se identifica
    por dispositivo + tipo de trama (PP-96):

      tp_trm='H' -> archivos H_*.dat: datos periódicos (lectura real)
      tp_trm='E' -> archivos E_*.dat: estados y eventos del equipo
      tp_trm='P' -> archivos P_*.dat: eventos de puerta/acceso

    tp_trm YA NO es un catálogo cerrado: el equipo de telemetría configura
    dataloggers con prefijos de archivo distintos según el proyecto, y
    exigir una migración + deploy por cada letra nueva no escala. H/E/P de
    arriba son simplemente los primeros valores cargados -no reciben trato
    especial en el modelo ni en el motor de ingesta-; el único chequeo de
    formato (una letra A-Z) vive en _validar_tipo_trama (routers/mapeos.py),
    y services/ingesta/mapeo.py resuelve el prefijo del archivo consultando
    los mp_frmt activos del dispositivo en vez de un diccionario fijo.

    DEC-09: antes el formato colgaba de (id_sd, mrc). Dos dataloggers de
    la misma marca en la misma sede, pero con sensores distintos
    conectados, compartían mapeo y las lecturas del segundo se guardaban
    bajo el parámetro equivocado, sin ningún error visible. Cada
    datalogger tiene su propia carpeta FTP exclusiva (cnxn_ftp, HU05) y
    un único dispositivo activo asociado (HU11), así que el dispositivo
    es la unidad correcta para colgar el mapeo. La marca y la sede se
    derivan del dispositivo (Dispositivo.mrc, Ubicacion.id_sd) en vez de
    duplicarse acá.
    """

    __tablename__ = "mp_frmt"
    __table_args__ = (
        # Sin CHECK de valores fijos: tp_trm es una letra libre validada en
        # el router (_validar_tipo_trama), no un catálogo cerrado en la BD.
        CheckConstraint("dlmtdr_dcml IN ('.', ',')", name="mpfrmt_dlmtdrdcml_check"),
        # Un dispositivo puede tener como máximo un mapeo ACTIVO por tipo
        # de trama (uno H y uno E). El parcial sobre estd deja convivir
        # versiones anteriores desactivadas del mismo mapeo; se declara
        # como Index con postgresql_where porque UniqueConstraint no
        # admite condición.
        Index(
            "uq_mpfrmt_dspstv_tptrm_activo",
            "id_dspstv",
            "tp_trm",
            unique=True,
            postgresql_where=text("estd = 'Activo'"),
        ),
        Index("idx_mpfrmt_dspstv", "id_dspstv"),
    )

    id_mp = Column(Integer, primary_key=True, autoincrement=True)
    id_dspstv = Column(Integer, ForeignKey("dspstv.id_dspstv"), nullable=False)
    tp_trm = Column(String(5), nullable=False, server_default="H")
    # Descripción corta y libre de qué es esta trama (p. ej. "Nivel de
    # napa" para una letra que el técnico de telemetría definió). Antes
    # de que tp_trm fuera libre no hacía falta -H/E/P se explicaban solos
    # en la UI-; con letras arbitrarias, sin esto nadie sabe qué es "X"
    # sin abrir el mapeo.
    dscrpcn = Column(String(200))
    dlmtdr = Column(String(5), nullable=False, server_default=",")
    # Separador decimal del propio dato numérico, independiente del
    # delimitador de columna: un datalogger en locale europeo manda
    # "23,5" con ';' de separador. El motor lo normaliza antes de float()
    # (ver services/ingesta/validador.py).
    dlmtdr_dcml = Column(String(1), nullable=False, server_default=".")
    fl_inc_dts = Column(Integer, nullable=False, server_default="1")
    frmt_fch = Column(String(50), nullable=False)
    estd = Column(String(20), nullable=False, server_default="Activo")


class Parametro(Base):
    """tipo_dato distingue una MEDICIÓN numérica (tlmtr.vlr es
    Numeric(14,4) NOT NULL, no admite texto) de un EVENTO de texto (ej.
    "MensajeP"/"MensajeA" de una trama de puerta: "Puerta Abierta", "Llave
    No Encontrada"). Antes de esto todo parámetro se validaba como
    número (validador._parsear_numero); un parámetro de texto perdía cada
    fila en silencio porque float("Puerta Abierta") siempre falla.

    Un parámetro de tipo 'texto' se persiste en evnt_txt (ver
    EventoTexto), no en tlmtr -no se puede simplemente volver tlmtr.vlr
    texto/nullable: es una tabla particionada con datos reales, y
    mezclar mediciones numéricas con mensajes de texto en la misma
    columna rompería las consultas/alarmas que asumen vlr numérico."""

    __tablename__ = "prmtr"
    __table_args__ = (
        CheckConstraint("tipo_dato IN ('numerico','texto')", name="prmtr_tipodato_check"),
    )

    id_prmtr = Column(Integer, primary_key=True, autoincrement=True)
    nmbr = Column(String(100), nullable=False, unique=True)
    undd = Column(String(30), nullable=False)
    dscrpcn = Column(String(200))
    tipo_dato = Column(String(10), nullable=False, server_default="numerico")


class MapeoColumna(Base):
    """Columna del archivo -> parámetro (HU 06)."""

    __tablename__ = "mp_clmn"
    __table_args__ = (UniqueConstraint("id_mp", "indc_clmn", name="uq_mpclmn_mp_indccolmn"),)

    id_mp_cl = Column(Integer, primary_key=True, autoincrement=True)
    id_mp = Column(Integer, ForeignKey("mp_frmt.id_mp"), nullable=False)
    indc_clmn = Column(Integer, nullable=False)
    id_prmtr = Column(Integer, ForeignKey("prmtr.id_prmtr"), nullable=False)


class Dispositivo(Base):
    """HU 10-11, HU 18-19, HU 36.

    DEC-09: ya no lleva id_mp. Un dispositivo puede tener 0, 1 o 2 mapeos
    de formato (uno por tipo de trama), así que la relación no cabe en una
    sola FK; vive del lado de MapeoFormato.id_dspstv.
    """

    __tablename__ = "dspstv"
    __table_args__ = (
        CheckConstraint("lttd BETWEEN -90 AND 90", name="dspstv_lttd_check"),
        CheckConstraint("lngtd BETWEEN -180 AND 180", name="dspstv_lngtd_check"),
        Index("idx_dspstv_ubccn", "id_ubccn"),
    )

    id_dspstv = Column(Integer, primary_key=True, autoincrement=True)
    id_ubccn = Column(Integer, ForeignKey("ubccn.id_ubccn"), nullable=False)
    id_cnxn = Column(Integer, ForeignKey("cnxn_ftp.id_cnxn"), nullable=False)
    nmbr = Column(String(150), nullable=False)
    mrc = Column(String(100), nullable=False)
    mdl = Column(String(100))
    lttd = Column(Numeric(9, 6), nullable=False)
    lngtd = Column(Numeric(9, 6), nullable=False)
    estd = Column(String(20), nullable=False, server_default="Activo")
    fch_rgstr = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
