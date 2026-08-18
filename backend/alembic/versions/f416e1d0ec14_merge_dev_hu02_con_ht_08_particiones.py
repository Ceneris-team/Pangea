"""merge dev (HU02) con HT-08 particiones

Revision ID: f416e1d0ec14
Revises: a7f31c4b9e02, ebeb9ec49fd3
Create Date: 2026-08-05 14:29:06.985446

Al traer dev a jareth quedaron dos heads de Alembic en paralelo:
ebeb9ec49fd3 (HU02, tabla tkn_rcprcn) colgando de 286308e821ed, y
a7f31c4b9e02 (HT-08, particiones de tlmtr) al final de la otra rama. Git
no lo marca como conflicto -son archivos distintos-, pero deja
"alembic upgrade head" inutilizable con "Multiple head revisions are
present".

Esta migración solo une ambas ramas del historial: no cambia el esquema,
por eso upgrade/downgrade van vacíos.
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "f416e1d0ec14"
down_revision: Union[str, Sequence[str], None] = ("a7f31c4b9e02", "ebeb9ec49fd3")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
