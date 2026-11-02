# Pangea 4.0

Plataforma de monitoreo ambiental de CENERIS. Recibe por FTP los archivos
`.dat` de los dataloggers, los valida y los guarda como telemetría, y los
muestra en mapas, gráficos, paneles personalizables y exportaciones.

| Capa | Tecnología |
|---|---|
| API | FastAPI, SQLAlchemy, Alembic, Python 3.12 |
| Tareas en segundo plano | Celery (worker y beat) con Redis 7 |
| Base de datos | PostgreSQL 16 (`tlmtr` particionada por mes) |
| Frontend | React 19, Vite, TypeScript, Tailwind CSS 3 |
| Producción | AWS: Lightsail Container Service, RDS, S3 y CloudFront |

Más documentación:

- [`CONTRIBUTING.md`](CONTRIBUTING.md): convenciones de código, ramas, commits y Pull Requests.
- [`docs/guia-modulos.md`](docs/guia-modulos.md): qué hace cada módulo y de qué depende.
- [`docs/traspaso-conocimiento.md`](docs/traspaso-conocimiento.md): guía del traspaso y registro de dudas resueltas.
- [`backend/README.md`](backend/README.md): decisiones técnicas por HU/HT (ingesta, particiones, caché, auditoría).
- [`frontend/README.md`](frontend/README.md): detalles del frontend.

## Estructura del proyecto

```
Pangea/
├── .github/workflows/ci.yml   # CI: ruff + black, pytest y build de la imagen
├── backend/
│   ├── app/
│   │   ├── main.py            # Crea la app FastAPI, CORS, rate limit y registra los routers
│   │   ├── database.py        # Motor SQLAlchemy y get_db()
│   │   ├── schemas.py         # Esquemas Pydantic (y schemas_exportaciones.py)
│   │   ├── core/              # celery_app.py: colas y tareas programadas (beat)
│   │   ├── models/            # Tablas SQLAlchemy (usuarios, sedes, telemetría, suscripciones...)
│   │   ├── routers/           # Endpoints HTTP y WebSocket, un archivo por módulo
│   │   ├── security/          # JWT, permisos, contraseñas, cifrado FTP, auditoría, correo
│   │   ├── services/          # Lógica de negocio: ingesta, caché, mapa, contratos, exportaciones
│   │   ├── tasks/             # Tareas de Celery (sondeo FTP, notificaciones, particiones...)
│   │   ├── ingesta/           # Cliente FTP que descarga los .dat
│   │   └── scripts/           # Seeds de datos de prueba y mediciones de rendimiento
│   ├── alembic/versions/      # Migraciones de la base de datos
│   ├── scripts/               # Scripts de uso único (rotar FTP_CREDENTIAL_KEY)
│   ├── scripts_sql/           # SQL manual (inmutabilidad del log de auditoría, HT-11)
│   ├── tests/                 # pytest: routers/, services/, tasks/, carga/ y fixtures .dat
│   ├── docs/                  # Documentos técnicos (rendimiento HT-16)
│   └── Dockerfile             # Imagen de api, worker y beat
├── frontend/
│   ├── src/
│   │   ├── pages/             # Una pantalla por archivo (Login, Paneles, Graficos...)
│   │   ├── components/        # Componentes reutilizables y de layout
│   │   ├── router/            # AppRouter.tsx: rutas y roles permitidos
│   │   ├── context/           # Sesión (AuthContext) y tema claro/oscuro
│   │   ├── services/api.ts    # Cliente HTTP único (cookie de sesión)
│   │   └── config/            # Roles, rutas por rol, Google Maps, terminología
│   ├── tests/                 # Tests de funciones puras (node --test)
│   └── Dockerfile             # Build de Vite servido con nginx
├── docs/                      # Guía de módulos y traspaso de conocimiento
├── docker-compose.yml         # Postgres y Redis (y el stack completo con --profile full)
├── containers.example.json    # Plantilla del deploy en Lightsail (sin secretos)
├── bucket-policy.json         # Política del bucket S3 del frontend
└── cloudfront-config.json     # Distribución CloudFront de pangea.ceneris.com
```

## Requisitos

- Docker Desktop (para Postgres y Redis).
- Python 3.12. Es la versión del CI y del `Dockerfile`; con otras versiones
  pueden cambiar los resultados.
- Node.js 20 y npm.
- Git.

## Cómo levantar el entorno local

1. Clona el repo y entra a la carpeta `Pangea/`.

2. Crea tu `.env` en la raíz a partir de la plantilla y completa las claves:

   ```bash
   cp .env.example .env
   ```

   - `JWT_SECRET`: `python -c "import secrets; print(secrets.token_hex(32))"`
   - `FTP_CREDENTIAL_KEY`: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

   Completa las dos. Con `FTP_CREDENTIAL_KEY=` vacía el backend no arranca
   (`Fernet("")` falla al importar). Con `JWT_SECRET` vacía arranca, pero
   firma las sesiones con una clave vacía.
   Guarda tu `FTP_CREDENTIAL_KEY`: si la cambias, las contraseñas FTP ya
   guardadas en tu base dejan de poder leerse.

3. Levanta Postgres y Redis:

   ```bash
   docker compose up -d db redis
   ```

   Postgres queda en el puerto **5433** de tu PC (no en el 5432) para no
   chocar con un Postgres instalado en Windows.

4. Backend (en una terminal):

   ```bash
   cd backend
   python -m venv venv
   venv\Scripts\Activate.ps1          # Windows PowerShell
   # source venv/bin/activate         # Git Bash, Mac o Linux
   pip install -r requirements-dev.txt
   alembic upgrade head
   python -m app.scripts.seed_usuarios_prueba   # usuarios de prueba, uno por rol
   uvicorn app.main:app --reload
   ```

   La API queda en http://127.0.0.1:8000 y su documentación interactiva en
   http://127.0.0.1:8000/docs. Para datos de ejemplo de dispositivos:
   `python -m app.scripts.seed_dispositivos_demo`.

