# Cómo contribuir a Pangea

Convenciones de código, ramas, commits y Pull Requests. Lo marcado como
**propuesta** todavía no es una regla del equipo: está en el registro de
dudas de [`docs/traspaso-conocimiento.md`](docs/traspaso-conocimiento.md)
para que el Scrum Master lo confirme.

## Idioma

Todo en español: nombres de dominio, comentarios, mensajes de error de la
API, textos de la interfaz, commits y Pull Requests. Las palabras propias
del lenguaje o del framework (`router`, `session`, `useEffect`) se dejan
como están.

## Ramas

| Rama | Para qué |
|---|---|
| `main` | Lo que está en producción |
| `dev` | Integración: aquí se junta el trabajo terminado antes de pasar a `main` |
| `feature/PP-xxx-descripcion-corta` | Una HU o HT del backlog (ej. `feature/PP-47-modelo-comercial`) |
| `fix/PP-xxx-descripcion-corta` | Corrección de un defecto |
| `jareth`, `fabio`, `qa-elliot` | Ramas personales que ya existen; no crear nuevas de este tipo |

Flujo:

1. Antes de empezar, trae lo último: `git fetch --all --prune`.
2. Crea tu rama desde `origin/dev`:
   `git switch -c feature/PP-xxx-descripcion origin/dev`.
3. Al subirla por primera vez, dale su propio nombre en el remoto (si no,
   Git la asociaría a `dev`):
   `git push -u origin feature/PP-xxx-descripcion`.
4. Abre el Pull Request hacia `dev`, aunque lo fusiones tú mismo: así
   queda registro de qué entró, cuándo y de qué subtarea. Si quieres una
   revisión, asigna a otra persona del equipo.
5. `dev` pasa a `main` en un merge aparte («Merge dev into main: ...»),
   cuando se va a desplegar. Lo hace el Scrum Master (Jareth), porque lleva
   todo lo que haya en `dev`, también el trabajo de otras personas.

**Propuesta:** el CI hoy solo corre para `jareth` y `main`. Los Pull
Requests hacia `dev` no pasan por lint ni por tests; conviene agregar `dev`
a los disparadores de `.github/workflows/ci.yml`.

Las ramas `claude/...` son de sesiones de asistentes de IA y no se usan como
base.

## Commits

Formato, como en los últimos commits de `dev` y `qa-elliot`:

```
PP-xxx tipo(ámbito): descripción corta en minúsculas y en presente
```

- `PP-xxx`: la clave de Jira de la subtarea. Si el trabajo es de una HU/HT,
  se puede mencionar al final: `(HU33 HT-17)`.
- `tipo`: `feat` (funcionalidad nueva), `fix` (corrección), `test`, `docs`,
  `refactor`, `chore` (mantenimiento o configuración), `ci`.
- `ámbito` (opcional): el módulo, por ejemplo `ingesta`, `paneles`, `qa`.

Ejemplos:

```
PP-360 docs(readme): estructura actual y pasos de ejecución
PP-403 test(qa): reprueba de DEF-02, DEF-03 y DEF-04 en HT-30.2
fix: detener polling FTP de dispositivos inactivos (DEF-04)
```

Evitar mensajes como `a`, `abc` o `arrego`: no dicen qué cambió y hacen
imposible buscar en el historial. Un commit = un cambio con sentido propio.

## Pull Requests

- Título con el mismo formato que los commits.
- En la descripción: qué HU/HT o defecto cubre, qué cambió, cómo se probó
  (comandos y resultado) y qué criterios de aceptación cumple.
- Antes de abrirlo, corre en local lo mismo que el CI (ver abajo). Si algo
  ya fallaba antes de tu cambio, dilo en la descripción.
- Si agregas una migración, dilo: quien lo pruebe tiene que correr
  `alembic upgrade head`.
- No subir `.env`, `containers.json`, credenciales, datos reales de clientes
  ni archivos generados (`dist/`, `venv/`, `__pycache__/`).

## Antes de subir: lo mismo que revisa el CI

