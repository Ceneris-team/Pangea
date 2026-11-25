from sqlalchemy import TIMESTAMP, BigInteger, Column, ForeignKey, Index, Integer, String, text

from app.database import Base


class IntentoProcesamiento(Base):
    """Historial de reprocesos (HU 31)."""

    __tablename__ = "intnt_prcsmnt"
    __table_args__ = (
        Index(
            "uq_intento_ingesta_activo",
            "id_archv",
            unique=True,
            postgresql_where=text("rsltd IN ('Pendiente', 'Procesando')"),
        ),
        Index(
            "idx_intento_ingesta_despacho",
            "proximo_envio",
            postgresql_where=text("rsltd = 'Pendiente'"),
        ),
    )

    id_intnt = Column(BigInteger, primary_key=True, autoincrement=True)
    id_archv = Column(BigInteger, ForeignKey("archv_ingst.id_archv"), nullable=False)
    fch_intnt = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    rsltd = Column(String(20), nullable=False)
    mnsj_errr = Column(String(500))
    id_usr = Column(Integer, ForeignKey("usr.id_usr"))
    fch_inicio = Column(TIMESTAMP(timezone=True))
    fch_fin = Column(TIMESTAMP(timezone=True))
    proximo_envio = Column(TIMESTAMP(timezone=True))
    reintentos = Column(Integer, nullable=False, server_default="0")
    id_intento_anterior = Column(BigInteger, ForeignKey("intnt_prcsmnt.id_intnt"))
    registros_guardados = Column(Integer)
