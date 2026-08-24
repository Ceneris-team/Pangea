import { useEffect, useRef, useState, type FormEvent } from "react";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

interface UsuarioListItem {
  id_usr: number;
  nmbr_cmplt: string;
  crr: string;
  rol_nombre: string;
  estd: string;
}

/** HU04 CA2: respuesta de POST /usuarios, con el mensaje de éxito. */
interface UsuarioCreadoResponse {
  mensaje: string;
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
  const { nombreCompleto, rol: rolPropio, logout } = useAuth();

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

  // HU04 CA2/CA3: tras guardar, el formulario se reemplaza por un estado de
  // confirmación con el mensaje de éxito y el botón "VER USUARIOS". Ir al
  // listado es una acción explícita del usuario (CA3), no un refresco
  // automático: por eso `creado` se mantiene hasta que hace clic.
  const [creado, setCreado] = useState<UsuarioCreadoResponse | null>(null);

  // Fila a resaltar brevemente al volver al listado (CA3).
  const [idResaltado, setIdResaltado] = useState<number | null>(null);
  const filaResaltadaRef = useRef<HTMLTableRowElement | null>(null);

  function abrirForm() {
    setForm(FORM_VACIO);
    setErrorForm(null);
    setCreado(null);
    setMostrarForm(true);
  }

  function cancelarForm() {
    setMostrarForm(false);
    setForm(FORM_VACIO);
    setErrorForm(null);
    setCreado(null);
  }

