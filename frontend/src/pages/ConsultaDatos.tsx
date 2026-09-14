import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import DrawerPanel from "../components/layout/DrawerPanel";
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

  // HU21: hasta que /ubicaciones responda no se sabe si el usuario tiene
  // ubicaciones asignadas; sin esto el mensaje parpadearía en cada carga.
  const [cargandoUbicaciones, setCargandoUbicaciones] = useState(true);

  // Los filtros (parámetros, ubicaciones, rango de fechas) ya no viven
  // apilados en la pantalla principal -diecisiete parámetros más siete
  // ubicaciones más el selector de fechas, todo en un único bloque
  // horizontal, se sentía denso y "de formulario"-. Viven en un panel
  // lateral (mismo patrón que "Dataloggers" en Gráficos), colapsado por
  // defecto.
  const [panelFiltrosAbierto, setPanelFiltrosAbierto] = useState(false);

  // CA1: carga los parámetros y ubicaciones disponibles para el usuario (HU21/HU06)
  useEffect(() => {
    apiFetch<{ items: ParametroItem[] }>("/mediciones/parametros")
      .then((res) => setParametros(res.items))
      .catch(() => setParametros([]));

    apiFetch<{ items: UbicacionItem[] }>("/ubicaciones", { params: { por_pagina: 100 } })
      .then((res) => setUbicaciones(res.items))
      .catch(() => setUbicaciones([]))
      .finally(() => setCargandoUbicaciones(false));
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

  /** HU21: "Un Cliente Final sin ninguna ubicación asignada ve el módulo de
   *  consulta vacío con el mensaje 'No tienes ubicaciones asignadas. Contacta
   *  al administrador.'"
   *
   *  Se deduce de que /ubicaciones -que ya filtra por prms_ubccn- no devuelva
   *  nada: los roles con acceso total siempre reciben todas las ubicaciones
   *  registradas, así que una lista vacía solo puede significar o que no hay
   *  ninguna ubicación en el sistema o que a este usuario no le asignaron
   *  ninguna. En ambos casos no hay nada que consultar. */
  const sinUbicacionesAsignadas = !cargandoUbicaciones && ubicaciones.length === 0;

  // Conteo de filtros YA APLICADOS (no la selección en curso dentro del
  // panel) para el badge del botón "Filtros": deja ver de un vistazo que
  // hay algo filtrado sin tener que abrir el panel a revisar.
  const filtrosActivos = filtroParametros.length + filtroUbicaciones.length;

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
          <div className="franja-superior flex justify-end p-4 md:p-6 pb-0">
            <Topbar
            nombreCompleto={nombreCompleto}
            rol={rol}
            />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6 flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Consulta de Datos</h1>
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  Selecciona los parámetros y ubicaciones que quieres consultar para personalizar la vista de telemetría.
                </p>
              </div>

              {/* Los filtros (17 parámetros + 7 ubicaciones + rango de
                  fechas, en la cuenta de prueba) se sacaron del flujo
                  principal de la pantalla -antes iban apilados en un
                  único bloque horizontal denso, tipo formulario- a un
                  panel lateral, mismo patrón que "Dataloggers" en
                  Gráficos. Este botón es el único punto de entrada;
                  muestra cuántos filtros hay aplicados sin necesidad de
                  abrir el panel. */}
              {!sinUbicacionesAsignadas && (
                <button
                  type="button"
                  onClick={() => setPanelFiltrosAbierto(true)}
                  className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#8fb300]/40 dark:border-[#ccff00]/30 rounded-xl transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                  </svg>
                  Filtros
                  {filtrosActivos > 0 && (
                    <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-bold bg-[#ccff00] text-gray-900">
                      {filtrosActivos}
                    </span>
                  )}
                </button>
              )}
            </header>

            {/* HU21: un Cliente Final sin ninguna ubicación asignada ve el
                módulo vacío con este mensaje exacto, en lugar de unos filtros
                y una tabla que nunca podrían devolver nada. */}
            {sinUbicacionesAsignadas && (
              <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-8 text-center">
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  No tienes ubicaciones asignadas. Contacta al administrador.
                </p>
              </div>
            )}

            {!sinUbicacionesAsignadas && (
            <>
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
            </>
            )}
          </main>
        </div>
      </div>

      {/* Panel lateral de filtros: drawer que se desliza desde la
          derecha, en vez de un bloque de filtros apilado en el flujo
          principal de la pantalla. */}
      <DrawerPanel
        abierto={panelFiltrosAbierto}
        onCerrar={() => setPanelFiltrosAbierto(false)}
        titulo="Filtros"
      >
            <div className="flex flex-col gap-6">
              <fieldset>
                <legend className="text-sm font-bold text-gray-700 dark:text-gray-200 mb-3">Parámetros</legend>
                <div className="flex flex-wrap gap-2">
                  {parametros.length === 0 && (
                    <span className="text-sm text-gray-500 dark:text-gray-400">No hay parámetros disponibles.</span>
                  )}
                  {/* Chips tipo toggle en vez de checkboxes nativos, mismo
                      patrón que el filtro de Parámetros en Gráficos.tsx:
                      sigue siendo un <input type="checkbox"> real (oculto
                      con sr-only), solo que su estado lo dibuja el propio
                      <label>. */}
                  {parametros.map((p) => {
                    const activo = seleccionParametros.includes(p.id_prmtr);
                    return (
                      <label
                        key={p.id_prmtr}
                        className={`inline-flex items-center gap-1.5 pl-3 pr-3.5 py-1.5 rounded-full text-sm font-medium cursor-pointer border transition-colors ${
                          activo
                            ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#8fb300]/40 dark:border-[#ccff00]/30"
                            : "bg-black/5 dark:bg-white/5 text-gray-600 dark:text-gray-300 border-transparent hover:bg-black/10 dark:hover:bg-white/10"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={activo}
                          onChange={() => toggleSeleccion(seleccionParametros, setSeleccionParametros, p.id_prmtr)}
                          className="sr-only"
                        />
                        {activo && (
                          <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                        {p.nmbr}
                        <span className={activo ? "text-[#5a7000]/70 dark:text-[#ccff00]/70" : "text-gray-500 dark:text-gray-400"}>
                          {p.undd}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>

              <fieldset className="pt-6 border-t border-black/10 dark:border-white/10">
                <legend className="text-sm font-bold text-gray-700 dark:text-gray-200 mb-3">Ubicaciones</legend>
                <div className="flex flex-wrap gap-2">
                  {ubicaciones.length === 0 && (
                    <span className="text-sm text-gray-500 dark:text-gray-400">No hay ubicaciones disponibles.</span>
                  )}
                  {ubicaciones.map((u) => {
                    const activo = seleccionUbicaciones.includes(u.id_ubccn);
                    return (
                      <label
                        key={u.id_ubccn}
                        className={`inline-flex items-center gap-1.5 pl-3 pr-3.5 py-1.5 rounded-full text-sm font-medium cursor-pointer border transition-colors ${
                          activo
                            ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#8fb300]/40 dark:border-[#ccff00]/30"
                            : "bg-black/5 dark:bg-white/5 text-gray-600 dark:text-gray-300 border-transparent hover:bg-black/10 dark:hover:bg-white/10"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={activo}
                          onChange={() => toggleSeleccion(seleccionUbicaciones, setSeleccionUbicaciones, u.id_ubccn)}
                          className="sr-only"
                        />
                        {activo && (
                          <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                        {u.nmbr}
                      </label>
                    );
                  })}
                </div>
              </fieldset>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleAplicar}
                  className="flex-1 px-4 py-2.5 rounded-xl bg-[#ccff00] text-gray-900 text-sm font-bold hover:brightness-95 transition-all"
                >
                  APLICAR
                </button>
                <button
                  type="button"
                  onClick={handleLimpiar}
                  className="flex-1 px-4 py-2.5 rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 text-sm font-bold hover:bg-black/10 dark:hover:bg-white/10 transition-all"
                >
                  LIMPIAR
                </button>
              </div>

              {/* HU12: rango de fechas con su propio par Aplicar/Limpiar,
                  independiente del de arriba -es una decisión de diseño
                  documentada en SelectorRangoFechas.tsx, no algo que
                  cambie acá: "LIMPIAR FILTROS" (HU13/DEC-11) solo
                  controla parámetros y ubicaciones-. */}
              <div className="pt-6 border-t border-black/10 dark:border-white/10">
                <SelectorRangoFechas
                  seleccion={seleccionFechas}
                  onCambiarSeleccion={setSeleccionFechas}
                  onAplicar={handleAplicarFechas}
                  onLimpiar={handleLimpiarFechas}
                />
              </div>
            </div>
      </DrawerPanel>
    </div>
  );
}
