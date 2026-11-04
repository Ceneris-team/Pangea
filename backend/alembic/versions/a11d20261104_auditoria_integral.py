"""HT-11: auditoría transaccional, mensual e inmutable en PostgreSQL."""

from pathlib import Path

from alembic import op

revision = "a11d20261104"
down_revision = "f71d3b8a902c"
branch_labels = None
depends_on = None


def upgrade():
    # El SQL es parte de esta revisión, no un script manual pendiente de aplicar.
    sql = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    op.get_bind().exec_driver_sql(sql, execution_options={"no_parameters": True})


def downgrade():
    # No se destruye ni debilita un historial de seguridad mediante un downgrade.
    raise RuntimeError("HT-11 conserva el historial; restaurar un respaldo para volver atrás")
