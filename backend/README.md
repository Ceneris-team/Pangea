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
