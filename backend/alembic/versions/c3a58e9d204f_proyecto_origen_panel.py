"""Guardar el proyecto desde el que se crea un panel vacío.

Revision ID: c3a58e9d204f
Revises: b8c42e6f10a9
"""

import sqlalchemy as sa

from alembic import op

revision = "c3a58e9d204f"
down_revision = "b8c42e6f10a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pnl", sa.Column("id_ubccn_origen", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_pnl_ubccn_origen",
        "pnl",
        "ubccn",
        ["id_ubccn_origen"],
        ["id_ubccn"],
        ondelete="SET NULL",
    )
    op.create_index("idx_pnl_ubccn_origen", "pnl", ["id_ubccn_origen"])
    op.execute("""
        UPDATE pnl AS panel
        SET id_ubccn_origen = unico.id_ubccn
        FROM (
            SELECT id_pnl, MIN(id_ubccn) AS id_ubccn
            FROM pnl_ubccn
            GROUP BY id_pnl
            HAVING COUNT(*) = 1
        ) AS unico
        WHERE panel.id_pnl = unico.id_pnl
    """)


def downgrade() -> None:
    op.drop_index("idx_pnl_ubccn_origen", table_name="pnl")
    op.drop_constraint("fk_pnl_ubccn_origen", "pnl", type_="foreignkey")
    op.drop_column("pnl", "id_ubccn_origen")
