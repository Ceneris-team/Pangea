"""Estado y almacenamiento privado de exportaciones HU33 / HT-17."""

import sqlalchemy as sa
from alembic import op

revision = "f71d3b8a902c"
down_revision = "c3a58e9d204f"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("fch_inicio", "fch_fin", "notificada_en"):
        op.add_column("exprtcn", sa.Column(name, sa.TIMESTAMP(timezone=True)))
    for name, size in (
        ("objeto_clave", 500),
        ("objeto_version", 200),
        ("objeto_bucket", 255),
        ("error", 500),
    ):
        op.add_column("exprtcn", sa.Column(name, sa.String(size)))
    for name in ("filas", "bytes_archivo"):
        op.add_column("exprtcn", sa.Column(name, sa.BigInteger()))
    op.add_column(
        "exprtcn",
        sa.Column("notificacion_estado", sa.String(20), nullable=False, server_default="Pendiente"),
    )
    op.add_column(
        "exprtcn",
        sa.Column("notificacion_intentos", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "exprtcn", sa.Column("intentos", sa.Integer(), nullable=False, server_default="0")
    )
    op.create_index("idx_exprtcn_usr_fecha", "exprtcn", ["id_usr", "fch_slctd"])
    op.create_index("idx_exprtcn_estado_expira", "exprtcn", ["estd", "fch_exprcn"])


def downgrade():
    op.drop_index("idx_exprtcn_estado_expira", table_name="exprtcn")
    op.drop_index("idx_exprtcn_usr_fecha", table_name="exprtcn")
    for name in (
        "fch_inicio",
        "fch_fin",
        "notificada_en",
        "objeto_clave",
        "objeto_version",
        "objeto_bucket",
        "error",
        "filas",
        "bytes_archivo",
        "notificacion_estado",
        "notificacion_intentos",
        "intentos",
    ):
        op.drop_column("exprtcn", name)
