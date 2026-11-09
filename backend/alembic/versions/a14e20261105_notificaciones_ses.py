"""HT-14: SES, bandeja transaccional, activaciones e historial."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "a14e20261105"
down_revision = "a11d20261104"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("ntfccn_envd", "id_alrm", existing_type=sa.Integer(), nullable=True)
    op.alter_column(
        "ntfccn_envd",
        "fch_env",
        existing_type=sa.TIMESTAMP(timezone=True),
        nullable=True,
        server_default=None,
    )
    for column in (
        sa.Column("id_usr", sa.Integer(), sa.ForeignKey("usr.id_usr")),
        sa.Column("id_sd", sa.Integer(), sa.ForeignKey("sd.id_sd")),
        sa.Column("tipo", sa.String(50), nullable=False, server_default="alarma_activada"),
        sa.Column("plantilla", sa.String(50), nullable=False, server_default="alarma_activada"),
        sa.Column(
            "contexto", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("clave", sa.String(64)),
        sa.Column(
            "fch_crcn", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "prxm_intnt", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("bloqueo_hasta", sa.TIMESTAMP(timezone=True)),
        sa.Column("mensaje_id", sa.String(200)),
        sa.Column("ultimo_error", sa.Text()),
    ):
        op.add_column("ntfccn_envd", column)
    op.execute(
        "UPDATE ntfccn_envd n SET id_usr=a.id_usr, id_sd=a.id_sd FROM alrm a WHERE a.id_alrm=n.id_alrm"
    )
    op.create_unique_constraint("uq_ntfccn_clave", "ntfccn_envd", ["clave"])
    op.create_check_constraint(
        "ntfccnenvd_estado_check",
        "ntfccn_envd",
        "estd IN ('Pendiente','Encolado','Reintentando','Enviado','Fallido')",
    )
    op.create_index("idx_ntfccn_pendiente", "ntfccn_envd", ["estd", "prxm_intnt"])
    op.create_index("idx_ntfccn_usuario_fecha", "ntfccn_envd", ["id_usr", "fch_crcn"])
    op.create_table(
        "estd_alrm_dspstv",
        sa.Column(
            "id_alrm",
            sa.Integer(),
            sa.ForeignKey("alrm.id_alrm", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "id_dspstv",
            sa.Integer(),
            sa.ForeignKey("dspstv.id_dspstv", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("en_alarma", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ultima_fecha", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_table(
        "intnt_ntfccn",
        sa.Column("id_intnt", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "id_ntfccn", sa.BigInteger(), sa.ForeignKey("ntfccn_envd.id_ntfccn"), nullable=False
        ),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column(
            "fecha", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("resultado", sa.String(20), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("mensaje_id", sa.String(200)),
    )
    op.create_index("ix_intnt_ntfccn_id_ntfccn", "intnt_ntfccn", ["id_ntfccn"])
    # HT-11 usa un rol restringido; dar acceso también al desplegar con ese rol.
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='pangea_app') THEN
        GRANT SELECT,INSERT,UPDATE,DELETE ON estd_alrm_dspstv,intnt_ntfccn TO pangea_app;
        GRANT USAGE,SELECT ON SEQUENCE intnt_ntfccn_id_intnt_seq TO pangea_app;
    END IF; END $$""")


def downgrade():
    incompatibles = (
        op.get_bind()
        .execute(
            sa.text("SELECT count(*) FROM ntfccn_envd WHERE id_alrm IS NULL OR fch_env IS NULL")
        )
        .scalar_one()
    )
    if incompatibles:
        raise RuntimeError(
            "No se puede revertir HT-14 conservando notificaciones genéricas o pendientes"
        )
    op.drop_table("intnt_ntfccn")
    op.drop_table("estd_alrm_dspstv")
    op.drop_index("idx_ntfccn_usuario_fecha", "ntfccn_envd")
    op.drop_index("idx_ntfccn_pendiente", "ntfccn_envd")
    op.drop_constraint("ntfccnenvd_estado_check", "ntfccn_envd", type_="check")
    op.drop_constraint("uq_ntfccn_clave", "ntfccn_envd", type_="unique")
    for column in (
        "id_usr",
        "id_sd",
        "tipo",
        "plantilla",
        "contexto",
        "clave",
        "fch_crcn",
        "prxm_intnt",
        "bloqueo_hasta",
        "mensaje_id",
        "ultimo_error",
    ):
        op.drop_column("ntfccn_envd", column)
    op.alter_column("ntfccn_envd", "id_alrm", existing_type=sa.Integer(), nullable=False)
    op.alter_column(
        "ntfccn_envd",
        "fch_env",
        existing_type=sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.text("NOW()"),
    )
