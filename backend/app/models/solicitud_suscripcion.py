from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
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


class SolicitudSuscripcion(Base):
    __tablename__ = "solicitud_suscripcion"
    __table_args__ = (
        CheckConstraint("estado IN ('Pendiente','En evaluación','Esperando aceptación','Aceptada','Aplicada','Rechazada','Cancelada')", name="solicitud_suscripcion_estado_check"),
        UniqueConstraint("id_clnt", "clave_idempotencia", name="uq_solicitud_suscripcion_clave"),
        Index("uq_solicitud_suscripcion_abierta", "id_clnt", unique=True,
              postgresql_where=text("estado IN ('Pendiente','En evaluación','Esperando aceptación','Aceptada')")),
        Index("ix_solicitud_suscripcion_estado_fecha", "estado", "creada_en"),
    )

    id = Column(Integer, primary_key=True)
    id_clnt = Column(Integer, ForeignKey("clnt.id_clnt"), nullable=False)
    solicitante_id = Column(Integer, ForeignKey("usr.id_usr"), nullable=False)
    estado = Column(String(30), nullable=False, server_default="Pendiente")
    solicitud = Column(JSONB, nullable=False)
    propuesta = Column(JSONB)
    revision = Column(Integer, nullable=False, server_default="0")
    aceptante_id = Column(Integer, ForeignKey("usr.id_usr"))
    aceptada_en = Column(TIMESTAMP(timezone=True))
    suscripcion_resultante_id = Column(Integer, ForeignKey("sscrpcn.id_sscrpcn"))
    clave_idempotencia = Column(String(64), nullable=False)
    creada_en = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    actualizada_en = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
