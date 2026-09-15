import { motion, MotionConfig } from "framer-motion";
import { Link } from "react-router-dom";
import pangeaIconLight from "../../assets/pangea-icon-light.png";
import pangeaIconDark from "../../assets/pangea-icon-dark.png";
import { ROLES, rutaPorRol } from "../../config/roles";

export type SeccionActiva = "panel" | "usuarios" | "ubicaciones" | "dispositivos" | "conexiones-ftp" | "dashboard" | "configuracion" | "consulta-datos"| "mapeos" | "parametros" | "cola-ingesta" | "graficos" | "mapa-estaciones" | "mapa-ubicaciones" | "paneles" | "mi-perfil";

interface SidebarProps {
  onLogout: () => void;
  activo: SeccionActiva;
  rol: string | null;
}

// El sidebar cambia de paleta completa según el tema, con su propio logo
// para cada uno (pangeaIconDark en claro, pangeaIconLight en oscuro -el
// nombre de cada archivo es por el tono del ÍCONO, pensado para
// contrastar contra el fondo de SU tema, no por el tema en sí-): en claro
// es blanquito para hacer juego con el gris azulado y el verde lima del
// logo; en oscuro sigue siendo el tono muy oscuro de siempre. El item
// activo se resalta con una cápsula que "muerde" el carril con las dos
// esquinas exteriores cóncavas (ver notchArriba/notchAbajo): ese detalle
// es lo que distingue esto de un simple rounded-full -sin las esquinas
// mordidas, la cápsula se ve pegada al borde en vez de fundida con él-.
//
// La cápsula nace de la IZQUIERDA en los dos temas, de una franja de marca
// fija (ver FranjaActiva) pegada al borde izquierdo del sidebar -esa
// franja es lo que marca "activo" con color de acento-.
//
// La cápsula (CapsulaActiva, más abajo) se monta y desmonta con Framer
// Motion: cada vez que un item pasa a activo, React la crea de cero
// adentro de ESE link, y Motion anima su aparición con un fundido de
// opacidad -sin medir nada a mano con getBoundingClientRect ni
// ResizeObserver, que es como estaba antes de esta migración-.
// El link tiene la MISMA geometría activo o no (mismo ml-4, mismo
// padding): solo cambia el color. Si el activo se ensanchara -como cuando
// pintaba su propio fondo hasta el borde-, al seleccionarlo cambiaría el
// ancho disponible para el texto y un label largo saltaría a dos líneas.
// Quien llega hasta el borde izquierdo del <aside> ahora es la cápsula
// (con un left negativo que compensa el ml-4 del link, ver
// CapsulaActiva), no el link.
const linkBase = "relative z-10 flex items-center gap-3 pl-3 ml-4 py-2.5 rounded-lg transition-colors duration-300";
const linkInactivo = "text-gray-600 hover:bg-black/5 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-white/5 dark:hover:text-white";
const linkActivo = "text-[#14210a] font-semibold";
// Mismo verde lima de marca en los dos temas -antes era gray-400 en claro,
// pero el gris quedaba deslucido contra el nuevo fondo blanquito del
// sidebar en claro; el verde es el mismo acento de marca de FranjaActiva
// en ambos casos, así que no hace falta diferenciar por tema-.
const capsulaColor = "bg-[#ccff00]";
const linkDeshabilitado = "text-gray-500 opacity-60 cursor-not-allowed";

/** Franja fija de marca en el borde izquierdo del sidebar: el punto del
 *  que "nace" la cápsula activa, en los dos temas. */
function FranjaActiva() {
  return <div aria-hidden="true" className="absolute inset-y-0 left-0 w-1.5 z-20 bg-[#ccff00]" />;
}

/** Las dos "mordidas" cóncavas de la cápsula activa: un cuarto de círculo
 *  posicionado justo arriba y abajo de la cápsula, en la esquina donde se
 *  junta con el carril. Es puro CSS -radial-gradient-, sin SVG ni imagen.
 *
 *  El relleno sólido es el mismo color que capsulaColor (no el del sidebar
 *  ni el de la página): es la prolongación de la cápsula, y lo que "muerde"
 *  es el cuarto de círculo TRANSPARENTE, que deja ver el sidebar a través.
 *
 *  El corte del gradiente está en exactamente 50% (no otro valor): es el
 *  único punto donde el círculo queda tangente al borde recto vertical de
 *  la cápsula sin dejar un escalón visible en la unión de las dos curvas -
 *  cualquier otro porcentaje desalinea el radio real del círculo respecto
 *  al tamaño del cuadrado que lo contiene. */
const notchArriba =
  "absolute -top-4 left-0 w-[22.5px] h-6 bg-[radial-gradient(circle_at_top_right,transparent_50%,#ccff00_51%)]";
const notchAbajo =
  "absolute -bottom-4 left-0 w-[22.5px] h-6 bg-[radial-gradient(circle_at_bottom_right,transparent_50%,#ccff00_51%)]";

/** Encabezado de grupo del menú. En minúscula-versalita y sin borde: la
 *  separación la da el espacio (mt-5), no una línea; con 4 grupos, cuatro
 *  reglas horizontales competirían visualmente con el item activo. */
const tituloGrupo =
  "pl-3 pr-4 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-500 select-none";

/** Espaciado entre grupos. El primero no lo lleva (va pegado al logo). */
const grupo = "mt-5 first:mt-0";

