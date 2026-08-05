from sqlalchemy import BigInteger, Column, Integer, String, ForeignKey, TIMESTAMP, text

from app.database import Base


class IntentoProcesamiento(Base):
    """Historial de reprocesos (HU 31)."""
    __tablename__ = "intnt_prcsmnt"

    id_intnt = Column(BigInteger, primary_key=True, autoincrement=True)
    id_archv = Column(BigInteger, ForeignKey("archv_ingst.id_archv"), nullable=False)
    fch_intnt = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    rsltd = Column(String(20), nullable=False)
    mnsj_errr = Column(String(500))
    id_usr = Column(Integer, ForeignKey("usr.id_usr"))
