import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.routers import (
    usuarios, ubicaciones, auth, ingesta, conexiones_ftp, mediciones, mapeos, dispositivos,
)

RATELIMIT_STORAGE_URL = os.environ.get(
    "RATELIMIT_STORAGE_URL", "redis://localhost:6379/1"
)
limiter = Limiter(key_func=get_remote_address, storage_uri=RATELIMIT_STORAGE_URL)

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
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
app.include_router(dispositivos.router)


@app.get("/")
def read_root():
    return {"message": "Welcome to Pangea API"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}