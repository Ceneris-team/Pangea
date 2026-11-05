"""Entorno aislado PP-185, API y Vite del checkout actual; sin tocar servicios previos."""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
BACK = ROOT / 'backend'
HERE = Path(__file__).resolve().parent
EV = BACK / 'qa/03_Evidencias/HU21/reprueba_pp185'
ADMIN = 'postgresql+psycopg2://postgres:postgres@localhost:55432/pangea_retest_pp185'

def seed():
    # Sembrado administrativo, API con cuenta de ejecución restringida.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import database
    database.SessionLocal = sessionmaker(bind=create_engine(ADMIN))
    from app.scripts import seed_usuarios_prueba
    seed_usuarios_prueba.main()
    spec = importlib.util.spec_from_file_location('seed_pp185', HERE / 'seed_hu21.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()

def main():
    os.environ['DATABASE_URL'] = ADMIN
    os.environ['DATABASE_RUNTIME_URL'] = ADMIN
    seed()
    if '--seed' in __import__('sys').argv:
        return
    from scripts.aprovisionar_auditoria import aprovisionar
    runtime = ADMIN.replace('postgres:postgres@', 'qa_pp185_runtime:' + secrets.token_hex(24) + '@')
    aprovisionar(ADMIN, runtime)
    env = dict(os.environ, DATABASE_RUNTIME_URL=runtime,
               CORS_ALLOWED_ORIGINS='http://localhost:5200',
               RATELIMIT_STORAGE_URL='redis://localhost:6379/14',
               JWT_SECRET=secrets.token_hex(32))
    processes = []
    try:
        with (EV / 'api.log').open('w') as api_log, (EV / 'vite.log').open('w') as vite_log:
            processes.append(subprocess.Popen([str(BACK/'venv/Scripts/python.exe'), '-m', 'uvicorn', 'app.main:app', '--port', '8022', '--log-level', 'warning'], cwd=BACK, env=env, stdout=api_log, stderr=api_log, creationflags=subprocess.CREATE_NO_WINDOW))
            front_env = dict(env, VITE_API_BASE_URL='http://localhost:8022')
            processes.append(subprocess.Popen(['node', str(ROOT/'frontend/node_modules/vite/bin/vite.js'), '--port', '5200', '--strictPort'], cwd=ROOT/'frontend', env=front_env, stdout=vite_log, stderr=vite_log, creationflags=subprocess.CREATE_NO_WINDOW))
            for url in ['http://localhost:8022/', 'http://localhost:5200/']:
                for _ in range(60):
                    try:
                        urllib.request.urlopen(url, timeout=1).close()
                        break
                    except Exception:
                        time.sleep(0.5)
                else:
                    raise RuntimeError('No inició ' + url)
            print('API 8022 y Vite 5200: checkout actual; BD aislada pangea_retest_pp185', flush=True)
            result = subprocess.run(['node', str(HERE/'node_modules/@playwright/test/cli.js'), 'test', '-c', 'retest_pp185.config.mjs', *os.environ.get('PP185_ARGS', '').split()], cwd=HERE, env=env)
            raise SystemExit(result.returncode)
    finally:
        for process in reversed(processes):
            process.terminate()
            process.wait(timeout=15)

if __name__ == '__main__':
    main()
