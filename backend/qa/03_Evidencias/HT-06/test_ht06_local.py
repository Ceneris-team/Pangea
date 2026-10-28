"""QA HT-06 (PP-411) - pruebas locales estaticas sobre el repositorio.
Cada prueba lleva el CA que verifica. No requiere servicios ni red."""
import json
import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[4]
BACK = RAIZ / "backend"


def git(*args):
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def leer(p):
    return Path(p).read_text(encoding="utf-8", errors="replace")


def codigo_py():
    return [p for p in (BACK / "app").rglob("*.py")]


def todo_texto_backend():
    t = ""
    for p in list(BACK.glob("*.txt")) + list((BACK / "app").rglob("*.py")) + [RAIZ / "docker-compose.yml", RAIZ / "containers.example.json", BACK / "README.md"]:
        if p.exists():
            t += leer(p).lower()
    return t


# ---------- CA1: despliegue por imagenes Docker, un contenedor por componente ----------
def test_ca1_dockerfile_api_existe_y_arranca_uvicorn():
    d = leer(BACK / "Dockerfile")
    assert "uvicorn" in d and "app.main:app" in d


def test_ca1_containers_api_worker_beat_separados():
    c = json.loads(leer(RAIZ / "containers.example.json"))
    for nombre in ("api", "worker", "beat"):
        assert nombre in c and c[nombre]["image"].startswith(":pangea-app.")
    assert "celery" in " ".join(c["worker"]["command"]) and "worker" in c["worker"]["command"]
    assert "beat" in c["beat"]["command"]


def test_ca1_receptor_ftp_tcp_en_contenedor_propio():
    """El enunciado pide un contenedor aparte para el receptor FTP/TCP."""
    c = json.loads(leer(RAIZ / "containers.example.json"))
    claves = [k for k in c if "ftp" in k.lower() or "tcp" in k.lower() or "receptor" in k.lower()]
    assert claves, "No existe contenedor de receptor FTP/TCP en containers.example.json (solo: %s)" % list(c)


# ---------- CA2: BD privada ----------
def test_ca2_bd_por_variable_de_entorno_en_codigo():
    assert 'os.environ.get(\n    "DATABASE_URL"' in leer(BACK / "app" / "database.py") or '"DATABASE_URL"' in leer(BACK / "app" / "database.py")


def test_ca2_documentado_modo_privado():
    t = todo_texto_backend()
    assert re.search(r"(modo|base de datos|bd|postgres).{0,40}privad|publicly.accessible|sin exposici[oó]n", t), "No hay documentacion de BD en modo privado"


# ---------- CA3: Object Storage ----------
def test_ca3_dependencia_cliente_s3_en_requirements():
    assert re.search(r"boto3|minio|s3fs", leer(BACK / "requirements.txt"), re.I), "Sin boto3/cliente S3 en requirements.txt"


def test_ca3_codigo_escribe_dat_en_object_storage():
    assert any(re.search(r"boto3|put_object|upload_file|S3_BUCKET|OBJECT_STORAGE", leer(p)) for p in codigo_py()), "Ningun modulo de app/ usa Object Storage"


def test_ca3_variables_credenciales_object_storage_documentadas():
    assert re.search(r"BUCKET|ACCESS_KEY|S3_", leer(RAIZ / ".env.example")), ".env.example no declara variables de Object Storage"


# ---------- CA4: respaldo semanal ----------
def _beat():
    return leer(BACK / "app" / "core" / "celery_app.py")


def test_ca4_tarea_de_respaldo_en_beat_schedule():
    assert re.search(r"respaldo|backup|pg_dump", _beat(), re.I), "beat_schedule no tiene tarea de respaldo"


def test_ca4_respaldo_semanal_crontab():
    assert re.search(r"day_of_week", _beat()), "Ningun crontab semanal en beat_schedule"


def test_ca4_retencion_12_meses_configurada():
    assert re.search(r"retenci[oó]n.*(12|365|52)|RETENCION|RETENTION", todo_texto_backend(), re.I | re.S) and any(re.search(r"RETENCION|RETENTION", leer(p), re.I) for p in codigo_py()), "Sin politica de retencion de 12 meses en codigo"


