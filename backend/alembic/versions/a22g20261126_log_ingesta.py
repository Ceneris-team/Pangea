"""HU37: log de eventos con instantánea de origen y diagnóstico completo."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "a22g20261126"
down_revision = "a21f20261126"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("archv_ingst", sa.Column("origen_ingesta", JSONB()))
    op.create_table(
        "log_ingesta",
        sa.Column("id_evento", sa.BigInteger(), primary_key=True),
        sa.Column(
            "id_archv", sa.BigInteger(), sa.ForeignKey("archv_ingst.id_archv"), nullable=False
        ),
        sa.Column(
            "id_intnt", sa.BigInteger(), sa.ForeignKey("intnt_prcsmnt.id_intnt"), unique=True
        ),
        sa.Column("id_cnxn", sa.Integer(), nullable=False),
        sa.Column("id_dspstv", sa.Integer()),
        sa.Column("id_sd", sa.Integer(), nullable=False),
        sa.Column("id_ubccn", sa.Integer()),
        sa.Column("archivo", sa.String(300), nullable=False),
        sa.Column("datalogger", sa.String(300), nullable=False),
        sa.Column("proyecto", sa.String(300)),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recepcion", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inicio", sa.DateTime(timezone=True)),
        sa.Column("fin", sa.DateTime(timezone=True)),
        sa.Column("resultado", sa.String(20), nullable=False),
        sa.Column("mensaje", sa.Text()),
        sa.Column("registros_procesados", sa.Integer()),
        sa.Column("registros_rechazados", sa.Integer()),
        sa.Column("origen", sa.String(40), nullable=False),
    )
    op.create_index("ix_log_ingesta_id_archv", "log_ingesta", ["id_archv"])
    op.create_index("idx_log_ingesta_fecha", "log_ingesta", ["fecha", "id_evento"])
    op.create_index("idx_log_ingesta_ambito", "log_ingesta", ["id_sd", "id_ubccn", "fecha"])
    op.execute("GRANT SELECT, INSERT, DELETE ON log_ingesta TO pangea_app")
    op.execute("REVOKE UPDATE ON log_ingesta FROM pangea_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE log_ingesta_id_evento_seq TO pangea_app")
    # Recuperar solo hechos existentes. No inventar un intento inicial si no se registró.
    # El texto antiguo se sanea en la API; ya no se puede recuperar lo que se truncó.
    op.execute("""
        INSERT INTO log_ingesta
        (id_archv,id_intnt,id_cnxn,id_dspstv,id_sd,id_ubccn,archivo,datalogger,proyecto,
         fecha,recepcion,inicio,fin,resultado,mensaje,registros_procesados,origen)
        SELECT a.id_archv,i.id_intnt,a.id_cnxn,a.id_dspstv,c.id_sd,u.id_ubccn,
               a.nmbr_archv,COALESCE(d.nmbr,c.nmbr || ' · equipo sin identificar'),u.nmbr,
               COALESCE(i.fch_inicio,i.fch_intnt),a.fch_dtccn,i.fch_inicio,i.fch_fin,
               i.rsltd,i.mnsj_errr,i.registros_guardados,'Histórico migrado'
        FROM intnt_prcsmnt i JOIN archv_ingst a ON a.id_archv=i.id_archv
        JOIN cnxn_ftp c ON c.id_cnxn=a.id_cnxn
        LEFT JOIN dspstv d ON d.id_dspstv=a.id_dspstv
        LEFT JOIN ubccn u ON u.id_ubccn=d.id_ubccn
        WHERE i.rsltd IN ('Exitoso','Fallido')
          AND COALESCE(i.fch_inicio,i.fch_intnt) >= NOW() - INTERVAL '90 days'
    """)
    # Cargas antiguas sin intentos: conservar únicamente el último resultado conocido.
    op.execute("""
        INSERT INTO log_ingesta
        (id_archv,id_cnxn,id_dspstv,id_sd,id_ubccn,archivo,datalogger,proyecto,
         fecha,recepcion,fin,resultado,mensaje,registros_procesados,origen)
        SELECT a.id_archv,a.id_cnxn,a.id_dspstv,c.id_sd,u.id_ubccn,
               a.nmbr_archv,COALESCE(d.nmbr,c.nmbr || ' · equipo sin identificar'),u.nmbr,
               COALESCE(a.fch_prcsd,a.fch_dtccn),a.fch_dtccn,a.fch_prcsd,
               a.estd,a.mnsj_errr,a.rgstrs_prcsds,'Último resultado histórico'
        FROM archv_ingst a JOIN cnxn_ftp c ON c.id_cnxn=a.id_cnxn
        LEFT JOIN dspstv d ON d.id_dspstv=a.id_dspstv
        LEFT JOIN ubccn u ON u.id_ubccn=d.id_ubccn
        WHERE a.estd IN ('Exitoso','Fallido')
          AND COALESCE(a.fch_prcsd,a.fch_dtccn) >= NOW() - INTERVAL '90 days'
          AND NOT EXISTS (SELECT 1 FROM intnt_prcsmnt i WHERE i.id_archv=a.id_archv
                          AND i.rsltd IN ('Exitoso','Fallido'))
    """)


def downgrade():
    op.drop_table("log_ingesta")
    op.drop_column("archv_ingst", "origen_ingesta")
