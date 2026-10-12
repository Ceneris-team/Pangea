# HT-16: rendimiento de consultas filtradas (HU32 + HU36)

**Estado: HU32 y HU36 verificadas y optimizadas. HU40/HU41 no existen
todavía (Sprint 6) y quedan fuera de esta medición** — ver "Pendiente:
HU40/HU41" al final.

Depende de HT-08 (particionamiento de `tlmtr`, ya implementado).

## Cómo se generó el dataset de medición

5 clientes activos, 1 sede cada uno, 3 ubicaciones por sede, 2
dispositivos por ubicación, 4 parámetros numéricos por dispositivo, una
lectura cada 15 minutos (la cadencia real de un datalogger, ver
`frcnc_mnts`) durante 6 meses: **30 dispositivos, ~2.1 millones de filas
en `tlmtr`**.

Es el orden de magnitud que un despliegue con 5 clientes activos y un par
de dataloggers cada uno acumula en medio año — suficiente para que un
`OFFSET` o un escaneo completo se note en `EXPLAIN ANALYZE` si el índice
no se usa, y para que el partition pruning de HT-08 (particiones
mensuales) tenga varios meses reales entre los que descartar.

Reproducible con:

```bash
python -m app.scripts.medir_rendimiento_ht16
# o, sobre un dataset ya sembrado en una corrida anterior:
python -m app.scripts.medir_rendimiento_ht16 --sin-poblar
```

El script (`app/scripts/medir_rendimiento_ht16.py`, mismo patrón que
`medir_pruning_ht08.py` y `medir_cache_ht10.py`) siembra los datos bajo
clientes con el prefijo `HT16-Bench-Cliente-` (idempotente: limpia la
corrida anterior antes de sembrar) y mide contra el **endpoint HTTP
real** (`TestClient`, no un `SELECT` suelto), así que el número incluye
resolución de permisos, serialización Pydantic y el merge en Python de
`Telemetria` + `EventoTexto`, no solo el tiempo de Postgres.

El script Python es la versión reproducible para repetir la medición de
forma manual o en CI (ver "Benchmark automatizado" más abajo).

## CA1 + CA5: resultado (benchmark automatizado, p95)

Corrida de referencia (`--repeticiones 15`, sobre el dataset de arriba):

| Consulta                                                        | p95 (ms) | media (ms) |
|-------------------------------------------------------------------|---------:|-----------:|
| HU32 `GET /mediciones` (valor_min/max, 7 días, modo cursor)       |      6.8 |       14.6 |
| HU32 `GET /mediciones` (misma consulta, página 2 por cursor)      |      6.3 |       10.9 |
| HU32 `GET /mediciones` (frecuencia_muestreo=60, 7 días)           |      6.7 |       35.9 |
| HU36 `GET /dispositivos` (marca+estado, offset/limit)             |      9.6 |        8.7 |
| HU36 `GET /dispositivos` (misma consulta, página 3, offset)       |      6.1 |        5.5 |

**Peor p95: 9.6ms, muy por debajo del umbral de 1000ms de CA1.** Los
números son de Postgres/Redis locales (docker compose), no de Lightsail
-mismo criterio de honestidad que ya usa el README para la medición de
HT-10-: sirven para comparar antes/después en igualdad de condiciones,
no para predecir la latencia exacta en producción.

## Punto 1: qué se encontró con EXPLAIN ANALYZE (antes de tocar código)

### HU36 (`dispositivos.py`): la tabla es chica, offset ya alcanza

Con el dataset completo (41 dispositivos entre el benchmark y los datos
de desarrollo ya existentes), `EXPLAIN ANALYZE` sobre la consulta real de
`listar_dispositivos` (con `marca` + `OFFSET` alto) da:

```
Limit (actual time=0.075..0.077 rows=10 loops=1)
  ->  Sort (actual time=0.073..0.075 rows=40 loops=1)
        ->  Hash Join (actual time=0.016..0.024 rows=41 loops=1)
              ->  Seq Scan on dspstv d (actual time=0.003..0.007 rows=41 loops=1)
              ->  Seq Scan on ubccn u (actual time=0.001..0.003 rows=22 loops=1)
Execution Time: 0.121 ms
```

`Dispositivo` es, para 5 clientes activos, una tabla de decenas de filas
-el volumen que crece es `tlmtr`, no `dspstv`-. Un `Seq Scan` completo
sobre 41 filas tarda 0.12ms; con `OFFSET` en cualquier página, sigue
siendo un `Seq Scan` trivial porque toda la tabla entra en una sola
página de memoria. **Decisión: no se crea índice ni se migra a cursor
para HU36.** Ver "Índices NO creados" más abajo.

### HU32 (`mediciones.py`): el problema real no era el índice, era el volumen sin LIMIT

