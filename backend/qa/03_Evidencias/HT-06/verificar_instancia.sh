#!/usr/bin/env bash
# QA HT-06 (PP-411) - verificacion SOLO LECTURA dentro de la instancia Ubuntu "Servidores-ceneris".
# No cambia nada. De las variables de entorno se imprimen solo los NOMBRES; las URL se enmascaran.
# Uso:  bash verificar_instancia.sh
SALIDA="instancia_verificacion_$(date +%Y%m%d_%H%M).txt"
D="docker"; $D ps >/dev/null 2>&1 || D="sudo docker"
{
echo "== Fecha: $(date -Is)  Host: $(hostname)  SO: $(. /etc/os-release; echo $PRETTY_NAME)"

echo; echo "== CA1: contenedores en ejecucion (nombre | imagen | estado | puertos)"
$D ps --format '{{.Names}} | {{.Image}} | {{.Status}} | {{.Ports}}'

echo; echo "== CA1: politica de reinicio y montajes por contenedor"
for c in $($D ps --format '{{.Names}}'); do
  echo "-- $c"; $D inspect -f 'reinicio={{.HostConfig.RestartPolicy.Name}}' "$c"
  $D inspect -f '{{range .Mounts}}montaje: {{.Type}} {{.Source}} -> {{.Destination}}{{println}}{{end}}' "$c"
done

echo; echo "== CA5: NOMBRES de variables de entorno por contenedor (sin valores)"
for c in $($D ps --format '{{.Names}}'); do
  echo "-- $c"; $D inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" | cut -d= -f1 | grep -E 'URL|KEY|SECRET|BUCKET|S3|AWS|PASS|HOST' | sort
done

echo; echo "== CA2: host de la base de datos (usuario y clave NO se imprimen) y conexion desde la instancia"
for c in $($D ps --format '{{.Names}}'); do
  U=$($D inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" | grep '^DATABASE_URL=' | head -1 | cut -d= -f2-)
  if [ -n "$U" ]; then
    H=$(echo "$U" | sed -E 's#^[^@]*@([^:/]+):?([0-9]*)/.*#\1 \2#'); echo "$c -> host/puerto: $H"; set -- $H
    if timeout 6 bash -c "</dev/tcp/$1/${2:-5432}" 2>/dev/null; then echo "   conexion desde la instancia: ABIERTA"; else echo "   conexion desde la instancia: sin respuesta"; fi
    break
  fi
done

echo; echo "== CA2: puertos escuchando en la instancia (0.0.0.0 = expuesto, 127.0.0.1 = local)"
ss -tln 2>/dev/null | awk 'NR==1||/LISTEN/'

echo; echo "== CA3: volumenes Docker y espacio en disco"
$D volume ls; df -h / | tail -2

echo; echo "== CA4: tareas programadas del sistema (no de Celery)"
crontab -l 2>&1 | grep -v '^#' | head; ls /etc/cron.d 2>/dev/null; systemctl list-timers --no-pager 2>/dev/null | head -8

echo; echo "== CA4: el contenedor beat conoce alguna tarea de respaldo?"
B=$($D ps --format '{{.Names}}' | grep -i beat | head -1)
if [ -n "$B" ]; then $D exec "$B" sh -c 'grep -n -i -E "respaldo|backup|pg_dump" /app/app/core/celery_app.py || echo "sin coincidencias en celery_app.py"'; else echo "no hay contenedor beat"; fi

echo; echo "== CA5: archivos con secretos en la instancia (solo ruta y permisos, no contenido)"
find / -maxdepth 4 \( -name 'containers.json' -o -name '.env' -o -name 'endpoint.json' \) -not -path '*/node_modules/*' -not -path '/proc/*' -exec ls -l {} \; 2>/dev/null

echo; echo "== Imagenes locales"; $D images --format '{{.Repository}}:{{.Tag}} | {{.CreatedSince}}'
} 2>&1 | tee "$SALIDA"
echo; echo "Listo: $SALIDA"
