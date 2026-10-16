"""Solicitudes empresariales, propuesta y aceptación previa a la activación.

Revision ID: d9406bc12a85
Revises: c82af61d703e
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "d9406bc12a85"
down_revision = "c82af61d703e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("solicitud_suscripcion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("id_clnt", sa.Integer(), sa.ForeignKey("clnt.id_clnt"), nullable=False),
        sa.Column("solicitante_id", sa.Integer(), sa.ForeignKey("usr.id_usr"), nullable=False),
        sa.Column("estado", sa.String(30), nullable=False, server_default="Pendiente"),
        sa.Column("solicitud", JSONB(), nullable=False),
        sa.Column("propuesta", JSONB()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aceptante_id", sa.Integer(), sa.ForeignKey("usr.id_usr")),
        sa.Column("aceptada_en", sa.TIMESTAMP(timezone=True)),
        sa.Column("suscripcion_resultante_id", sa.Integer(), sa.ForeignKey("sscrpcn.id_sscrpcn")),
        sa.Column("clave_idempotencia", sa.String(64), nullable=False),
        sa.Column("creada_en", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("actualizada_en", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("estado IN ('Pendiente','En evaluación','Esperando aceptación','Aceptada','Aplicada','Rechazada','Cancelada')", name="solicitud_suscripcion_estado_check"),
        sa.UniqueConstraint("id_clnt", "clave_idempotencia", name="uq_solicitud_suscripcion_clave"))
    op.create_index("uq_solicitud_suscripcion_abierta", "solicitud_suscripcion", ["id_clnt"], unique=True,
                    postgresql_where=sa.text("estado IN ('Pendiente','En evaluación','Esperando aceptación','Aceptada')"))
    op.create_index("ix_solicitud_suscripcion_estado_fecha", "solicitud_suscripcion", ["estado", "creada_en"])


def downgrade():
    op.drop_table("solicitud_suscripcion")
