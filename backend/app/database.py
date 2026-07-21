"""
Configuración central de SQLAlchemy. Lee la cadena de conexión desde la
variable de entorno DATABASE_URL (definida en tu .env, junto a las de
seguridad de HT-04).

Ejemplo de valor para desarrollo local:
    DATABASE_URL=postgresql+psycopg2://usuario:clave@localhost:5432/pangea_dev
"""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Busca el archivo .env desde la carpeta actual hacia arriba (funciona tanto
# si corres uvicorn desde backend/ como si el .env está en la raíz del repo).
load_dotenv()

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/pangea_dev"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependencia de FastAPI: entrega una sesión por request y la cierra
    siempre al final, incluso si hay una excepción."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
