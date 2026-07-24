import { useEffect, useState, type FormEvent } from "react";
import { apiFetch, ApiError } from "../services/api";

interface UsuarioListItem {
  id_usr: number;
  nmbr_cmplt: string;
  crr: string;
  rol_nombre: string;
  estd: string;
}

interface ListadoPaginado {
  total: number;
  pagina: number;
  por_pagina: number;
  items: UsuarioListItem[];
}

const ROLES_DISPONIBLES = [
  "Administrador",
  "Técnico CENERIS",
  "Cliente Final",
  "Administrador Comercial",
];

const POR_PAGINA = 10;

interface FormAgregarUsuario {
  nmbr_cmplt: string;
  crr: string;
  rol_nombre: string;
  tlfn: string;
}

const FORM_VACIO: FormAgregarUsuario = { nmbr_cmplt: "", crr: "", rol_nombre: "", tlfn: "" };

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timeout = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timeout);
  }, [value, delayMs]);
  return debounced;
}

export default function Usuarios() {
  // Estado para el Modo Oscuro
  const [isDarkMode, setIsDarkMode] = useState(false);

  const [busquedaInput, setBusquedaInput] = useState("");
  const busqueda = useDebouncedValue(busquedaInput, 400);

  const [rol, setRol] = useState("");
  const [estado, setEstado] = useState("");
  const [pagina, setPagina] = useState(1);

  const [data, setData] = useState<ListadoPaginado | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [recargarTick, setRecargarTick] = useState(0);

  // HU04: alta mínima, sin diseño definido todavía.
  const [mostrarForm, setMostrarForm] = useState(false);
  const [form, setForm] = useState<FormAgregarUsuario>(FORM_VACIO);
  const [guardando, setGuardando] = useState(false);
  const [errorForm, setErrorForm] = useState<string | null>(null);

  function abrirForm() {
    setForm(FORM_VACIO);
    setErrorForm(null);
    setMostrarForm(true);
  }

  function cancelarForm() {
    setMostrarForm(false);
    setForm(FORM_VACIO);
    setErrorForm(null);
  }

  async function guardarUsuario(e: FormEvent) {
    e.preventDefault();
    setErrorForm(null);

    if (!form.nmbr_cmplt.trim() || !form.crr.trim() || !form.rol_nombre) {
      setErrorForm("Nombre completo, correo y rol son obligatorios.");
      return;
    }

    setGuardando(true);
    try {
      await apiFetch("/usuarios", {
        method: "POST",
        body: {
          nmbr_cmplt: form.nmbr_cmplt.trim(),
          crr: form.crr.trim(),
          rol_nombre: form.rol_nombre,
          tlfn: form.tlfn.trim() || undefined,
        },
      });
      setMostrarForm(false);
      setForm(FORM_VACIO);
      setRecargarTick((t) => t + 1); // CA3: refresca el listado, usuario nuevo queda "Activo"
    } catch (err) {
      setErrorForm(err instanceof ApiError ? err.message : "No se pudo crear el usuario");
    } finally {
      setGuardando(false);
    }
  }

  useEffect(() => {
    setPagina(1);
  }, [busqueda, rol, estado]);

  useEffect(() => {
    let cancelado = false;
    setLoading(true);
    setError(null);

    apiFetch<ListadoPaginado>("/usuarios", {
      params: {
        busqueda: busqueda || undefined,
        rol: rol || undefined,
        estado: estado || undefined,
        pagina,
        por_pagina: POR_PAGINA,
      },
    })
      .then((res) => {
        if (!cancelado) setData(res);
      })
      .catch((err) => {
        if (cancelado) return;
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el listado");
      })
      .finally(() => {
        if (!cancelado) setLoading(false);
      });

    return () => {
      cancelado = true;
    };
  }, [busqueda, rol, estado, pagina, recargarTick]);

  const totalPaginas = data ? Math.max(1, Math.ceil(data.total / data.por_pagina)) : 1;
  const inicioRango = data ? ((data.pagina - 1) * data.por_pagina) + 1 : 0;
  const finRango = data ? Math.min(data.pagina * data.por_pagina, data.total) : 0;

  return (
    <div className={`${isDarkMode ? "dark" : ""} font-sans`}>
      {/* Contenedor Principal Layout */}
      <div className="flex h-screen bg-gray-50 dark:bg-gray-900 transition-colors duration-300 overflow-hidden">
        
        {/* SIDEBAR */}
        <aside className="w-64 bg-white dark:bg-[#2d3748] border-r border-gray-200 dark:border-gray-700 hidden md:flex flex-col transition-colors duration-300">
          <div className="h-16 flex items-center px-6 border-b border-gray-200 dark:border-gray-700">
            {/* Logo Placeholder (Nexus Flow colors) */}
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-[#2d3748] dark:bg-white rounded flex items-center justify-center">
                <div className="w-4 h-4 bg-[#ccff00] rounded-sm"></div>
              </div>
              <span className="font-bold text-lg text-gray-900 dark:text-white tracking-wide">NEXUS FLOW</span>
            </div>
          </div>

          <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
            {/* Link Inactivo Ejemplos */}
            <a href="#" className="flex items-center gap-3 px-3 py-2 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"></path></svg>
              Dashboard
            </a>
            
            {/* Link Activo (Usuarios) */}
            <a href="#" className="flex items-center gap-3 px-3 py-2 bg-[#ccff00]/10 text-[#5a7000] dark:text-[#ccff00] font-medium rounded-lg transition-colors">
              <svg className="w-5 h-5 text-[#8fb300] dark:text-[#ccff00]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"></path></svg>
              Gestión de Usuarios
            </a>
            
            <a href="#" className="flex items-center gap-3 px-3 py-2 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
              Configuración
            </a>
          </nav>

          <div className="p-4 border-t border-gray-200 dark:border-gray-700">
            <button className="flex items-center gap-3 px-3 py-2 w-full text-left text-gray-600 dark:text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10 dark:hover:text-red-400 rounded-lg transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
              Cerrar Sesión
            </button>
          </div>
        </aside>

        {/* ÁREA PRINCIPAL */}
        <div className="flex-1 flex flex-col overflow-hidden">
          
          {/* TOP NAVBAR */}
          <header className="h-16 bg-white dark:bg-[#2d3748] border-b border-gray-200 dark:border-gray-700 flex items-center justify-between px-6 transition-colors duration-300">
            {/* Título de la sección en móvil (opcional) */}
            <div className="md:hidden font-bold text-gray-900 dark:text-white">NEXUS FLOW</div>
            <div className="hidden md:block"></div> {/* Espaciador */}

            <div className="flex items-center gap-6">
              {/* Toggle Tema (Sol / Luna) */}
              <button 
                onClick={() => setIsDarkMode(!isDarkMode)}
                className="text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 p-2 rounded-full transition-colors"
                aria-label="Alternar modo oscuro"
              >
                {isDarkMode ? (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"></path></svg>
                ) : (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"></path></svg>
                )}
              </button>

              {/* Perfil de Usuario */}
              <div className="flex items-center gap-3 pl-6 border-l border-gray-200 dark:border-gray-700">
                <div className="text-right hidden sm:block">
                  <div className="text-sm font-semibold text-gray-900 dark:text-white">Carlos Administrador</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">carlos@nexusflow.com</div>
                </div>
                <img 
                  className="w-10 h-10 rounded-full border-2 border-[#ccff00] object-cover" 
                  src="https://ui-avatars.com/api/?name=Carlos+Admin&background=2d3748&color=ccff00" 
                  alt="Avatar del usuario" 
                />
              </div>
            </div>
          </header>

          {/* CONTENIDO DE LA PÁGINA (Usuarios) */}
          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-extrabold text-gray-900 dark:text-white">Gestión de Usuarios</h1>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 font-light">Administra los accesos y roles del sistema.</p>
              </div>
              {!mostrarForm && (
                <button
                  onClick={abrirForm}
                  className="px-4 py-2.5 text-sm font-semibold text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#ccff00]/30 rounded-xl transition-colors"
                >
                  + Agregar usuario
                </button>
              )}
            </header>

            {/* HU04: formulario de alta mínimo, sin mockup definido todavía */}
            {mostrarForm && (
              <div className="bg-white dark:bg-[#2d3748] rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 mb-6">
                <h2 className="text-base font-bold text-gray-900 dark:text-white mb-4">Agregar usuario</h2>
                <form onSubmit={guardarUsuario} className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-600 dark:text-gray-300 mb-1">Nombre completo *</label>
                    <input
                      type="text"
                      value={form.nmbr_cmplt}
                      onChange={(e) => setForm((f) => ({ ...f, nmbr_cmplt: e.target.value }))}
                      className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl block w-full p-2.5 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-600 dark:text-gray-300 mb-1">Correo electrónico *</label>
                    <input
                      type="email"
                      value={form.crr}
                      onChange={(e) => setForm((f) => ({ ...f, crr: e.target.value }))}
                      className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl block w-full p-2.5 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-600 dark:text-gray-300 mb-1">Rol *</label>
                    <select
                      value={form.rol_nombre}
                      onChange={(e) => setForm((f) => ({ ...f, rol_nombre: e.target.value }))}
                      className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl block w-full p-2.5 outline-none cursor-pointer"
                    >
                      <option value="">Selecciona un rol</option>
                      {ROLES_DISPONIBLES.map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-gray-600 dark:text-gray-300 mb-1">Teléfono (opcional)</label>
                    <input
                      type="text"
                      value={form.tlfn}
                      onChange={(e) => setForm((f) => ({ ...f, tlfn: e.target.value }))}
                      className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl block w-full p-2.5 outline-none"
                    />
                  </div>

                  {errorForm && (
                    <div className="md:col-span-2 text-sm text-red-600 dark:text-red-400">{errorForm}</div>
                  )}

                  <div className="md:col-span-2 flex gap-3 justify-end">
                    <button
                      type="button"
                      onClick={cancelarForm}
                      disabled={guardando}
                      className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 transition-colors"
                    >
                      Cancelar
                    </button>
                    <button
                      type="submit"
                      disabled={guardando}
                      className="px-4 py-2 text-sm font-semibold text-[#0c1712] bg-[#ccff00] hover:bg-[#b8e600] rounded-lg disabled:opacity-50 transition-colors"
                    >
                      {guardando ? "Guardando…" : "Guardar"}
                    </button>
                  </div>
                </form>
              </div>
            )}

            {/* Contenedor Principal (Tarjeta) */}
            <div className="bg-white dark:bg-[#2d3748] rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden transition-colors duration-300">
              
              {/* Barra de Herramientas */}
              <div className="p-5 border-b border-gray-100 dark:border-gray-700 flex flex-col lg:flex-row gap-4 items-center">
                <div className="relative flex-1 w-full">
                  <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                    <svg className="w-5 h-5 text-gray-400 dark:text-gray-500" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 20 20">
                      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="m19 19-4-4m0-7A7 7 0 1 1 1 8a7 7 0 0 1 14 0Z"/>
                    </svg>
                  </div>
                  <input
                    type="search"
                    placeholder="Buscar por nombre o correo..."
                    value={busquedaInput}
                    onChange={(e) => setBusquedaInput(e.target.value)}
                    className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full pl-10 p-2.5 transition-all outline-none placeholder-gray-400 dark:placeholder-gray-500"
                  />
                </div>

                <div className="flex w-full lg:w-auto gap-3">
                  <select 
                    value={rol} 
                    onChange={(e) => setRol(e.target.value)}
                    className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block p-2.5 outline-none cursor-pointer"
                  >
                    <option value="">Todos los roles</option>
                    {ROLES_DISPONIBLES.map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>

                  <select 
                    value={estado} 
                    onChange={(e) => setEstado(e.target.value)}
                    className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block p-2.5 outline-none cursor-pointer"
                  >
                    <option value="">Todos los estados</option>
                    <option value="Activo">Activo</option>
                    <option value="Inactivo">Inactivo</option>
                  </select>
                </div>
              </div>

              {error && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-100 dark:border-red-800/30">
                  {error}
                </div>
              )}

              {/* Tabla */}
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                  <thead className="text-xs text-gray-500 dark:text-gray-400 uppercase bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                    <tr>
                      <th className="px-6 py-4 font-bold tracking-wider">Nombre</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Correo</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Rol</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Estado</th>
                      <th className="px-6 py-4 font-bold tracking-wider text-right">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                          <div className="flex justify-center items-center gap-2">
                            <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                            <span>Cargando datos...</span>
                          </div>
                        </td>
                      </tr>
                    )}

                    {!loading && data?.items.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                          No se encontraron usuarios con ese criterio.
                        </td>
                      </tr>
                    )}

                    {!loading && data?.items.map((u) => (
                      <tr key={u.id_usr} className="bg-white dark:bg-[#2d3748] border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors group">
                        <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{u.nmbr_cmplt}</td>
                        <td className="px-6 py-4">{u.crr}</td>
                        <td className="px-6 py-4">{u.rol_nombre}</td>
                        <td className="px-6 py-4">
                          <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${
                            u.estd === "Activo" 
                              ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#ccff00]/30" 
                              : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-600"
                          }`}>
                            {u.estd === "Activo" && <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-[#8fb300] dark:bg-[#ccff00]"></span>}
                            {u.estd}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-right">
                          <button 
                            disabled 
                            title="Próximamente: HU20"
                            className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-transparent border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white focus:ring-4 focus:outline-none focus:ring-gray-200 dark:focus:ring-gray-800 disabled:opacity-50 disabled:hover:bg-white dark:disabled:hover:bg-transparent transition-all"
                          >
                            <svg className="w-4 h-4 mr-2 text-gray-500 dark:text-gray-400" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                            </svg>
                            Editar
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Paginación */}
              {data && (
                <div className="p-5 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between">
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    Mostrando <span className="font-semibold text-gray-900 dark:text-white">{inicioRango}</span> a <span className="font-semibold text-gray-900 dark:text-white">{finRango}</span> de <span className="font-semibold text-gray-900 dark:text-white">{data.total}</span> registros
                  </span>
                  <div className="inline-flex gap-2">
                    <button 
                      disabled={pagina <= 1} 
                      onClick={() => setPagina((p) => p - 1)}
                      className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      Anterior
                    </button>
                    <button 
                      disabled={pagina >= totalPaginas} 
                      onClick={() => setPagina((p) => p + 1)}
                      className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      Siguiente
                    </button>
                  </div>
                </div>
              )}
            </div>
            
          </main>
        </div>
      </div>
    </div>
  );
}