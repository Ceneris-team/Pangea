from sqlalchemy import (
    TIMESTAMP,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)

from app.database import Base


class Panel(Base):
    """HU 23-25, HT-13."""

    __tablename__ = "pnl"
    __table_args__ = (
        UniqueConstraint("id_usr", "nmbr", name="uq_pnl_usr_nombre"),
        Index("idx_pnl_sd", "id_sd"),
    )

    id_pnl = Column(Integer, primary_key=True, autoincrement=True)
    id_usr = Column(Integer, ForeignKey("usr.id_usr"), nullable=False)
    id_sd = Column(Integer, ForeignKey("sd.id_sd"), nullable=False)
    nmbr = Column(String(150), nullable=False)
    vsbldd = Column(String(20), nullable=False, server_default="Privado")
    fch_crcn = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))


class PanelUbicacion(Base):
    """HU 26."""

    __tablename__ = "pnl_ubccn"
    __table_args__ = (UniqueConstraint("id_pnl", "id_ubccn", name="uq_pnlubccn_pnl_ubccn"),)

    id_pnl_ubc = Column(Integer, primary_key=True, autoincrement=True)
    id_pnl = Column(Integer, ForeignKey("pnl.id_pnl"), nullable=False)
    id_ubccn = Column(Integer, ForeignKey("ubccn.id_ubccn"), nullable=False)


class Widget(Base):
    """HU 34."""

    __tablename__ = "wdgt"

    id_wdgt = Column(Integer, primary_key=True, autoincrement=True)
    id_pnl = Column(Integer, ForeignKey("pnl.id_pnl"), nullable=False)
    tp = Column(String(30), nullable=False)
    id_prmtr = Column(Integer, ForeignKey("prmtr.id_prmtr"), nullable=False)
    id_ubccn = Column(Integer, ForeignKey("ubccn.id_ubccn"), nullable=False)
    pscn = Column(Integer, nullable=False, server_default="0")
