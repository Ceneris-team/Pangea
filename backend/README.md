# Backend - Pangea 4.0

## Middleware de autorización (HT-09)

**Estado: cerrada para los endpoints que existen hoy; CA1 queda parcial
porque HU08/HU10-HU13 todavía no están implementadas.** Ver el detalle CA
por CA abajo.

`app/security/permisos.py` valida, para cada endpoint protegido, que el
usuario autenticado (HT-04) tenga el permiso pedido según `prms_usr_sd`
(HT-03: Usuario-Sede-Rol-Permiso), no según un rol hardcodeado. La primera
versión de este archivo usaba una matriz `rol -> módulo -> acciones` en
memoria como implementación provisional; se reemplazó por una consulta
real a la tabla, que es lo que pedía HT-03 CA4 desde el principio (permisos
editables en BD, no fijos en código).

| CA | Qué pide | Estado |
|---|---|---|
| CA1 | Todos los endpoints del PMV (HU08, HU10, HU11, HU12, HU13) validan permiso | **Parcial.** Esas 5 HU no tienen ningún endpoint implementado todavía (no existe router de dispositivos ni de tableros/dashboards) - no hay nada que conectar. Sí se aplicó/confirmó `require_permiso()` en los 3 endpoints que sí existen y tocan módulos del CHECK constraint de HT-03: `GET /ubicaciones` (HU07), `GET /ingesta/metricas` (HU09) y `GET`+`POST /usuarios` (HU03/HU04), reemplazando en los dos últimos un chequeo de rol hardcodeado por el permiso real. |
| CA2 | Solo-lectura en Dispositivos -> 403 al intentar HU11 (edición) | **Cerrado.** `tiene_permiso()` consulta `prms_usr_sd` filtrando por usuario+sede+módulo y compara el nivel (`Lectura`/`Edición`/`Ninguno`) contra la acción pedida. Sin fila = sin permiso, igual que `Ninguno`. |
| CA3 | Usuario `por_sede` de la Sede A no toca la Sede B ni con permiso de edición | **Cerrado**, ya estaba implementado en `verificar_sede()`; se confirmó que sigue aplicando después de conectar CA2 a la BD (son chequeos independientes: uno filtra por módulo/nivel, el otro por sede del recurso). |
| CA4 | Usuario `global` opera cualquier sede sin asignación previa | **Cerrado, con una decisión documentada.** Ver "Scope global y prms_usr_sd" abajo. |
| CA5 | Cada acceso denegado queda registrado (usuario, sede, módulo, acción) | **Cerrado**, sin cambios: `_registrar_acceso_denegado()` no dependía de la matriz y sigue funcionando igual con el chequeo basado en BD. |

### Scope global y prms_usr_sd (CA4)

`verificar_sede()` ya eximía a `scope == "global"` del filtro de sede. La
pregunta que quedaba abierta era si ese usuario también necesita una fila
en `prms_usr_sd` para el chequeo de módulo/nivel, o si `global` debería
implicar edición total.

**Decisión (conservadora): sí necesita la fila.** `scope == "global"` solo
exime del filtro de *sede*, no del de *módulo/nivel* - son dos ejes
independientes en el modelo de HT-03, y no hay razón para que uno implique
el otro. Como `prms_usr_sd.id_sd` es `NOT NULL` (no se puede tocar ese
constraint, es de HT-03), un usuario global no puede tener una fila
"sede-agnóstica"; `tiene_permiso()` resuelve esto ignorando el filtro de
sede cuando `id_sd` viene en `None` y aceptando cualquier fila del usuario
para ese módulo, sea cual sea su sede - consistente con que `verificar_sede`
ya lo deja operar en cualquier sede de todos modos. Ver el docstring de
`tiene_permiso()` en `app/security/permisos.py` para el detalle.

### Limitación real encontrada en el modelo de datos

Dos hallazgos de esta conexión, ninguno de los cuales toca el esquema de
HT-03 ni el JWT de HT-04 (fuera de alcance de HT-09), pero que conviene
resolver antes de que un usuario `por_sede` real dependa de esto en
producción:

1. **`POST /auth/login` (HT-04) siempre emite `sede_id=None` en el JWT**,
   sin importar `usr.scp`. Es un bug de HT-04, no de HT-09, pero bloquea
   CA3 en la práctica: un usuario `por_sede` real jamás podría pasar
   `verificar_sede()` ni siquiera para su propia sede, porque
   `usuario.sede_id` (`None`) nunca es igual al `sede_id_recurso` real. Los
   tests de HT-09 no lo tocan porque prueban `verificar_sede()` con un
   payload construido a mano (como lo emitiría un login correcto), no a
   través del flujo real de `/auth/login`. Queda para quien cierre esa
   parte de HT-04, o para una HT nueva si HT-04 ya se dio por cerrada.
2. **`prms_usr_sd.id_sd` es `NOT NULL`**, así que no hay forma de expresar
   en el esquema actual "este usuario tiene permiso en TODAS las sedes"
   con una sola fila - ni para roles global ni para sedes que se creen
   después. Hoy se resuelve en `tiene_permiso()` interpretando "cualquier
   fila del usuario para ese módulo" como suficiente para un usuario
   global (ver arriba), pero un usuario global sin ninguna fila para un
   módulo nuevo queda bloqueado hasta que alguien le cree una fila a mano
   en alguna sede. Si esto se vuelve un problema operativo real, la
   solución de fondo (agregar una fila "comodín" con `id_sd` nulleable, o
   una tabla de permisos separada para scope global) es un cambio de
   esquema de HT-03 y no se hizo aquí a propósito.

### Correr los tests

Los tests de autorización (`tests/test_permisos.py`,
`tests/routers/test_autorizacion_endpoints.py`) corren contra una Postgres
real con las migraciones aplicadas -no contra SQLite-, porque el esquema
real usa tipos (`JSONB`) que SQLite no puede compilar y porque HT-09
necesita validar contra `prms_usr_sd` tal como la define la migración de
HT-03, no una recreación aproximada del modelo.

```bash
createdb pangea_test
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pangea_test \
    python -m alembic upgrade head

# Redis debe estar corriendo (lo usa el broker de resultados de Celery,
# que se dispara en el test de POST /usuarios al encolar el correo de
# bienvenida de HU04).
TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pangea_test \
    python -m pytest tests/test_permisos.py tests/routers/test_autorizacion_endpoints.py -v
```

Cada test corre dentro de un SAVEPOINT que se revierte al final
(`tests/conftest.py`), así que no ensucia `pangea_test` ni necesita volver
a migrar entre corridas.

---
## Cola de ingesta (HT-05)

**Estado: cerrada.** Los cuatro criterios de aceptación están implementados y
verificados:

| CA | Qué pide | Dónde está | Verificación |
|---|---|---|---|
| CA1 | Cada `.dat` recibido genera un job sin bloquear la recepción | `sondear_conexiones_ftp` + `beat_schedule` (cada 60s) | Sondeo corriendo en Beat |
| CA2 | Reintentos automáticos ante fallos transitorios | `autoretry_for` + backoff exponencial con jitter (5 intentos, tope 600s) | Ver "Reintentos" abajo |
| CA3 | Métricas de jobs pendientes / en proceso / fallidos | `GET /ingesta/metricas` (`app/routers/ingesta.py`) | Router registrado en `main.py` |
| CA4 | Soportar ≥1 archivo/min por datalogger sin cuello de botella | — | Medido: 60 archivos en 1.0s (ver "Prueba de carga") |

> El pendiente de particiones de `tlmtr` que quedó abierto al cerrar HT-05
> **ya está resuelto en HT-08** — ver "Particionamiento de tlmtr (HT-08)".

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
## Mapeo de formato por marca (HU06 / PP-96)

Un datalogger manda **dos formatos de archivo distintos**, con distinto número
y significado de columnas. El tipo se deduce del prefijo del nombre:

