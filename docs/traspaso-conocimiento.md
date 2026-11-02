# Traspaso de conocimiento

Guía para la sesión de traspaso de Pangea 4.0 (PP-363, HT-25) y registro de
las dudas que surjan y de cómo se resolvieron. Los documentos base son el
[`README.md`](../README.md), [`CONTRIBUTING.md`](../CONTRIBUTING.md) y la
[guía de módulos](guia-modulos.md).

## 1. Datos de la sesión

| Campo | Valor |
|---|---|
| Fecha y hora | _(por definir)_ |
| Modalidad | _(presencial / Meet / Teams)_ |
| Expone | _(por definir)_ |
| Participan | _(por definir)_ |
| Grabación | _(enlace, si se graba)_ |

## 2. Antes de la sesión

Cada participante:

- [ ] Tiene acceso al repo `Ceneris-team/Pangea` (permiso de escritura) y al tablero PP de Jira.
- [ ] Leyó el `README.md`, el `CONTRIBUTING.md` y la guía de módulos.
- [ ] Levantó el entorno local siguiendo el `README.md`: Postgres y Redis
      con Docker, `alembic upgrade head`, API en http://127.0.0.1:8000/docs y
      frontend en http://localhost:5173.
- [ ] Inició sesión con un usuario de prueba del seed.
- [ ] Anotó en la [sección 5](#5-registro-de-dudas) lo que no le funcionó o no entendió.

## 3. Agenda (unas 2 horas)

| # | Tema | Tiempo | Material |
|---|---|---|---|
| 1 | Qué es Pangea, roles y flujo de negocio (cliente, proyecto, datalogger, plan) | 15 min | `README.md`, `frontend/src/config/roles.ts` |
| 2 | Arquitectura: API, worker, beat, Redis, Postgres y AWS | 15 min | Guía de módulos, sección 1; SAD en el OneDrive (Arquitectura) |
| 3 | Recorrido por la ingesta: de un `.dat` a la pantalla | 25 min | Guía de módulos, sección 2; `backend/app/tasks/ingesta.py` |
| 4 | Seguridad: sesión con cookie, permisos por módulo y por empresa, auditoría | 15 min | `backend/app/security/` |
| 5 | Frontend: rutas, roles, `api.ts` y una pantalla de punta a punta | 15 min | `frontend/README.md` |
| 6 | Forma de trabajo: ramas, commits, PR, CI y migraciones | 10 min | `CONTRIBUTING.md` |
| 7 | Producción y deploy | 10 min | `README.md` (Producción) |
| 8 | Dudas abiertas (sección 5) y cierre | 15 min | Este documento |

## 4. Ejercicios prácticos

Para comprobar que el traspaso funcionó, cada participante hace al menos
uno, en su rama y sin subirlo a `dev`:

1. **Ingesta de punta a punta:** correr
   `python -m pytest tests/services/test_pipeline_ingesta_manual.py -v` y
   seguir en el código cada paso (parser, mapeo, estandarizador, validador,
   persistencia) con la guía de módulos al lado.
2. **Seguir una petición:** abrir «Gráficos», ubicar en la pestaña Red del
   navegador la llamada a `/mediciones`, y encontrar en el backend el
   router, el permiso que exige y dónde se cachea.
3. **Test nuevo:** agregar un caso a `backend/tests/services/test_validador.py`
   y correr `python -m pytest tests/services/test_validador.py`.
4. **Rama y PR de prueba:** crear `feature/PP-xxx-prueba` desde `origin/dev`
   con un commit en el formato de `CONTRIBUTING.md` (sin abrir el PR).

## 5. Registro de dudas

Estado: **Abierta**, **Resuelta** o **Descartada**. Al resolver una duda,
anotar la respuesta, quién respondió y la fecha; si la respuesta cambia una
regla, actualizar también el documento correspondiente.

Las dudas D-01 a D-12 salieron al revisar el repositorio para HT-25 (rama
`dev`, commit `f9c0967`, 02/11/2026).

| ID | Tema | Duda | Estado | Respuesta | Respondió | Fecha |
|---|---|---|---|---|---|---|
| D-01 | CI | El CI solo corre en push y PR hacia `jareth` y `main`. Los PR hacia `dev`, que hoy es la rama de integración, no pasan por lint ni tests. ¿Se agrega `dev` a `.github/workflows/ci.yml`? | Abierta | | | |
| D-02 | CI | El lint no pasa en `dev`: en local (02/11) ruff da 5 errores y black reformatearía 55 archivos. ¿Se corrige en una tarea aparte con `ruff check --fix` y `black .`? | Abierta | | | |
| D-03 | Ramas | ¿El flujo oficial es `feature/PP-xxx` → `dev` → `main`? En el historial, cada desarrollador sube a `dev` (directo o con PR) y solo Jareth pasa `dev` a `main`. ¿Se deja así como regla? ¿Siguen usándose las ramas personales (`jareth`, `fabio`)? | Abierta | | | |
| D-04 | Commits | ¿Se adopta el formato `PP-xxx tipo(ámbito): descripción` propuesto en `CONTRIBUTING.md`? | Abierta | | | |
| D-05 | Deploy | No están documentados los pasos del deploy: construir y subir las imágenes a Lightsail, aplicar migraciones en la RDS, publicar el frontend en S3 e invalidar CloudFront. ¿Quién los documenta? | Abierta | | | |
| D-06 | Deploy | `containers.example.json` no tiene un worker para la cola `exportaciones`. Como `generar_exportacion` va a esa cola, en producción las exportaciones (HT-17) no se procesarían. ¿Ya se agregó en el `containers.json` real? | Abierta | | | |
| D-07 | Deploy | `containers.example.json` menciona `docs/incidentes`, que no existe en el repo. ¿Dónde están esos incidentes? | Abierta | | | |
| D-08 | Configuración | `.env.example` traía `JWT_SECRET_KEY` y el puerto 5432, pero el código lee `JWT_SECRET` y Docker publica Postgres en el 5433. Se corrigió en esta HT. ¿Producción define `JWT_SECRET`? (riesgo R-02 del SAD) | Abierta | | | |
| D-09 | Configuración | El perfil `full` de `docker-compose.yml` usa el usuario `pangea`, que no existe en el contenedor `db`. ¿Se corrige el compose o se quita el perfil? | Abierta | | | |
| D-10 | Tests | Con `PLAN_LIMITS_REQUIRE_SUBSCRIPTION=true` (valor por defecto) fallaban 96 tests en local (19/10, rama `jareth`). ¿Qué valor deben usar los tests y el CI? | Abierta | | | |
| D-11 | Base de datos | Algunas columnas nuevas usan palabras completas (`moneda`, `revision`) y no la forma abreviada sin vocales. ¿Cuál es la regla para las nuevas? | Abierta | | | |
| D-12 | Producto | Los umbrales del semáforo del mapa (`services/mapa/semaforo.py`) son provisionales «hasta HU28». ¿HU28 sigue en el backlog? | Abierta | | | |
| | | | | | | |

## 6. Cierre

| Campo | Valor |
|---|---|
| Asistentes | |
| Temas cubiertos | |
| Ejercicios hechos | |
| Dudas resueltas / abiertas | |
| Próximos pasos | |