5. Worker y beat de Celery, cada uno en su terminal, con el venv activado y
   desde `backend/`. Hacen falta para la ingesta FTP, los correos, las
   suscripciones y las exportaciones:

   ```bash
   celery -A app.core.celery_app worker --loglevel=info --concurrency=4
   celery -A app.core.celery_app worker --loglevel=info --queues=exportaciones --concurrency=1
   celery -A app.core.celery_app beat --loglevel=info
   ```

   En Windows agrega `-P solo` a los dos `worker`: el modo por defecto de
   Celery (prefork) no funciona en Windows.

6. Frontend (en otra terminal):

   ```bash
   cd frontend
   cp .env.example .env     # pide al equipo la VITE_GOOGLE_MAPS_API_KEY
   npm install
   npm run dev
   ```

   Abre http://localhost:5173.

**Al reiniciar la PC:** abre Docker Desktop y vuelve a correr
`docker compose up -d db redis` antes del backend. En cada terminal nueva,
activa el venv antes de usar Python.

## Variables de entorno

El backend lee el `.env` de la raíz (`load_dotenv()` lo busca subiendo
carpetas). El frontend lee `frontend/.env` **al compilar**: después de un
cambio hay que reiniciar `npm run dev` o volver a construir la imagen.

| Variable | Para qué | Valor local |
|---|---|---|
| `DATABASE_URL` | Base de la API, el worker y beat | `postgresql+psycopg2://postgres:postgres@localhost:5433/pangea_dev` |
| `TEST_DATABASE_URL` | Base de pytest | la misma, con `pangea_test` |
| `JWT_SECRET` | Firma de la sesión | obligatoria en producción |
| `FTP_CREDENTIAL_KEY` | Cifra las contraseñas FTP guardadas | la misma en api, worker y beat |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Colas de Celery | `redis://localhost:6379/2` y `/3` |
| `RATELIMIT_STORAGE_URL` | Límite de intentos de login | `redis://localhost:6379/1` |
| `CORS_ALLOWED_ORIGINS` | Orígenes permitidos, separados por coma | por defecto `http://localhost:5173` |
| `FRONTEND_URL` | Enlaces de los correos | `http://localhost:5173` |
| `SMTP_*` | Envío de correos | vacío: el enlace solo sale en el log |
| `EXPORT_S3_*`, `EXPORT_*` | Bucket privado y límites de las exportaciones (HT-17) | ver `.env.example` |
| `PLAN_LIMITS_REQUIRE_SUBSCRIPTION` | Exigir una suscripción activa para aplicar los límites del plan | `true` por defecto |
| `VITE_API_BASE_URL` | URL de la API para el frontend | `http://127.0.0.1:8000` |
| `VITE_GOOGLE_MAPS_API_KEY` | Mapas (HU08, HU17, HU22) | pedirla al equipo |

Redis usa varias bases: 1 límite de login, 2 broker, 3 resultados, 4 eventos
del mapa en vivo, 5 caché de consultas y 6 tickets de WebSocket.

## Pruebas

**Backend** (Postgres y Redis levantados; desde `backend/` con el venv
activado, en Git Bash):

```bash
docker compose exec db createdb -U postgres pangea_test     # solo la primera vez
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/pangea_test python -m alembic upgrade head
TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/pangea_test python -m pytest
```

Los tests corren contra un Postgres real (no SQLite) y cada uno se revierte
al terminar, así que no ensucian la base. Cuando llegue una migración nueva,
vuelve a correr `alembic upgrade head` sobre `pangea_test`.

**Lint del backend** (lo mismo que revisa el CI):

```bash
python -m ruff check .
python -m black --check .
```

**Frontend** (desde `frontend/`):

```bash
npm run lint
npm run test:series     # tests de tests/*.test.ts con node --test
npm run build           # compila TypeScript y genera dist/
```

## CI

`.github/workflows/ci.yml` corre en cada push y Pull Request hacia `jareth`
y `main`: lint (ruff y black), pytest con Postgres 16 y Redis 7, y el build
de la imagen del backend, etiquetada con el hash del commit. El job de
deploy es solo un marcador: **el deploy no está automatizado**.

## Producción

| Pieza | Dónde |
|---|---|
| API, worker, beat y Redis | Lightsail Container Service; plantilla en `containers.example.json` |
| Base de datos | Amazon RDS (PostgreSQL) |
| Frontend | Bucket S3 `pangea-frontend-prod` detrás de CloudFront, en https://pangea.ceneris.com |
| Exportaciones | Bucket S3 privado (`EXPORT_S3_BUCKET`) |

`containers.json` lleva secretos en texto plano y está en `.gitignore`:
nunca se sube. El plan de Lightsail debe ser al menos *small* (0.5 vCPU y
1 GB); en *nano* el deploy con worker falla por falta de memoria. Los pasos
exactos del deploy todavía no están documentados: están en el registro de
dudas de [`docs/traspaso-conocimiento.md`](docs/traspaso-conocimiento.md).

## Problemas conocidos

- El perfil `full` de `docker-compose.yml` conecta la API con el usuario
  `pangea`, que no existe en el contenedor `db` (ese contenedor crea
  `postgres`). Para trabajar en local, usa solo `db` y `redis`, como en los
  pasos de arriba.
- Una migración nueva en `dev` exige `alembic upgrade head` en `pangea_dev`
  y en `pangea_test`.