| Prefijo | `mp_frmt.tp_trm` | Contenido |
|---|---|---|
| `H_*.dat` | `H` | Datos periódicos (la lectura en tiempo real) |
| `E_*.dat` | `E` | Estados y eventos que genera el equipo |

Por eso un formato se identifica por **sede + marca + tipo de trama**
(`uq_mpfrmt_sd_mrc_tptrm`), no solo por marca: sin `tp_trm` no habría forma de
guardar ambos sin inventar marcas falsas tipo `"Campbell_H"`.

### Cómo se resuelve un archivo

`app/services/ingesta/mapeo.py`, antes de descargar nada:

1. `detectar_tipo_trama()` saca `H`/`E` del prefijo del nombre (tolera
   minúsculas y rutas).
2. `resolver_formato()` busca el `mp_frmt` activo de esa sede + marca + trama, y
   de ahí salen delimitador, fila de inicio de datos y formato de fecha.
3. Tras parsear el header, `construir_mapeo()` traduce `mp_clmn` a
   `columna → parámetro`.

**`mp_clmn` referencia las columnas por índice (`indc_clmn`, 0-based sobre el
header), no por nombre.** Es a propósito: los archivos de campo traen headers
con nombres inconsistentes, repetidos o con unidades pegadas
(`Temperatura(C°)`), y el índice es estable frente a eso. El contrapeso es que
si el datalogger inserta una columna al principio, los índices se desplazan y
hay que recargar el mapeo.

### Qué pasa si falta el mapeo

Se lanza `MapeoNoEncontradoError`, que el pipeline clasifica como error de datos
**no reintentable**: el archivo queda `Fallido` con una causa accionable
("no hay formato activo para sede=X, marca=Y, trama=Z"). No se adivina el
formato: interpretar un archivo con el mapeo equivocado produciría lecturas
incorrectas en silencio, que es peor que no procesarlo.

Lo mismo si el archivo no tiene prefijo reconocible, o si ninguna columna del
mapeo existe en el header.

### Cargar un formato nuevo

Hoy se hace por SQL/seed: una fila en `mp_frmt` (sede, marca, `tp_trm`,
delimitador, formato de fecha) y una fila en `mp_clmn` por cada columna que se
quiera capturar, apuntando a su `prmtr`.

> **Pendiente**: el equipo de telemetría pidió poder crear y editar estos
> formatos ellos mismos, sin tocar la base de datos, porque el tipo de variables
> que manejan es muy variado. Eso es una historia aparte (endpoints CRUD +
> pantalla de configuración); el modelo de datos que necesita ya existe.

## Particionamiento de `tlmtr` (HT-08)

**Estado: implementado.** `tlmtr` está particionada por RANGE mensual sobre
`fch_hr`. Postgres no crea particiones por su cuenta: una fila cuya `fch_hr`
no caiga en ninguna partición existente **hace fallar el INSERT**, así que
hay tres piezas que garantizan que eso no ocurra en operación normal.

| CA | Qué pide | Dónde está |
|---|---|---|
| CA1 | Tabla particionada por rango de fecha | `app/models/telemetria.py` (RANGE sobre `fch_hr`, PK compuesta, BRIN + índices por `id_dspstv`/`id_sd`) |
| CA2 | Las consultas por rango excluyen particiones irrelevantes | Verificado con `EXPLAIN ANALYZE`, ver abajo |
| CA3 | Particiones creadas automáticamente con anticipación | `app/tasks/particiones.py` + `beat_schedule` |
| CA4 | Insertar fuera de rango no genera un error no controlado | `ParticionInexistenteError`, ver "Fecha sin partición" |

### Piezas

1. **Migración inicial** (`a7f31c4b9e02`): crea 12 meses de particiones desde
   el mes en que se aplica. Es el arranque del PMV; a partir de ahí manda el
   job. La migración `eadc512979fc` había creado a mano solo `2026_07` ..
   `2026_10`, que se agotaban el 1-nov-2026.
