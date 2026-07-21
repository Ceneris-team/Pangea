from sqlalchemy import (
    Column, Integer, String, ForeignKey, TIMESTAMP, Numeric, CheckConstraint,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class Ubicacion(Base):
    __tablename__ = "ubccn"
    __table_args__ = (
        UniqueConstraint("id_sd", "nmbr", name="uq_ubccn_sd_nombre"),
        CheckConstraint("lttd BETWEEN -90 AND 90", name="ubccn_lttd_check"),
        CheckConstraint("lngtd BETWEEN -180 AND 180", name="ubccn_lngtd_check"),
    )

    id_ubccn = Column(Integer, primary_key=True, autoincrement=True)
    id_sd = Column(Integer, ForeignKey("sd.id_sd"), nullable=False)
    nmbr = Column(String(150), nullable=False)
    dscrpcn = Column(String(300))
    lttd = Column(Numeric(9, 6), nullable=False)
    lngtd = Column(Numeric(9, 6), nullable=False)
    plgn_gjsn = Column(JSONB, nullable=False)  # [corrección compañero] polígono GeoJSON
    estd = Column(String(20), nullable=False, server_default="Activa")
    fch_crcn = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))


class ConexionFTP(Base):
    __tablename__ = "cnxn_ftp"
    __table_args__ = (
        CheckConstraint("prtcl IN ('FTP','TCP')", name="cnxnftp_prtcl_check"),
        CheckConstraint(
            "prtcl <> 'FTP' OR (usr_ftp IS NOT NULL AND rt_rmt IS NOT NULL)",
            name="cnxnftp_ftp_obligatorio_check",
        ),
    )

    id_cnxn = Column(Integer, primary_key=True, autoincrement=True)
    id_sd = Column(Integer, ForeignKey("sd.id_sd"), nullable=False)
    nmbr = Column(String(150), nullable=False)
    prtcl = Column(String(10), nullable=False, server_default="FTP")  # [corrección compañero]
    hst = Column(String(255), nullable=False)
    prt = Column(Integer, nullable=False, server_default="21")
    usr_ftp = Column(String(100))
    crdncl_cfrd = Column(String(500), nullable=False)
    rt_rmt = Column(String(300))
    frcnc_mnts = Column(Integer, nullable=False, server_default="15")
    estd = Column(String(20), nullable=False, server_default="Activa")
