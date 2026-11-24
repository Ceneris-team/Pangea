from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.orm import deferred

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
        Index("idx_archv_cnxn_nombre_version", "id_cnxn", "nmbr_archv", "version_origen"),
    )

    id_archv = Column(BigInteger, primary_key=True, autoincrement=True)
    id_cnxn = Column(Integer, ForeignKey("cnxn_ftp.id_cnxn"), nullable=False)
    id_dspstv = Column(Integer, ForeignKey("dspstv.id_dspstv"), nullable=True, index=True)
    version_origen = Column(String(64))
    sha256 = Column(String(64))
    clave_original = Column(String(600))
    contenido_original = deferred(Column(LargeBinary))
    nmbr_archv = Column(String(300), nullable=False)
    estd = Column(String(20), nullable=False, server_default="Pendiente")
    fch_dtccn = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    fch_prcsd = Column(TIMESTAMP(timezone=True))
    mnsj_errr = Column(String(500))
    rgstrs_prcsds = Column(Integer)