/** La cápsula clara del item activo + sus dos mordidas. Vive DENTRO del
 *  link activo (position: absolute, inset-0) y no en un elemento
 *  compartido en el <nav>: como cada item la vuelve a montar de cero al
 *  activarse, Framer Motion la anima con `initial`/`animate`. Es solo un
 *  fundido de opacidad -sin desplazamiento- para que la entrada se sienta
 *  ligera al clickear en vez de una transición vistosa.
 *  z-[-1] la manda detrás del ícono y el texto del propio link. */
function CapsulaActiva() {
  return (
    // top-0/bottom-0/right-0 + left-[-1rem]: el link tiene ml-4 (1rem), así
    // que su propio ancho (inset-0) empieza 16px después del borde real
    // del <aside>. El left negativo compensa ese hueco para que la cápsula
    // llegue justo al borde izquierdo (donde está FranjaActiva) y se funda
    // con él -sin él, quedaba corta y el hueco se notaba en items con
    // label de dos líneas-.
    <motion.span
      aria-hidden="true"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.15 }}
      className={`absolute top-0 bottom-0 right-0 left-[-1rem] z-[-1] rounded-r-lg ${capsulaColor}`}
    >
      <span className={notchArriba} />
      <span className={notchAbajo} />
    </motion.span>
  );
}

/** Un item de menú. El item activo no pinta su fondo con className: lo
 *  pinta CapsulaActiva, montada de nuevo cada vez que este item pasa a
 *  estar activo (ver su comentario). */
function ItemMenu({ to, activo, icono, children }: { to: string; activo: boolean; icono: React.ReactNode; children: React.ReactNode }) {
  return (
    <Link to={to} className={linkBase + " " + (activo ? linkActivo : linkInactivo)}>
      {activo && <CapsulaActiva />}
      <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        {icono}
      </svg>
      {/* El ancho lo reserva SIEMPRE la versión en negrita (el ::after
          invisible), no el texto visible: si no, al activarse el item el
          texto engorda, deja de entrar en una línea y el label salta a dos
          -y con él el alto de la cápsula-. */}
      <span
        className="min-w-0 after:block after:h-0 after:overflow-hidden after:font-semibold after:invisible after:content-[attr(data-label)]"
        data-label={typeof children === "string" ? children : undefined}
      >
        {children}
      </span>
    </Link>
  );
}

export default function Sidebar({ onLogout, activo, rol }: SidebarProps) {
  return (
    // reducedMotion="user": si el sistema pide menos movimiento, Framer
    // Motion recorta la animación de CapsulaActiva a un cambio instantáneo
    // en vez del deslizamiento -sin esto la librería anima igual, no
    // respeta la preferencia sola-.
    <MotionConfig reducedMotion="user">
    {/* relative isolate: sin esto el <aside> no forma su propio stacking
        context, así que el z-[-1] de CapsulaActiva (ver más abajo) no
        queda contenido dentro del sidebar sino que compite con el stacking
        context raíz del documento -pintándose por momentos detrás del
        propio fondo del <aside>, dejando ver la textura del body a través
        justo en la zona del item activo-. */}
    <aside className="relative isolate w-64 bg-gray-50 dark:bg-[#0a0e1a] border-r border-gray-200 dark:border-white/10 hidden md:flex flex-col transition-colors duration-300">
      <FranjaActiva />
      <div className="h-16 flex items-center gap-2.5 px-5 border-b border-gray-200 dark:border-white/10">
        <img src={pangeaIconDark} alt="" className="h-10 w-auto dark:hidden" />
        <img src={pangeaIconLight} alt="" className="hidden h-10 w-auto dark:block" />
        <span className="text-2xl font-bold text-gray-900 dark:text-white tracking-tight">Pangea</span>
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
      {/* pl-0 pr-4 (no px-4): el margen izquierdo lo pone cada link con
          ml-4, no el nav, para que la cápsula de cada item pueda llegar al
          borde izquierdo del aside, donde está FranjaActiva (ver
          CapsulaActiva). */}
      <nav className="flex-1 pl-0 pr-4 py-4 overflow-y-auto scrollbar-oculta">
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

        {/* ---------------- Notificaciones ----------------
            HU27: alarmas configuradas sobre los parámetros del usuario.
            Visible para todos los roles, igual que Ubicaciones/Dispositivos:
            el backend ya exige permiso de Lectura sobre 'Alarmas' y, dentro
            de eso, cada usuario solo ve las suyas. */}
        <div className={grupo}>
          <p className={tituloGrupo}>Notificaciones</p>
          <div className="space-y-1">
            <Link
              to="/alarmas"
              className={linkBase + " " + (activo === "alarmas" ? linkActivo : linkInactivo)}
            >
              <svg
                className={"w-5 h-5 " + (activo === "alarmas" ? iconoActivo : "")}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"
                />
              </svg>
              Alarmas
            </Link>
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

      <div className="p-4 border-t border-gray-200 dark:border-white/10">
        <button
          onClick={onLogout}
          className="flex items-center gap-3 px-3 py-2 w-full text-left text-gray-600 hover:bg-red-500/10 hover:text-red-500 dark:text-gray-300 dark:hover:text-red-400 rounded-lg transition-colors"
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
    </MotionConfig>
  );
}
