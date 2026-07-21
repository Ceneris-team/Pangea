from sqlalchemy import Column, Integer, String, ForeignKey, TIMESTAMP, CheckConstraint, text
from sqlalchemy.orm import relationship

from app.database import Base


class Rol(Base):
    __tablename__ = "rl"

    id_rl = Column(Integer, primary_key=True, autoincrement=True)
    nmbr = Column(String(50), nullable=False, unique=True)
    dscrpcn = Column(String(200))

    usuarios = relationship("Usuario", back_populates="rol")


class Usuario(Base):
    __tablename__ = "usr"
    __table_args__ = (
        CheckConstraint("scp IN ('global','por_sede')", name="usr_scp_check"),
    )

    id_usr = Column(Integer, primary_key=True, autoincrement=True)
    id_rl = Column(Integer, ForeignKey("rl.id_rl"), nullable=False)
    scp = Column(String(20), nullable=False, server_default="por_sede")  # [corrección compañero]
    nmbr_cmplt = Column(String(150), nullable=False)
    crr = Column(String(150), nullable=False, unique=True)
    cntrsn_hsh = Column(String(255), nullable=False)
    zn_hrr = Column(String(50), nullable=False, server_default="America/Lima")
    estd = Column(String(20), nullable=False, server_default="Activo")
    intnts_fllds = Column(Integer, nullable=False, server_default="0")
    fch_crcn = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))

    rol = relationship("Rol", back_populates="usuarios")
