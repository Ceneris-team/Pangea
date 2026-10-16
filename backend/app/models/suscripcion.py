from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class PlanSuscripcion(Base):
    __tablename__ = "pln_sscrpcn"

    id_pln = Column(Integer, primary_key=True, autoincrement=True)
    nmbr = Column(String(100), nullable=False, unique=True)
    dscrpcn = Column(String(300))
    prc_mnsl = Column(Numeric(12, 2), nullable=False)
    estd = Column(String(20), nullable=False, server_default="Activo")
    moneda = Column(String(3), nullable=False, server_default="PEN")
    revision = Column(Integer, nullable=False, server_default="1")
    funcionalidades = Column(JSONB, nullable=False, server_default="[]")


class FuncionalidadComercial(Base):
    __tablename__ = "funcionalidad_comercial"

    codigo = Column(String(80), primary_key=True)
    nombre = Column(String(150), nullable=False)
    disponible = Column(Integer, nullable=False, server_default="0")


class ComplementoComercial(Base):
    __tablename__ = "complemento_comercial"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(150), nullable=False, unique=True)
    tipo = Column(String(20), nullable=False)  # Recurrente / Servicio
    precio = Column(Numeric(12, 2), nullable=False)
    moneda = Column(String(3), nullable=False, server_default="PEN")
    cupos = Column(JSONB, nullable=False, server_default="{}")
    funcionalidades = Column(JSONB, nullable=False, server_default="[]")
    activo = Column(Integer, nullable=False, server_default="1")


class LimitePlan(Base):
    __tablename__ = "lmt_pln"
    __table_args__ = (
        CheckConstraint("mx_sds >= 0", name="lmtpln_mxsds_check"),
        CheckConstraint("mx_ubccns >= 0", name="lmtpln_mxubccns_check"),
        CheckConstraint("mx_dspstvs >= 0", name="lmtpln_mxdspstvs_check"),
        CheckConstraint("mx_usrs >= 0", name="lmtpln_mxusrs_check"),
    )

    id_lmt = Column(Integer, primary_key=True, autoincrement=True)
    id_pln = Column(Integer, ForeignKey("pln_sscrpcn.id_pln"), nullable=False, unique=True)
    mx_sds = Column(Integer, nullable=False, server_default="1")
    mx_ubccns = Column(Integer, nullable=False)
    mx_dspstvs = Column(Integer, nullable=False)
    mx_usrs = Column(Integer, nullable=False)


class Suscripcion(Base):
    __tablename__ = "sscrpcn"
    __table_args__ = (
        UniqueConstraint("id_clnt", "clave_idempotencia", name="uq_suscripcion_idempotencia"),
        Index("uq_suscripcion_programada", "id_clnt", unique=True, postgresql_where=text("estd = 'Programada'")),
        Index("idx_sscrpcn_vncmnt", "fch_vncmnt", "estd"),
        Index(
            "uq_sscrpcn_clnt_activa",
            "id_clnt",
            unique=True,
            postgresql_where=text("estd = 'Activa'"),
        ),
    )

    id_sscrpcn = Column(Integer, primary_key=True, autoincrement=True)
    id_clnt = Column(Integer, ForeignKey("clnt.id_clnt"), nullable=False)
    id_pln = Column(Integer, ForeignKey("pln_sscrpcn.id_pln"), nullable=False)
    fch_inc = Column(Date, nullable=False)
    fch_vncmnt = Column(Date, nullable=False)
    estd = Column(String(20), nullable=False, server_default="Activa")
    condiciones = Column(JSONB)
    clave_idempotencia = Column(String(64))


class Cobro(Base):
    __tablename__ = "cbr"
    __table_args__ = (CheckConstraint("fch_cbr <= CURRENT_DATE", name="cbr_fchcbr_check"),)

    id_cbr = Column(Integer, primary_key=True, autoincrement=True)
    id_sscrpcn = Column(Integer, ForeignKey("sscrpcn.id_sscrpcn"), nullable=False)
    mnt = Column(Numeric(12, 2), nullable=False)
    fch_cbr = Column(Date, nullable=False)
    mtd_pg = Column(String(30), nullable=False)
    fch_rgstr = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))


class PermisoUsuarioSede(Base):
    """HT-03: permisos granulares por módulo y sede."""

    __tablename__ = "prms_usr_sd"
    __table_args__ = (
        UniqueConstraint("id_usr", "id_sd", "mdl", name="uq_prmsusrsd_usr_sd_mdl"),
        CheckConstraint(
            "mdl IN ('Usuarios','Ubicaciones','Dispositivos','Ingesta','Tableros','Alarmas','Comercial')",
            name="prmsusrsd_mdl_check",
        ),
        CheckConstraint(
            "nvl IN ('Lectura','Edición','Ninguno')",
            name="prmsusrsd_nvl_check",
        ),
    )

    id_prms = Column(Integer, primary_key=True, autoincrement=True)
    id_usr = Column(Integer, ForeignKey("usr.id_usr"), nullable=False)
    id_sd = Column(Integer, ForeignKey("sd.id_sd"), nullable=False)
    id_rl = Column(Integer, ForeignKey("rl.id_rl"), nullable=False)
    mdl = Column(String(50), nullable=False)
    nvl = Column(String(20), nullable=False)
