import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

interface ParametroItem {
  id_prmtr: number;
  nmbr: string;
  undd: string;
}

interface UbicacionItem {
  id_ubccn: number;
  nmbr: string;
}

interface MedicionItem {
  id_lctr: number;
  fch_hr: string;
  ubicacion_nombre: string;
  parametro_nombre: string;
  undd: string;
  vlr: number;
}

interface ListadoMediciones {
  total: number;
  items: MedicionItem[];
}

function construirQuery(parametroIds: number[], ubicacionIds: number[]): string {
  const params = new URLSearchParams();
  parametroIds.forEach((id) => params.append("parametro_ids", String(id)));
  ubicacionIds.forEach((id) => params.append("ubicacion_ids", String(id)));
  const query = params.toString();
  return query ? `/mediciones?${query}` : "/mediciones";
}

export default function ConsultaDatos() {
  const { nombreCompleto, rol, logout } = useAuth();
  const [isDarkMode, setIsDarkMode] = useState(false);

  const [parametros, setParametros] = useState<ParametroItem[]>([]);
  const [ubicaciones, setUbicaciones] = useState<UbicacionItem[]>([]);

  // CA: selección en curso vs. filtros aplicados (se aplican al pulsar "APLICAR")
  const [seleccionParametros, setSeleccionParametros] = useState<number[]>([]);
  const [seleccionUbicaciones, setSeleccionUbicaciones] = useState<number[]>([]);
  const [filtroParametros, setFiltroParametros] = useState<number[]>([]);
  const [filtroUbicaciones, setFiltroUbicaciones] = useState<number[]>([]);

  const [mediciones, setMediciones] = useState<ListadoMediciones | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // CA1: carga los parámetros y ubicaciones disponibles para el usuario (HU21/HU06)
  useEffect(() => {
    apiFetch<{ items: ParametroItem[] }>("/mediciones/parametros")
      .then((res) => setParametros(res.items))
      .catch(() => setParametros([]));

    apiFetch<{ items: UbicacionItem[] }>("/ubicaciones", { params: { por_pagina: 100 } })
      .then((res) => setUbicaciones(res.items))
      .catch(() => setUbicaciones([]));
  }, []);

  useEffect(() => {
    let cancelado = false;
    setLoading(true);
    setError(null);

    apiFetch<ListadoMediciones>(construirQuery(filtroParametros, filtroUbicaciones))
      .then((res) => {
        if (!cancelado) setMediciones(res);
      })
      .catch((err) => {
        if (cancelado) return;
        setError(err instanceof ApiError ? err.message : "No se pudo cargar la telemetría");
      })
      .finally(() => {
        if (!cancelado) setLoading(false);
      });

    return () => {
      cancelado = true;
    };
  }, [filtroParametros, filtroUbicaciones]);

  const toggleSeleccion = (lista: number[], setLista: (v: number[]) => void, id: number) => {
    setLista(lista.includes(id) ? lista.filter((v) => v !== id) : [...lista, id]);
  };

  // CA2/CA3: "APLICAR" traslada la selección en curso a los filtros activos
  const handleAplicar = () => {
    setFiltroParametros(seleccionParametros);
    setFiltroUbicaciones(seleccionUbicaciones);
  };

  // CA4: "LIMPIAR FILTROS" quita los filtros y muestra todos los datos disponibles
  const handleLimpiar = () => {
    setSeleccionParametros([]);
    setSeleccionUbicaciones([]);
    setFiltroParametros([]);
    setFiltroUbicaciones([]);
  };

  return (
    <div className={`${isDarkMode ? "dark" : ""} font-sans`}>
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="consulta-datos" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
            isDarkMode={isDarkMode}
            onToggleDarkMode={() => setIsDarkMode(!isDarkMode)}
            nombreCompleto={nombreCompleto}
            rol={rol}
            />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6">
              <h1 className="text-2xl font-bold text-white">Consulta de Datos</h1>
              <p className="text-sm text-gray-300">
                Selecciona los parámetros y ubicaciones que quieres consultar para personalizar la vista de telemetría.
              </p>
            </header>

            <div className="bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-sm border border-white/10 p-5 mb-6">
              <div className="flex flex-col lg:flex-row gap-6">
                <fieldset className="flex-1">
                  <legend className="text-sm font-bold text-gray-200 mb-2">Parámetros</legend>
                  <div className="flex flex-wrap gap-3">
                    {parametros.length === 0 && (
                      <span className="text-sm text-gray-400">No hay parámetros disponibles.</span>
                    )}
                    {parametros.map((p) => (
                      <label key={p.id_prmtr} className="flex items-center gap-2 text-sm text-gray-200 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={seleccionParametros.includes(p.id_prmtr)}
                          onChange={() => toggleSeleccion(seleccionParametros, setSeleccionParametros, p.id_prmtr)}
                          className="accent-[#ccff00]"
                        />
                        {p.nmbr} ({p.undd})
                      </label>
                    ))}
                  </div>
                </fieldset>

                <fieldset className="flex-1">
                  <legend className="text-sm font-bold text-gray-200 mb-2">Ubicaciones</legend>
                  <div className="flex flex-wrap gap-3">
                    {ubicaciones.length === 0 && (
                      <span className="text-sm text-gray-400">No hay ubicaciones disponibles.</span>
                    )}
                    {ubicaciones.map((u) => (
                      <label key={u.id_ubccn} className="flex items-center gap-2 text-sm text-gray-200 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={seleccionUbicaciones.includes(u.id_ubccn)}
                          onChange={() => toggleSeleccion(seleccionUbicaciones, setSeleccionUbicaciones, u.id_ubccn)}
                          className="accent-[#ccff00]"
                        />
                        {u.nmbr}
                      </label>
                    ))}
                  </div>
                </fieldset>

                <div className="flex lg:flex-col gap-2 justify-end">
                  <button
                    type="button"
                    onClick={handleAplicar}
                    className="px-4 py-2 rounded-xl bg-[#ccff00] text-gray-900 text-sm font-bold hover:brightness-95 transition-all"
                  >
                    APLICAR
                  </button>
                  <button
                    type="button"
                    onClick={handleLimpiar}
                    className="px-4 py-2 rounded-xl border border-white/20 text-gray-200 text-sm font-bold hover:bg-white/10 transition-all"
                  >
                    LIMPIAR FILTROS
                  </button>
                </div>
              </div>
            </div>

            <div className="bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-sm border border-white/10">
              {error && (
                <div className="p-4 bg-red-900/20 text-red-400 text-sm border-b border-red-800/30">
                  {error}
                </div>
              )}
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-300">
                  <thead className="text-xs text-gray-300 uppercase bg-white/5 border-b border-white/10">
                    <tr>
                      <th className="px-6 py-4 font-bold tracking-wider">Parámetro</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Ubicación</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Valor</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Fecha</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={4} className="px-6 py-8 text-center text-gray-300">
                          Cargando datos...
                        </td>
                      </tr>
                    )}
                    {!loading && mediciones?.items.length === 0 && (
                      <tr>
                        <td colSpan={4} className="px-6 py-8 text-center text-gray-300">
                          No hay registros para los filtros seleccionados.
                        </td>
                      </tr>
                    )}
                    {!loading &&
                      mediciones?.items.map((m) => (
                        <tr
                          key={m.id_lctr}
                          className="bg-white/[0.04] backdrop-blur-md border-b border-white/10 hover:bg-white/5 transition-colors"
                        >
                          <td className="px-6 py-4 font-medium text-white">{m.parametro_nombre}</td>
                          <td className="px-6 py-4">{m.ubicacion_nombre}</td>
                          <td className="px-6 py-4">
                            {m.vlr} {m.undd}
                          </td>
                          <td className="px-6 py-4">{new Date(m.fch_hr).toLocaleString()}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
