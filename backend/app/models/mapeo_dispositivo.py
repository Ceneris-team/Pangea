from sqlalchemy import (
    Column, Integer, String, ForeignKey, Numeric, TIMESTAMP,
    CheckConstraint, Index, UniqueConstraint, text,
)

from app.database import Base


class MapeoFormato(Base):
    """HU 06: mini-ETL por DISPOSITIVO (DEC-09).

    Un datalogger manda dos formatos distintos de archivo, con distinto
    número y significado de columnas, y por eso el formato se identifica
    por dispositivo + tipo de trama (PP-96):

      tp_trm='H' -> archivos H_*.dat: datos periódicos (lectura real)
      tp_trm='E' -> archivos E_*.dat: estados y eventos del equipo

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
        CheckConstraint("tp_trm IN ('H','E')", name="mpfrmt_tptrm_check"),
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
    __tablename__ = "prmtr"

    id_prmtr = Column(Integer, primary_key=True, autoincrement=True)
    nmbr = Column(String(100), nullable=False, unique=True)
    undd = Column(String(30), nullable=False)
    dscrpcn = Column(String(200))


class MapeoColumna(Base):
    """Columna del archivo -> parámetro (HU 06)."""
    __tablename__ = "mp_clmn"
    __table_args__ = (
        UniqueConstraint("id_mp", "indc_clmn", name="uq_mpclmn_mp_indccolmn"),
    )

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
