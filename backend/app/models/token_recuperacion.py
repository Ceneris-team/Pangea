"""
HU 02 - Gestionar contraseña

Token de un solo uso para el flujo de "¿Olvidaste tu contraseña?". Vive
30 minutos (fch_exp) y queda inutilizable después de canjearse (usad) o de
vencer, según el detalle de conversación de la historia.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, TIMESTAMP, Boolean, text
from sqlalchemy.orm import relationship

from app.database import Base


class TokenRecuperacion(Base):
    __tablename__ = "tkn_rcprcn"

    id_tkn = Column(Integer, primary_key=True, autoincrement=True)
    id_usr = Column(Integer, ForeignKey("usr.id_usr"), nullable=False)
    tkn = Column(String(255), nullable=False, unique=True)
    fch_crcn = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    fch_exp = Column(TIMESTAMP(timezone=True), nullable=False)
    usad = Column(Boolean, nullable=False, server_default="false")

    usuario = relationship("Usuario", back_populates="tokens_recuperacion")
