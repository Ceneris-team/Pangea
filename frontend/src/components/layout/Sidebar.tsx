import { Link } from "react-router-dom";
import pangeaIconLight from "../../assets/pangea-icon-light.png";
import { ROLES, rutaPorRol } from "../../config/roles";

export type SeccionActiva = "panel" | "usuarios" | "ubicaciones" | "dispositivos" | "conexiones-ftp" | "dashboard" | "configuracion" | "consulta-datos"| "mapeos" | "parametros" | "cola-ingesta" | "graficos" | "mapa-estaciones" | "mapa-ubicaciones" | "paneles" | "mi-perfil";

interface SidebarProps {
  onLogout: () => void;
  activo: SeccionActiva;
  rol: string | null;
}

// El sidebar es oscuro en los dos temas (a diferencia del resto de la
// app): en modo claro un gris oscuro, en modo oscuro un tono aún más
// oscuro. El item activo, en cambio, es CLARO -toma el color de fondo de
// la página, no del sidebar- y "muerde" el carril entrando desde la
// derecha, con las dos esquinas exteriores cóncavas (ver notchArriba/
// notchAbajo): ese detalle es lo que distingue esto de un simple
// rounded-r-full -sin las esquinas mordidas, la cápsula se ve pegada al
// borde en vez de fundida con él-.
const linkBase = "relative flex items-center gap-3 pl-3 py-2.5 transition-all";
const linkInactivo = "mr-4 rounded-lg text-gray-300 hover:bg-white/5 hover:text-white";
const linkActivo =
  "mr-0 pr-7 rounded-l-lg bg-[#f6f7f8] dark:bg-[#0b1220] text-gray-900 dark:text-white font-semibold";
const linkDeshabilitado = "mr-4 rounded-lg text-gray-500 opacity-60 cursor-not-allowed";
const iconoActivo = "text-gray-900 dark:text-white";

/** Las dos "mordidas" cóncavas de la cápsula activa: un cuarto de círculo
 *  del color del SIDEBAR (no del fondo de página) posicionado justo
 *  arriba y abajo de la cápsula, en la esquina donde se junta con el
 *  carril. Es puro CSS -radial-gradient recortado con el propio
 *  border-radius del pseudo-elemento-, sin SVG ni imagen. */
const notchArriba =
  "absolute -top-4 right-0 w-4 h-4 bg-[radial-gradient(circle_at_top_left,transparent_70%,#F6F7F8_71%)] dark:bg-[radial-gradient(circle_at_top_left,transparent_70%,#111827_71%)]";
const notchAbajo =
  "absolute -bottom-4 right-0 w-4 h-4 bg-[radial-gradient(circle_at_bottom_left,transparent_70%,#F6F7F8_71%)] dark:bg-[radial-gradient(circle_at_bottom_left,transparent_70%,#111827_71%)]";

/** Encabezado de grupo del menú. En minúscula-versalita y sin borde: la
 *  separación la da el espacio (mt-5), no una línea; con 4 grupos, cuatro
 *  reglas horizontales competirían visualmente con el item activo. */
const tituloGrupo =
  "pl-3 pr-4 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-500 select-none";

/** Espaciado entre grupos. El primero no lo lleva (va pegado al logo). */
const grupo = "mt-5 first:mt-0";

/** Un item de menú, con el detalle de las esquinas cóncavas cuando está
 *  activo. Se centralizó en un componente en vez de repetir el mismo
 *  bloque de "cápsula + dos mordidas" en los 13 links del menú. */
function ItemMenu({ to, activo, icono, children }: { to: string; activo: boolean; icono: React.ReactNode; children: React.ReactNode }) {
  return (
    <Link to={to} className={linkBase + " " + (activo ? linkActivo : linkInactivo)}>
      {activo && (
        <>
          <span className={notchArriba} aria-hidden="true" />
          <span className={notchAbajo} aria-hidden="true" />
        </>
      )}
      <svg className={"w-5 h-5 shrink-0 " + (activo ? iconoActivo : "")} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        {icono}
      </svg>
      {children}
    </Link>
  );
}

