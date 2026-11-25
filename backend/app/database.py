"""
Configuración central de SQLAlchemy. Lee la cadena de conexión desde la
variable de entorno DATABASE_URL (definida en tu .env, junto a las de
seguridad de HT-04).

Ejemplo de valor para desarrollo local:
    DATABASE_URL=postgresql+psycopg2://usuario:clave@localhost:5432/pangea_dev
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# Busca el archivo .env desde la carpeta actual hacia arriba (funciona tanto
# si corres uvicorn desde backend/ como si el .env está en la raíz del repo).
load_dotenv()

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/pangea_dev"
)

engine = create_engine(os.environ.get("DATABASE_RUNTIME_URL") or DATABASE_URL, hide_parameters=True)


class RuntimeSession(Session):
    """La API y los workers ejecutan SQL con un rol sin propiedad del historial."""


@event.listens_for(RuntimeSession, "after_begin")
def _rol_de_ejecucion(session, transaction, connection):
    permitido = connection.execute(
        text("""SELECT NOT (rolsuper OR rolcreaterole OR rolcreatedb OR rolbypassrls)
        AND NOT pg_has_role(session_user, 'pangea_auditoria', 'MEMBER')
        AND NOT has_table_privilege(session_user, 'public.lg_adtr', 'UPDATE,DELETE,TRUNCATE')
        AND NOT EXISTS (SELECT 1 FROM pg_inherits WHERE inhparent='public.lg_adtr'::regclass
            AND has_table_privilege(session_user, inhrelid, 'UPDATE,DELETE,TRUNCATE'))
        AND NOT EXISTS (SELECT 1 FROM pg_class WHERE relname IN
            ('usr','usr_clnt','usr_pryct_ubccn','prms_ubccn','prms_usr_sd','lg_adtr')
            AND pg_has_role((SELECT oid FROM pg_roles WHERE rolname=session_user), relowner, 'MEMBER'))
        FROM pg_roles WHERE rolname=session_user""")
    ).scalar_one()
    if not permitido:
        raise RuntimeError(
            "DATABASE_RUNTIME_URL debe usar una cuenta sin privilegios administrativos ni propiedad de las tablas; ejecuta scripts/aprovisionar_auditoria.py"
        )
    connection.exec_driver_sql("SET LOCAL ROLE pangea_app")


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=RuntimeSession)
Base = declarative_base()


def get_db():
    """Dependencia de FastAPI: entrega una sesión por request y la cierra
    siempre al final, incluso si hay una excepción."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
