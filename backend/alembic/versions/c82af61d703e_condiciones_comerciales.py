"""Condiciones contratadas, catálogo y programación comercial.

Revision ID: c82af61d703e
Revises: b36e91f20c74
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "c82af61d703e"
down_revision = "b36e91f20c74"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pln_sscrpcn", sa.Column("moneda", sa.String(3), nullable=False, server_default="PEN"))
    op.add_column("pln_sscrpcn", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("pln_sscrpcn", sa.Column("funcionalidades", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("sscrpcn", sa.Column("condiciones", postgresql.JSONB()))
    op.add_column("sscrpcn", sa.Column("clave_idempotencia", sa.String(64)))
    op.create_unique_constraint("uq_suscripcion_idempotencia", "sscrpcn", ["id_clnt", "clave_idempotencia"])
    op.create_index("uq_suscripcion_programada", "sscrpcn", ["id_clnt"], unique=True,
                    postgresql_where=sa.text("estd = 'Programada'"))
    op.create_table("funcionalidad_comercial",
        sa.Column("codigo", sa.String(80), primary_key=True),
        sa.Column("nombre", sa.String(150), nullable=False),
        sa.Column("disponible", sa.Integer(), nullable=False, server_default="0"))
    op.create_table("complemento_comercial",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(150), nullable=False, unique=True),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("precio", sa.Numeric(12, 2), nullable=False),
        sa.Column("moneda", sa.String(3), nullable=False, server_default="PEN"),
        sa.Column("cupos", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("funcionalidades", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("activo", sa.Integer(), nullable=False, server_default="1"))
    op.execute("""INSERT INTO funcionalidad_comercial (codigo, nombre, disponible) VALUES
        ('tableros', 'Tableros personalizables', 1),
        ('ml_predicciones', 'Predicciones con machine learning', 0),
        ('reportes_avanzados', 'Reportes avanzados', 0)""")
    op.execute("UPDATE pln_sscrpcn SET funcionalidades = '[\"tableros\"]'::jsonb")
    op.execute("""UPDATE sscrpcn s SET condiciones = jsonb_build_object(
        'plan_nombre', p.nmbr, 'revision_plan', 1, 'moneda', 'PEN',
        'periodicidad', 'Mensual', 'precio_acordado', p.prc_mnsl::text,
        'referencia', 'Migración de suscripción existente', 'motivo', 'Migración',
        'dias_gracia', 0, 'es_prueba', false,
        'limites', jsonb_build_object('ubicaciones', l.mx_ubccns, 'dispositivos', l.mx_dspstvs, 'usuarios', l.mx_usrs),
        'funcionalidades', '["tableros"]'::jsonb, 'complementos', '[]'::jsonb,
        'importe_servicios', '0.00', 'politica_vencimiento', 'Solo lectura; ingesta preservada')
        FROM pln_sscrpcn p JOIN lmt_pln l ON l.id_pln = p.id_pln
        WHERE s.id_pln = p.id_pln""")


def downgrade():
    op.drop_table("complemento_comercial")
    op.drop_table("funcionalidad_comercial")
    op.drop_index("uq_suscripcion_programada", table_name="sscrpcn")
    op.drop_constraint("uq_suscripcion_idempotencia", "sscrpcn", type_="unique")
    op.drop_column("sscrpcn", "clave_idempotencia")
    op.drop_column("sscrpcn", "condiciones")
    op.drop_column("pln_sscrpcn", "funcionalidades")
    op.drop_column("pln_sscrpcn", "revision")
    op.drop_column("pln_sscrpcn", "moneda")
