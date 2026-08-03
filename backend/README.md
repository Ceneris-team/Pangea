# Backend - Pangea 4.0

## Cola de ingesta (HT-05)

La ingesta de archivos `.dat` de los dataloggers corre sobre Celery + Redis,
con tres roles separados que corren como contenedores/procesos independientes:

| Servicio (docker-compose) | Comando | Rol |
|---|---|---|
| `api` | `uvicorn app.main:app` | HTTP, nunca toca la cola directamente |
| `worker` | `celery -A app.core.celery_app worker` | Consume jobs: sondea FTP (`sondear_conexiones_ftp`) y procesa archivos (`procesar_archivo_dat`) |
| `beat` | `celery -A app.core.celery_app beat` | Dispara `sondear_conexiones_ftp` cada minuto (ver `beat_schedule` en `app/core/celery_app.py`) |

`api`, `worker` y `beat` son procesos independientes del servidor principal
(contenedores separados, mismo Dockerfile, distinto `command`), tal como
pide el procedimiento de HT-05: un worker caído o saturado no afecta la
disponibilidad de la API, y viceversa.

### Límite de concurrencia

El worker arranca con `--concurrency=4` (ver `docker-compose.yml`, servicio
`worker`). Ese número es el máximo de jobs que un worker procesa en
paralelo, y existe para evitar que picos de archivos saturen la conexión a
Postgres o el ancho de banda hacia los FTP de los dataloggers.

CA4 pide soportar al menos 1 archivo/minuto por datalogger sin cuello de
botella perceptible. Con `--concurrency=4`, un solo worker soporta ~4
archivos en paralelo; como el procesamiento de cada archivo es una
operación corta (segundos, no minutos), esto cubre varias decenas de
dataloggers reportando cada uno una vez por minuto sin acumular cola. Si
el número de dataloggers crece más allá de eso, la vía es escalar
horizontalmente (ver abajo), no subir la concurrencia de un único worker
sin límite -mantiene cada worker liviano y predecible en uso de memoria-.

### Prueba de carga (CA4)

`tests/carga/prueba_carga_ca4.py` valida CA4 ("la cola soporta al menos un
archivo por minuto por datalogger sin cuellos de botella perceptibles").
Levanta un FTP local que sirve los fixtures de `tests/fixtures/`, crea N
conexiones `cnxn_ftp` de prueba apuntando a él, encola todo de golpe y mide
cuánto tarda la cola real (Celery + Redis + worker) en drenar.

```bash
# el stack debe estar levantado SIN docker-compose.override.aws-test.yml,
# si no se escriben datos de prueba en la RDS compartida
docker compose -f docker-compose.yml --profile full up -d

cd backend
./venv/Scripts/python.exe tests/carga/prueba_carga_ca4.py
./venv/Scripts/python.exe tests/carga/prueba_carga_ca4.py --limpiar
```

No basta con que la cola drene rápido: el script exige las tres cosas
(drenar a tiempo, **todos** los archivos en `Exitoso`, y filas reales
escritas en `tlmtr`) y devuelve exit code 1 si alguna falla. Sin la
verificación de `tlmtr`, un pipeline que marcara los archivos como
`Exitoso` sin persistir nada daría un falso "CUMPLE".

Resultado medido (3 ago 2026, `--concurrency=4`, un solo worker, todo en
una máquina de desarrollo con Docker Desktop):

| Métrica | Valor |
|---|---|
| Escenario | 5 dataloggers x 12 archivos = 60 archivos de golpe |
| Equivalente en operación real | 12 min (1 archivo/min/datalogger) |
| Tiempo en drenar la cola | **1.0 s** |
| Throughput | ~59 archivos/s (~3.500 archivos/min) |
| Estados finales | 60/60 `Exitoso` |
| Filas persistidas en `tlmtr` | 220 |

**CA4 se cumple con amplio margen**: la cola absorbe en 1 segundo lo que en
operación real llegaría a lo largo de 12 minutos (~700x de margen). No se
observó cuello de botella; con `--concurrency=4` el limitante práctico sería
el FTP de los dataloggers o el pool de Postgres, no la cola. La medición es
optimista respecto a producción en un punto: el FTP de prueba es local
(latencia ~0), mientras que un datalogger real en campo añade latencia de red
por descarga. Aun así el margen es tan amplio que la conclusión no cambia.

### Escalar horizontalmente

El diseño permite agregar más workers a medida que se suman sedes/clientes,
sin tocar la lógica de negocio del mapeo de formatos (detalle técnico #3
del documento HT-05):

- Los workers son **stateless**: no guardan nada en memoria entre jobs, todo
  el estado vive en Postgres (`archv_ingst`) y Redis (broker/resultados).
  Levantar una segunda, tercera o N-ésima réplica del servicio `worker` es
  seguro sin coordinación adicional - Celery reparte los jobs de la cola
  entre todos los workers conectados al mismo broker.
- El **mapeo de formato por marca de sensor** vive en datos (tablas
  `mp_frmt`/`mp_clmn`/`prmtr`), no en código. Agregar un datalogger de una
  marca nueva es una fila nueva en esas tablas, no un cambio en
  `app/tasks/ingesta.py` ni en los workers.
- En Docker Compose local, escalar es `docker compose up --scale worker=3`
  (con el perfil `full` activo). En un orquestador real (K8s, ECS, etc.) es
  el equivalente de subir el número de réplicas del deployment/servicio
  `worker` - no requiere cambios de código.
- `beat` **no debe escalarse** a más de una instancia: es el scheduler que
  dispara `sondear_conexiones_ftp`, y correr dos instancias duplicaría cada
  sondeo. Solo `worker` (y `api`) son horizontalmente escalables.

### Deduplicación de archivos

`sondear_conexiones_ftp` (en `app/tasks/ingesta.py`) evita reencolar un
archivo ya visto comparando el nombre contra los `archv_ingst.nmbr_archv`
ya existentes para esa conexión, antes de crear la fila `Pendiente`. No
requiere estado adicional más allá de la tabla que ya existe.

Cada `cnxn_ftp` respeta su propia `frcnc_mnts` (frecuencia en minutos)
gracias a la columna `ultm_snd`: aunque Celery Beat dispara el sondeo cada
minuto, cada conexión solo se sondea de verdad si ya pasó su `frcnc_mnts`
desde el último sondeo.
