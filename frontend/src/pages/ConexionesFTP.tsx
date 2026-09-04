import { useEffect, useRef, useState, type FormEvent } from "react";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

const SEGUNDOS_CONFIRMACION = 5;

interface ConexionFTPListItem {
  id_cnxn: number;
  nmbr: string;
  id_sd: number;
  hst: string;
  prt: number;
  usr_ftp: string | null;
  rt_rmt: string | null;
  frcnc_mnts: number;
  estd: string;
}

interface ListadoPaginado {
  total: number;
  pagina: number;
  por_pagina: number;
  items: ConexionFTPListItem[];
}

interface Sede {
  id_sd: number;
  nmbr: string;
}

interface ConexionFTPForm {
  id_sd: string;
  nmbr: string;
  hst: string;
  prt: string;
  usr_ftp: string;
  contrasena_ftp: string;
  rt_rmt: string;
  frcnc_mnts: "1" | "60";
}

const POR_PAGINA = 10;

const FORM_VACIO: ConexionFTPForm = {
  id_sd: "",
  nmbr: "",
  hst: "",
  prt: "21", // CA: "el puerto es numérico con valor por defecto 21"
  usr_ftp: "",
  contrasena_ftp: "",
  rt_rmt: "",
  frcnc_mnts: "1",
};

function textoFrecuencia(frcnc_mnts: number): string {
  return frcnc_mnts === 1 ? "Cada minuto" : "Cada hora";
}

