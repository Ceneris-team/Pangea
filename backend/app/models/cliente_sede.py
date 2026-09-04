from sqlalchemy import TIMESTAMP, Column, ForeignKey, Integer, String, text
from sqlalchemy.orm import relationship

from app.database import Base


class Cliente(Base):
    __tablename__ = "clnt"

    id_clnt = Column(Integer, primary_key=True, autoincrement=True)
    rzn_scl = Column(String(200), nullable=False)
    rc = Column(String(11), nullable=False, unique=True)
    crr_cntct = Column(String(150), nullable=False)
    tlfn_cntct = Column(String(20))
    estd = Column(String(20), nullable=False, server_default="Activo")
    fch_rgstr = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))

    sedes = relationship("Sede", back_populates="cliente")


class Sede(Base):
    __tablename__ = "sd"

    id_sd = Column(Integer, primary_key=True, autoincrement=True)
    id_clnt = Column(Integer, ForeignKey("clnt.id_clnt"), nullable=False)
    nmbr = Column(String(150), nullable=False)
    dscrpcn = Column(String(300))
    estd = Column(String(20), nullable=False, server_default="Activa")
    fch_crcn = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))

    cliente = relationship("Cliente", back_populates="sedes")
