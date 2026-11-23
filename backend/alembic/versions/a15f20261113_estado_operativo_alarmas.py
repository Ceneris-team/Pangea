"""Inicio de la condición de alarma y reevaluación tras editar una regla."""

import sqlalchemy as sa

from alembic import op

revision = "a15f20261113"
down_revision = "a14e20261105"
branch_labels = None
depends_on = None


def upgrade():
    # No se inventa una fecha de inicio para alarmas disparadas antes de esta migración.
    op.add_column(
        "estd_alrm_dspstv", sa.Column("inicio_alarma", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column(
        "estd_alrm_dspstv",
        sa.Column("pendiente_evaluacion", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("estd_alrm_dspstv", "pendiente_evaluacion")
    op.drop_column("estd_alrm_dspstv", "inicio_alarma")
