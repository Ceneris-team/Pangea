"""Agrega tipo_visualizacion al catalogo de parametros

Un contador acumulativo (contador_puerta, contador_eventos_puerta) y un
estado binario (estado_puerta, estado_gabinete) son hoy indistinguibles
de una medicion ambiental: los tres son tipo_dato='numerico' con
undd='N/A'. La pantalla de Graficos los dibuja a todos como una linea
continua y les calcula min/promedio/maximo, que para una serie que solo
sube -o que solo vale 0/1- no significa nada: el promedio de un contador
acumulativo es el promedio de una cuenta corrida.

tipo_dato NO sirve para esto: separa donde se persiste el valor
(numerico -> tlmtr, texto -> evnt_txt), y un contador es numerico igual
que la temperatura. Por eso una columna nueva y no un valor mas en el
CHECK de tipo_dato.

Valores:
- 'continuo': medicion que sube y baja (temperatura, ph, bateria_v).
  Linea/area + min/promedio/maximo. Es el default, asi que todo el
  catalogo existente queda exactamente como estaba.
- 'contador': serie monotona acumulativa. Se grafica en escalon y el
  resumen pasa a ser total acumulado / eventos en el rango.
- 'estado': binario o de pocos niveles discretos. Se grafica como banda
  de estado y el resumen pasa a % de tiempo activo / transiciones.

Revision ID: d2f8a1c34b57
Revises: c1d4e7f90a21
Create Date: 2026-09-16

"""

from alembic import op
import sqlalchemy as sa


revision = "d2f8a1c34b57"
down_revision = "c1d4e7f90a21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prmtr",
        sa.Column(
            "tipo_visualizacion",
            sa.String(length=20),
            nullable=False,
            server_default="continuo",
        ),
    )
    op.create_check_constraint(
        "prmtr_tipovisualizacion_check",
        "prmtr",
        "tipo_visualizacion IN ('continuo','contador','estado')",
    )

    # Clasificacion inicial de los parametros que ya existen y que son el
    # motivo de esta migracion. Va por nombre exacto a proposito: el
    # catalogo crece con la ingesta automatica (orgn_crcn='Automatico') y
    # un LIKE 'contador%' clasificaria mal cualquier parametro futuro que
    # arranque igual sin ser acumulativo. Lo que no matchee queda
    # 'continuo' y un Administrador lo corrige desde el ABM.
    op.execute(
        """
        UPDATE prmtr
           SET tipo_visualizacion = 'contador'
         WHERE nmbr IN ('contador_puerta', 'contador_eventos_puerta')
        """
    )
    op.execute(
        """
        UPDATE prmtr
           SET tipo_visualizacion = 'estado'
         WHERE nmbr IN ('estado_puerta', 'estado_gabinete')
        """
    )


def downgrade() -> None:
    op.drop_constraint("prmtr_tipovisualizacion_check", "prmtr", type_="check")
    op.drop_column("prmtr", "tipo_visualizacion")
