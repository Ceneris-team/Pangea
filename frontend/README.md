# Frontend - Pangea 4.0

SPA en React 19 + Vite + TypeScript + Tailwind CSS 3. Cómo levantar todo el
proyecto: ver el [`README.md`](../README.md) de la raíz.

## Comandos

| Comando | Qué hace |
|---|---|
| `npm install` | Instala dependencias (en el CI y en Docker se usa `npm ci`) |
| `npm run dev` | Servidor de desarrollo en http://localhost:5173 |
| `npm run build` | `tsc -b` y `vite build`; deja el sitio en `dist/` |
| `npm run lint` | ESLint (`eslint.config.js`) |
| `npm run test:series` | Tests de `tests/*.test.ts` con `node --test` (sin navegador) |
| `npm run preview` | Sirve `dist/` para revisar el build |

## Variables de entorno

Copia `.env.example` a `.env`. Vite las fija **al compilar**: después de
cambiarlas, reinicia `npm run dev` o vuelve a construir.

- `VITE_API_BASE_URL`: URL de la API. Si no está, usa `http://127.0.0.1:8000`.
- `VITE_GOOGLE_MAPS_API_KEY`: clave de Google Maps, restringida por dominio.
  Pídela al equipo. Sin ella, las pantallas con mapa muestran «Falta
  configurar VITE_GOOGLE_MAPS_API_KEY». Para un dominio nuevo hay que
  agregarlo a las restricciones de la clave en Google Cloud Console.

## Organización de `src/`

| Carpeta | Contenido |
|---|---|
| `main.tsx`, `App.tsx` | Arranque: montan `AppRouter` |
| `router/AppRouter.tsx` | Proveedores de tema y sesión, y todas las rutas. Cada ruta privada va envuelta en `ProtectedRoute` con sus roles |
| `components/ProtectedRoute.tsx` | Redirige al login sin sesión, o al panel del rol si el rol no está permitido. `requiereOperacion` y `requiereAdministracionEmpresa` agregan reglas de la empresa |
| `context/` | `AuthContext` (sesión, rol, empresa) y `ThemeContext` (claro/oscuro con `darkMode: 'class'`) |
| `hooks/` | `useAuth`, `useTheme` y `useMapaEnVivo` (WebSocket del mapa) |
| `services/api.ts` | Único cliente HTTP. Manda siempre `credentials: "include"` |
| `config/roles.ts` | Nombres de los 5 roles y a qué panel va cada uno al iniciar sesión |
| `config/espacios.ts` | Qué rutas son de administración y cuáles operativas |
| `config/terminologia.ts` | Cambia «ubicación» por «proyecto» en los textos visibles |
| `pages/` | Una pantalla por archivo. Las utilidades puras de cada pantalla van al lado (`graficosUtils.ts`, `seriesTelemetria.ts`...) y tienen sus tests en `tests/` |
| `components/` | Componentes compartidos; `layout/` (Sidebar, Topbar, Drawer), `comercial/` y `perfil/` |
| `types/`, `utils/` | Tipos compartidos y utilidades de fechas |

## Sesión

El login deja la sesión en una **cookie httpOnly**: el frontend no guarda ni
manda tokens. Por eso todas las llamadas pasan por `services/api.ts`, que
agrega `credentials: "include"`. El WebSocket del mapa en vivo no puede usar
esa cookie: antes de abrirlo, `useMapaEnVivo` pide un ticket corto a
`POST /auth/ws-ticket`.

## Roles y panel de inicio

| Rol | Panel al iniciar sesión |
|---|---|
| Administrador | `/panel-admin` |
| Técnico CENERIS | `/panel-tecnico` |
| Administrador Comercial | `/panel-comercial` |
| Cliente Final | `/paneles` |
| Usuario Empresa | `/paneles` |

Para un rol nuevo: agrégalo en `config/roles.ts` (nombre y ruta), crea la
ruta en `AppRouter.tsx` y revisa los permisos del backend
(`backend/app/security/permisos.py`).

## Convenciones

- Componentes y páginas en **PascalCase** (`Usuarios.tsx`). En Windows un
  error de mayúsculas no falla, pero **rompe el build en Linux**, que es
  donde corren Docker y producción.
- Lógica sin interfaz en archivos `.ts` aparte, para poder probarla con
  `node --test`.
- Más convenciones en [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Build y deploy

El `Dockerfile` compila con Node 20 y sirve `dist/` con nginx
(`nginx.conf` devuelve `index.html` en cualquier ruta, para que funcione el
router). En producción el sitio está en el bucket S3 `pangea-frontend-prod`
detrás de CloudFront (https://pangea.ceneris.com). Ver `bucket-policy.json` y
`cloudfront-config.json` en la raíz.