La query original (`_query_base(Telemetria).all()`, JOIN con
`Dispositivo`/`Ubicacion`/`Parametro` antes del `ORDER BY`, filtros
`valor_min`/`valor_max`, rango de 30 días) tarda **153ms** y trae **todo
el resultado filtrado a Python** (decenas de miles de filas), sin
importar qué página se pida -ese es el bug real que motivó esta HT, más
grave que "`OFFSET` es lento"-:

```
Limit ... Sort (Sort Method: external merge, Disk: 11920kB) actual time=104..110
  ->  Hash Join (Hash Cond: t.id_prmtr = p.id_prmtr)
        ->  Hash Join (Hash Cond: d.id_ubccn = u.id_ubccn)
              ->  Hash Join (Hash Cond: t.id_dspstv = d.id_dspstv)
                    ->  Parallel Append (Subplans Removed: 15)
                          ->  Parallel Seq Scan on tlmtr_2026_08 ... Filter: vlr/fch_hr
                          ->  Parallel Seq Scan on tlmtr_2026_09 ... Filter: vlr/fch_hr
Execution Time: 153.393 ms
```

Puntos clave de este plan:

- **El partition pruning de HT-08 SÍ funciona** (`Subplans Removed: 15`
  de 17 particiones): eso no era el problema.
- **Ningún índice existente se usa sobre `vlr`**: con `enable_seqscan =
  off` forzado, el único índice disponible (`idx_tlmtr_fchhr_brin`) da un
  `Bitmap Heap Scan` "lossy" que tarda MÁS (169ms) que el propio `Seq
  Scan` paralelo -el planner elige bien sin forzarlo-. No hay índice
  selectivo posible sobre un rango numérico abierto (`vlr >= X AND vlr <=
  Y`) combinado con un rango de fechas amplio: la fracción de filas que
  matchea sigue siendo demasiado grande para que un índice B-tree gane al
  escaneo secuencial de la partición. **Esto descarta "crear un índice
  sobre `vlr`" como solución** -ver "Índices NO creados"-.
- Agregar solo `LIMIT` al `ORDER BY` sin cambiar nada más **no ayuda**
  (116ms, prácticamente igual): con el `JOIN` completo por delante,
  Postgres no puede aplicar un plan de tipo top-N heapsort porque el
  `Hash Join` no preserva el orden de `fch_hr`. Tiene que materializar y
  ordenar la unión completa antes de poder cortar.

**La solución real fue reestructurar la consulta, no agregar un índice**:

1. El filtro de ubicación/dispositivo se resuelve como `id_dspstv IN
   (subquery)` en vez de `JOIN` contra `Dispositivo`/`Ubicacion` -evita
   arrastrar esas tablas por delante del corte-.
2. `Ubicacion`/`Parametro`/`Dispositivo` se resuelven DESPUÉS del
   `LIMIT`, sobre el conjunto ya acotado de la página (`_enriquecer_items`
   en `mediciones.py`): 2-3 `SELECT ... WHERE id IN (<=cientos de ids)`
   contra la PK de cada tabla, en vez de un `JOIN` sobre potencialmente
   cientos de miles de filas.
3. Cursor keyset (ver CA3 más abajo) en vez de `OFFSET`, con `LIMIT`
   real en SQL.

Con esos tres cambios, la misma consulta (7 días, `valor_min`/`valor_max`,
primera página) pasa a **28ms**, y la página siguiente por cursor a
**~22-23ms, estable** (ver CA3):

```
Limit ... Sort Method: top-N heapsort  Memory: 32kB   actual time=22.700..22.703
  ->  Hash Join (Hash Cond: t.id_dspstv = dspstv.id_dspstv)
        ->  Parallel Append (Subplans Removed: 16)
              ->  Parallel Seq Scan on tlmtr_2026_09 ... Filter: vlr/fch_hr
Execution Time: 28.168 ms
```

## CA2: los índices ya existentes SÍ se usan cuando corresponde

`idx_tlmtr_sd` (`id_sd, fch_hr`) y el BRIN sobre `fch_hr` (`
idx_tlmtr_fchhr_brin`) ya estaban implementados por HT-08/HT-10 y se
verificaron sin tocarlos. El plan reescrito de arriba los deja fuera
porque el filtro de partition pruning (`fch_hr >= ... AND fch_hr <=
...`) ya resuelve la selección de partición sin necesitar el índice BRIN
-el `Seq Scan` paralelo sobre la partición ya acotada es más barato que
un `Bitmap Heap Scan` "lossy" sobre esa misma partición, como muestra la
comparación con `enable_seqscan = off` de arriba-. Esto es correcto: un
índice que el planner decide NO usar porque el escaneo secuencial ya es
más barato no es un índice "roto", es el planner haciendo su trabajo.