export default function Sidebar({ onLogout, activo, rol }: SidebarProps) {
  return (
    <aside className="w-64 bg-gray-800 dark:bg-[#0a0e1a] hidden md:flex flex-col transition-colors duration-300">
      <div className="h-16 flex items-center gap-2.5 px-5 border-b border-white/10">
        <img src={pangeaIconLight} alt="" className="h-10 w-auto" />
        <span className="text-2xl font-bold text-white tracking-tight">Pangea</span>
      </div>

      {/* El menú va agrupado por AFINIDAD de tarea, no por orden de
          implementación de las HU. Los grupos existen sobre todo por los
          mapas: había dos pantallas de mapa ("Mapa de Ubicaciones", HU22, y
          "Mapa de Estaciones", HU17) separadas por items sin relación y con
          nombres parecidos, así que costaba saber cuál era cuál.

          Los encabezados no son links ni plegables a propósito: con ~11
          items visibles como máximo, plegar añadiría un clic para llegar a
          todo sin ahorrar scroll real. */}
      {/* scrollbar-oculta (ver index.css): en pantallas bajas el menú tiene
          que poder desplazarse, pero la barra de scroll en un panel angosto
          queda como una franja permanente que ensucia el diseño. Se oculta
          solo el indicador; el scroll con rueda, trackpad, teclado y touch
          sigue funcionando. */}
      {/* pl-4 pr-0 py-4 (no p-4): el padding derecho lo pone cada LINK
          -mr-4 en los inactivos, pr-7 sin margen en el activo-, no el
          nav, para que el item activo pueda llegar hasta el borde real
          del <aside> en vez de quedar recortado por el padding del
          contenedor con scroll. */}
      <nav className="flex-1 pl-4 pr-0 py-4 overflow-y-auto scrollbar-oculta">
        {/* ---------------- General ---------------- */}
        <div className={grupo + " space-y-1"}>
          {/* Panel: lleva al panel real del rol logueado (panel-admin / panel-tecnico) */}
          <ItemMenu
            to={rutaPorRol(rol ?? "")}
            activo={activo === "panel"}
            icono={<path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h7" />}
          >
            Panel
          </ItemMenu>

          {/* HU23: Tableros Personalizables (E05). Reemplaza al antiguo
              placeholder "Dashboard" -deshabilitado, sin ruta real-. */}
          <ItemMenu
            to="/paneles"
            activo={activo === "paneles"}
            icono={
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
              />
            }
          >
            Tableros Personalizables
          </ItemMenu>
        </div>

        {/* ---------------- Mapas ----------------
            Las dos vistas de mapa, juntas. Son pantallas distintas y se
            parecen de nombre, así que el orden importa: primero la de
            gestión (zonas y dispositivos, HU22), después la operativa
            (estado de las estaciones en vivo, HU17). */}
        <div className={grupo}>
          <p className={tituloGrupo}>Mapas</p>
          <div className="space-y-1">
            {/* HU22: mapa de ubicaciones, solo lectura. */}
            <ItemMenu
              to="/ubicaciones/mapa"
              activo={activo === "mapa-ubicaciones"}
              icono={
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"
                />
              }
            >
              Mapa de Ubicaciones
            </ItemMenu>

            {/* HU17: mapa de estaciones con datos en vivo. Separado de
                "Mapa de Ubicaciones" (HU22), que es la vista de gestión:
                aquella muestra zonas y dispositivos, esta el estado actual
                de las estaciones asignadas al usuario. */}
            <ItemMenu
              to="/mapa-estaciones"
              activo={activo === "mapa-estaciones"}
              icono={
                <>
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M17.657 16.657L13.414 20.9a2 2 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
                  />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                </>
              }
            >
              Mapa de Estaciones
            </ItemMenu>
          </div>
        </div>

        {/* ---------------- Datos ----------------
            Las dos formas de mirar la misma telemetría: tabla (HU13) y
            gráfico (HU15). Van pegadas a Mapas porque el botón "Ver
            gráfico" del panel del mapa aterriza justamente acá. */}
        <div className={grupo}>
          <p className={tituloGrupo}>Datos</p>
          <div className="space-y-1">
            {/* HU13: consulta de datos de telemetria filtrada por parametros/ubicaciones */}
            <ItemMenu
              to="/consulta-datos"
              activo={activo === "consulta-datos"}
              icono={
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M9 17V7m6 10V11m-9 6h12a2 2 0 002-2V5a2 2 0 00-2-2H6a2 2 0 00-2 2v10a2 2 0 002 2z"
                />
              }
            >
              Consulta de Datos
            </ItemMenu>

            {/* Graficos: vista rapida de telemetria en charts (misma fuente que Consulta de Datos) */}
            <ItemMenu
              to="/graficos"
              activo={activo === "graficos"}
              icono={<path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 3v18h18M7 15l4-5 3 3 5-7" />}
            >
              Gráficos
            </ItemMenu>
          </div>
        </div>

        {/* ---------------- Gestión ----------------
            El inventario: qué ubicaciones y qué dispositivos existen, y
            quién los usa. Es el catálogo del sistema, distinto de mirarlo
            en un mapa. */}
        <div className={grupo}>
          <p className={tituloGrupo}>Gestión</p>
          <div className="space-y-1">
            <ItemMenu
              to="/ubicaciones"
              activo={activo === "ubicaciones"}
              icono={
                <>
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M17.657 16.657L13.414 20.9a2 2 0 01-2.828 0l-4.243-4.243a8 8 0 1111.314 0z"
                  />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                </>
              }
            >
              Gestion de Ubicaciones
            </ItemMenu>

            {/* HU10: listar dispositivos. Visible para todos los roles, igual
                que Ubicaciones: el backend ya filtra qué ve cada uno. */}
            <ItemMenu
              to="/dispositivos"
              activo={activo === "dispositivos"}
              icono={
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"
                />
              }
            >
              Gestion de Dispositivos
            </ItemMenu>

            {/* HU03: Solo el rol Administrador puede acceder a este modulo */}
            {rol === ROLES.ADMINISTRADOR && (
              <ItemMenu
                to="/usuarios"
                activo={activo === "usuarios"}
                icono={
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"
                  />
                }
              >
                Gestion de Usuarios
              </ItemMenu>
            )}
          </div>
        </div>

        {/* ---------------- Ingesta ----------------
            Todo lo necesario para que los datos ENTREN al sistema: de dónde
            se bajan (FTP), cómo se interpretan (Parámetros) y en qué estado
            va el procesamiento (Cola). Solo Administrador y Técnico CENERIS,
            mismo criterio que ya tenía cada item por separado.

            El grupo entero se oculta si el rol no tiene ninguno de sus
            items: si no, quedaría un encabezado "Ingesta" suelto sobre
            nada, que se lee como un error de la interfaz. */}
        {(rol === ROLES.ADMINISTRADOR || rol === ROLES.TECNICO_CENERIS) && (
          <div className={grupo}>
            <p className={tituloGrupo}>Ingesta</p>
            <div className="space-y-1">
              {/* HU05 */}
              <ItemMenu
                to="/conexiones-ftp"
                activo={activo === "conexiones-ftp"}
                icono={
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M5 12h14M5 12a2 2 0 01-2-2V7a2 2 0 012-2h14a2 2 0 012 2v3a2 2 0 01-2 2M5 12a2 2 0 00-2 2v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 00-2-2M6 8h.01M6 16h.01"
                  />
                }
              >
                Conexiones FTP
              </ItemMenu>

              {/* Catálogo de parámetros estándar que consume HU06. */}
              <ItemMenu
                to="/parametros"
                activo={activo === "parametros"}
                icono={
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M9 17V7m3 10V11m3 6V9M5 21h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v14a2 2 0 002 2z"
                  />
                }
              >
                Parámetros
              </ItemMenu>

              {/* HU09: monitoreo de la cola de procesamiento. */}
              <ItemMenu
                to="/cola-ingesta"
                activo={activo === "cola-ingesta"}
                icono={<path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 7h16M4 12h16M4 17h16" />}
              >
                Cola de Ingesta
              </ItemMenu>
            </div>
          </div>
        )}

        {/* DEC-09: el link "Mapeos de Formato" se retiró. El formato ya no
            es un módulo propio navegable por sede+marca: se configura
            dentro de la ficha de cada Dispositivo (Gestión de Dispositivos
            -> click en el dispositivo -> pestañas Formato y Datos), porque
            el mapeo depende de qué sensores tiene cableados ese datalogger
            concreto. */}

        {/* ---------------- Sistema ---------------- */}
        <div className={grupo}>
          <p className={tituloGrupo}>Sistema</p>
          <div className="space-y-1">
            {/* Configuracion: placeholder, aun no implementado */}
            <a
              href="#"
              title="Proximamente"
              onClick={(e) => e.preventDefault()}
              className={linkBase + " " + linkDeshabilitado}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              Configuracion
            </a>
          </div>
        </div>
      </nav>

      <div className="p-4 border-t border-white/10">
        <button
          onClick={onLogout}
          className="flex items-center gap-3 px-3 py-2 w-full text-left text-gray-300 hover:bg-red-500/10 hover:text-red-400 rounded-lg transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
            />
          </svg>
          Cerrar Sesion
        </button>
      </div>
    </aside>
  );
}
