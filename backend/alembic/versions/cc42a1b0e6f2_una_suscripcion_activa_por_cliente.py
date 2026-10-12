"""Una suscripción activa por cliente.

Revision ID: cc42a1b0e6f2
Revises: d2f8a1c34b57
"""

from alembic import op

revision = "cc42a1b0e6f2"
down_revision = "d2f8a1c34b57"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX uq_sscrpcn_clnt_activa ON sscrpcn (id_clnt) "
        "WHERE estd = 'Activa'"
    )


def downgrade() -> None:
    op.drop_index("uq_sscrpcn_clnt_activa", table_name="sscrpcn")
