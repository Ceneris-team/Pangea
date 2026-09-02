"""HU49: seed del usuario Sistema para auditoria de tramas automaticas

Revision ID: a070693e2870
Revises: 6cf46ba44eab
Create Date: 2026-09-01 00:10:00.000000

HU49 CA5: la creación automática de una trama (mp_frmt) debe quedar en
el log de auditoría (HT-11, lg_adtr), pero esa auditoría ocurre dentro de
una tarea de Celery -sin request HTTP ni JWT de por medio-, y lg_adtr.id_usr
es NOT NULL. Se resuelve sembrando un usuario "Sistema" real y fijo, para
que la auditoría automática tenga a quién atribuirse sin inventar un caso
especial de id_usr NULL en una tabla que hoy no lo permite.

Un ROL DEDICADO ("Sistema"), no reutilizar "Administrador": si alguna vez
alguien lograra loguearse con esta cuenta (bloqueado por estd='Inactivo',
ver abajo), no heredaría los permisos de un rol real - defensa en
profundidad, no solo por prolijidad.

La contraseña es aleatoria, de un solo uso, y NUNCA se persiste en texto
plano en ningún lado (ni siquiera en esta migración: se genera y se
hashea en la misma línea, la variable en claro nunca sale de memoria).
No hace falta guardarla ni comunicarla: estd='Inactivo' hace que
POST /auth/login rechace cualquier intento con este correo antes de que
importe si la contraseña es correcta (ver routers/auth.py: el chequeo de
estd corre después de verify_password, pero como la contraseña real
nunca existió en ningún medio legible, no es una superficie de fuerza
bruta practicable).

Idempotente (ON CONFLICT DO NOTHING): un re-run de esta migración en un
entorno donde ya corrió no debe fallar ni generar un segundo usuario
Sistema.
"""

import secrets
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

from app.security.hashing import hash_password

# revision identifiers, used by Alembic.
revision: str = "a070693e2870"
down_revision: Union[str, Sequence[str], None] = "6cf46ba44eab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Correo fijo: el código de aplicación (services/ingesta/usuario_sistema.py)
# lo usa para resolver el id_usr en tiempo de ejecución, así que este valor
# es efectivamente un contrato entre esta migración y ese módulo.
CORREO_USUARIO_SISTEMA = "sistema.ingesta@pangea.internal"
NOMBRE_ROL_SISTEMA = "Sistema"


def upgrade() -> None:
    """Upgrade schema."""
    conexion = op.get_bind()

    conexion.execute(
        sa.text(
            "INSERT INTO rl (nmbr, dscrpcn) VALUES (:nmbr, :dscrpcn) "
            "ON CONFLICT (nmbr) DO NOTHING"
        ).bindparams(
            nmbr=NOMBRE_ROL_SISTEMA,
            dscrpcn=(
                "Rol técnico reservado para acciones automáticas del sistema "
                "(HU49); no debe asignarse a personas."
            ),
        )
    )

    id_rl = conexion.execute(
        sa.text("SELECT id_rl FROM rl WHERE nmbr = :nmbr").bindparams(
            nmbr=NOMBRE_ROL_SISTEMA
        )
    ).scalar()

    password_desechable = secrets.token_urlsafe(32)
    hash_desechable = hash_password(password_desechable)

    conexion.execute(
        sa.text(
            "INSERT INTO usr "
            "(id_rl, scp, nmbr_cmplt, crr, cntrsn_hsh, dbe_cmbr_pswrd, estd) "
            "VALUES "
            "(:id_rl, 'global', :nmbr_cmplt, :crr, :hsh, false, 'Inactivo') "
            "ON CONFLICT (crr) DO NOTHING"
        ).bindparams(
            id_rl=id_rl,
            nmbr_cmplt="Sistema (procesos automáticos)",
            crr=CORREO_USUARIO_SISTEMA,
            hsh=hash_desechable,
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    conexion = op.get_bind()
    conexion.execute(
        sa.text("DELETE FROM usr WHERE crr = :crr").bindparams(
            crr=CORREO_USUARIO_SISTEMA
        )
    )
    # El rol solo se borra si quedó sin usuarios (podría haber otro usuario
    # Sistema creado a mano en dev, aunque no es el flujo esperado).
    conexion.execute(
        sa.text(
            "DELETE FROM rl WHERE nmbr = :nmbr "
            "AND NOT EXISTS (SELECT 1 FROM usr WHERE usr.id_rl = rl.id_rl)"
        ).bindparams(nmbr=NOMBRE_ROL_SISTEMA)
    )
