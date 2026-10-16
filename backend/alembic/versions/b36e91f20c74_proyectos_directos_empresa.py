"""Asignaciones directas a proyectos geográficos, sin grupos.

Revision ID: b36e91f20c74
Revises: a14d78e3b921

Las tablas anteriores se conservan como histórico para poder revertir
esta migración. La aplicación deja de usarlas o permitir crear grupos.
"""

import sqlalchemy as sa

from alembic import op

revision = "b36e91f20c74"
down_revision = "a14d78e3b921"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usr_pryct_ubccn",
        sa.Column("id_usr_pryct", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id_mmb", sa.Integer(), sa.ForeignKey("usr_clnt.id_mmb", ondelete="CASCADE"), nullable=False),
        sa.Column("id_ubccn", sa.Integer(), sa.ForeignKey("ubccn.id_ubccn"), nullable=False),
        sa.UniqueConstraint("id_mmb", "id_ubccn", name="uq_usrpryctubccn_mmb_ubccn"),
    )
    # Expande cada acceso anterior a los mismos proyectos que podía consultar.
    # La comprobación de empresa evita arrastrar asociaciones inconsistentes.
    op.execute("""
        INSERT INTO usr_pryct_ubccn (id_mmb, id_ubccn)
        SELECT DISTINCT a.id_mmb, u.id_ubccn
        FROM usr_pryct a
        JOIN usr_clnt m ON m.id_mmb = a.id_mmb
        JOIN sd s ON s.id_pryct = a.id_pryct AND s.id_clnt = m.id_clnt
        JOIN ubccn u ON u.id_sd = s.id_sd
    """)


def downgrade():
    op.drop_table("usr_pryct_ubccn")
