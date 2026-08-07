# Pangea 4.0

Plataforma de monitoreo ambiental en tiempo real. Backend en FastAPI +
PostgreSQL, frontend en React + Vite + TypeScript.

## Estructura del proyecto

```
Pangea/
├── backend/
│   ├── app/
│   │   ├── models/        # Entidades SQLAlchemy (Usuario, Rol, Sede, Ubicacion...)
│   │   ├── routers/       # Endpoints agrupados por módulo (auth, usuarios, ubicaciones)
│   │   ├── security/      # JWT, hashing de contraseñas, cifrado de credenciales FTP
│   │   ├── core/          # Configuración de Celery
│   │   ├── database.py    # Conexión SQLAlchemy
│   │   └── main.py        # Punto de entrada de la API
│   ├── alembic/            # Migraciones de base de datos
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/          # Una página por pantalla (Login, PanelAdmin, Usuarios...)
│       ├── context/        # AuthContext: sesión, token, rol
│       ├── router/         # Definición de rutas y protección por rol
│       ├── services/       # Cliente HTTP centralizado (api.ts)
│       ├── components/     # Componentes reutilizables (ProtectedRoute...)
│       └── config/         # Mapeos de configuración (roles -> rutas)
├── docs/
│   └── prototipos/          # Mockups estáticos de referencia (NO son la fuente de verdad)
└── docker-compose.yml       # Postgres + Redis para desarrollo local
```

**Convención de nombres:** un archivo por componente/página, en PascalCase
(`Login.tsx`, `Usuarios.tsx`). Evitar minúsculas en nombres de componentes:
en Windows/Mac no da error, pero **rompe el build en Linux/Docker**, que es
donde corre CI/CD y producción (ver HT-06, HT-07).

## Cómo levantar el entorno local

1. Clona el repo y entra a la carpeta `Pangea/`.
2. Copia el archivo de entorno: `cp .env.example .env` (ajusta valores solo
   si tu Postgres/Redis local usan credenciales distintas).
3. Levanta base de datos y Redis: `docker-compose up -d`
4. Backend:
   ```bash
   cd backend
   python -m venv venv
   venv\Scripts\Activate.ps1      # Windows PowerShell
   # source venv/bin/activate     # Mac/Linux
   pip install -r requirements.txt
   alembic upgrade head
   uvicorn app.main:app --reload
   ```
5. Frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

**Nota:** cada vez que reinicies la PC o cierres Docker Desktop, hay que
volver a levantar los contenedores con `docker-compose up -d` antes de
correr el backend. Cada vez que abras una terminal nueva, activa el venv
antes de correr comandos de Python.

## Convenciones de ramas y HU/HT

Cada historia de usuario (HU) o historia técnica (HT) del backlog debe
desarrollarse en su propia rama: `feature/HU03-listar-usuarios`,
`feature/HT09-middleware-autorizacion`, etc. Los criterios de aceptación
documentados en cada HU son la referencia para las pruebas antes de abrir
el Pull Request.