Desde `backend/`:

```bash
python -m ruff check .
python -m black --check .        # para corregir: python -m black .
python -m pytest
```

Desde `frontend/`:

```bash
npm run lint
npm run test:series
npm run build
```

## Backend (Python)

- **Formato:** black y ruff, con línea de 100 caracteres
  (`backend/pyproject.toml`). Ruff revisa errores, imports ordenados y
  espacios (`E`, `F`, `I`, `W`).
- **Nombres en el código:** clases en PascalCase y en español completo
  (`PermisoUsuarioSede`, `ArchivoIngesta`); funciones y variables en
  snake_case (`vencer_sin_cobro`, `sondear_conexiones_ftp`).
- **Nombres en la base de datos:** tablas y columnas en español
  **abreviado, sin vocales**, en snake_case: `tlmtr` (telemetría),
  `prms_usr_sd` (permisos usuario-sede), `cnxn_ftp`, `nmbr`, `dscrpcn`. La
  clave primaria es `id_<tabla>` (`id_pln`). Hay columnas recientes con
  palabras completas (`moneda`, `revision`); **propuesta:** que las nuevas
  sigan la forma abreviada.
- **Dónde va cada cosa:**
  - `routers/`: solo HTTP (validar entrada, permisos y respuesta). Cada
    endpoint protegido usa `Depends(require_permiso("Modulo", LECTURA))` o
    `EDICION` (`security/permisos.py`).
  - `services/`: la lógica de negocio, sin depender de FastAPI.
  - `tasks/`: tareas de Celery; llaman a `services/`.
  - `models/`: tablas; un modelo nuevo se importa en `models/__init__.py`.
  - `security/`: autenticación, permisos, cifrado y auditoría.
- **Migraciones:** cada cambio de tablas va en una migración de Alembic
  (`alembic revision -m "descripcion"`; con `--autogenerate` revisa el
  resultado a mano). Nunca editar una migración que ya está en `dev`. Si
  dos ramas crean migraciones a la vez, se resuelve con una migración de
  merge (`alembic merge`), como `f416e1d0ec14_merge_dev_hu02_con_ht_08`.
- **Tests:** en `backend/tests/` con la misma estructura que `app/`
  (`routers/`, `services/`, `tasks/`). Usan Postgres real y la fixture
  `db_session`, que revierte todo al final. Los archivos `.dat` de ejemplo
  van en `tests/fixtures/`.
- **Comentarios:** explican el porqué (la HU, el criterio o el incidente),
  no lo que ya dice el código. Es la costumbre del repo: por ejemplo,
  `core/celery_app.py` explica por qué la concurrencia es 4.
- **Secretos:** solo por variables de entorno. Una variable nueva va
  también en `.env.example` (sin valor real) y en la tabla del `README.md`.

## Frontend (React + TypeScript)

- **Formato:** ESLint (`frontend/eslint.config.js`) con las reglas de hooks
  de React.
- **Archivos:** componentes y páginas en PascalCase (`Usuarios.tsx`); en
  Linux, un error de mayúsculas rompe el build. Utilidades en camelCase
  (`graficosUtils.ts`).
- **Pantallas:** una por archivo en `pages/`; su ruta y sus roles en
  `router/AppRouter.tsx` con `ProtectedRoute`.
- **Llamadas a la API:** siempre con `services/api.ts`, nunca con `fetch`
  suelto (perdería la cookie de sesión).
- **Textos:** la interfaz dice «proyecto» donde la API dice «ubicación»;
  usar `config/terminologia.ts`.
- **Lógica sin interfaz:** en un `.ts` aparte con su test en
  `frontend/tests/`.

## Documentación

- Una decisión técnica de una HU/HT va en `backend/README.md` (o en
  `backend/docs/` si es larga), con el criterio de aceptación que cubre.
- Un módulo nuevo o una dependencia nueva entre módulos va en
  [`docs/guia-modulos.md`](docs/guia-modulos.md).
- Un paso nuevo para levantar el proyecto va en el `README.md`.
