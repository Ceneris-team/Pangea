# Backend - Pangea 4.0

## Mapeo de formato: CRUD y vista previa (HU06)

**Estado: cerrada.** El *motor* de mapeo (`app/services/ingesta/mapeo.py` y
`parser.py`) ya existía y está en uso por el pipeline de ingesta; lo que
faltaba para cerrar HU06 era la capa que permite al Técnico CENERIS crear
y editar los mapeos desde la interfaz, en vez de insertarlos a mano en la
base de datos. Eso es `app/routers/mapeos.py` + las pantallas
`frontend/src/pages/Mapeos.tsx` y `ConfigurarMapeo.tsx`.

| CA | Qué pide | Endpoint / pantalla |
|---|---|---|
| CA1 | Formulario "Nuevo mapeo" con la tabla de asignación columna→parámetro | `GET /parametros` + `ConfigurarMapeo.tsx` |
| CA2 | "Vista previa": primeras 10 filas del .dat de muestra interpretadas | `POST /mapeos/vista-previa` |
| CA3 | "Guardar" → "Mapeo guardado correctamente" | `POST /mapeos` |
| CA4 | "Actualizar" → "Mapeo actualizado correctamente" | `PUT /mapeos/{id_mp}`, `GET /mapeos/{id_mp}` |
| CA5 | "Ver mapeos": el registro aparece asociado a su marca | `GET /mapeos` + `Mapeos.tsx` |

Acceso: `require_permiso("Ingesta", …)` (HT-09). No existe un módulo
"Mapeos" en el CHECK constraint de `prms_usr_sd`; `Ingesta` es el que
corresponde a la configuración del pipeline. Lectura para consultar y
previsualizar, Edición para crear/actualizar.

### El archivo de muestra no se persiste (CA2)

Regla explícita de la HU. `POST /mapeos/vista-previa` recibe el `.dat` por
`multipart/form-data`, lo lee **en memoria** (`await archivo.read()`), lo
pasa por el `parsear_dat()` que ya existía y devuelve las primeras 10
filas. No se escribe en disco ni en base de datos: por eso el endpoint
pide permiso de *Lectura* y no de Edición, y por eso hay un test
(`test_no_persiste_nada`) que verifica que los conteos de `mp_frmt` y
`mp_clmn` no cambian tras previsualizar.

### Bug real encontrado en el motor: CRLF revienta parsear_dat()

Al probar la vista previa con un `.dat` real de datalogger (no uno de los
fixtures, que usan `LF`), `parsear_dat()` reventaba con
`_csv.Error: new-line character seen in unquoted field`. Causa: la función
arma `io.StringIO(contenido)` y se lo pasa a `csv.reader`, pero
`io.StringIO` **no hace la traducción universal de saltos de línea** que sí
hace abrir un archivo en modo texto (`open(..., newline=None)`); un `\r`
suelto que sobrevive dentro de lo que el `csv.reader` trata como una sola
línea dispara ese error de la librería estándar. Los `.dat` reales de
Campbell Scientific (y probablemente de otras marcas) vienen con `CRLF`, a
veces con un byte `NUL` de relleno al final del archivo.

Esto **no es exclusivo de la vista previa**: `app/tasks/ingesta.py` llama a
`parsear_dat()` con el contenido de `descargar_archivo_dat()`
(`app/ingesta/ftp_receptor.py`), que descarga por FTP en modo binario y
decodifica sin ninguna normalización de saltos de línea -el mismo patrón
que tenía el endpoint nuevo antes de este fix-. Es decir, **la ingesta real
probablemente falla hoy con cualquier `.dat` que use CRLF**, no solo la
vista previa de HU06.

