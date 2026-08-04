# Backend - Pangea 4.0

## Cola de ingesta (HT-05)

**Estado: cerrada.** Los cuatro criterios de aceptación están implementados y
verificados:

| CA | Qué pide | Dónde está | Verificación |
|---|---|---|---|
| CA1 | Cada `.dat` recibido genera un job sin bloquear la recepción | `sondear_conexiones_ftp` + `beat_schedule` (cada 60s) | Sondeo corriendo en Beat |
| CA2 | Reintentos automáticos ante fallos transitorios | `autoretry_for` + backoff exponencial con jitter (5 intentos, tope 600s) | Ver "Reintentos" abajo |
| CA3 | Métricas de jobs pendientes / en proceso / fallidos | `GET /ingesta/metricas` (`app/routers/ingesta.py`) | Router registrado en `main.py` |
| CA4 | Soportar ≥1 archivo/min por datalogger sin cuello de botella | — | Medido: 60 archivos en 1.0s (ver "Prueba de carga") |

> **Pendiente que NO bloquea HT-05 pero sí afecta a la ingesta en
> producción — ver "Particiones de tlmtr" al final de este documento.**

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

### Reintentos (CA2)

`procesar_archivo_dat` distingue dos clases de error, porque no todos se
arreglan reintentando:

- **Transitorios** (`ERRORES_TRANSITORIOS` = `ftplib.all_errors`: conexión
  caída, timeout, EOF, SSL): hasta 5 reintentos con backoff exponencial +
  jitter, tope de 600s entre intentos. Al agotarlos, el archivo queda
  `Fallido` para reproceso manual (HU31).
- **No reintentables** (`ErrorDatosNoRecuperable`, o cualquier otra excepción
  como un `IntegrityError` de Postgres): se marcan `Fallido` de inmediato.
  Reintentar no cambiaría el resultado.

Dos trampas que costaron un diagnóstico largo y conviene no reintroducir:

1. **No anidar `ftplib.all_errors`**: ya es una tupla. Escribir
   `(ftplib.all_errors, OSError)` hace que Celery falle con `TypeError:
   catching classes that do not inherit from BaseException`, y **el retry
   deja de funcionar por completo**.
2. **Marcar `Fallido` también cuando el error no es reintentable**, no solo
   al agotar reintentos. Si solo se contempla lo segundo, un error
   inesperado deja el archivo colgado en `Procesando` para siempre:
   invisible en las métricas de CA3/HU09 y no reprocesable por HU31.

Ambos casos producían el mismo síntoma —archivos zombis en `Procesando`— y
los detectó la prueba de carga de CA4, no una prueba unitaria.

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

---

## PENDIENTE: particiones de `tlmtr` (fuera de HT-05)

> **Fecha límite: 1 de noviembre de 2026.** A partir de esa fecha la ingesta
> empieza a perder lecturas si nadie actúa antes.

`tlmtr` está particionada por rango mensual sobre `fch_hr`. La migración
`eadc512979fc` (22-jul-2026) creó **a mano** solo cuatro particiones:
`tlmtr_2026_07`, `_08`, `_09` y `_10`. No hay criterio de negocio detrás de
ese rango: es "el mes en curso + 3 de colchón" en el momento de escribir la
migración.

Esa migración asume que existe un job que crea las siguientes
automáticamente ("*el job de HT-08/Celery Beat creará las siguientes*"),
pero **ese job no está implementado**: no hay ninguna función que cree
particiones en `app/`, y `beat_schedule` solo tiene la entrada de
`sondear_conexiones_ftp`. El docstring de `app/models/telemetria.py` es el
que refleja la realidad actual: *"las particiones mensuales se crean a mano
en la migración"*.

**Consecuencia.** Una lectura cuyo `fch_hr` caiga fuera de las particiones
existentes falla al insertarse:

```
IntegrityError: no partition of relation "tlmtr" found for row
DETAIL: Partition key of the failing row contains (fch_hr) = (2026-11-01 ...)
```

Desde el fix de CA2, ese archivo se marca `Fallido` y queda visible en las
métricas y reprocesable por HU31 -antes se quedaba colgado en `Procesando`-,
pero **la lectura no se guarda igual**. No es una degradación silenciosa,
pero sí es pérdida de ingesta hasta que existan las particiones.

**Opciones para cerrarlo** (decisión del equipo, no se tomó en HT-05):

1. **Implementar el job de HT-08** que la migración da por hecho: una tarea
   en `beat_schedule` que cree con antelación la partición del mes
   siguiente. Es la solución de fondo.
2. **Parche temporal**: una migración que agregue particiones hasta mediados
   de 2027. Compra ~1 año y vuelve a presentar el mismo problema después.

Nota para quien corra pruebas: `tests/carga/prueba_carga_ca4.py` ya sortea
esto eligiendo automáticamente una fecha dentro de una partición existente
(y no futura, porque PP-99 rechaza timestamps futuros). Si esa prueba
empieza a fallar con el `IntegrityError` de arriba, la causa es esta y no
el pipeline.
