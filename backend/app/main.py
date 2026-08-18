import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.routers import (
    auth,
    conexiones_ftp,
    dispositivos,
    ingesta,
    mapeos,
    mediciones,
    ubicaciones,
    usuarios,
)

RATELIMIT_STORAGE_URL = os.environ.get("RATELIMIT_STORAGE_URL", "redis://localhost:6379/1")
limiter = Limiter(key_func=get_remote_address, storage_uri=RATELIMIT_STORAGE_URL)

# Lista separada por comas (ej. "https://a.com,https://b.com"). Si no está
# seteada, cae en los orígenes de dev local con Vite para no romper el
# flujo de nadie del equipo que no tenga esta variable configurada.
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(ubicaciones.router)
app.include_router(ingesta.router)
app.include_router(conexiones_ftp.router)
app.include_router(mediciones.router)
app.include_router(mapeos.router)
app.include_router(mapeos.router_parametros)
app.include_router(mapeos.router_sedes)
app.include_router(mapeos.router_dispositivos_mapeo)
app.include_router(dispositivos.router)


@app.get("/")
def read_root():
    return {"message": "Welcome to Pangea API"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
