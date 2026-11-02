# DEF-05: se fija la base a Debian 13 (trixie). `python:3.12-slim` (sin sufijo)
# sigue al "slim" actual, que pasó de Debian 12 (bookworm) a Debian 13
# (trixie); al cambiar la base cambia qué repo PGDG corresponde y el build se
# rompía. Fijar el sufijo evita que vuelva a moverse sola.
FROM python:3.12-slim-trixie

WORKDIR /app

# HT-06 (PP-129): el job de respaldo necesita pg_dump, openssl y gzip dentro
# del contenedor (ver app/services/respaldos.py). pg_dump DEBE ser >= la
# versión del servidor (PostgreSQL 16 en Lightsail), así que se instala
# postgresql-client-16 desde el repo oficial PGDG. El repo PGDG debe coincidir
# con la versión de Debian de la base: trixie-pgdg para Debian 13 (DEF-05 -con
# bookworm-pgdg el build fallaba con exit 100 porque libpq5 dependía de
# libldap-2.5-0, inexistente en Debian 13).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg openssl gzip \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] http://apt.postgresql.org/pub/repos/apt trixie-pgdg main" \
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
