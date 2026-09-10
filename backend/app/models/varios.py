from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class ParametroCalculado(Base):
    """HU 38-40."""

    __tablename__ = "prmtr_clcld"
    __table_args__ = (UniqueConstraint("id_sd", "nmbr", name="uq_prmtrclcld_sd_nombre"),)

    id_prm_clc = Column(Integer, primary_key=True, autoincrement=True)
    id_sd = Column(Integer, ForeignKey("sd.id_sd"), nullable=False)
    nmbr = Column(String(100), nullable=False)
    frml = Column(String(500), nullable=False)
    undd = Column(String(30), nullable=False)
    dscrpcn = Column(String(300))
    estd = Column(String(20), nullable=False, server_default="Activo")


class LogAuditoria(Base):
    """HT-11: inmutable, sin UPDATE/DELETE a nivel de aplicación (ver
    routers/auditoria.py, que solo expone GET, y security/auditoria.py,
    el único lugar del código que hace INSERT sobre este modelo).

    NO particionada a propósito (a diferencia de Telemetria en HT-08): el
    volumen esperado -acciones administrativas humanas, no lecturas de
    sensores- no se acerca al que justificaba particionar tlmtr. Ver
    "Log de auditoría (HT-11)" en backend/README.md para el detalle y qué
    haría falta si esa premisa cambiara."""

    __tablename__ = "lg_adtr"
    __table_args__ = (
        Index("idx_lgadtr_sd_fch", "id_sd", "fch_evnt"),
        Index("idx_lgadtr_usr_fch", "id_usr", "fch_evnt"),
    )

    id_evnt = Column(BigInteger, primary_key=True, autoincrement=True)
    id_usr = Column(Integer, ForeignKey("usr.id_usr"), nullable=False)
    id_sd = Column(Integer, ForeignKey("sd.id_sd"))
    accn = Column(String(50), nullable=False)
    entdd = Column(String(50), nullable=False)
    vlrs_antrrs = Column(JSONB)
    vlrs_nvs = Column(JSONB)
    fch_evnt = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))


class Exportacion(Base):
    """HU 33, HT-17."""

    __tablename__ = "exprtcn"

    id_exprtcn = Column(BigInteger, primary_key=True, autoincrement=True)
    id_usr = Column(Integer, ForeignKey("usr.id_usr"), nullable=False)
    frmt = Column(String(10), nullable=False)
    fltrs_aplcds = Column(JSONB, nullable=False)
    estd = Column(String(20), nullable=False, server_default="En proceso")
    url_dscrg = Column(String(500))
    fch_slctd = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    fch_exprcn = Column(TIMESTAMP(timezone=True))