Como HU06 tiene explícitamente prohibido tocar `parser.py` y el pipeline de
ingesta ("son el motor ya probado, solo consumirlos" / "no tocar
`tasks/ingesta.py`"), el fix se aplicó **solo en la frontera de
`vista_previa()`**: normaliza `\r\n`/`\r` a `\n` y quita bytes `NUL` antes
de llamar a `parsear_dat()`, y envuelve la llamada para devolver 422 en vez
de un 500 crudo si igual falla. La causa raíz sigue viva en
`parser.parsear_dat()` y en `app/tasks/ingesta.py`, y debería resolverse ahí
-lo más simple sería aplicar la misma normalización dentro de
`parsear_dat()`, ya que así cualquier llamador queda cubierto-, pero eso es
tocar el motor, así que quedó fuera de este cierre a propósito. Hay un test
de regresión con el archivo real que disparó el bug
(`tests/fixtures/H_ejemplo_crlf_real.dat`,
`test_archivo_real_con_crlf_no_revienta`).

### Formato de fecha: dos lenguajes, una traducción en la frontera

La HU dice que el campo "acepta cadenas tipo `YYYY-MM-DD HH:mm:ss`", pero
el motor (`parser._parsear_fecha`) usa `strptime`, y los mapeos sembrados
antes de HU06 ya están guardados como `%Y-%m-%d %H:%M:%S`. En vez de tocar
el motor -que está probado y en producción-, la traducción vive en el
router: `a_formato_strptime()` al guardar y `a_formato_legible()` al leer.
Un valor que ya venga con `%` se deja pasar tal cual, así los mapeos
existentes siguen funcionando sin migrar nada.

### Limitaciones del modelo de datos encontradas (no resueltas)

Ninguna se resolvió aquí: HU06 no incluía cambios de esquema y el modelo
de datos ya se daba por cerrado. Se reportan para decidir aparte.

1. **No hay columna para "Extensión de archivo"**, que CA1 lista como campo
   obligatorio del formulario. Lo más cercano en `mp_frmt` es `tp_trm`
   (`'H'`/`'E'`), que no es la extensión sino el *tipo de trama*, y que el
   motor deduce del **prefijo** del nombre (`H_*.dat` / `E_*.dat`), no de
   la extensión. El formulario expone `tp_trm` en ese lugar, porque es el
   campo que el motor realmente usa y forma parte de la clave única
   `(id_sd, mrc, tp_trm)`. Si el equipo quiere una extensión configurable
   de verdad (hoy el pipeline solo procesa `.dat`), hace falta una columna
   nueva **y** que el motor la consuma; agregarla sola sería dato muerto.
2. **No hay columna para el nombre de la columna de fecha.**
   `ConfiguracionParseo.columna_fecha` existe en el parser y por defecto
   vale `"Fecha"`, pero `resolver_formato()` no lo setea, así que el motor
   siempre usa ese valor fijo. La vista previa acepta `columna_fecha` como
   parámetro (para poder previsualizar tramas cuyo header use otro nombre)
   pero **no puede persistirlo**: una marca cuya columna de fecha no se
   llame "Fecha" se previsualizaría bien y luego fallaría en la ingesta
   real. Si aparece un datalogger así, hace falta la columna en `mp_frmt`.

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
## Mapeo de formato por dispositivo (HU06 / PP-96 / DEC-09)

Un datalogger puede mandar **varios formatos de archivo distintos**, con
distinto número y significado de columnas. El tipo se deduce del prefijo del
nombre, y es una **letra libre que el técnico de telemetría define al crear
el mapeo** (`_validar_tipo_trama` en `routers/mapeos.py` solo exige A-Z, ya
no hay un catálogo cerrado en la base de datos): agregar un prefijo nuevo no
requiere tocar código ni desplegar. H/E/P son simplemente los primeros
valores cargados:

| Prefijo | `mp_frmt.tp_trm` | Contenido |
|---|---|---|
| `H_*.dat` | `H` | Datos periódicos (la lectura en tiempo real) |
| `E_*.dat` | `E` | Estados y eventos que genera el equipo |
| `P_*.dat` | `P` | Eventos de puerta/acceso |
| `X_*.dat` | cualquier letra | Lo que el técnico configure para ese dispositivo |

Un formato se identifica por **dispositivo + tipo de trama** (índice único
parcial `uq_mpfrmt_dspstv_tptrm_activo`, solo un mapeo `Activo` por
dispositivo+letra): dos dataloggers de la misma marca pueden tener sensores
distintos conectados, así que el mapeo cuelga del dispositivo concreto, no
de la marca ni de la sede.

### Cómo se resuelve un archivo

`app/services/ingesta/mapeo.py`, antes de descargar nada:

1. `detectar_tipo_trama(db, id_dspstv, nombre_archivo)` compara el prefijo
   del nombre (tolera minúsculas y rutas) contra los `tp_trm` que ESE
   dispositivo tiene con un `mp_frmt` activo -no contra un diccionario fijo
   en código, y no contra los de otros dispositivos, que podrían usar la
   misma letra con otro significado-.
2. `resolver_formato()` busca el `mp_frmt` activo de ese dispositivo + trama, y
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

> **Resuelto en HU06**: el equipo de telemetría pedía poder crear y editar estos
> formatos ellos mismos, sin tocar la base de datos. Ya existe el CRUD
> (`app/routers/mapeos.py`) y la pantalla de configuración - ver "Mapeo de
> formato: CRUD y vista previa (HU06)" al inicio de este README. Cargar un
> formato por SQL/seed sigue funcionando, pero ya no es la única vía.

## Particionamiento de `tlmtr` (HT-08)

**Estado: implementado.** `tlmtr` está particionada por RANGE mensual sobre
`fch_hr`. Postgres no crea particiones por su cuenta: una fila cuya `fch_hr`
no caiga en ninguna partición existente **hace fallar el INSERT**, así que
hay tres piezas que garantizan que eso no ocurra en operación normal.

| CA | Qué pide | Dónde está |
|---|---|---|
| CA1 | Tabla particionada por rango de fecha | `app/models/telemetria.py` (RANGE sobre `fch_hr`, PK compuesta, BRIN + índices por `id_dspstv`/`id_sd`) |
| CA2 | Las consultas por rango excluyen particiones irrelevantes | Verificado con `EXPLAIN ANALYZE`, ver abajo. Reproducible con `python -m app.scripts.medir_pruning_ht08` |
| CA3 | Particiones creadas automáticamente con anticipación | `app/tasks/particiones.py` + `beat_schedule` |
| CA4 | Insertar fuera de rango no genera un error no controlado | `ParticionInexistenteError`, ver "Fecha sin partición" |

Cubierto por tests automatizados en `tests/services/test_particiones.py`: cálculo de
nombres/rangos, idempotencia y reparación de huecos de `asegurar_particiones` contra
Postgres real, clasificación de `es_error_de_particion_faltante` (sin confundirla con
otro `CHECK` que use el mismo SQLSTATE), y el flujo completo de `guardar_lecturas`
insertando en una partición existente vs. una fecha sin partición (CA4).

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

**Medición reproducible:** `python -m app.scripts.medir_pruning_ht08` siembra datos
sintéticos (2 sedes, idempotente: limpia su propia corrida anterior antes de sembrar)
y corre `EXPLAIN (ANALYZE, BUFFERS)` con y sin filtro de fecha, dejando el número de
particiones tocadas en cada caso. La tabla de arriba corresponde a una corrida de este
script (`--meses 7`); Postgres reporta explícitamente `Subplans Removed: 12` en el plan
con filtro.

> Nota para HT-16 (optimización de índices, sprint posterior): esta medición es la
> línea base. `medir_pruning_ht08.py` ya siembra dos sedes, pero sigue siendo un solo
> dispositivo por sede; para HT-16 conviene extenderlo con más dispositivos por sede y
> volumen mayor, que es cuando el índice `(id_sd, fch_hr)` empieza a competir de
> verdad con el BRIN sobre `fch_hr`.

### Pendientes fuera de alcance de HT-08 (para otro ticket)

Estos dos puntos aparecieron durante la auditoría de HT-08 pero **no** son parte de
sus 4 CA, así que quedan documentados en vez de implementados aquí:

- ~~**El endpoint de HU12/HU13 (`GET /mediciones` en `app/routers/mediciones.py`) no
  filtra por rango de fechas todavía**, ni lo hace el frontend
  (`ConsultaDatos.tsx`). Filtra por ubicación/parámetro, pero sin filtro de fecha la
  consulta toca las 13 particiones (confirmado con `medir_pruning_ht08.py` contra la
  forma real del endpoint). El particionamiento de HT-08 ya deja el terreno listo
  -índice `(id_sd, fch_hr)` e índice BRIN sobre `fch_hr`- para que ese filtro sea
  barato en cuanto HU12 (u HT-16) lo agregue; hoy simplemente no se usa porque nadie
  lo pide.~~
  **RESUELTO en HT-10** (backend): el filtro de fechas ya se aplica en SQL y la
  consulta toca 1 de 17 particiones usando el índice `(id_sd, fch_hr)` de HT-08. Ver
  "Caché de consultas (HT-10)" más abajo. El frontend (`ConsultaDatos.tsx`) sigue sin
  enviar el rango: eso queda fuera del alcance de HT-10, que es backend.
- **HT-16** (optimización de índices) debería repetir la medición de CA2 con varias
  sedes y dispositivos y volumen realista -el script de arriba es el punto de partida-,
  y **HT-18** (pruebas de carga con Locust) queda para su propio sprint. Ninguno de los
  dos se tocó en este trabajo.

## Caché de consultas (HT-10)

Capa de caché en Redis para los tres endpoints de lectura que alimentan las vistas
pesadas, más el filtro de fechas y el downsampling que faltaban en `GET /mediciones`.

| Endpoint | HU | Qué cachea |
|---|---|---|
| `GET /mediciones` | HU12/HU13/HU15 | la página de la tabla/gráfica ya paginada |
| `GET /mapa-cliente` | HU17 | la **carga inicial** del mapa |
| `GET /ubicaciones/mapa` | HU22 | el listado con polígonos y conteo de dispositivos |

El WebSocket `/mapa-cliente/ws` **no se toca**: sigue empujando cada lectura en vivo
por pub/sub (DB 4) y no tiene nada que cachear.

### Piezas

- `app/services/cache/consultas.py` — clave, TTL, lectura/escritura e invalidación.
- `app/services/cache/invalidacion.py` — punto único por el que entran los dos
  caminos de escritura de telemetría.
- `app/services/cache/downsampling.py` — muestreo para rangos amplios.
- `app/scripts/medir_cache_ht10.py` — medición reproducible (mismo patrón que
  `medir_pruning_ht08.py`).

### DB de Redis: la 5

Las anteriores ya estaban tomadas y **no** se comparten: `1` rate limiting,
`2` broker de Celery, `3` result backend, `4` pub/sub del mapa (HU17). Configurable
con `CACHE_REDIS_URL`; por defecto se deriva de `CELERY_BROKER_URL`, igual que
`MAPA_EVENTOS_REDIS_URL`.

### Aislamiento entre sedes (CA4)

La clave **nunca** se arma solo con la query string. Se arma con el *ámbito de
visibilidad* del usuario: `sede_id` del JWT **+ hash del conjunto ordenado de
ubicaciones permitidas** (`prms_ubccn`, HU21).

Los dos parámetros son necesarios y ninguno sobra:

- solo la query string → el Cliente Final de la sede A recibiría los datos de la
  sede B por pedir la misma URL un segundo después. En `/mapa-cliente` y
  `/ubicaciones/mapa`, que **no tienen ningún parámetro de consulta**, esa colisión
  sería universal;
- solo `sede_id` → dos Clientes Finales de la **misma** sede con asignaciones de
  HU21 distintas compartirían entrada; y como un usuario con `scope: "global"` trae
  `sede_id=None` (ver `security/permisos.py`), *todos* los globales caerían en el
  mismo cubo.

Cubierto por `tests/routers/test_cache_ht10.py::TestCA4AislamientoEntreSedes` sobre
los tres endpoints, con el orden que rompería una caché mal construida (la sede A
pide primero y deja la entrada caliente; la sede B pide después con la misma URL).

### TTL

`TTL_CORTO = 45s` (`CACHE_TTL_CORTO`) para los tres endpoints: punto medio del rango
30-60s que pide la HT, muy por debajo de la cadencia real del dato (~15 min por
archivo). Es además la red de seguridad si un evento de invalidación se pierde.

`TTL_LARGO = 24h` (`CACHE_TTL_LARGO`) queda **definido pero sin uso**: la HT lo pide
solo para agregados históricos precalculados, y **hoy no existe ninguno** — no hay
tabla de rollup ni vista materializada (y la restricción de HT-08 sigue vigente:
Lightsail Managed Database no admite extensiones, así que tampoco hay agregados
continuos de TimescaleDB). Caso **no aplica todavía**; cuando exista ese precálculo,
la constante ya está y el único cambio es pasarla como `ttl` al guardar.

### Invalidación dirigida (CA2)

Se dispara en los **dos** caminos de escritura de telemetría:

1. `services/ingesta/persistencia.py::guardar_lecturas` — pipeline automático;
   además `tasks/ingesta.py` vuelve a invalidar **después del commit**, para cerrar
   la ventana en la que un request podría repoblar la caché con el estado anterior.
2. `routers/dispositivos.py`, `POST /dispositivos/{id}/carga-manual` — escribe
   directo en `tlmtr` sin pasar por el pipeline, así que necesita su propia llamada.

La invalidación es **filtrada por sede y ubicación**, nunca un flush global: cada
entrada se registra al guardarse en un índice (`SET` de Redis) por sede y/o
ubicación, y la escritura borra solo esos índices. Con el pipeline corriendo cada
minuto sobre varias sedes, un flush global dejaría la caché sin llegar viva al
segundo request.

### Downsampling (CA3)

`GET /mediciones` acepta `max_puntos` (default 2000, `MEDICIONES_MAX_PUNTOS`). Si el
rango supera 30 días (`MEDICIONES_DIAS_RANGO_AMPLIO`) y hay más puntos que el máximo,
se aplica **muestreo uniforme** (cada n-ésimo punto, conservando primero y último) y
la respuesta lo declara con `downsampling: true` y `total_sin_muestrear`.

Uniforme y no LTTB: es O(n), **determinista** —importa porque la respuesta se
cachea— y el repo no tiene hoy ninguna implementación de LTTB que reutilizar. La
limitación asumida está anotada en el módulo: el muestreo puede saltarse un pico
aislado, aceptable para una vista de tendencia; el dato exacto sigue en la BD y
aparece al acotar el rango.

Un rango **abierto** (sin `fecha_inicio` o sin `fecha_fin`) cuenta como amplio: pide
toda la historia disponible, que es el caso más pesado de todos.

### Bug encontrado y corregido: el filtro de fechas de HU12 no llegaba a la consulta

`GET /mediciones` recibía `fecha_inicio`/`fecha_fin` y los documentaba, pero **no los
aplicaba a la query**: traía todas las filas de las ubicaciones permitidas, las
ordenaba en Python y recién ahí paginaba. Es justo el pendiente que HT-08 dejó
anotado más arriba. Ahora el rango, el orden y el filtro van en SQL, que es lo que
permite el partition pruning:

```
Bitmap Heap Scan on tlmtr_2026_08
  Recheck Cond: ((id_sd = 12) AND (fch_hr >= ...) AND (fch_hr <= ...))
  ->  Bitmap Index Scan on tlmtr_2026_08_id_sd_fch_hr_idx
Execution Time: 0.177 ms
```

**1 de 17 particiones tocadas**, resuelto por el índice `(id_sd, fch_hr)` que ya
existía de HT-08. No se creó ningún índice nuevo.

### Medición de tiempo de respuesta (CA1 / CA5)

```bash
docker compose up -d db redis
python -m app.scripts.medir_cache_ht10
python -m app.scripts.medir_cache_ht10 --meses 6 --minutos 15 --repeticiones 30
```

Corrida del 2026-08-28 — dataset sintético de **51.843 filas en 3 sedes** (17.281 en
la sede medida), 1 lectura cada 15 min durante ~6 meses, 20 repeticiones por
consulta. `ANTES` = cada petición golpea Postgres; `DESPUES` = la capa real de HT-10
(primera repetición MISS, resto HIT):

| Consulta | Filas | ANTES p95 | DESPUES p95 | HIT medio | Mejora |
|---|---:|---:|---:|---:|---:|
| Gráfico 1 día | 96 | 1,3 ms | 0,7 ms | 0,47 ms | 3x |
| **Gráfico 7 días (CA1)** | **672** | **1,7 ms** | **1,0 ms** | **0,75 ms** | **2x** |
| Gráfico 30 días | 2.880 | 5,5 ms | 2,3 ms | 1,91 ms | 3x |
| Gráfico 90 días | 8.640 | 34,8 ms | 6,1 ms | 5,06 ms | 7x |

**CA1 cumplido con margen**: los rangos de hasta 7 días quedan en **1,0 ms p95**,
tres órdenes de magnitud por debajo del objetivo de 1 s. La mejora relativa crece con
el tamaño del rango, que es lo esperable: la caché ahorra más cuanto más pesada es la
consulta que evita.

> **Esta medición es LOCAL, no de staging.** Corre contra `docker compose`
> (Postgres y Redis en `localhost`) sobre datos sintéticos. Sirve para comparar el
> antes y el después en igualdad de condiciones, **no** para predecir la latencia real
> en Lightsail, donde la BD es managed, la red no es localhost y hay otros procesos
> compitiendo. No hubo entorno de staging disponible para validar el CA tal como está
> redactado.

#### Detalle encontrado al medir: una conexión a Redis por operación anulaba la caché

La primera versión abría y cerraba la conexión en cada `get`, igual que hace
`publicar_lectura()` en `services/mapa/eventos.py`. Medido: **16,5 ms** por operación
contra **0,35 ms** reutilizando el pool (~47x), es decir mucho más de lo que tarda la
consulta a Postgres que la caché pretende evitar — la caché era **más lenta** que no
tenerla (los 7 días daban 23,3 ms p95 *con* caché contra 1,7 ms sin ella).

Ahora se reutiliza un cliente por proceso, invalidado si cambia el PID para que el
prefork de Celery y los workers de uvicorn no compartan un socket heredado. El patrón
de `eventos.py` se deja como está: ahí se publica un puñado de veces por archivo
`.dat`, dentro de un job que ya tardó segundos en FTP, no en el camino crítico de cada
petición HTTP.

### Degradación si Redis se cae

Ninguna función de la caché lanza hacia el llamador: leer devuelve `None` (miss) y
escribir no hace nada, así que los endpoints responden igual consultando Postgres,
solo más lento. Los sockets llevan `socket_timeout=2s` para que un Redis colgado no
bloquee una petición. Los tests que requieren Redis se saltan solos si no está
levantado.