  /** CA3: "CUANDO selecciono 'VER USUARIOS', ENTONCES redirige al listado
   *  con el nuevo usuario en estado 'Activo'." */
  function verUsuarios() {
    const idNuevo = creado?.id_usr ?? null;
    setMostrarForm(false);
    setCreado(null);
    setForm(FORM_VACIO);
    setRecargarTick((t) => t + 1);
    setIdResaltado(idNuevo);
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
      const data = await apiFetch<UsuarioCreadoResponse>("/usuarios", {
        method: "POST",
        body: {
          nmbr_cmplt: form.nmbr_cmplt.trim(),
          crr: form.crr.trim(),
          rol_nombre: form.rol_nombre,
          tlfn: form.tlfn.trim() || undefined,
        },
      });
      // CA2: se muestra "Usuario creado exitosamente" (mensaje del backend).
      setCreado(data);
    } catch (err) {
      setErrorForm(err instanceof ApiError ? err.message : "No se pudo crear el usuario");
    } finally {
      setGuardando(false);
    }
  }

  // CA3: al volver al listado, la fila del usuario nuevo se resalta y se
  // trae a la vista; el resaltado se apaga solo a los pocos segundos.
  useEffect(() => {
    if (idResaltado === null) return;
    filaResaltadaRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    const timeout = setTimeout(() => setIdResaltado(null), 3000);
    return () => clearTimeout(timeout);
  }, [idResaltado, data]);

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
  const inicioRango = data ? (data.pagina - 1) * data.por_pagina + 1 : 0;
  const finRango = data ? Math.min(data.pagina * data.por_pagina, data.total) : 0;

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="usuarios" rol={rolPropio} />

        <div className="flex-1 flex flex-col overflow-hidden">
          {/* TOP NAVBAR */}
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
            nombreCompleto={nombreCompleto}
            rol={rol}
            />
          </div>

          {/* CONTENIDO DE LA PÁGINA (Usuarios) */}
          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-extrabold text-gray-900 dark:text-white">Gestión de Usuarios</h1>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 font-light">
                  Administra los accesos y roles del sistema.
                </p>
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

            {/* HU04 CA2/CA3: confirmación tras crear. Reemplaza al formulario
                y exige un clic explícito en "VER USUARIOS" para ir al listado. */}
            {mostrarForm && creado && (
              <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-[#ccff00]/40 p-5 mb-6">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 inline-flex items-center justify-center w-8 h-8 rounded-full bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00]">
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth="2.5" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                    </svg>
                  </span>
                  <div className="flex-1">
                    <h2 className="text-base font-bold text-gray-900 dark:text-white">
                      {creado.mensaje}
                    </h2>
                    <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">
                      <span className="font-medium text-gray-700 dark:text-gray-200">{creado.nmbr_cmplt}</span>{" "}
                      ({creado.crr}) · {creado.rol_nombre} · Estado {creado.estd}. Se le envió un correo de
                      bienvenida con sus credenciales temporales.
                    </p>

                    <div className="flex gap-3 mt-4">
                      <button
                        type="button"
                        onClick={verUsuarios}
                        className="px-4 py-2 text-sm font-semibold text-[#0c1712] bg-[#ccff00] hover:bg-[#b8e600] rounded-lg transition-colors"
                      >
                        VER USUARIOS
                      </button>
                      <button
                        type="button"
                        onClick={abrirForm}
                        className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                      >
                        Agregar otro
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* HU04: formulario de alta mínimo, sin mockup definido todavía */}
            {mostrarForm && !creado && (
              <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-5 mb-6">
                <h2 className="text-base font-bold text-gray-900 dark:text-white mb-4">Agregar usuario</h2>
                <form onSubmit={guardarUsuario} className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-700 dark:text-gray-200 mb-1">Nombre completo *</label>
                    <input
                      type="text"
                      value={form.nmbr_cmplt}
                      onChange={(e) => setForm((f) => ({ ...f, nmbr_cmplt: e.target.value }))}
                      className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl block w-full p-2.5 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-700 dark:text-gray-200 mb-1">Correo electrónico *</label>
                    <input
                      type="email"
                      value={form.crr}
                      onChange={(e) => setForm((f) => ({ ...f, crr: e.target.value }))}
                      className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl block w-full p-2.5 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-700 dark:text-gray-200 mb-1">Rol *</label>
                    <select
                      value={form.rol_nombre}
                      onChange={(e) => setForm((f) => ({ ...f, rol_nombre: e.target.value }))}
                      className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl block w-full p-2.5 outline-none cursor-pointer"
                    >
                      <option value="">Selecciona un rol</option>
                      {ROLES_DISPONIBLES.map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-gray-700 dark:text-gray-200 mb-1">Teléfono (opcional)</label>
                    <input
                      type="text"
                      value={form.tlfn}
                      onChange={(e) => setForm((f) => ({ ...f, tlfn: e.target.value }))}
                      className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl block w-full p-2.5 outline-none"
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
                      className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 disabled:opacity-50 transition-colors"
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
            <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 overflow-hidden transition-colors duration-300">
              {/* Barra de Herramientas */}
              <div className="p-5 border-b border-black/10 dark:border-white/10 flex flex-col lg:flex-row gap-4 items-center">
                <div className="relative flex-1 w-full">
                  <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                    <svg className="w-5 h-5 text-gray-500 dark:text-gray-400" fill="none" viewBox="0 0 20 20">
                      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="m19 19-4-4m0-7A7 7 0 1 1 1 8a7 7 0 0 1 14 0Z" />
                    </svg>
                  </div>
                  <input
                    type="search"
                    placeholder="Buscar por nombre o correo..."
                    value={busquedaInput}
                    onChange={(e) => setBusquedaInput(e.target.value)}
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full pl-10 p-2.5 transition-all outline-none placeholder-gray-400"
                  />
                </div>

                <div className="flex w-full lg:w-auto gap-3">
                  <select
                    value={rol}
                    onChange={(e) => setRol(e.target.value)}
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block p-2.5 outline-none cursor-pointer"
                  >
                    <option value="">Todos los roles</option>
                    {ROLES_DISPONIBLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>

                  <select
                    value={estado}
                    onChange={(e) => setEstado(e.target.value)}
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block p-2.5 outline-none cursor-pointer"
                  >
                    <option value="">Todos los estados</option>
                    <option value="Activo">Activo</option>
                    <option value="Inactivo">Inactivo</option>
                  </select>
                </div>
              </div>

              {error && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-200 dark:border-red-800/30">
                  {error}
                </div>
              )}

              {/* Tabla */}
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-600 dark:text-gray-300">
                  <thead className="text-xs text-gray-600 dark:text-gray-300 uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
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
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          <div className="flex justify-center items-center gap-2">
                            <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                            <span>Cargando datos...</span>
                          </div>
                        </td>
                      </tr>
                    )}

                    {!loading && data?.items.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          No se encontraron usuarios con ese criterio.
                        </td>
                      </tr>
                    )}

                    {!loading &&
                      data?.items.map((u) => (
                        <tr
                          key={u.id_usr}
                          // CA3: la fila del usuario recién creado se resalta
                          // brevemente y se trae a la vista al volver al listado.
                          ref={u.id_usr === idResaltado ? filaResaltadaRef : undefined}
                          className={`border-b border-black/10 dark:border-white/10 transition-colors group ${
                            u.id_usr === idResaltado
                              ? "bg-[#ccff00]/10"
                              : "bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm hover:bg-black/5 dark:hover:bg-white/5 "
                          }`}
                        >
                          <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{u.nmbr_cmplt}</td>
                          <td className="px-6 py-4">{u.crr}</td>
                          <td className="px-6 py-4">{u.rol_nombre}</td>
                          <td className="px-6 py-4">
                            <span
                              className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${
                                u.estd === "Activo"
                                  ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#ccff00]/30"
                                  : "bg-black/5 dark:bg-white/10 text-gray-600 dark:text-gray-300 border-black/20 dark:border-white/20"
                              }`}
                            >
                              {u.estd === "Activo" && (
                                <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-[#ccff00]"></span>
                              )}
                              {u.estd}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-right">
                            <button
                              disabled
                              title="Próximamente: HU20"
                              className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 hover:text-gray-900 dark:hover:text-white focus:ring-4 focus:outline-none focus:ring-black/10 dark:focus:ring-white/10 disabled:opacity-50 disabled:hover:bg-transparent transition-all"
                            >
                              <svg className="w-4 h-4 mr-2 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
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
                <div className="p-5 border-t border-black/10 dark:border-white/10 flex items-center justify-between">
                  <span className="text-sm text-gray-600 dark:text-gray-300">
                    Mostrando <span className="font-semibold text-gray-900 dark:text-white">{inicioRango}</span> a{" "}
                    <span className="font-semibold text-gray-900 dark:text-white">{finRango}</span> de{" "}
                    <span className="font-semibold text-gray-900 dark:text-white">{data.total}</span> registros
                  </span>
                  <div className="inline-flex gap-2">
                    <button
                      disabled={pagina <= 1}
                      onClick={() => setPagina((p) => p - 1)}
                      className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      Anterior
                    </button>
                    <button
                      disabled={pagina >= totalPaginas}
                      onClick={() => setPagina((p) => p + 1)}
                      className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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