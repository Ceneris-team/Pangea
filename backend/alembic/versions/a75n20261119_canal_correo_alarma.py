"""HU30 (PP-75 / PP-232): canal de correo activable por alarma.

alrm.cnl_crr_actv indica si la alarma notifica por correo. Activar el canal
sin destinatarios agrega el correo de la cuenta del usuario; desactivarlo
conserva los destinatarios pero deja de enviar avisos (CA4).

server_default true: las alarmas que ya existen siguen notificando como
hasta ahora.
"""

import sqlalchemy as sa

from alembic import op

revision = "a75n20261119"
down_revision = "a14e20261105"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "alrm",
        sa.Column("cnl_crr_actv", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade():
    op.drop_column("alrm", "cnl_crr_actv")
