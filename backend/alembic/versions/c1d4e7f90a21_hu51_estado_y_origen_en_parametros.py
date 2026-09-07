"""HU51: estado y origen de creacion en el catalogo de parametros

Agrega a prmtr las columnas que HU51 necesita para distinguir un
parametro auto-creado por el motor de ingesta (a partir de una columna
de header sin match) de uno dado de alta a mano:

- estd: 'Activo' (todo lo preexistente y lo creado a mano),
  'Pendiente de revision' (auto-creado, esperando que un Administrador
  le ponga nombre/unidad reales y lo active) y 'Fusionado' (soft delete
  de CA5: sus datos ya se reasignaron a otro parametro).
- orgn_crcn: 'Manual' / 'Automatico', mismo par de valores y misma
  semantica que ya usa mp_frmt desde HU49 -es historial de origen, no
  se resetea a Manual porque un humano lo edite despues (CA4)-.
- id_prmtr_fusionado_en: a que parametro se fusiono (CA5), para no
  perder el rastro de la decision.

Los server_default ('Activo'/'Manual') son lo que garantiza cero
regresion: todas las filas existentes del catalogo quedan exactamente
como estaban semanticamente -activas y de origen manual- sin necesidad
de un UPDATE de datos.

Revision ID: c1d4e7f90a21
Revises: a070693e2870
Create Date: 2026-09-02

"""

from alembic import op
import sqlalchemy as sa


revision = "c1d4e7f90a21"
down_revision = "a070693e2870"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prmtr",
        sa.Column(
            "estd",
            sa.String(length=30),
            nullable=False,
            server_default="Activo",
        ),
    )
    op.add_column(
        "prmtr",
        sa.Column(
            "orgn_crcn",
            sa.String(length=20),
            nullable=False,
            server_default="Manual",
        ),
    )
    op.add_column(
        "prmtr",
        sa.Column("id_prmtr_fusionado_en", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "prmtr_id_prmtr_fusionado_en_fkey",
        "prmtr",
        "prmtr",
        ["id_prmtr_fusionado_en"],
        ["id_prmtr"],
    )
    op.create_check_constraint(
        "prmtr_estd_check",
        "prmtr",
        "estd IN ('Activo','Pendiente de revision','Fusionado')",
    )
    op.create_check_constraint(
        "prmtr_orgncrcn_check",
        "prmtr",
        "orgn_crcn IN ('Manual','Automatico')",
    )
    # Acelera el filtro de la pantalla de catalogo (CA3: ver solo los
    # pendientes de revision) y el de los selectores, que ahora tienen
    # que excluir los Fusionados.
    op.create_index("idx_prmtr_estd", "prmtr", ["estd"])


def downgrade() -> None:
    # Guarda explicita: si ya hay parametros auto-creados sin revisar o
    # fusionados, bajar esta migracion perderia esa informacion en
    # silencio -y los Fusionados volverian a ser indistinguibles de un
    # parametro normal, reapareciendo en los selectores-. Mejor fallar
    # ruidoso y que se decida a mano que hacer con ellos.
    conexion = op.get_bind()
    pendientes = conexion.execute(
        sa.text("SELECT count(*) FROM prmtr WHERE estd <> 'Activo'")
    ).scalar()
    if pendientes:
        raise RuntimeError(
            f"No se puede bajar la migracion HU51: hay {pendientes} parametro(s) "
            "en estado distinto de 'Activo' (Pendiente de revision o Fusionado). "
            "Resolvelos o activalos antes de hacer downgrade."
        )

    op.drop_index("idx_prmtr_estd", table_name="prmtr")
    op.drop_constraint("prmtr_orgncrcn_check", "prmtr", type_="check")
    op.drop_constraint("prmtr_estd_check", "prmtr", type_="check")
    op.drop_constraint("prmtr_id_prmtr_fusionado_en_fkey", "prmtr", type_="foreignkey")
    op.drop_column("prmtr", "id_prmtr_fusionado_en")
    op.drop_column("prmtr", "orgn_crcn")
    op.drop_column("prmtr", "estd")
