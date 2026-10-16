import { useAuth } from "../../context/AuthContext";
import { motion, MotionConfig } from "framer-motion";
import { Link, useLocation } from "react-router-dom";
import { esAdministracion, esCeneris } from "../../config/espacios";
import { volverAdministracion } from "../../services/api";
import pangeaIconLight from "../../assets/pangea-icon-light.png";
import pangeaIconDark from "../../assets/pangea-icon-dark.png";
import { ROLES, rutaPorRol } from "../../config/roles";

export type SeccionActiva = "panel" | "usuarios" | "ubicaciones" | "dispositivos" | "conexiones-ftp" | "dashboard" | "configuracion" | "consulta-datos"| "mapeos" | "parametros" | "cola-ingesta" | "graficos" | "mapa-estaciones" | "mapa-ubicaciones" | "paneles" | "mi-perfil" | "planes" | "suscripciones" | "empresas" | "clientes";

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

const iconos = {
  panel: "M4 6h16M4 12h16M4 18h7",
  usuarios: "M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2m18 0v-2a4 4 0 00-3-3.87M9 11a4 4 0 100-8 4 4 0 000 8m8-7.87a4 4 0 010 7.75",
  empresa: "M3 21h18M5 21V5h14v16M9 9h2m-2 4h2m4-4h2m-2 4h2M9 21v-4h6v4",
  planes: "M4 5h16v14H4zM8 9h8m-8 4h5",
  clientes: "M9 18l6-6-6-6M3 12h12m4-9h2v18h-2",
  ubicaciones: "M17.657 16.657L13.414 20.9a2 2 0 01-2.828 0l-4.243-4.243a8 8 0 1111.314 0zM15 11a3 3 0 11-6 0 3 3 0 016 0z",
  dispositivos: "M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10V7H7zM9 9h6v6H9z",
  graficos: "M3 3v18h18M7 15l4-5 3 3 5-7",
  datos: "M9 17V7m6 10V11m-9 6h12V5H6z",
  mapa: "M9 20l-5-3V4l5 3m0 13l6-3m-6 3V7m6 10l5 3V7l-5-3m0 13V4m0 0L9 7",
  ftp: "M5 5h14v5H5zM5 14h14v5H5zM8 8h.01M8 17h.01",
};

type Entrada = { ruta: string; seccion: SeccionActiva; titulo: string; icono: keyof typeof iconos };

