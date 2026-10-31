FROM python:3.12-slim

WORKDIR /app

# HT-06 (PP-129): el job de respaldo necesita pg_dump, openssl y gzip dentro
# del contenedor (ver app/services/respaldos.py). pg_dump DEBE ser >= la
# versión del servidor (PostgreSQL 16 en Lightsail), así que se instala
# postgresql-client-16 desde el repo oficial PGDG -el `postgresql-client` de
# Debian bookworm es la 15 y pg_dump rechaza volcar un servidor más nuevo.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg openssl gzip \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && apt-get purge -y curl gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