`idx_tlmtr_dspstv_prmtr` (`id_dspstv, id_prmtr, fch_hr`) es el que
resuelve la consulta cuando se filtra por `dispositivo_ids`/`parametro_ids`
específicos con un rango de fechas angosto (no medido en detalle acá
porque no es el caso que HT-16 identificó como problemático: ver el
punto 1 de la HT, "confirmar qué índices ya se usan y cuáles faltan").

## CA3: paginación por cursor (HU32) — y por qué HU36 la NO necesita

### HU32: cursor keyset sobre `(fch_hr, origen, id_registro)`

`GET /mediciones` ahora acepta `cursor` (opaco, base64) en vez de pedir
`pagina=N`, **solo quando el rango pedido no es amplio y no hay
`frecuencia_muestreo` activo** (ver "Por qué el cursor no es universal"
más abajo). El orden total es `(fch_hr DESC, origen DESC, id DESC)`:

- `origen` (`"t"` Telemetria / `"e"` EventoTexto) desempata entre las dos
  tablas que se fusionan en Python -pueden compartir el mismo `fch_hr`
  exacto-.
- `id_lctr`/`id_evnt` desempata dentro de la misma tabla y el mismo
  `fch_hr` -real en telemetría de alta frecuencia, donde más de un
  dispositivo/parámetro puede compartir timestamp-.

Ese orden total es lo que hace al cursor **estable ante una inserción
concurrente**: una fila nueva se inserta en su posición según esa clave,
nunca antes del cursor ya entregado, así que la página siguiente nunca
repite ni salta una fila ya servida -a diferencia de `OFFSET`, que se
corre si algo se inserta/borra antes de la página pedida-. Cubierto por
`TestHT16PaginacionPorCursor.test_cursor_estable_ante_insercion_concurrente_entre_paginas`
en `tests/routers/test_mediciones.py`.

`total` en modo cursor es un `COUNT(*)` real en SQL (barato, usa los
mismos índices/pruning que la consulta principal), no `len(items)` sobre
todo el resultado traído a Python -ese último es justo el patrón que
esta HT vino a eliminar-.

**Cambio de contrato**: `GET /mediciones?cursor=<valor>` reemplaza
`?pagina=N` para pedir la página siguiente, cuando el modo cursor está
activo. Se decidió **no** tocar el frontend (`ConsultaDatos.tsx`,
`Graficos.tsx`): ninguno de los dos pide hoy una "página 2" de este
endpoint -ver "Por qué no se tocó el frontend" más abajo-, así que el
cambio de contrato no tiene, hoy, ningún consumidor que romper.
`pagina`/`por_pagina` se conservan en la respuesta y siguen funcionando
igual que antes para el caso no-cursor.

### Por qué el cursor no es universal (rango amplio / frecuencia_muestreo)

El downsampling de HT-10 (`services/cache/downsampling.py`, usado por
`Graficos.tsx`/HU15 cuando el rango supera 30 días) necesita conocer el
**conjunto completo y ya ordenado** para poder tomar 1 de cada N puntos
de forma determinista (`muestrear()`). Cortar ese conjunto con `LIMIT`
antes de muestrear rompería el criterio "conserva la forma de la serie
completa" -literalmente le impediría ver la mayoría de los puntos que
tiene que promediar/saltear-. Por eso el modo cursor solo se activa
cuando `rango_es_amplio()` es `False` (mismo umbral de 30 días que ya
usa HT-10) y no hay `frecuencia_muestreo` (ese camino usa `DISTINCT ON` +
`date_bin`, que no tiene una columna de desempate estable para keyset).
Fuera de esas condiciones, el endpoint sigue con el contrato
`pagina`/`por_pagina` de siempre.

### Por qué HU36 (`dispositivos.py`) no migró a cursor

Ver CA1 arriba: con offset/limit, cualquier página de `GET /dispositivos`
tarda <10ms sobre el dataset de 5 clientes -la tabla es demasiado chica
para que la posición del cursor/offset importe-. Migrar a cursor ahí
habría sido: (a) un cambio de contrato de API sin beneficio medible, (b)
un cambio en `Dispositivos.tsx` (que si usa paginación visible con
"Anterior"/"Siguiente" por número de página) sin ninguna ganancia de
rendimiento que lo justifique. Se verificó primero con `EXPLAIN ANALYZE`
antes de decidir, no se asumió.

### Por qué no se tocó el frontend

Se revisó `ConsultaDatos.tsx` (HU12/HU13/HU32) y `Graficos.tsx` (HU15):
ninguno de los dos pide una "página siguiente" de `GET /mediciones` hoy.
`ConsultaDatos.tsx` no tiene paginación visible -llama al endpoint sin
`pagina`/`cursor` y muestra `items` completo (acotado por el `por_pagina`
default y, en rango amplio, por `max_puntos`)-. `Graficos.tsx` solo
compara `total` contra `items.length` para mostrar un aviso de "resultado
truncado", sin pedir más páginas. El cambio de contrato de HU32 es, por
lo tanto, de bajo riesgo: no rompe nada que exista hoy, y deja el cursor
listo para cuando un frontend futuro (o HU40/HU41) lo necesite.