export default function Sidebar({ onLogout, activo, rol }: SidebarProps) {
  const { puedeOperar, rolEmpresa } = useAuth();
  const { pathname } = useLocation();
  const ceneris = esCeneris(rol);
  const administracion = ceneris && esAdministracion(pathname);
  const panelCliente = ceneris || rol === ROLES.USUARIO_EMPRESA ? "/paneles" : rutaPorRol(rol ?? "");
  const principales: Entrada[] = rol === ROLES.ADMINISTRADOR ? [
    { ruta: "/usuarios", seccion: "usuarios", titulo: "Gestión de usuarios", icono: "usuarios" },
    { ruta: "/empresas", seccion: "empresas", titulo: "Empresas y proyectos", icono: "empresa" },
    { ruta: "/planes-suscripciones", seccion: "planes", titulo: "Planes y suscripciones", icono: "planes" },
    { ruta: "/clientes", seccion: "clientes", titulo: "Entorno de clientes", icono: "clientes" },
  ] : [
    { ruta: "/clientes", seccion: "clientes", titulo: "Entorno de clientes", icono: "clientes" },
    { ruta: "/empresas", seccion: "empresas", titulo: "Empresas y proyectos", icono: "empresa" },
  ];
  const grupos: { titulo: string; entradas: Entrada[] }[] = [
    { titulo: "Operación", entradas: [
      { ruta: "/paneles", seccion: "paneles", titulo: "Tableros personalizables", icono: "panel" },
    ] },
    { titulo: "Datos", entradas: [
      { ruta: "/consulta-datos", seccion: "consulta-datos", titulo: "Consulta de datos", icono: "datos" },
      { ruta: "/graficos", seccion: "graficos", titulo: "Gráficos", icono: "graficos" },
      { ruta: "/mapa-estaciones", seccion: "mapa-estaciones", titulo: "Mapa de lecturas", icono: "ubicaciones" },
      { ruta: "/ubicaciones/mapa", seccion: "mapa-ubicaciones", titulo: "Mapa de proyectos", icono: "mapa" },
    ] },
    { titulo: "Gestión", entradas: [
      { ruta: "/ubicaciones", seccion: "ubicaciones", titulo: "Proyectos", icono: "ubicaciones" },
      { ruta: "/dispositivos", seccion: "dispositivos", titulo: "Dispositivos", icono: "dispositivos" },
      ...(!ceneris && rol === ROLES.USUARIO_EMPRESA && rolEmpresa === "Administrador" ? [
        { ruta: "/empresas", seccion: "empresas" as const, titulo: "Mi empresa y usuarios", icono: "empresa" as const },
      ] : []),
    ] },
    ...(puedeOperar ? [{ titulo: "Ingesta", entradas: [
      { ruta: "/conexiones-ftp", seccion: "conexiones-ftp" as const, titulo: "Conexiones FTP", icono: "ftp" as const },
      { ruta: "/parametros", seccion: "parametros" as const, titulo: "Parámetros", icono: "datos" as const },
      { ruta: "/cola-ingesta", seccion: "cola-ingesta" as const, titulo: "Cola de ingesta", icono: "panel" as const },
    ] }] : []),
  ];
  function entrada(item: Entrada) {
    return <ItemMenu key={item.ruta} to={item.ruta}
      activo={activo === item.seccion || (item.seccion === "planes" && activo === "suscripciones")}
      icono={<path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" d={iconos[item.icono]} />}>
      {item.titulo}
    </ItemMenu>;
  }
  return <MotionConfig reducedMotion="user">
    <aside className="relative isolate flex-shrink-0 w-64 bg-gray-50 dark:bg-[#0a0e1a] border-r border-gray-200 dark:border-white/10 hidden md:flex flex-col transition-colors duration-300">
      <FranjaActiva />
      <Link to={ceneris ? (rol === ROLES.ADMINISTRADOR ? "/panel-admin" : "/clientes") : panelCliente}
        className="min-h-20 flex items-center gap-2.5 px-5 border-b border-gray-200 dark:border-white/10">
        <img src={pangeaIconDark} alt="" className="h-10 w-auto dark:hidden" />
        <img src={pangeaIconLight} alt="" className="hidden h-10 w-auto dark:block" />
        <div><span className="text-2xl font-bold text-gray-900 dark:text-white tracking-tight">Pangea</span>
          <p className="text-[11px] text-gray-500 dark:text-gray-400">{administracion ? "Administración CENERIS" : "Entorno del cliente"}</p>
        </div>
      </Link>
      {!administracion && ceneris && <div className="border-b border-gray-200 p-4 dark:border-white/10">
        <button type="button" onClick={volverAdministracion} className="text-xs font-semibold text-gray-600 hover:text-gray-950 dark:text-gray-300 dark:hover:text-white">← Volver a {rol === ROLES.ADMINISTRADOR ? "administración" : "clientes"}</button>
      </div>}
      <nav aria-label={administracion ? "Administración CENERIS" : "Módulos del cliente"} className="flex-1 pl-0 pr-4 py-4 overflow-y-auto scrollbar-oculta">
        {administracion ? <div className={grupo + " space-y-2"}>{principales.map(entrada)}</div>
          : grupos.map((g) => <div key={g.titulo} className={grupo}><p className={tituloGrupo}>{g.titulo}</p><div className="space-y-1">{g.entradas.map(entrada)}</div></div>)}
        {rol === ROLES.ADMINISTRADOR_COMERCIAL && <div className={grupo}>{entrada({ruta:"/planes-suscripciones",seccion:"planes",titulo:"Planes y suscripciones",icono:"planes"})}</div>}
      </nav>
      <div className="p-4 border-t border-gray-200 dark:border-white/10">
        <button onClick={onLogout} className="flex items-center gap-3 px-3 py-2 w-full text-left text-gray-600 hover:bg-red-500/10 hover:text-red-500 dark:text-gray-300 rounded-lg transition-colors">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeWidth="2" d="M9 5H4v14h5m5-14l7 7-7 7M8 12h13" /></svg>Cerrar sesión
        </button>
      </div>
    </aside>
  </MotionConfig>;
}
