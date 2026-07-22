from sqlalchemy import (
    BigInteger, Column, Integer, String, ForeignKey, TIMESTAMP,
    CheckConstraint, Index, text,
)

from app.database import Base


class ArchivoIngesta(Base):
    """Cola de HU 09, log de HU 37: registro de cada archivo .dat encolado
    para procesar, con su estado para permitir reintentos (CA2) y
    métricas de la cola (CA3). El CHECK de estados no está en el
    diccionario de datos original pero se agrega como capa extra de
    validación a nivel BD."""
    __tablename__ = "archv_ingst"
    __table_args__ = (
        CheckConstraint(
            "estd IN ('Pendiente','Procesando','Exitoso','Fallido')",
            name="archvingst_estd_check",
        ),
        Index("idx_archvingst_estd", "estd", "fch_dtccn"),
    )

    id_archv = Column(BigInteger, primary_key=True, autoincrement=True)
    id_cnxn = Column(Integer, ForeignKey("cnxn_ftp.id_cnxn"), nullable=False)
    nmbr_archv = Column(String(300), nullable=False)
    estd = Column(String(20), nullable=False, server_default="Pendiente")
    fch_dtccn = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    fch_prcsd = Column(TIMESTAMP(timezone=True))
    mnsj_errr = Column(String(500))
    rgstrs_prcsds = Column(Integer)
