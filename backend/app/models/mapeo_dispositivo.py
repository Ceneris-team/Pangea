from sqlalchemy import (
    Column, Integer, String, ForeignKey, Numeric, TIMESTAMP,
    CheckConstraint, Index, UniqueConstraint, text,
)

from app.database import Base


class MapeoFormato(Base):
    """HU 06: mini-ETL por marca de sensor."""
    __tablename__ = "mp_frmt"

    id_mp = Column(Integer, primary_key=True, autoincrement=True)
    id_sd = Column(Integer, ForeignKey("sd.id_sd"), nullable=False)
    mrc = Column(String(100), nullable=False)
    dlmtdr = Column(String(5), nullable=False, server_default=",")
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
    """HU 10-11, HU 18-19, HU 36."""
    __tablename__ = "dspstv"
    __table_args__ = (
        CheckConstraint("lttd BETWEEN -90 AND 90", name="dspstv_lttd_check"),
        CheckConstraint("lngtd BETWEEN -180 AND 180", name="dspstv_lngtd_check"),
        Index("idx_dspstv_ubccn", "id_ubccn"),
    )

    id_dspstv = Column(Integer, primary_key=True, autoincrement=True)
    id_ubccn = Column(Integer, ForeignKey("ubccn.id_ubccn"), nullable=False)
    id_cnxn = Column(Integer, ForeignKey("cnxn_ftp.id_cnxn"), nullable=False)
    id_mp = Column(Integer, ForeignKey("mp_frmt.id_mp"), nullable=False)
    nmbr = Column(String(150), nullable=False)
    mrc = Column(String(100), nullable=False)
    mdl = Column(String(100))
    lttd = Column(Numeric(9, 6), nullable=False)
    lngtd = Column(Numeric(9, 6), nullable=False)
    estd = Column(String(20), nullable=False, server_default="Activo")
    fch_rgstr = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
