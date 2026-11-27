from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text

from app.database import Base


class LogIngesta(Base):
    """Resultado inmutable de una ejecución; independiente del estado de la cola."""

    __tablename__ = "log_ingesta"
    __table_args__ = (
        Index("idx_log_ingesta_fecha", "fecha", "id_evento"),
        Index("idx_log_ingesta_ambito", "id_sd", "id_ubccn", "fecha"),
    )

    id_evento = Column(BigInteger, primary_key=True, autoincrement=True)
    id_archv = Column(BigInteger, ForeignKey("archv_ingst.id_archv"), nullable=False, index=True)
    id_intnt = Column(BigInteger, ForeignKey("intnt_prcsmnt.id_intnt"), unique=True)
    # Instantánea del origen: mover/reemplazar un equipo no cambia su historial.
    id_cnxn = Column(Integer, nullable=False)
    id_dspstv = Column(Integer)
    id_sd = Column(Integer, nullable=False)
    id_ubccn = Column(Integer)
    archivo = Column(String(300), nullable=False)
    datalogger = Column(String(300), nullable=False)
    proyecto = Column(String(300))
    fecha = Column(DateTime(timezone=True), nullable=False)
    recepcion = Column(DateTime(timezone=True), nullable=False)
    inicio = Column(DateTime(timezone=True))
    fin = Column(DateTime(timezone=True))
    resultado = Column(String(20), nullable=False)
    mensaje = Column(Text)
    registros_procesados = Column(Integer)
    registros_rechazados = Column(Integer)
    origen = Column(String(40), nullable=False)
