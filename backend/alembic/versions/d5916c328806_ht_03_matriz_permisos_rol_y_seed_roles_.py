"""HT-03: matriz de permisos con rol y seed de los 4 roles base

Revision ID: d5916c328806
Revises: 4c12e5dcc697
Create Date: 2026-07-24 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd5916c328806'
down_revision: Union[str, Sequence[str], None] = '4c12e5dcc697'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Los 4 roles base del sistema (HT-03 CA4): plantillas de permisos editables
# en BD, no valores fijos en código. Grafía alineada con
# app/scripts/seed_usuarios_prueba.py (HT-04) y frontend/src/config/roles.ts.
ROLES_BASE = ["Administrador", "Técnico CENERIS", "Cliente Final", "Administrador Comercial"]


def upgrade() -> None:
    """Upgrade schema."""
    # Seed idempotente: si el rol ya existe (p.ej. por seed_usuarios_prueba.py
    # corrido a mano en dev), no falla por duplicado.
    for nombre in ROLES_BASE:
        op.execute(
            sa.text(
                "INSERT INTO rl (nmbr, dscrpcn) VALUES (:nmbr, :dscrpcn) "
                "ON CONFLICT (nmbr) DO NOTHING"
            ).bindparams(nmbr=nombre, dscrpcn=f"Rol {nombre}")
        )

    # Eslabón Usuario-Sede-Rol-Permiso: prms_usr_sd pasa a registrar también
    # bajo qué rol se otorgó el permiso, no solo usuario+sede+módulo.
    op.add_column('prms_usr_sd', sa.Column('id_rl', sa.Integer(), nullable=True))
    op.execute(
        "UPDATE prms_usr_sd SET id_rl = usr.id_rl "
        "FROM usr WHERE usr.id_usr = prms_usr_sd.id_usr"
    )
    op.alter_column('prms_usr_sd', 'id_rl', nullable=False)
    op.create_foreign_key(
        'fk_prmsusrsd_rl', 'prms_usr_sd', 'rl', ['id_rl'], ['id_rl'],
    )

    op.create_check_constraint(
        'prmsusrsd_mdl_check',
        'prms_usr_sd',
        "mdl IN ('Usuarios','Ubicaciones','Dispositivos','Ingesta','Tableros','Alarmas','Comercial')",
    )
    op.create_check_constraint(
        'prmsusrsd_nvl_check',
        'prms_usr_sd',
        "nvl IN ('Lectura','Edición','Ninguno')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('prmsusrsd_nvl_check', 'prms_usr_sd', type_='check')
    op.drop_constraint('prmsusrsd_mdl_check', 'prms_usr_sd', type_='check')
    op.drop_constraint('fk_prmsusrsd_rl', 'prms_usr_sd', type_='foreignkey')
    op.drop_column('prms_usr_sd', 'id_rl')

    # No se borran los roles: pueden estar en uso por usr.id_rl.
