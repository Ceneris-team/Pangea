#!/bin/sh
# PP-408 · Rendimiento en el worker de referencia: 2 CPU y 512 MiB (los límites de worker-exportaciones en docker-compose.yml).
# Requiere la BD pangea_test migrada en el servicio db de Docker Compose. Ejecutar desde backend/.
docker run --rm --memory 512m --memory-swap 512m --cpus 2 --network pangea_default \
  -v "$(pwd)/tests:/app/tests" -v "$(pwd)/qa:/app/qa" \
  -e TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/pangea_test \
  --entrypoint sh pangea-worker-exportaciones:latest -c '
    python -m pytest qa/03_Evidencias/HU33-HT15/test_criterios_hu15.py -k rendimiento -s -q -p no:cacheprovider \
      --junitxml=qa/03_Evidencias/HU33-HT15/pytest_rendimiento_referencia.xml;
    echo "memory.events del contenedor:"; cat /sys/fs/cgroup/memory.events 2>/dev/null'
