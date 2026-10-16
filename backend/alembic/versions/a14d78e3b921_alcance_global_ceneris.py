"""El equipo CENERIS trabaja sobre todas las empresas.

Revision ID: a14d78e3b921
Revises: f2183a6d9b42
"""

from alembic import op

revision = "a14d78e3b921"
down_revision = "f2183a6d9b42"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE usr SET scp = 'global' FROM rl WHERE usr.id_rl = rl.id_rl "
               "AND rl.nmbr IN ('Administrador', 'Técnico CENERIS', 'Tecnico CENERIS')")


def downgrade():
    # No se inventa una sede anterior para usuarios que ahora atienden varios clientes.
    pass
