from sqlalchemy import TIMESTAMP, BigInteger, Column, ForeignKey, Index, Integer, String

from app.database import Base


class EventoTexto(Base):
    """Contraparte de Telemetria (tlmtr) para parámetros de tipo 'texto'
    (prmtr.tipo_dato): mensajes de eventos que no son una medición
    numérica, como "MensajeP"/"MensajeA" de una trama de puerta ("Puerta
    Abierta", "Llave No Encontrada").

    Misma forma que tlmtr (dispositivo + parámetro + sede + fecha + valor
    + archivo de origen), pero SIN particionar: el volumen esperado de
    eventos de texto es órdenes de magnitud menor que la telemetría
    numérica de todos los dataloggers, y particionar de entrada sería
    complejidad sin necesidad real todavía (se puede particionar más
    adelante si el volumen lo justifica, mismo criterio que HT-08 aplicó
    a tlmtr cuando SÍ hizo falta)."""

    __tablename__ = "evnt_txt"
    __table_args__ = (
        Index("idx_evnttxt_dspstv_prmtr", "id_dspstv", "id_prmtr", "fch_hr"),
        Index("idx_evnttxt_fchhr", "fch_hr"),
    )

    id_evnt = Column(BigInteger, primary_key=True, autoincrement=True)
    fch_hr = Column(TIMESTAMP(timezone=True), nullable=False)
    id_dspstv = Column(Integer, ForeignKey("dspstv.id_dspstv"), nullable=False)
    id_prmtr = Column(Integer, ForeignKey("prmtr.id_prmtr"), nullable=False)
    id_sd = Column(Integer, ForeignKey("sd.id_sd"), nullable=False)
    vlr = Column(String(500), nullable=False)
    id_archv = Column(BigInteger, ForeignKey("archv_ingst.id_archv"))
