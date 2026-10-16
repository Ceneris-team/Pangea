"""Empresas con proyectos y membresías de usuarios.

Revision ID: f2183a6d9b42
Revises: cc42a1b0e6f2
"""

from alembic import op
import sqlalchemy as sa

revision = "f2183a6d9b42"
down_revision = "cc42a1b0e6f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pryct",
        sa.Column("id_pryct", sa.Integer(), primary_key=True),
        sa.Column("id_clnt", sa.Integer(), sa.ForeignKey("clnt.id_clnt"), nullable=False),
        sa.Column("nmbr", sa.String(150), nullable=False),
        sa.Column("dscrpcn", sa.String(300)),
        sa.Column("estd", sa.String(20), nullable=False, server_default="Activo"),
        sa.UniqueConstraint("id_clnt", "nmbr", name="uq_pryct_clnt_nmbr"),
    )
    op.add_column("sd", sa.Column("id_pryct", sa.Integer(), sa.ForeignKey("pryct.id_pryct")))
    op.create_index("idx_sd_pryct", "sd", ["id_pryct"])
    # Las sedes históricas quedan en un proyecto visible, sin alterar sus IDs.
    op.execute(
        "INSERT INTO pryct (id_clnt, nmbr, dscrpcn) "
        "SELECT DISTINCT id_clnt, 'Operación general', 'Sedes previas a proyectos' FROM sd"
    )
    op.execute(
        "UPDATE sd SET id_pryct = pryct.id_pryct FROM pryct "
        "WHERE sd.id_clnt = pryct.id_clnt AND pryct.nmbr = 'Operación general' "
        "AND sd.id_pryct IS NULL"
    )
    op.create_table(
        "usr_clnt",
        sa.Column("id_mmb", sa.Integer(), primary_key=True),
        sa.Column("id_usr", sa.Integer(), sa.ForeignKey("usr.id_usr"), nullable=False),
        sa.Column("id_clnt", sa.Integer(), sa.ForeignKey("clnt.id_clnt"), nullable=False),
        sa.Column("rol_emp", sa.String(20), nullable=False),
        sa.Column("estd", sa.String(20), nullable=False, server_default="Activo"),
        sa.UniqueConstraint("id_usr", "id_clnt", name="uq_usrclnt_usr_clnt"),
        sa.CheckConstraint("rol_emp IN ('Administrador','Tecnico','Lector')", name="usrclnt_rol_check"),
        sa.CheckConstraint("estd IN ('Activo','Inactivo')", name="usrclnt_estd_check"),
    )
    op.create_index("idx_usrclnt_clnt_estd", "usr_clnt", ["id_clnt", "estd"])
    op.create_table(
        "usr_pryct",
        sa.Column("id_usr_pryct", sa.Integer(), primary_key=True),
        sa.Column("id_mmb", sa.Integer(), sa.ForeignKey("usr_clnt.id_mmb", ondelete="CASCADE"), nullable=False),
        sa.Column("id_pryct", sa.Integer(), sa.ForeignKey("pryct.id_pryct"), nullable=False),
        sa.UniqueConstraint("id_mmb", "id_pryct", name="uq_usrpryct_mmb_pryct"),
    )
    op.drop_constraint("usr_scp_check", "usr", type_="check")
    op.create_check_constraint("usr_scp_check", "usr", "scp IN ('global','por_sede','por_cliente')")
    op.execute(
        "INSERT INTO rl (nmbr, dscrpcn) VALUES "
        "('Usuario Empresa', 'El rol y proyectos efectivos se definen en cada empresa') "
        "ON CONFLICT (nmbr) DO NOTHING"
    )


def downgrade() -> None:
    conexion = op.get_bind()
    if conexion.execute(sa.text("SELECT 1 FROM usr WHERE scp = 'por_cliente' LIMIT 1")).first():
        raise RuntimeError("No se puede revertir mientras existan usuarios empresariales")
    op.drop_constraint("usr_scp_check", "usr", type_="check")
    op.create_check_constraint("usr_scp_check", "usr", "scp IN ('global','por_sede')")
    op.drop_table("usr_pryct")
    op.drop_index("idx_usrclnt_clnt_estd", table_name="usr_clnt")
    op.drop_table("usr_clnt")
    op.drop_index("idx_sd_pryct", table_name="sd")
    op.drop_column("sd", "id_pryct")
    op.drop_table("pryct")
    op.execute("DELETE FROM rl WHERE nmbr = 'Usuario Empresa'")
