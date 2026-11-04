import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.routers import (
    alarmas,
    auditoria,
    auth,
    comercial,
    conexiones_ftp,
    dispositivos,
    empresas,
    exportaciones,
    ingesta,
    mapa_cliente,
    mapeos,
    mediciones,
    panel,
    solicitudes_suscripcion,
    ubicaciones,
    usuarios,
)
from app.security.auditoria_contexto import preparar_peticion
from app.security.auditoria_denegaciones import manejar_denegacion

RATELIMIT_STORAGE_URL = os.environ.get("RATELIMIT_STORAGE_URL", "redis://localhost:6379/1")
limiter = Limiter(key_func=get_remote_address, storage_uri=RATELIMIT_STORAGE_URL)

# Lista separada por comas (ej. "https://a.com,https://b.com"). Si no está
# seteada, cae en los orígenes de dev local con Vite para no romper el
# flujo de nadie del equipo que no tenga esta variable configurada.
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

app = FastAPI(dependencies=[Depends(preparar_peticion)])
app.add_exception_handler(StarletteHTTPException, manejar_denegacion)
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
app.include_router(comercial.router)
app.include_router(solicitudes_suscripcion.router)
app.include_router(empresas.router)
app.include_router(usuarios.router)
app.include_router(auditoria.router)
app.include_router(ubicaciones.router)
app.include_router(ingesta.router)
app.include_router(conexiones_ftp.router)
app.include_router(mediciones.router)
app.include_router(exportaciones.router)
app.include_router(mapeos.router)
app.include_router(mapeos.router_parametros)
app.include_router(mapeos.router_sedes)
app.include_router(mapeos.router_dispositivos_mapeo)
app.include_router(dispositivos.router)
# HU17: mapa del Cliente Final (REST de carga inicial + WebSocket en vivo).
# Router propio, separado del de HU22 (/ubicaciones/mapa), que no se toca.
app.include_router(mapa_cliente.router)
# HU23: listar paneles (Tableros Personalizables, E05).
app.include_router(panel.router)
# HU27/HU28 (PP-73): listar y crear alarmas (Gestión de Alarmas y Notificaciones).
app.include_router(alarmas.router)


@app.get("/")
def read_root():
    return {"message": "Welcome to Pangea API"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
