"""Unificar mayúsculas y espacios exteriores de marcas existentes (HU36 / DEF-17)."""

import sqlalchemy as sa

from alembic import op

revision = "a20e20261126"
down_revision = "a19d20261125"
branch_labels = None
depends_on = None


def upgrade():
    conexion = op.get_bind()
    # Se congela aquí la normalización para no depender de futuros cambios de la app.
    marcas = conexion.execute(sa.text("SELECT DISTINCT mrc FROM dspstv")).scalars().all()
    cambios = [
        {"original": marca, "normalizada": marca.strip().title()}
        for marca in marcas
        if marca != marca.strip().title()
    ]
    if cambios:
        conexion.execute(
            sa.text("UPDATE dspstv SET mrc = :normalizada WHERE mrc = :original"), cambios
        )


def downgrade():
    # La limpieza de datos no permite reconstruir la escritura original.
    pass