def test_ca4_tarea_de_respaldo_cifra_el_dump():
    assert any(re.search(r"pg_dump", leer(p)) and re.search(r"encrypt|cifr|Fernet|gpg|AES", leer(p), re.I) for p in codigo_py()), "No existe codigo de dump cifrado"


# ---------- CA5: secretos fuera del codigo ----------
def test_ca5_codigo_sin_credenciales_reales_versionadas():
    rx = re.compile(r"(postgres(ql)?(\+psycopg2)?)://[^:/\s]+:([^@<\$\s]{4,})@([^/\s]+)")
    ok = {"postgres", "pangea_dev", "usuario", "clave", "password", "pangea"}
    malos = []
    for f in git("ls-files").splitlines():
        if f.endswith((".py", ".json", ".yml", ".yaml", ".md", ".example", ".env", ".txt")) and "tests" not in f:
            for m in rx.finditer(leer(RAIZ / f)):
                host = m.group(5)
                if "localhost" not in host and not host.startswith("db:") and not host.startswith("<"):
                    malos.append((f, host.split(".")[0]))
    assert not malos, "Credenciales con host remoto en %d archivos versionados" % len(malos)


def test_ca5_containers_json_ignorado_y_no_versionado():
    assert "containers.json" not in git("ls-files").split()
    assert "containers.json" in leer(RAIZ / ".gitignore") or ".env" in leer(RAIZ / ".gitignore")


def test_ca5_plantilla_containers_usa_marcadores():
    t = leer(RAIZ / "containers.example.json")
    assert "<password>" in t and "<generar con" in t


def test_ca5_historial_git_sin_contrasena_de_bd_remota():
    """El commit dba450f subio la cadena de conexion de la RDS con contrasena."""
    hist = git("log", "--all", "-p", "-S", "rds.amazonaws.com", "--format=%h", "--", "containers.json", "endpoint.json")
    expuesto = bool(re.search(r"://[^:/\s]+:[^@<\s]{4,}@[^\s\"]*rds\.amazonaws\.com", hist))
    assert not expuesto, "Contrasena de la RDS expuesta en el historial de git (commit dba450f y siguientes)"


def test_ca5_secretos_jwt_y_ftp_no_en_historial():
    hist = git("log", "--all", "-p", "-S", "FTP_CREDENTIAL_KEY", "--format=%h", "--", "containers.json")
    expuesto = bool(re.search(r"\"(JWT_SECRET|FTP_CREDENTIAL_KEY)\":\s*\"[A-Za-z0-9_\-=]{20,}\"", hist))
    assert not expuesto, "JWT_SECRET/FTP_CREDENTIAL_KEY en texto plano en historial de git"


# ---------- Entornos y documentacion ----------
def test_entornos_dev_staging_produccion_definidos():
    t = todo_texto_backend()
    assert re.search(r"tres entornos|3 entornos|entornos? (de )?(desarrollo|dev).{0,60}staging.{0,60}producci", t, re.S), "No hay definicion de 3 entornos (dev/staging/prod)"


def test_umbral_migracion_timescaledb_documentado():
    t = todo_texto_backend()
    assert re.search(r"umbral de migraci[oó]n|5 clientes activos", t) and re.search(r"3 segundos|> ?3 ?s", t), "Sin umbral de migracion (5 clientes activos / 3 s) documentado"


def test_postgis_restriccion_documentada():
    assert "postgis" in todo_texto_backend(), "No se documenta la restriccion de PostGIS en Lightsail"


def test_poligonos_como_geojson_en_columna_json():
    t = leer(BACK / "app" / "models" / "ubicacion_conexion.py")
    assert "plgn_gjsn" in t and re.search(r"JSONB?\b", t)


def test_particionamiento_nativo_en_lugar_de_timescaledb():
    assert any(BACK.glob("app/tasks/particiones.py"))
