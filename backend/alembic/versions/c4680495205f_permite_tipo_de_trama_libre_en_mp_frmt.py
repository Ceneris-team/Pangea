"""permite tipo de trama libre en mp_frmt

Revision ID: c4680495205f
Revises: dcc96950695d
Create Date: 2026-08-21 15:10:00.000000

El equipo de telemetría configura dataloggers con prefijos de archivo
propios según el proyecto (no solo H_/E_/P_), y cada letra nueva exigía
hasta ahora una migración + deploy para agregarla al CHECK constraint
(ver dcc96950695d, c8d47a2b6f13). Se saca el catálogo cerrado de la BD:
tp_trm pasa a validarse en la aplicación (_validar_tipo_trama en
routers/mapeos.py: una letra A-Z) y el técnico de telemetría la define
al crear el mapeo desde la UI, sin tocar código. H/E/P siguen siendo
valores válidos -no eran especiales, solo los primeros cargados-.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4680495205f'
down_revision: Union[str, Sequence[str], None] = 'dcc96950695d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("mpfrmt_tptrm_check", "mp_frmt", type_="check")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_check_constraint(
        "mpfrmt_tptrm_check",
        "mp_frmt",
        "tp_trm IN ('H','E','P')",
    )
