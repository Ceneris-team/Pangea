"""Resultados derivados separados de la telemetría original."""

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import synonym

from app.database import Base


class ConfiguracionCalculo(Base):
    __tablename__ = "clcl_config"
    __table_args__ = (
        CheckConstraint("tolerancia_segundos BETWEEN 0 AND 3600"),
        CheckConstraint("espera_horas BETWEEN 1 AND 720"),
    )
    id_sd = Column(Integer, ForeignKey("sd.id_sd"), primary_key=True)
    tolerancia_segundos = Column(Integer, nullable=False, server_default="60")
    espera_horas = Column(Integer, nullable=False, server_default="24")


class DependenciaCalculo(Base):
    __tablename__ = "clcl_dependencia"
    __table_args__ = (
        CheckConstraint("(id_prmtr IS NULL) <> (id_origen_calculado IS NULL)"),
        CheckConstraint("id_prm_clc <> id_origen_calculado"),
    )
    id_prm_clc = Column(Integer, ForeignKey("prmtr_clcld.id_prm_clc"), primary_key=True)
    variable = Column(String(40), primary_key=True)
    id_prmtr = Column(Integer, ForeignKey("prmtr.id_prmtr"))
    id_origen_calculado = Column(Integer, ForeignKey("prmtr_clcld.id_prm_clc"))
    unidad_origen = Column(String(30), nullable=False)


class SerieCalculada(Base):
    __tablename__ = "clcl_serie"
    __table_args__ = (UniqueConstraint("id_prm_clc", "id_ubccn"),)
    id_serie = Column(Integer, primary_key=True)
    id_prm_clc = Column(Integer, ForeignKey("prmtr_clcld.id_prm_clc"), nullable=False)
    id_ubccn = Column(Integer, ForeignKey("ubccn.id_ubccn"), nullable=False)


class ResultadoCalculo(Base):
    __tablename__ = "clcl_resultado"
    __table_args__ = (
        UniqueConstraint("id_prm_clc", "id_ubccn", "fch_hr"),
        Index("idx_clcl_resultado_contexto", "id_ubccn", "id_prm_clc", "fch_hr"),
        CheckConstraint("estado IN ('Calculado','Pendiente de datos','Incompleto','Fallido')"),
        CheckConstraint("(estado = 'Calculado') = (vlr IS NOT NULL)"),
    )
    id_resultado = Column(BigInteger, primary_key=True)
    id_lctr = synonym("id_resultado")
    id_prm_clc = Column(Integer, ForeignKey("prmtr_clcld.id_prm_clc"), nullable=False)
    id_ubccn = Column(Integer, ForeignKey("ubccn.id_ubccn"), nullable=False)
    id_sd = Column(Integer, ForeignKey("sd.id_sd"), nullable=False)
    fch_hr = Column(TIMESTAMP(timezone=True), nullable=False)
    vlr = Column(Float)
    estado = Column(String(30), nullable=False)
    causa = Column(String(500))
    revision = Column(Integer, nullable=False, server_default="1")
    trazabilidad = Column(JSONB, nullable=False)
    actualizado_en = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))

    # Identidades de lectura públicas: los valores negativos son fuentes
    # calculadas, nunca dispositivos ni parámetros físicos ficticios.
    @hybrid_property
    def id_prmtr(self):
        return -self.id_prm_clc

    @hybrid_property
    def id_dspstv(self):
        return -self.id_ubccn


class RevisionCalculo(Base):
    __tablename__ = "clcl_revision"
    id_revision = Column(BigInteger, primary_key=True)
    id_resultado = Column(BigInteger, ForeignKey("clcl_resultado.id_resultado"), nullable=False)
    revision = Column(Integer, nullable=False)
    anterior = Column(JSONB, nullable=False)
    creada_en = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    __table_args__ = (UniqueConstraint("id_resultado", "revision"),)


class TrabajoCalculo(Base):
    """Cola transaccional: Beat rescata trabajos si el broker/worker cae."""

    __tablename__ = "clcl_trabajo"
    id_trabajo = Column(BigInteger, primary_key=True)
    id_sd = Column(Integer, ForeignKey("sd.id_sd"), nullable=False)
    id_prm_clc = Column(Integer, ForeignKey("prmtr_clcld.id_prm_clc"))
    id_ubccn = Column(Integer, ForeignKey("ubccn.id_ubccn"))
    inicio = Column(TIMESTAMP(timezone=True))
    fin = Column(TIMESTAMP(timezone=True))
    cursor = Column(JSONB)
    estado = Column(String(40), nullable=False, server_default="Pendiente")
    procesados = Column(Integer, nullable=False, server_default="0")
    incidencias = Column(Integer, nullable=False, server_default="0")
    error = Column(String(500))
    creado_en = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    actualizado_en = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    __table_args__ = (Index("idx_clcl_trabajo_estado", "estado", "id_trabajo"),)