2. **Job diario** (`app.tasks.particiones.asegurar_particiones_futuras`):
   corre a las 03:00 vía Celery Beat y mantiene `MESES_DE_COLCHON = 3` meses
   creados por delante. La partición del mes siguiente existe siempre con
   semanas de anticipación (HT-08 pide al menos una).
3. **Helper compartido** (`app/services/particiones.py`): el cálculo de
   nombres/rangos y el `CREATE` viven en un solo sitio, usado tanto por la
   migración como por el job, para que no diverjan.

**Por qué el job corre a diario y no una vez al mes:** si falla un día -o el
worker está caído justo el día que tocaba-, al día siguiente se recupera
solo. Un job mensual que falle deja un hueco que nadie nota hasta que la
ingesta empieza a rechazar lecturas. Por lo mismo el job **también repara
huecos** hacia atrás dentro de su ventana, no solo crea hacia adelante.

Todo es idempotente (`CREATE TABLE IF NOT EXISTS`): re-aplicar la migración
o que el job corra dos veces el mismo día no falla ni duplica nada.

### Fecha sin partición (CA4)

Insertar una lectura sin partición produce en Postgres crudo:

```
ERROR: no partition of relation "tlmtr" found for row
DETAIL: Partition key of the failing row contains (fch_hr) = (2019-03-01 ...)
```

`guardar_lecturas` hace `flush()` explícito para que ese INSERT viaje a la
BD dentro de la función -no en el `commit()` del llamador- y traduce el
fallo (SQLSTATE `23514` + mensaje de partición) a `ParticionInexistenteError`,
con el rango de fechas concreto y qué revisar. El pipeline la clasifica como
`ErrorDatosNoRecuperable`: el archivo se marca `Fallido` **sin reintentar**
-reintentar no crea la partición- y queda reprocesable por HU31.

**Se rechaza el insert; no se crea la partición al vuelo.** Decisión
deliberada: (a) ejecutar DDL desde el path de ingesta toma un lock sobre la
tabla padre y con varios workers concurrentes puede bloquear la ingesta
entera; (b) crear particiones automáticamente enmascara datos corruptos -un
datalogger mal configurado que reporte el año 2019 o 2040 generaría
particiones basura en silencio-; (c) el caso legítimo ya lo cubre el job de
Beat, así que una fecha fuera de rango es una anomalía real que conviene ver.

### Partition pruning verificado (CA2)

Medido sobre 15.410 filas repartidas en 7 meses (13 particiones), con la
consulta típica de HU12/HU13 -filtro por sede + rango de fechas-:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT fch_hr, vlr FROM tlmtr
WHERE id_sd = :sede AND fch_hr >= '2026-09-01' AND fch_hr < '2026-10-01'
ORDER BY fch_hr;
```

```
Index Scan using tlmtr_2026_09_id_sd_fch_hr_idx on tlmtr_2026_09 tlmtr
  (cost=0.28..136.19 rows=2160) (actual time=0.157..0.814 rows=2160 loops=1)
  Index Cond: ((id_sd = $0) AND (fch_hr >= ...) AND (fch_hr < ...))
  Buffers: shared hit=29
Execution Time: 0.952 ms
```

| Consulta | Particiones tocadas | Buffers |
|---|---|---|
| Con filtro de rango mensual | **1** de 13 | 29 |
| Sin filtro de fecha | 13 de 13 | 132 |

El planner descarta las 12 particiones irrelevantes y ataca solo
`tlmtr_2026_09` por el índice `(id_sd, fch_hr)`. CA2 cumplido.

> Nota para HT-16 (optimización de índices, sprint posterior): esta medición
> es la línea base. Se hizo con datos sintéticos de un solo dispositivo y una
> sola sede; para HT-16 conviene repetirla con varias sedes y dispositivos,
> que es cuando el índice `(id_sd, fch_hr)` empieza a competir de verdad con
> el BRIN sobre `fch_hr`.