## Punto 4: JOIN entre telemetría particionada y tablas relacionales, con `frecuencia_muestreo` activo

Se verificó que el `date_bin` + `DISTINCT ON` de `frecuencia_muestreo`
(agregado recientemente para HU32) no rompe el partition pruning: la
query de esa rama sigue filtrando por `fch_hr` en SQL antes de aplicar
`DISTINCT ON`, así que Postgres sigue descartando particiones fuera de
rango de la misma forma que sin `frecuencia_muestreo`. Confirmado con el
benchmark automatizado (`HU32 ... frecuencia_muestreo=60, 7 días`: p95
6.7ms) y con `EXPLAIN ANALYZE` manual sobre el dataset de 2.1M filas: el
plan sigue mostrando `Subplans Removed` para las particiones fuera del
rango de 7 días, igual que sin el filtro.

## Índices NO creados (y por qué)

- **`Dispositivo.mrc` / `Dispositivo.estd` (HU36)**: no se crean. Ver CA1
  arriba -`EXPLAIN ANALYZE` muestra `Seq Scan` de <1ms sobre 41 filas-.
  Un índice sobre una tabla de esta escala es puro costo de escritura
  (cada `crear_dispositivo`/`actualizar_dispositivo` paga el mantenimiento
  del índice) sin ningún beneficio de lectura medible. Si el número de
  dispositivos por cliente creciera en órdenes de magnitud en el futuro
  (miles, no decenas), esta decisión debería revisarse con un `EXPLAIN
  ANALYZE` nuevo -no se anticipa ahora sin ese dato-.
- **Índice GIN sobre `Dispositivo.nmbr`/`mrc` (búsqueda de texto libre,
  HU10)**: no se crea, mismo motivo -`EXPLAIN ANALYZE` sobre el filtro
  `lower(nmbr) LIKE '%...%' OR lower(mrc) LIKE '%...%'` tarda 1.3ms sobre
  la tabla completa-. El índice compuesto que ya existe
  (`idx_dspstv_ubccn`) no participa en esta búsqueda porque no es
  prefijo-friendly para `LIKE '%...%'`, pero tampoco hace falta: la tabla
  es demasiado chica para que un GIN aporte algo a esta escala.
- **Índice sobre `Telemetria.vlr`** (para acelerar `valor_min`/`valor_max`
  directamente): no se crea. Ver el punto 1 -un B-tree sobre un rango
  numérico abierto, combinado con un rango de fechas ya amplio, no reduce
  la fracción de filas lo suficiente como para ganarle al escaneo
  secuencial de la partición; se verificó con `enable_seqscan = off`-.
  El problema real no era la falta de índice sino la falta de `LIMIT`
  real antes del corte (ver el punto 1), que es lo que se corrigió.

## Benchmark automatizado (CA1, tests)

`app/scripts/medir_rendimiento_ht16.py` es el benchmark reproducible:
siembra el dataset de 5 clientes, mide p95 contra el endpoint HTTP real y
falla visualmente (imprime "ADVERTENCIA" y dejaría un exit distinto de
éxito si se quisiera engancharlo a CI) si el peor p95 supera 1000ms.

**Decisión: manual, no en CI.** Sembrar ~2.1M filas y correr 20+
repeticiones por consulta tarda ~30-60s -aceptable para una corrida
manual antes de un release o al tocar `mediciones.py`/`dispositivos.py`,
pero demasiado para correr en cada PR-. Mismo criterio que
`medir_cache_ht10.py`/`medir_pruning_ht08.py`, que tampoco están
enganchados a CI. Las pruebas FUNCIONALES del cursor (página siguiente,
dataset vacío, cursor inválido, estabilidad ante inserción concurrente)
sí están en la suite normal de pytest
(`TestHT16PaginacionPorCursor` en `tests/routers/test_mediciones.py`) y
corren en cada PR -son rápidas porque no dependen del volumen de datos,
solo de la lógica del cursor-.

## Pendiente: HU40/HU41

CA1 ("HU32/HU36/HU40/HU41 responden en <1s p95"), CA3 (cursor) y CA4
(JOIN sin escaneo completo) de la HT-16 completa mencionan las cuatro
HU, pero HU40 y HU41 no existen todavía (Sprint 6). Esta medición cubre
**solo HU32 y HU36**: quedan **verificados parcialmente**, no cumplidos
del todo, hasta que HU40/HU41 existan y se pueda repetir esta misma
medición sobre sus consultas reales. El patrón para hacerlo, cuando
llegue el momento, es este documento + `medir_rendimiento_ht16.py` como
punto de partida.
