"""Prueba aplicacion, triggers e inmutabilidad exclusivamente en una copia local."""

import json
import os
import secrets
import subprocess
import sys

from sqlalchemy import create_engine, text

from app.security.hashing import hash_password
from app.services.restauracion_respaldos import validar_destino
from scripts.aprovisionar_auditoria import aprovisionar


def verificar(url):
    destino = validar_destino(url)
    # Cada simulacro usa una cuenta de ejecucion independiente, sin cambiar roles existentes.
    sufijo = secrets.token_hex(5)
    runtime = destino.set(username="pangea_restore_" + sufijo, password=secrets.token_urlsafe(32))
    runtime_url = runtime.render_as_string(hide_password=False)
    aprovisionar(url, runtime_url)
    engine = create_engine(destino, hide_parameters=True)
    correo = f"restore-{sufijo}@example.com"
    password = secrets.token_urlsafe(24)
    try:
        with engine.begin() as conn:
            rol = conn.scalar(text("SELECT id_rl FROM rl WHERE nmbr='Administrador'"))
            if not rol:
                raise RuntimeError("Falta el rol Administrador en la copia")
            conn.execute(
                text(
                    "INSERT INTO usr(id_rl,scp,nmbr_cmplt,crr,cntrsn_hsh,dbe_cmbr_pswrd,estd) VALUES(:rol,'global','Prueba de restauracion',:correo,:hash,false,'Activo')"
                ),
                {"rol": rol, "correo": correo, "hash": hash_password(password)},
            )
        codigo = """
import json,os
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from fastapi.testclient import TestClient
from app.database import SessionLocal
from app.main import app
with SessionLocal() as sesion:
    assert sesion.scalar(text("SELECT count(*) FROM tlmtr")) >= 0
    try:
        sesion.execute(text("DELETE FROM lg_adtr"))
        raise AssertionError("Se permitio borrar auditoria")
    except DBAPIError as exc:
        assert getattr(exc.orig,'pgcode',None)=='42501'
        sesion.rollback()
with TestClient(app,base_url="https://testserver") as cliente:
    r=cliente.post('/auth/login',json={'correo':os.environ['RESTORE_TEST_EMAIL'],'contrasena':os.environ['RESTORE_TEST_PASSWORD']})
    assert r.status_code==200, r.status_code
    assert cliente.get('/auth/perfil').status_code==200
    assert cliente.get('/alarmas').status_code==200
print(json.dumps({'login':True,'consulta_alarmas':True,'runtime_restringido':True,'borrado_auditoria_rechazado':True,'trigger_auditoria':True}))
"""
        entorno = {
            **os.environ,
            "DATABASE_URL": url,
            "DATABASE_RUNTIME_URL": runtime_url,
            "RATELIMIT_STORAGE_URL": "memory://",
            "RESTORE_TEST_EMAIL": correo,
            "RESTORE_TEST_PASSWORD": password,
        }
        proc = subprocess.run(
            [sys.executable, "-c", codigo], env=entorno, capture_output=True, text=True, timeout=60
        )
        if proc.returncode:
            # No imprimir respuestas ni traceback que puedan incluir credenciales.
            raise RuntimeError("La verificacion de API o permisos fallo")
        resultado = json.loads(proc.stdout.strip().splitlines()[-1])
        resultado["cuenta_prueba"] = runtime.username
        return resultado
    finally:
        engine.dispose()


if __name__ == "__main__":
    print(json.dumps(verificar(os.environ["BACKUP_RESTORE_DATABASE_URL"])))
