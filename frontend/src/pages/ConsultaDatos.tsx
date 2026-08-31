import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import SelectorRangoFechas from "../components/SelectorRangoFechas";
import { formatearFechaHoraEnZona, rangoUltimas24Horas, type RangoFechas } from "../utils/fechas";

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
  id_registro: number;
  fch_hr: string;
  ubicacion_nombre: string;
  parametro_nombre: string;
  undd: string;
  vlr: number | string;
}

interface ListadoMediciones {
  total: number;
  items: MedicionItem[];
}

function construirQuery(
  parametroIds: number[],
  ubicacionIds: number[],
  rangoFechas: RangoFechas | null,
): string {
  const params = new URLSearchParams();
  parametroIds.forEach((id) => params.append("parametro_ids", String(id)));
  ubicacionIds.forEach((id) => params.append("ubicacion_ids", String(id)));
  if (rangoFechas) {
    params.append("fecha_inicio", new Date(rangoFechas.inicio).toISOString());
    params.append("fecha_fin", new Date(rangoFechas.fin).toISOString());
  }
  const query = params.toString();
  return query ? `/mediciones?${query}` : "/mediciones";
}

export default function ConsultaDatos() {
  const { nombreCompleto, rol, logout, zonaHoraria } = useAuth();

  // HU19 CA4: "VER HISTORIAL DE DATOS" desde el panel de estadísticas de un
  // dispositivo llega acá con su ubicación preseleccionada -este módulo
  // solo filtra por ubicación, no por dispositivo-, mismo patrón que
  // ubicacion_id en Graficos.tsx (HU17 CA4).
  const [searchParams] = useSearchParams();
  const ubicacionIdParam = searchParams.get("ubicacion_id");
  const ubicacionIdInicial = ubicacionIdParam !== null ? Number(ubicacionIdParam) : null;
  const ubicacionesIniciales =
    ubicacionIdInicial !== null && Number.isFinite(ubicacionIdInicial) ? [ubicacionIdInicial] : [];

  const [parametros, setParametros] = useState<ParametroItem[]>([]);
  const [ubicaciones, setUbicaciones] = useState<UbicacionItem[]>([]);

  // CA: selección en curso vs. filtros aplicados (se aplican al pulsar "APLICAR")
  const [seleccionParametros, setSeleccionParametros] = useState<number[]>([]);
  const [seleccionUbicaciones, setSeleccionUbicaciones] = useState<number[]>(ubicacionesIniciales);
  const [filtroParametros, setFiltroParametros] = useState<number[]>([]);
  const [filtroUbicaciones, setFiltroUbicaciones] = useState<number[]>(ubicacionesIniciales);

  // HU12: rango de fechas, con su propia selección/filtro aplicado.
  // CA: el rango por defecto al ingresar al módulo son las últimas 24 horas.
  const [seleccionFechas, setSeleccionFechas] = useState<RangoFechas>(rangoUltimas24Horas);
  const [filtroFechas, setFiltroFechas] = useState<RangoFechas>(rangoUltimas24Horas);

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

    apiFetch<ListadoMediciones>(construirQuery(filtroParametros, filtroUbicaciones, filtroFechas))
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
  }, [filtroParametros, filtroUbicaciones, filtroFechas]);

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

  // HU12 CA2/CA3: aplica el rango de fechas en curso como filtro activo
  const handleAplicarFechas = (rango: RangoFechas) => {
    setFiltroFechas(rango);
  };

  // HU12 CA4: "LIMPIAR FILTRO" vuelve al rango por defecto (últimas 24 horas)
  const handleLimpiarFechas = () => {
    const rangoPorDefecto = rangoUltimas24Horas();
    setSeleccionFechas(rangoPorDefecto);
    setFiltroFechas(rangoPorDefecto);
  };

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="consulta-datos" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
            nombreCompleto={nombreCompleto}
            rol={rol}
            />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Consulta de Datos</h1>
              <p className="text-sm text-gray-600 dark:text-gray-300">
                Selecciona los parámetros y ubicaciones que quieres consultar para personalizar la vista de telemetría.
              </p>
            </header>

            <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-5 mb-6">
              <div className="flex flex-col lg:flex-row gap-6">
                <fieldset className="flex-1">
                  <legend className="text-sm font-bold text-gray-700 dark:text-gray-200 mb-2">Parámetros</legend>
                  <div className="flex flex-wrap gap-3">
                    {parametros.length === 0 && (
                      <span className="text-sm text-gray-500 dark:text-gray-400">No hay parámetros disponibles.</span>
                    )}
                    {parametros.map((p) => (
                      <label key={p.id_prmtr} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200 cursor-pointer">
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
                  <legend className="text-sm font-bold text-gray-700 dark:text-gray-200 mb-2">Ubicaciones</legend>
                  <div className="flex flex-wrap gap-3">
                    {ubicaciones.length === 0 && (
                      <span className="text-sm text-gray-500 dark:text-gray-400">No hay ubicaciones disponibles.</span>
                    )}
                    {ubicaciones.map((u) => (
                      <label key={u.id_ubccn} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200 cursor-pointer">
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
                    className="px-4 py-2 rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 text-sm font-bold hover:bg-black/10 dark:hover:bg-white/10 transition-all"
                  >
                    LIMPIAR FILTROS
                  </button>
                </div>
              </div>

              <div className="mt-6 pt-6 border-t border-black/10 dark:border-white/10">
                <SelectorRangoFechas
                  seleccion={seleccionFechas}
                  onCambiarSeleccion={setSeleccionFechas}
                  onAplicar={handleAplicarFechas}
                  onLimpiar={handleLimpiarFechas}
                />
              </div>
            </div>

            <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10">
              {error && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-200 dark:border-red-800/30">
                  {error}
                </div>
              )}
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-600 dark:text-gray-300">
                  <thead className="text-xs text-gray-600 dark:text-gray-300 uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
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
                        <td colSpan={4} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          Cargando datos...
                        </td>
                      </tr>
                    )}
                    {!loading && mediciones?.items.length === 0 && (
                      <tr>
                        <td colSpan={4} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          No hay registros para los filtros seleccionados.
                        </td>
                      </tr>
                    )}
                    {!loading &&
                      mediciones?.items.map((m) => (
                        <tr
                          key={m.id_registro}
                          className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm border-b border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                        >
                          <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{m.parametro_nombre}</td>
                          <td className="px-6 py-4">{m.ubicacion_nombre}</td>
                          <td className="px-6 py-4">
                            {m.vlr}
                            {typeof m.vlr === "number" && m.undd ? ` ${m.undd}` : ""}
                          </td>
                          <td className="px-6 py-4">{formatearFechaHoraEnZona(m.fch_hr, zonaHoraria)}</td>
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
