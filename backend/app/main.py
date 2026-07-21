from fastapi import FastAPI, Depends, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.security.dependencies import get_current_user
from app.security.jwt_auth import create_access_token

# T43: rate limiting con slowapi (ya estaba en tu requirements.txt), en vez
# del limitador con Redis a mano. Usa Redis como backend de conteo para que
# funcione igual si corres varios workers de uvicorn.
limiter = Limiter(key_func=get_remote_address, storage_uri="redis://localhost:6379/1")

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/")
def read_root():
    return {"message": "Welcome to Pangea API"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/auth/login-demo")
@limiter.limit("5/5minutes")  # T43: máximo 5 intentos cada 5 minutos por IP
def login_demo(request: Request):
    """Endpoint de ejemplo para HU 01 - en la versión real, aquí se valida
    el usuario/contraseña con verify_password() antes de emitir el token."""
    token = create_access_token(user_id=1, sede_id=1, scope="por_sede", rol="Administrador")
    return {"access_token": token, "token_type": "bearer"}


@app.get("/perfil-demo")
def perfil_demo(usuario: dict = Depends(get_current_user)):
    """Endpoint de ejemplo protegido: solo responde con un JWT válido en
    el header Authorization: Bearer <token> (criterio de aceptación de HT-04)."""
    return {"mensaje": "Token válido", "payload": usuario}

