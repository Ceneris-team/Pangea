from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class Alarma(Base):
    """HU 27-28, HT-13."""

    __tablename__ = "alrm"
    __table_args__ = (Index("idx_alrm_sd", "id_sd"),)

    id_alrm = Column(Integer, primary_key=True, autoincrement=True)
    id_usr = Column(Integer, ForeignKey("usr.id_usr"), nullable=False)
    id_sd = Column(Integer, ForeignKey("sd.id_sd"), nullable=False)
    nmbr = Column(String(150), nullable=False)
    id_prmtr = Column(Integer, ForeignKey("prmtr.id_prmtr"), nullable=False)
    id_ubccn = Column(Integer, ForeignKey("ubccn.id_ubccn"), nullable=False)
    estd = Column(String(20), nullable=False, server_default="Activa")
    fch_crcn = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))


class CondicionAlarma(Base):
    """HU 29."""

    __tablename__ = "cndcn_alrm"
    __table_args__ = (
        CheckConstraint("oprdr IN ('>','<','>=','<=','=')", name="cndcnalrm_oprdr_check"),
    )

    id_cndcn = Column(Integer, primary_key=True, autoincrement=True)
    id_alrm = Column(Integer, ForeignKey("alrm.id_alrm"), nullable=False)
    oprdr = Column(String(5), nullable=False)
    vlr_umbrl = Column(Numeric(14, 4), nullable=False)


class DestinatarioAlarma(Base):
    """HU 30, HU 35. Dos índices únicos parciales (uno por canal) reemplazan
    el UNIQUE compuesto original, que no funcionaba porque en SQL dos NULL
    nunca se consideran iguales para un UNIQUE."""

    __tablename__ = "dstntr_alrm"
    __table_args__ = (
        CheckConstraint("cnl IN ('email','telegram')", name="dstntralrm_cnl_check"),
        CheckConstraint(
            "(cnl = 'email' AND crr IS NOT NULL AND cht_id_tlgrm IS NULL) OR "
            "(cnl = 'telegram' AND cht_id_tlgrm IS NOT NULL AND crr IS NULL)",
            name="dstntralrm_canal_destino_check",
        ),
        Index(
            "uq_dstntr_email",
            "id_alrm",
            "crr",
            unique=True,
            postgresql_where=text("cnl = 'email'"),
        ),
        Index(
            "uq_dstntr_telegram",
            "id_alrm",
            "cht_id_tlgrm",
            unique=True,
            postgresql_where=text("cnl = 'telegram'"),
        ),
    )

    id_dstntr = Column(Integer, primary_key=True, autoincrement=True)
    id_alrm = Column(Integer, ForeignKey("alrm.id_alrm"), nullable=False)
    cnl = Column(String(20), nullable=False, server_default="email")
    crr = Column(String(150))
    cht_id_tlgrm = Column(String(50))


class NotificacionEnviada(Base):
    """HT-14: bandeja transaccional e historial de notificaciones."""

    __tablename__ = "ntfccn_envd"
    __table_args__ = (
        CheckConstraint("cnl IN ('email','telegram')", name="ntfccnenvd_cnl_check"),
        CheckConstraint(
            "estd IN ('Pendiente','Encolado','Reintentando','Enviado','Fallido')",
            name="ntfccnenvd_estado_check",
        ),
        Index("idx_ntfccn_pendiente", "estd", "prxm_intnt"),
        Index("idx_ntfccn_usuario_fecha", "id_usr", "fch_crcn"),
    )

    id_ntfccn = Column(BigInteger, primary_key=True, autoincrement=True)
    id_alrm = Column(Integer, ForeignKey("alrm.id_alrm"), nullable=True)
    id_usr = Column(Integer, ForeignKey("usr.id_usr"))
    id_sd = Column(Integer, ForeignKey("sd.id_sd"))
    tipo = Column(String(50), nullable=False, server_default="alarma_activada")
    plantilla = Column(String(50), nullable=False, server_default="alarma_activada")
    contexto = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    clave = Column(String(64), unique=True)
    cnl = Column(String(20), nullable=False)
    dstn = Column(String(150), nullable=False)
    fch_crcn = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    fch_env = Column(TIMESTAMP(timezone=True))
    prxm_intnt = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    bloqueo_hasta = Column(TIMESTAMP(timezone=True))
    mensaje_id = Column(String(200))
    ultimo_error = Column(Text)
    estd = Column(String(20), nullable=False)
    rntnts = Column(Integer, nullable=False, server_default="0")


class EstadoAlarma(Base):
    """Estado por dispositivo: notifica al entrar en alarma y rearma al salir."""

    __tablename__ = "estd_alrm_dspstv"
    id_alrm = Column(Integer, ForeignKey("alrm.id_alrm", ondelete="CASCADE"), primary_key=True)
    id_dspstv = Column(
        Integer, ForeignKey("dspstv.id_dspstv", ondelete="CASCADE"), primary_key=True
    )
    en_alarma = Column(Boolean, nullable=False, server_default=text("false"))
    ultima_fecha = Column(TIMESTAMP(timezone=True), nullable=False)


class IntentoNotificacion(Base):
    __tablename__ = "intnt_ntfccn"
    id_intnt = Column(BigInteger, primary_key=True, autoincrement=True)
    id_ntfccn = Column(BigInteger, ForeignKey("ntfccn_envd.id_ntfccn"), nullable=False, index=True)
    numero = Column(Integer, nullable=False)
    fecha = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    resultado = Column(String(20), nullable=False)
    error = Column(Text)
    mensaje_id = Column(String(200))
