"""Conserva originales y separa archivo, equipo y monitoreo del proyecto."""

import sqlalchemy as sa

from alembic import op

revision = "a16a20261123"
down_revision = "a15f20261113"
branch_labels = None
depends_on = None


def upgrade():
    duplicadas = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT id_cnxn FROM dspstv WHERE estd='Activo' "
                "GROUP BY id_cnxn HAVING count(*) > 1"
            )
        )
        .scalars()
        .all()
    )
    if duplicadas:
        raise RuntimeError(
            f"Resuelve las conexiones con varios equipos activos antes de migrar: {duplicadas}"
        )
    op.create_index(
        "uq_dspstv_conexion_activa",
        "dspstv",
        ["id_cnxn"],
        unique=True,
        postgresql_where=sa.text("estd = 'Activo'"),
    )
    op.add_column(
        "ubccn",
        sa.Column("monitoreo_activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "archv_ingst", sa.Column("id_dspstv", sa.Integer(), sa.ForeignKey("dspstv.id_dspstv"))
    )
    op.create_index("ix_archv_ingst_id_dspstv", "archv_ingst", ["id_dspstv"])
    for nombre, tipo in [
        ("version_origen", sa.String(64)),
        ("sha256", sa.String(64)),
        ("clave_original", sa.String(600)),
        ("contenido_original", sa.LargeBinary()),
    ]:
        op.add_column("archv_ingst", sa.Column(nombre, tipo, nullable=True))
    # Solo se atribuye el histórico si la conexión tuvo UN equipo en total.
    op.create_index(
        "idx_archv_cnxn_nombre_version", "archv_ingst", ["id_cnxn", "nmbr_archv", "version_origen"]
    )
    # En conexiones reutilizadas se conserva sin adjudicarlo al equipo actual.
    op.execute(
        sa.text(
            "UPDATE archv_ingst a SET id_dspstv=d.id FROM "
            "(SELECT id_cnxn, min(id_dspstv) AS id FROM dspstv "
            "GROUP BY id_cnxn HAVING count(*)=1) d WHERE a.id_cnxn=d.id_cnxn"
        )
    )


def downgrade():
    op.drop_index("idx_archv_cnxn_nombre_version", table_name="archv_ingst")
    for nombre in ["contenido_original", "clave_original", "sha256", "version_origen"]:
        op.drop_column("archv_ingst", nombre)
    op.drop_index("ix_archv_ingst_id_dspstv", table_name="archv_ingst")
    op.drop_column("archv_ingst", "id_dspstv")
    op.drop_column("ubccn", "monitoreo_activo")
    op.drop_index("uq_dspstv_conexion_activa", table_name="dspstv")
