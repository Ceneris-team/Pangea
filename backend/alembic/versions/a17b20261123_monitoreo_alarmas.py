"""Continuidad de captura y notificaciones compartidas por proyecto."""

import sqlalchemy as sa

from alembic import op

revision = "a17b20261123"
down_revision = "a16a20261123"
branch_labels = None
depends_on = None


def upgrade():
    for nombre in ["ultima_recepcion", "sin_datos_desde", "aviso_sin_datos"]:
        op.add_column("dspstv", sa.Column(nombre, sa.TIMESTAMP(timezone=True)))
    op.execute(
        sa.text(
            "UPDATE dspstv d SET ultima_recepcion=a.ultima FROM "
            "(SELECT id_dspstv, max(fch_dtccn) ultima FROM archv_ingst "
            "WHERE estd='Exitoso' GROUP BY id_dspstv) a WHERE d.id_dspstv=a.id_dspstv"
        )
    )
    op.add_column(
        "estd_alrm_dspstv",
        sa.Column(
            "resumen_pendiente", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column("estd_alrm_dspstv", sa.Column("ultimo_valor", sa.Numeric(14, 4)))
    op.add_column(
        "ntfccn_envd", sa.Column("id_ubccn", sa.Integer(), sa.ForeignKey("ubccn.id_ubccn"))
    )
    op.execute(
        sa.text(
            "UPDATE ntfccn_envd n SET id_ubccn=a.id_ubccn FROM alrm a WHERE n.id_alrm=a.id_alrm"
        )
    )
    op.drop_constraint("ntfccnenvd_estado_check", "ntfccn_envd", type_="check")
    op.create_check_constraint(
        "ntfccnenvd_estado_check",
        "ntfccn_envd",
        "estd IN ('Pendiente','Encolado','Reintentando','Enviado','Fallido','Omitido')",
    )


def downgrade():
    op.execute(sa.text("UPDATE ntfccn_envd SET estd='Fallido' WHERE estd='Omitido'"))
    op.drop_constraint("ntfccnenvd_estado_check", "ntfccn_envd", type_="check")
    op.create_check_constraint(
        "ntfccnenvd_estado_check",
        "ntfccn_envd",
        "estd IN ('Pendiente','Encolado','Reintentando','Enviado','Fallido')",
    )
    op.drop_column("ntfccn_envd", "id_ubccn")
    op.drop_column("estd_alrm_dspstv", "ultimo_valor")
    op.drop_column("estd_alrm_dspstv", "resumen_pendiente")
    for nombre in ["aviso_sin_datos", "sin_datos_desde", "ultima_recepcion"]:
        op.drop_column("dspstv", nombre)
