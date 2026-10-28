#!/usr/bin/env bash
# QA HT-06 (PP-411) - verificacion SOLO LECTURA de Lightsail. No crea, modifica ni borra nada.
# Uso:  bash verificar_lightsail.sh [servicio] [region]    (por defecto: pangea-app us-east-1)
# Requiere: aws cli v2 con credenciales de lectura, python3. Los valores de las variables
# de entorno se enmascaran: solo se imprimen los NOMBRES.
SERVICIO="${1:-pangea-app}"; export AWS_DEFAULT_REGION="${2:-us-east-1}"
SALIDA="lightsail_verificacion_$(date +%Y%m%d_%H%M).txt"
{
echo "== Fecha: $(date -Is)  Region: $AWS_DEFAULT_REGION  Servicio: $SERVICIO"
echo "== Identidad (solo cuenta/ARN)"; aws sts get-caller-identity --query '{Cuenta:Account,Arn:Arn}' --output json

echo; echo "== CA1: servicios de contenedores (nombre, estado, plan, escala)"
aws lightsail get-container-services --query 'containerServices[].{nombre:containerServiceName,estado:state,potencia:power,escala:scale}' --output table

echo; echo "== CA1: despliegue actual (imagen, comando, puertos, NOMBRES de variables)"
aws lightsail get-container-service-deployments --service-name "$SERVICIO" --output json | python3 -c '
import json,sys
d=json.load(sys.stdin)["deployments"]
for dep in d[:3]:
    print("version",dep["version"],dep["state"],dep.get("createdAt"))
    for n,c in (dep.get("containers") or {}).items():
        print("  contenedor:",n,"| imagen:",c.get("image"),"| comando:",c.get("command"),"| puertos:",c.get("ports"))
        print("    variables:",sorted((c.get("environment") or {}).keys()))
'

echo; echo "== CA2: bases de datos (publiclyAccessible debe ser False)"
aws lightsail get-relational-databases --query 'relationalDatabases[].{nombre:name,motor:engine,version:engineVersion,estado:state,publica:publiclyAccessible,host:masterEndpoint.address,puerto:masterEndpoint.port,respaldoAuto:backupRetentionEnabled}' --output table

echo; echo "== CA2: intento de conexion TCP desde ESTE equipo (debe fallar si es privada)"
aws lightsail get-relational-databases --query 'relationalDatabases[].[name,masterEndpoint.address,masterEndpoint.port]' --output text | while read -r N H P; do
  if timeout 6 bash -c "</dev/tcp/$H/$P" 2>/dev/null; then echo "$N $H:$P -> ABIERTO desde internet (FALLA CA2)"; else echo "$N $H:$P -> sin conexion (correcto si es privada)"; fi
done

echo; echo "== CA3/CA4: buckets (Object Storage) y versionado"
aws lightsail get-buckets --query 'buckets[].{nombre:name,estado:state,versionado:objectVersioning,acceso:accessRules.getObject,creado:createdAt}' --output table

echo; echo "== CA4: contenido del bucket (solo listado)"
aws lightsail get-buckets --query 'buckets[].name' --output text | tr '\t' '\n' | while read -r B; do
  echo "-- $B"; aws s3 ls "s3://$B" --recursive 2>&1 | tail -5 || true
done

echo; echo "== CA4: snapshots de BD (retencion nativa)"
aws lightsail get-relational-database-snapshots --query 'relationalDatabaseSnapshots[].{nombre:name,creado:createdAt,estado:state}' --output table
} 2>&1 | tee "$SALIDA"
echo; echo "Listo. Envia el archivo: $SALIDA"
