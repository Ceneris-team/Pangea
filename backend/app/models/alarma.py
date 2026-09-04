from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)

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
    """HT-14, AWS SES + Telegram."""

    __tablename__ = "ntfccn_envd"
    __table_args__ = (CheckConstraint("cnl IN ('email','telegram')", name="ntfccnenvd_cnl_check"),)

    id_ntfccn = Column(BigInteger, primary_key=True, autoincrement=True)
    id_alrm = Column(Integer, ForeignKey("alrm.id_alrm"), nullable=False)
    cnl = Column(String(20), nullable=False)
    dstn = Column(String(150), nullable=False)
    fch_env = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    estd = Column(String(20), nullable=False)
    rntnts = Column(Integer, nullable=False, server_default="0")