export default function ConexionesFTP() {
  const { nombreCompleto, rol, logout } = useAuth();

  const [pagina, setPagina] = useState(1);
  const [data, setData] = useState<ListadoPaginado | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Confirmación de borrado: id de la fila en confirmación + segundos
  // restantes antes de que el botón "Eliminar definitivamente" se habilite.
  const [confirmandoId, setConfirmandoId] = useState<number | null>(null);
  const [segundosRestantes, setSegundosRestantes] = useState(SEGUNDOS_CONFIRMACION);
  const [eliminandoId, setEliminandoId] = useState<number | null>(null);
  const intervaloRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function iniciarConfirmacion(id: number) {
    setConfirmandoId(id);
    setSegundosRestantes(SEGUNDOS_CONFIRMACION);
    if (intervaloRef.current) clearInterval(intervaloRef.current);
    intervaloRef.current = setInterval(() => {
      setSegundosRestantes((prev) => {
        if (prev <= 1) {
          if (intervaloRef.current) clearInterval(intervaloRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }

  function cancelarConfirmacion() {
    if (intervaloRef.current) clearInterval(intervaloRef.current);
    setConfirmandoId(null);
  }

  useEffect(() => {
    return () => {
      if (intervaloRef.current) clearInterval(intervaloRef.current);
    };
  }, []);

  async function handleEliminar(id: number) {
    setEliminandoId(id);
    setError(null);
    try {
      await apiFetch<{ mensaje: string }>(`/conexiones-ftp/${id}`, { method: "DELETE" });
      cancelarConfirmacion();
      cargarConexiones();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo eliminar la conexión");
    } finally {
      setEliminandoId(null);
    }
  }

  function cargarConexiones() {
    let cancelado = false;
    setLoading(true);
    setError(null);

    apiFetch<ListadoPaginado>("/conexiones-ftp", {
      params: { pagina, por_pagina: POR_PAGINA },
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
  }

  useEffect(cargarConexiones, [pagina]);

  // Selector de sede: un usuario con scope "global" (p. ej. Administrador o
  // Técnico CENERIS sin sede única asignada) debe indicar a qué sede
  // pertenece el datalogger (ver _resolver_sede en el backend).
  const [sedes, setSedes] = useState<Sede[]>([]);
  useEffect(() => {
    apiFetch<Sede[]>("/sedes").then(setSedes).catch(() => {});
  }, []);

  const totalPaginas = data ? Math.max(1, Math.ceil(data.total / data.por_pagina)) : 1;

  // Formulario de "Nueva conexión FTP" / "Editar" como ventana emergente
  // sobre el listado (mismo patrón que Parámetros y Dispositivos).
  const [mostrarFormulario, setMostrarFormulario] = useState(false);
  const [idEdicion, setIdEdicion] = useState<number | null>(null);
  const [form, setForm] = useState<ConexionFTPForm>(FORM_VACIO);
  const [probando, setProbando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [conexionValidada, setConexionValidada] = useState(false); // habilita GUARDAR
  const [mensaje, setMensaje] = useState("");
  const [mensajeOk, setMensajeOk] = useState(false);

  function abrirFormularioNueva() {
    setIdEdicion(null);
    setForm(FORM_VACIO);
    setConexionValidada(false);
    setMensaje("");
    setMostrarFormulario(true);
  }

  function abrirFormularioEditar(c: ConexionFTPListItem) {
    setIdEdicion(c.id_cnxn);
    setForm({
      id_sd: String(c.id_sd),
      nmbr: c.nmbr,
      hst: c.hst,
      prt: String(c.prt),
      usr_ftp: c.usr_ftp ?? "",
      contrasena_ftp: "",
      rt_rmt: c.rt_rmt ?? "",
      frcnc_mnts: c.frcnc_mnts === 1 ? "1" : "60",
    });
    setConexionValidada(false);
    setMensaje("");
    setMostrarFormulario(true);
  }

  function cerrarFormulario() {
    setMostrarFormulario(false);
  }

  function actualizarCampo<K extends keyof ConexionFTPForm>(campo: K, valor: ConexionFTPForm[K]) {
    setForm((prev) => ({ ...prev, [campo]: valor }));
    // CA: cualquier cambio invalida una prueba de conexión previa
    setConexionValidada(false);
  }

  function camposObligatoriosCompletos(): boolean {
    return Boolean(
      form.nmbr.trim() &&
        form.hst.trim() &&
        form.prt.trim() &&
        form.usr_ftp.trim() &&
        form.contrasena_ftp.trim() &&
        form.rt_rmt.trim()
    );
  }

  // CA: "El directorio remoto es una cadena de texto tipo ruta, por ejemplo /datos/estacion01."
  function rutaRemotaValida(): boolean {
    return form.rt_rmt.trim().startsWith("/");
  }

  async function handleProbarConexion() {
    setMensaje("");
    if (!camposObligatoriosCompletos()) {
      setMensajeOk(false);
      setMensaje("Completa todos los campos obligatorios antes de probar la conexión");
      return;
    }
    if (!rutaRemotaValida()) {
      setMensajeOk(false);
      setMensaje("El directorio remoto debe ser una ruta absoluta (ej. /datos/estacion01)");
      return;
    }

    setProbando(true);
    try {
      const res = await apiFetch<{ exitosa: boolean; mensaje: string }>("/conexiones-ftp/probar", {
        method: "POST",
        body: {
          hst: form.hst.trim(),
          prt: Number(form.prt),
          usr_ftp: form.usr_ftp.trim(),
          contrasena_ftp: form.contrasena_ftp,
          rt_rmt: form.rt_rmt.trim(),
        },
      });
      setConexionValidada(res.exitosa);
      setMensajeOk(res.exitosa);
      setMensaje(res.mensaje); // CA: "Conexión exitosa"
    } catch (err) {
      setConexionValidada(false);
      setMensajeOk(false);
      setMensaje(err instanceof ApiError ? err.message : "No se pudo probar la conexión");
    } finally {
      setProbando(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!conexionValidada) return; // CA: GUARDAR solo se habilita tras prueba exitosa

    const esEdicion = idEdicion !== null;

    // id_sd solo es obligatorio al crear: el backend infiere la sede del
    // usuario "por_sede" y, al editar, la sede de la conexión no se modifica.
    if (!esEdicion && !form.id_sd) {
      setMensajeOk(false);
      setMensaje("Selecciona la sede a la que pertenece este datalogger");
      return;
    }

    setGuardando(true);
    setMensaje("");
    try {
      const payload = {
        ...(esEdicion ? {} : { id_sd: Number(form.id_sd) }),
        nmbr: form.nmbr.trim(),
        hst: form.hst.trim(),
        prt: Number(form.prt),
        usr_ftp: form.usr_ftp.trim(),
        contrasena_ftp: form.contrasena_ftp,
        rt_rmt: form.rt_rmt.trim(),
        frcnc_mnts: Number(form.frcnc_mnts),
      };

      esEdicion
        ? await apiFetch<{ mensaje: string }>(`/conexiones-ftp/${idEdicion}`, { method: "PUT", body: payload })
        : await apiFetch<{ mensaje: string }>("/conexiones-ftp", { method: "POST", body: payload });

      setMostrarFormulario(false);
      cargarConexiones();
    } catch (err) {
      setMensajeOk(false);
      setMensaje(err instanceof ApiError ? err.message : "No se pudo guardar la conexión");
    } finally {
      setGuardando(false);
    }
  }

  const esEdicion = idEdicion !== null;

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="conexiones-ftp" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
            nombreCompleto={nombreCompleto}
            rol={rol}
            />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-extrabold text-gray-900 dark:text-white">Conexiones FTP</h1>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 font-light">
                  Conexiones FTP configuradas para la ingesta automática de telemetría.
                </p>
              </div>
              <button
                onClick={abrirFormularioNueva}
                className="px-4 py-2.5 text-sm font-semibold text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#ccff00]/30 rounded-xl transition-colors"
              >
                + Nueva conexión FTP
              </button>
            </header>

            <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 overflow-hidden transition-colors duration-300">
              {error && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-200 dark:border-red-800/30">
                  {error}
                </div>
              )}

              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-600 dark:text-gray-300">
                  <thead className="text-xs text-gray-600 dark:text-gray-300 uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
                    <tr>
                      <th className="px-6 py-4 font-bold tracking-wider">Conexión</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Host/IP</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Directorio remoto</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Frecuencia</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Estado</th>
                      <th className="px-6 py-4 font-bold tracking-wider text-right">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={6} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          <div className="flex justify-center items-center gap-2">
                            <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                            <span>Cargando conexiones...</span>
                          </div>
                        </td>
                      </tr>
                    )}

                    {!loading && data?.items.length === 0 && (
                      <tr>
                        <td colSpan={6} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          Todavía no hay conexiones FTP registradas.
                        </td>
                      </tr>
                    )}

                    {!loading &&
                      data?.items.map((c) => (
                        <tr
                          key={c.id_cnxn}
                          className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm border-b border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                        >
                          <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{c.nmbr}</td>
                          <td className="px-6 py-4">
                            {c.hst}:{c.prt}
                          </td>
                          <td className="px-6 py-4">{c.rt_rmt}</td>
                          <td className="px-6 py-4">{textoFrecuencia(c.frcnc_mnts)}</td>
                          <td className="px-6 py-4">
                            <span
                              className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${
                                c.estd === "Activa"
                                  ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#ccff00]/30"
                                  : "bg-black/5 dark:bg-white/10 text-gray-600 dark:text-gray-300 border-black/20 dark:border-white/20"
                              }`}
                            >
                              {c.estd === "Activa" && (
                                <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-[#ccff00]"></span>
                              )}
                              {c.estd}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-right">
                            {confirmandoId === c.id_cnxn ? (
                              <div className="inline-flex items-center gap-2">
                                <button
                                  type="button"
                                  onClick={() => handleEliminar(c.id_cnxn)}
                                  disabled={segundosRestantes > 0 || eliminandoId === c.id_cnxn}
                                  className="px-3 py-1.5 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                                >
                                  {eliminandoId === c.id_cnxn
                                    ? "Eliminando..."
                                    : segundosRestantes > 0
                                      ? `Confirmar (${segundosRestantes})`
                                      : "Confirmar eliminación"}
                                </button>
                                <button
                                  type="button"
                                  onClick={cancelarConfirmacion}
                                  disabled={eliminandoId === c.id_cnxn}
                                  className="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 transition-all"
                                >
                                  Cancelar
                                </button>
                              </div>
                            ) : (
                              <div className="inline-flex items-center gap-2">
                                <button
                                  type="button"
                                  onClick={() => abrirFormularioEditar(c)}
                                  className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 hover:text-gray-900 dark:hover:text-white transition-all"
                                >
                                  <svg
                                    className="w-4 h-4 mr-2 text-gray-600 dark:text-gray-300"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    strokeWidth="2"
                                    stroke="currentColor"
                                  >
                                    <path
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
                                      d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
                                    />
                                  </svg>
                                  Editar
                                </button>
                                <button
                                  type="button"
                                  onClick={() => iniciarConfirmacion(c.id_cnxn)}
                                  className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-red-600 dark:text-red-400 bg-transparent border border-black/20 dark:border-white/20 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-all"
                                >
                                  <svg
                                    className="w-4 h-4 mr-2"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    strokeWidth="2"
                                    stroke="currentColor"
                                  >
                                    <path
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
                                      d="M6 18L18 6M6 6l12 12"
                                    />
                                  </svg>
                                  Eliminar
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>

              {data && (
                <div className="p-5 border-t border-black/10 dark:border-white/10 flex items-center justify-between">
                  <span className="text-sm text-gray-600 dark:text-gray-300">
                    Página {data.pagina} de {totalPaginas}
                  </span>
                  <div className="flex gap-2">
                    <button
                      disabled={pagina <= 1}
                      onClick={() => setPagina((p) => p - 1)}
                      className="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Anterior
                    </button>
                    <button
                      disabled={pagina >= totalPaginas}
                      onClick={() => setPagina((p) => p + 1)}
                      className="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
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

      {mostrarFormulario && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-xl border border-black/10 dark:border-white/10">
            <form onSubmit={handleSubmit}>
              <div className="p-6 border-b border-black/10 dark:border-white/10">
                <h2 className="text-lg font-bold text-gray-900 dark:text-white">
                  {esEdicion ? "Editar conexión FTP" : "Nueva conexión FTP"}
                </h2>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 font-light">
                  Configura el acceso FTP de un servidor de telemetría. Luego podrás enlazar uno o varios
                  dispositivos a esta conexión desde la sección Dispositivos.
                </p>
              </div>

              <div className="p-6 space-y-4">
                {!esEdicion && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">Sede</label>
                    <select
                      required
                      value={form.id_sd}
                      onChange={(e) => actualizarCampo("id_sd", e.target.value)}
                      className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none cursor-pointer"
                    >
                      <option value="">— Selecciona una sede —</option>
                      {sedes.map((s) => (
                        <option key={s.id_sd} value={s.id_sd}>
                          {s.nmbr}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    Nombre de la conexión FTP
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="Ej: FTP Estación 01"
                    value={form.nmbr}
                    onChange={(e) => actualizarCampo("nmbr", e.target.value)}
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Identifica esta conexión FTP (puede reutilizarse para varios dispositivos). El nombre del
                    dispositivo se asigna por separado al crearlo.
                  </p>
                </div>

                <div className="grid grid-cols-3 gap-4">
                  <div className="col-span-2">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                      Host/IP
                    </label>
                    <input
                      type="text"
                      required
                      value={form.hst}
                      onChange={(e) => actualizarCampo("hst", e.target.value)}
                      className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">Puerto</label>
                    <input
                      type="number"
                      required
                      value={form.prt}
                      onChange={(e) => actualizarCampo("prt", e.target.value)}
                      className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                      Usuario FTP
                    </label>
                    <input
                      type="text"
                      required
                      value={form.usr_ftp}
                      onChange={(e) => actualizarCampo("usr_ftp", e.target.value)}
                      className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                      Contraseña FTP
                    </label>
                    <input
                      type="password"
                      required
                      value={form.contrasena_ftp}
                      onChange={(e) => actualizarCampo("contrasena_ftp", e.target.value)}
                      className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    Directorio remoto
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="/datos/estacion01"
                    value={form.rt_rmt}
                    onChange={(e) => actualizarCampo("rt_rmt", e.target.value)}
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    Frecuencia de polling
                  </label>
                  <select
                    value={form.frcnc_mnts}
                    onChange={(e) => actualizarCampo("frcnc_mnts", e.target.value as "1" | "60")}
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none cursor-pointer"
                  >
                    <option value="1">Cada minuto</option>
                    <option value="60">Cada hora</option>
                  </select>
                </div>

                {mensaje && (
                  <div
                    className={`p-3 rounded-xl text-sm ${
                      mensajeOk
                        ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00]"
                        : "bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400"
                    }`}
                  >
                    {mensaje}
                  </div>
                )}
              </div>

              <div className="p-6 border-t border-black/10 dark:border-white/10 flex flex-wrap justify-end gap-3">
                <button
                  type="button"
                  onClick={cerrarFormulario}
                  className="px-4 py-2.5 text-sm font-semibold text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-xl hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  onClick={handleProbarConexion}
                  disabled={probando}
                  className="px-4 py-2.5 text-sm font-medium text-gray-900 dark:text-white bg-transparent border border-black/20 dark:border-white/20 rounded-xl hover:bg-black/10 dark:hover:bg-white/10 disabled:opacity-50 transition-all"
                >
                  {probando ? "Probando..." : "Probar conexión"}
                </button>
                <button
                  type="submit"
                  disabled={!conexionValidada || guardando}
                  className="px-4 py-2.5 text-sm font-semibold text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#ccff00]/30 rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {guardando ? "Guardando..." : esEdicion ? "Actualizar" : "Guardar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
