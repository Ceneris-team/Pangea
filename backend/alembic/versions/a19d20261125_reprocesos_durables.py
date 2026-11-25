"""Solicitudes durables y tiempos del historial de reprocesos."""

from alembic import op
import sqlalchemy as sa

revision = "a19d20261125"
down_revision = "a18c20261124"
branch_labels = None
depends_on = None


def upgrade():
    for nombre in ("fch_inicio", "fch_fin", "proximo_envio"):
        op.add_column("intnt_prcsmnt", sa.Column(nombre, sa.DateTime(timezone=True)))
    op.add_column(
        "intnt_prcsmnt", sa.Column("reintentos", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("intnt_prcsmnt", sa.Column("id_intento_anterior", sa.BigInteger()))
    op.add_column("intnt_prcsmnt", sa.Column("registros_guardados", sa.Integer()))
    op.create_foreign_key(
        "fk_intento_anterior",
        "intnt_prcsmnt",
        "intnt_prcsmnt",
        ["id_intento_anterior"],
        ["id_intnt"],
    )
    op.execute("UPDATE intnt_prcsmnt SET fch_fin = fch_intnt WHERE rsltd IN ('Exitoso', 'Fallido')")
    op.create_index(
        "uq_intento_ingesta_activo",
        "intnt_prcsmnt",
        ["id_archv"],
        unique=True,
        postgresql_where=sa.text("rsltd IN ('Pendiente', 'Procesando')"),
    )
    op.create_index(
        "idx_intento_ingesta_despacho",
        "intnt_prcsmnt",
        ["proximo_envio"],
        postgresql_where=sa.text("rsltd = 'Pendiente'"),
    )


def downgrade():
    op.drop_index("idx_intento_ingesta_despacho", table_name="intnt_prcsmnt")
    op.drop_index("uq_intento_ingesta_activo", table_name="intnt_prcsmnt")
    op.drop_constraint("fk_intento_anterior", "intnt_prcsmnt", type_="foreignkey")
    for nombre in (
        "registros_guardados",
        "id_intento_anterior",
        "reintentos",
        "proximo_envio",
        "fch_fin",
        "fch_inicio",
    ):
        op.drop_column("intnt_prcsmnt", nombre)
