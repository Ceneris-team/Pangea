"""HU38: cálculo histórico, dependencias y resultados trazables."""

import sqlalchemy as sa
from alembic import op

revision = "a18c20261124"
down_revision = "a17b20261123"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "prmtr_clcld",
        sa.Column("validada", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "prmtr_clcld", sa.Column("id_usr_creador", sa.Integer(), sa.ForeignKey("usr.id_usr"))
    )
    op.add_column(
        "prmtr_clcld",
        sa.Column(
            "creada_en",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    # Esquema congelado: no depende de los modelos de futuras versiones.
    op.execute("""CREATE TABLE clcl_config (
    id_sd INTEGER NOT NULL,
    tolerancia_segundos INTEGER DEFAULT '60' NOT NULL,
    espera_horas INTEGER DEFAULT '24' NOT NULL,
    PRIMARY KEY (id_sd),
    CHECK (tolerancia_segundos BETWEEN 0 AND 3600),
    CHECK (espera_horas BETWEEN 1 AND 720),
    FOREIGN KEY(id_sd) REFERENCES sd (id_sd)
)""")
    op.execute("""CREATE TABLE clcl_dependencia (
    id_prm_clc INTEGER NOT NULL,
    variable VARCHAR(40) NOT NULL,
    id_prmtr INTEGER,
    id_origen_calculado INTEGER,
    unidad_origen VARCHAR(30) NOT NULL,
    PRIMARY KEY (id_prm_clc, variable),
    CHECK ((id_prmtr IS NULL) <> (id_origen_calculado IS NULL)),
    CHECK (id_prm_clc <> id_origen_calculado),
    FOREIGN KEY(id_prm_clc) REFERENCES prmtr_clcld (id_prm_clc),
    FOREIGN KEY(id_prmtr) REFERENCES prmtr (id_prmtr),
    FOREIGN KEY(id_origen_calculado) REFERENCES prmtr_clcld (id_prm_clc)
)""")
    op.execute("""CREATE TABLE clcl_serie (
    id_serie SERIAL NOT NULL,
    id_prm_clc INTEGER NOT NULL,
    id_ubccn INTEGER NOT NULL,
    PRIMARY KEY (id_serie),
    UNIQUE (id_prm_clc, id_ubccn),
    FOREIGN KEY(id_prm_clc) REFERENCES prmtr_clcld (id_prm_clc),
    FOREIGN KEY(id_ubccn) REFERENCES ubccn (id_ubccn)
)""")
    op.execute("""CREATE TABLE clcl_resultado (
    id_resultado BIGSERIAL NOT NULL,
    id_prm_clc INTEGER NOT NULL,
    id_ubccn INTEGER NOT NULL,
    id_sd INTEGER NOT NULL,
    fch_hr TIMESTAMP WITH TIME ZONE NOT NULL,
    vlr FLOAT,
    estado VARCHAR(30) NOT NULL,
    causa VARCHAR(500),
    revision INTEGER DEFAULT '1' NOT NULL,
    trazabilidad JSONB NOT NULL,
    actualizado_en TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    PRIMARY KEY (id_resultado),
    UNIQUE (id_prm_clc, id_ubccn, fch_hr),
    CHECK (estado IN ('Calculado','Pendiente de datos','Incompleto','Fallido')),
    CHECK ((estado = 'Calculado') = (vlr IS NOT NULL)),
    FOREIGN KEY(id_prm_clc) REFERENCES prmtr_clcld (id_prm_clc),
    FOREIGN KEY(id_ubccn) REFERENCES ubccn (id_ubccn),
    FOREIGN KEY(id_sd) REFERENCES sd (id_sd)
)""")
    op.execute(
        "CREATE INDEX idx_clcl_resultado_contexto ON clcl_resultado (id_ubccn, id_prm_clc, fch_hr)"
    )
    op.execute("""CREATE TABLE clcl_revision (
    id_revision BIGSERIAL NOT NULL,
    id_resultado BIGINT NOT NULL,
    revision INTEGER NOT NULL,
    anterior JSONB NOT NULL,
    creada_en TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    PRIMARY KEY (id_revision),
    UNIQUE (id_resultado, revision),
    FOREIGN KEY(id_resultado) REFERENCES clcl_resultado (id_resultado)
)""")
    op.execute("""CREATE TABLE clcl_trabajo (
    id_trabajo BIGSERIAL NOT NULL,
    id_sd INTEGER NOT NULL,
    id_prm_clc INTEGER,
    id_ubccn INTEGER,
    inicio TIMESTAMP WITH TIME ZONE,
    fin TIMESTAMP WITH TIME ZONE,
    cursor JSONB,
    estado VARCHAR(40) DEFAULT 'Pendiente' NOT NULL,
    procesados INTEGER DEFAULT '0' NOT NULL,
    incidencias INTEGER DEFAULT '0' NOT NULL,
    error VARCHAR(500),
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    actualizado_en TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    PRIMARY KEY (id_trabajo),
    FOREIGN KEY(id_sd) REFERENCES sd (id_sd),
    FOREIGN KEY(id_prm_clc) REFERENCES prmtr_clcld (id_prm_clc),
    FOREIGN KEY(id_ubccn) REFERENCES ubccn (id_ubccn)
)""")
    op.execute("CREATE INDEX idx_clcl_trabajo_estado ON clcl_trabajo (estado, id_trabajo)")
    # Serializar el alta por sede evita carreras incluso con nombres cuyo
    # índice normalizado no podría crearse sobre duplicados heredados.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='pangea_app') THEN "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON clcl_config, clcl_dependencia, clcl_serie, clcl_resultado, clcl_trabajo TO pangea_app; "
        "GRANT SELECT, INSERT ON clcl_revision TO pangea_app; "
        "REVOKE UPDATE, DELETE, TRUNCATE ON clcl_revision FROM pangea_app; "
        "GRANT USAGE, SELECT ON SEQUENCE clcl_serie_id_serie_seq, clcl_resultado_id_resultado_seq, clcl_revision_id_revision_seq, clcl_trabajo_id_trabajo_seq TO pangea_app; "
        "END IF; END $$"
    )
    for operacion, fuente, transicion in [
        ("INSERT", "SELECT * FROM nuevas", "NEW TABLE AS nuevas"),
        (
            "UPDATE",
            "SELECT * FROM nuevas UNION ALL SELECT * FROM anteriores",
            "OLD TABLE AS anteriores NEW TABLE AS nuevas",
        ),
        ("DELETE", "SELECT * FROM anteriores", "OLD TABLE AS anteriores"),
    ]:
        nombre = f"clcl_encolar_{operacion.lower()}"
        op.execute(f"""
        CREATE FUNCTION {nombre}() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          INSERT INTO clcl_trabajo (id_sd,id_ubccn,inicio,fin)
          SELECT u.id_sd,d.id_ubccn,min(t.fch_hr),
                 max(t.fch_hr) + make_interval(secs =>
                   coalesce(c.tolerancia_segundos,60) * (SELECT count(*)+1 FROM prmtr_clcld p
                     WHERE p.id_sd=u.id_sd AND p.validada))
          FROM ({fuente}) t JOIN dspstv d USING(id_dspstv)
          JOIN ubccn u ON u.id_ubccn=d.id_ubccn
          LEFT JOIN clcl_config c ON c.id_sd=u.id_sd
          WHERE EXISTS (SELECT 1 FROM prmtr_clcld p WHERE p.id_sd=u.id_sd AND p.validada)
          GROUP BY u.id_sd,d.id_ubccn,c.tolerancia_segundos;
          RETURN NULL;
        END $$;
        CREATE TRIGGER {nombre} AFTER {operacion} ON tlmtr
        REFERENCING {transicion} FOR EACH STATEMENT EXECUTE FUNCTION {nombre}();
        """)
    op.execute("""
    CREATE FUNCTION clcl_origen_modificado() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF (OLD.undd, OLD.estd, OLD.tipo_dato) IS DISTINCT FROM (NEW.undd, NEW.estd, NEW.tipo_dato) THEN
        INSERT INTO clcl_trabajo (id_sd)
        SELECT DISTINCT p.id_sd FROM clcl_dependencia d
        JOIN prmtr_clcld p ON p.id_prm_clc=d.id_prm_clc
        WHERE d.id_prmtr=NEW.id_prmtr AND p.validada;
      END IF;
      RETURN NULL;
    END $$;
    CREATE TRIGGER clcl_origen_modificado AFTER UPDATE OF undd,estd,tipo_dato ON prmtr
    FOR EACH ROW EXECUTE FUNCTION clcl_origen_modificado();
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS clcl_origen_modificado ON prmtr")
    op.execute("DROP FUNCTION IF EXISTS clcl_origen_modificado()")
    for operacion in ("insert", "update", "delete"):
        op.execute(f"DROP TRIGGER clcl_encolar_{operacion} ON tlmtr")
        op.execute(f"DROP FUNCTION clcl_encolar_{operacion}()")
    for nombre in (
        "clcl_revision",
        "clcl_resultado",
        "clcl_serie",
        "clcl_dependencia",
        "clcl_trabajo",
        "clcl_config",
    ):
        op.drop_table(nombre)
    for nombre in ("creada_en", "id_usr_creador", "validada"):
        op.drop_column("prmtr_clcld", nombre)
