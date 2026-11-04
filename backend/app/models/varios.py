from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class ParametroCalculado(Base):
    """HU 38-40."""

    __tablename__ = "prmtr_clcld"
    __table_args__ = (UniqueConstraint("id_sd", "nmbr", name="uq_prmtrclcld_sd_nombre"),)

    id_prm_clc = Column(Integer, primary_key=True, autoincrement=True)
    id_sd = Column(Integer, ForeignKey("sd.id_sd"), nullable=False)
    nmbr = Column(String(100), nullable=False)
    frml = Column(String(500), nullable=False)
    undd = Column(String(30), nullable=False)
    dscrpcn = Column(String(300))
    estd = Column(String(20), nullable=False, server_default="Activo")


class LogAuditoria(Base):
    """HT-11: historial mensual, transaccional e inmutable en PostgreSQL."""

    __tablename__ = "lg_adtr"
    __table_args__ = (
        Index("idx_lgadtr_sd_fch", "id_sd", "fch_evnt"),
        Index("idx_lgadtr_usr_fch", "id_usr", "fch_evnt"),
        Index("idx_lgadtr_empresa_fch", "id_clnt", "fch_evnt", "id_evnt"),
        Index("idx_lgadtr_afectado_fch", "id_afectado", "fch_evnt"),
        {"postgresql_partition_by": "RANGE (fch_evnt)"},
    )

    id_evnt = Column(BigInteger, primary_key=True, autoincrement=True)
    # Se conservan los identificadores incluso al eliminar el usuario/recurso.
    id_usr = Column(Integer)
    id_afectado = Column(Integer)
    id_sd = Column(Integer)
    id_clnt = Column(Integer)
    id_ubccn = Column(Integer)
    accn = Column(String(50), nullable=False)
    entdd = Column(String(100), nullable=False)
    vlrs_antrrs = Column(JSONB)
    vlrs_nvs = Column(JSONB)
    fch_evnt = Column(
        TIMESTAMP(timezone=True),
        primary_key=True,
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    resultado = Column(String(20), nullable=False, server_default="Exitoso")
    origen = Column(String(20), nullable=False, server_default="Proceso")
    ejecutor = Column(String(200), nullable=False, server_default=text("session_user"))
    motivo = Column(String(100))
    operacion = Column(String(300))
    solicitud_id = Column(String(36))


class Exportacion(Base):
    """HU 33, HT-17."""

    __tablename__ = "exprtcn"
    __table_args__ = (
        Index("idx_exprtcn_usr_fecha", "id_usr", "fch_slctd"),
        Index("idx_exprtcn_estado_expira", "estd", "fch_exprcn"),
    )

    id_exprtcn = Column(BigInteger, primary_key=True, autoincrement=True)
    id_usr = Column(Integer, ForeignKey("usr.id_usr"), nullable=False)
    frmt = Column(String(10), nullable=False)
    fltrs_aplcds = Column(JSONB, nullable=False)
    estd = Column(String(20), nullable=False, server_default="En proceso")
    url_dscrg = Column(String(500))
    fch_slctd = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    fch_exprcn = Column(TIMESTAMP(timezone=True))
    fch_inicio = Column(TIMESTAMP(timezone=True))
    fch_fin = Column(TIMESTAMP(timezone=True))
    objeto_clave = Column(String(500))
    objeto_version = Column(String(200))
    objeto_bucket = Column(String(255))
    filas = Column(BigInteger)
    bytes_archivo = Column(BigInteger)
    error = Column(String(500))
    notificacion_estado = Column(String(20), nullable=False, server_default="Pendiente")
    notificacion_intentos = Column(Integer, nullable=False, server_default="0")
    notificada_en = Column(TIMESTAMP(timezone=True))
    intentos = Column(Integer, nullable=False, server_default="0")
