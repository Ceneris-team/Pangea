import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiFetch, apiUpload, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

/**
 * HU06 - Mapear formato de marca de sensor.
 *
 *   CA1  formulario "Nuevo mapeo" + tabla de asignación columna -> parámetro
 *   CA2  "Vista previa" con un .dat de muestra (el archivo NO se persiste)
 *   CA3  "Guardar"    -> "Mapeo guardado correctamente"
 *   CA4  "Actualizar" -> "Mapeo actualizado correctamente"
 *
 * La tabla de asignación se puebla sola tras la vista previa: es el
 * momento en que se conocen los nombres reales de las columnas del
 * archivo. Antes de eso no hay contra qué asignar.
 */

interface Parametro {
  id_prmtr: number;
  nmbr: string;
  undd: string;
  dscrpcn: string | null;
}

interface Sede {
  id_sd: number;
  nmbr: string;
}

interface ColumnaVistaPrevia {
  indc_clmn: number;
  nombre_columna: string;
  parametro_nombre: string | null;
  parametro_unidad: string | null;
}

interface FilaVistaPrevia {
  numero_fila: number;
  fecha_hora: string | null;
  error: string | null;
  valores: Record<string, string | null>;
}

interface VistaPreviaResponse {
  columnas: ColumnaVistaPrevia[];
  filas: FilaVistaPrevia[];
  total_filas_archivo: number;
  filas_mostradas: number;
}

interface MapeoColumnaDetalle {
  indc_clmn: number;
  id_prmtr: number;
  parametro_nombre: string;
  parametro_unidad: string;
}

interface MapeoDetalle {
  id_mp: number;
  id_sd: number;
  mrc: string;
  tp_trm: string;
  dlmtdr: string;
  fl_inc_dts: number;
  frmt_fch: string;
  estd: string;
  columnas: MapeoColumnaDetalle[];
}

interface MapeoForm {
  id_sd: string;
  mrc: string;
  tp_trm: "H" | "E";
  dlmtdr: string;
  fl_inc_dts: string;
  frmt_fch: string;
  columna_fecha: string;
}

// Regla de negocio HU06: el delimitador acepta solo estos cuatro.
const DELIMITADORES = [
  { valor: ",", etiqueta: "Coma (,)" },
  { valor: ";", etiqueta: "Punto y coma (;)" },
  { valor: "tab", etiqueta: "Tabulador" },
  { valor: "espacio", etiqueta: "Espacio" },
];

const FORM_VACIO: MapeoForm = {
  id_sd: "",
  mrc: "",
  tp_trm: "H",
  dlmtdr: ",",
  fl_inc_dts: "1", // regla de negocio: entero, por defecto 1
  frmt_fch: "YYYY-MM-DD HH:mm:ss",
  columna_fecha: "Fecha",
};

export default function ConfigurarMapeo() {
  const { id } = useParams();
  const esEdicion = Boolean(id);
  const navigate = useNavigate();
  const { nombreCompleto, rol, logout } = useAuth();
  const [isDarkMode, setIsDarkMode] = useState(false);

  const [form, setForm] = useState<MapeoForm>(FORM_VACIO);
  const [parametros, setParametros] = useState<Parametro[]>([]);
  const [sedes, setSedes] = useState<Sede[]>([]);

  const [archivo, setArchivo] = useState<File | null>(null);
  const [vistaPrevia, setVistaPrevia] = useState<VistaPreviaResponse | null>(null);
  // indice de columna -> id_prmtr asignado. Es la tabla de asignación de CA1.
  const [asignaciones, setAsignaciones] = useState<Record<number, number>>({});

  const [cargando, setCargando] = useState(false);
  const [previsualizando, setPrevisualizando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [mensaje, setMensaje] = useState("");
  const [mensajeOk, setMensajeOk] = useState(false);

  // CA1: el selector de parámetro estándar de la tabla de asignación.
  useEffect(() => {
    apiFetch<Parametro[]>("/parametros")
      .then(setParametros)
      .catch((err) => {
        setMensajeOk(false);
        setMensaje(
          err instanceof ApiError ? err.message : "No se pudieron cargar los parámetros estándar"
        );
      });
  }, []);

  // Selector de sede: un usuario con scope "global" debe indicar a qué
  // sede pertenece el mapeo (ver _resolver_sede en el backend).
  useEffect(() => {
    apiFetch<Sede[]>("/sedes")
      .then(setSedes)
      .catch((err) => {
        setMensajeOk(false);
        setMensaje(err instanceof ApiError ? err.message : "No se pudieron cargar las sedes");
      });
  }, []);

  // CA4: al abrir un mapeo existente se cargan sus datos y su asignación.
  useEffect(() => {
    if (!id) return;
    setCargando(true);
    apiFetch<MapeoDetalle>(`/mapeos/${id}`)
      .then((detalle) => {
        setForm({
          id_sd: String(detalle.id_sd),
          mrc: detalle.mrc,
          tp_trm: detalle.tp_trm === "E" ? "E" : "H",
          dlmtdr: detalle.dlmtdr,
          fl_inc_dts: String(detalle.fl_inc_dts),
          frmt_fch: detalle.frmt_fch,
          columna_fecha: FORM_VACIO.columna_fecha,
        });
        setAsignaciones(
          Object.fromEntries(detalle.columnas.map((c) => [c.indc_clmn, c.id_prmtr]))
        );
      })
      .catch((err) => {
        setMensajeOk(false);
        setMensaje(err instanceof ApiError ? err.message : "No se pudo cargar el mapeo");
      })
      .finally(() => setCargando(false));
  }, [id]);

  function actualizarCampo<K extends keyof MapeoForm>(campo: K, valor: MapeoForm[K]) {
    setForm((prev) => ({ ...prev, [campo]: valor }));
  }

  function seleccionarArchivo(e: ChangeEvent<HTMLInputElement>) {
    setArchivo(e.target.files?.[0] ?? null);
    setVistaPrevia(null);
  }

  function serializarAsignaciones(): string {
    return Object.entries(asignaciones)
      .filter(([, idParametro]) => Boolean(idParametro))
      .map(([indice, idParametro]) => `${indice}:${idParametro}`)
      .join(",");
  }

  /** CA2: sube el .dat de muestra y muestra las 10 primeras filas ya
   *  interpretadas. El archivo es temporal: no se guarda en la BD. */
  async function handleVistaPrevia() {
    if (!archivo) {
      setMensajeOk(false);
      setMensaje("Selecciona un archivo .dat de muestra para ver la vista previa");
      return;
    }

    setPrevisualizando(true);
    setMensaje("");
    try {
      const formData = new FormData();
      formData.append("archivo", archivo);
      formData.append("dlmtdr", form.dlmtdr);
      formData.append("fl_inc_dts", form.fl_inc_dts);
      formData.append("frmt_fch", form.frmt_fch);
      formData.append("columna_fecha", form.columna_fecha);
      formData.append("asignaciones", serializarAsignaciones());

      const res = await apiUpload<VistaPreviaResponse>("/mapeos/vista-previa", formData);
      setVistaPrevia(res);
    } catch (err) {
      setVistaPrevia(null);
      setMensajeOk(false);
      setMensaje(err instanceof ApiError ? err.message : "No se pudo generar la vista previa");
    } finally {
      setPrevisualizando(false);
    }
  }

  /** CA3 (crear) y CA4 (actualizar). */
  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    // Campos obligatorios según la HU: marca, delimitador y tipo de trama
    // (este último ocupa el lugar de "extensión de archivo", ver README).
    // id_sd solo es obligatorio al crear: el backend infiere la sede del
    // usuario "por_sede" y, al editar, la sede del mapeo no se modifica.
    if (!form.mrc.trim() || !form.dlmtdr) {
      setMensajeOk(false);
      setMensaje("La marca y el delimitador son obligatorios");
      return;
    }
    if (!esEdicion && !form.id_sd) {
      setMensajeOk(false);
      setMensaje("Selecciona la sede a la que pertenece este mapeo");
      return;
    }

    setGuardando(true);
    setMensaje("");
    try {
      const columnas = Object.entries(asignaciones)
        .filter(([, idParametro]) => Boolean(idParametro))
        .map(([indice, idParametro]) => ({
          indc_clmn: Number(indice),
          id_prmtr: Number(idParametro),
        }));

      const payload = {
        ...(esEdicion ? {} : { id_sd: Number(form.id_sd) }),
        mrc: form.mrc.trim(),
        tp_trm: form.tp_trm,
        dlmtdr: form.dlmtdr,
        fl_inc_dts: Number(form.fl_inc_dts),
        frmt_fch: form.frmt_fch.trim(),
        columnas,
      };

      const res = esEdicion
        ? await apiFetch<{ mensaje: string }>(`/mapeos/${id}`, { method: "PUT", body: payload })
        : await apiFetch<{ mensaje: string }>("/mapeos", { method: "POST", body: payload });

      setMensajeOk(true);
      setMensaje(res.mensaje); // "Mapeo guardado/actualizado correctamente"
    } catch (err) {
      setMensajeOk(false);
      setMensaje(err instanceof ApiError ? err.message : "No se pudo guardar el mapeo");
    } finally {
      setGuardando(false);
    }
  }

  const inputClase =
    "bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none";
  const labelClase = "block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1";

  // CA4: al editar, la asignación guardada existe aunque todavía no se
  // haya subido un archivo de muestra en esta sesión. Se muestra igual.
  const filasAsignacion =
    vistaPrevia?.columnas ??
    Object.keys(asignaciones)
      .map(Number)
      .sort((a, b) => a - b)
      .map((indice) => ({
        indc_clmn: indice,
        nombre_columna: `Columna ${indice}`,
        parametro_nombre: null,
        parametro_unidad: null,
      }));

  return (
    <div className={`${isDarkMode ? "dark" : ""} font-sans`}>
      <div className="flex h-screen bg-gray-50 dark:bg-gray-900 transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="mapeos" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <Topbar
            isDarkMode={isDarkMode}
            onToggleDarkMode={() => setIsDarkMode(!isDarkMode)}
            nombreCompleto={nombreCompleto}
            rol={rol}
          />

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6">
              <h1 className="text-2xl font-extrabold text-gray-900 dark:text-white">
                {esEdicion ? "Editar mapeo de formato" : "Nuevo mapeo de formato"}
              </h1>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 font-light">
                Define cómo se interpretan los archivos .dat de una marca de sensor.
              </p>
            </header>

            {cargando ? (
              <div className="text-sm text-gray-500 dark:text-gray-400">Cargando mapeo…</div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-6">
                {/* CA1: datos del formato */}
                <section className="bg-white dark:bg-[#2d3748] rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
                  <h2 className="text-base font-bold text-gray-900 dark:text-white mb-4">Datos del formato</h2>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {!esEdicion && (
                      <div>
                        <label className={labelClase}>Sede *</label>
                        <select
                          required
                          value={form.id_sd}
                          onChange={(e) => actualizarCampo("id_sd", e.target.value)}
                          className={inputClase + " cursor-pointer"}
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
                      <label className={labelClase}>Nombre de marca *</label>
                      <input
                        type="text"
                        required
                        placeholder="Campbell Scientific"
                        value={form.mrc}
                        onChange={(e) => actualizarCampo("mrc", e.target.value)}
                        className={inputClase}
                      />
                    </div>

                    <div>
                      <label className={labelClase}>Tipo de trama *</label>
                      <select
                        value={form.tp_trm}
                        onChange={(e) => actualizarCampo("tp_trm", e.target.value as "H" | "E")}
                        className={inputClase + " cursor-pointer"}
                      >
                        <option value="H">H · Datos periódicos (H_*.dat)</option>
                        <option value="E">E · Estados y eventos (E_*.dat)</option>
                      </select>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        Determina la extensión/prefijo del archivo que aplica a este mapeo.
                      </p>
                    </div>

                    <div>
                      <label className={labelClase}>Delimitador *</label>
                      <select
                        value={form.dlmtdr}
                        onChange={(e) => actualizarCampo("dlmtdr", e.target.value)}
                        className={inputClase + " cursor-pointer"}
                      >
                        {DELIMITADORES.map((d) => (
                          <option key={d.valor} value={d.valor}>
                            {d.etiqueta}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className={labelClase}>Fila de inicio de datos</label>
                      <input
                        type="number"
                        min={1}
                        value={form.fl_inc_dts}
                        onChange={(e) => actualizarCampo("fl_inc_dts", e.target.value)}
                        className={inputClase}
                      />
                    </div>

                    <div>
                      <label className={labelClase}>Formato de fecha/hora</label>
                      <input
                        type="text"
                        placeholder="YYYY-MM-DD HH:mm:ss"
                        value={form.frmt_fch}
                        onChange={(e) => actualizarCampo("frmt_fch", e.target.value)}
                        className={inputClase}
                      />
                    </div>

                    <div>
                      <label className={labelClase}>Columna de fecha</label>
                      <input
                        type="text"
                        placeholder="Fecha"
                        value={form.columna_fecha}
                        onChange={(e) => actualizarCampo("columna_fecha", e.target.value)}
                        className={inputClase}
                      />
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        Solo afecta la vista previa: el motor de ingesta usa "Fecha" (ver README).
                      </p>
                    </div>
                  </div>
                </section>

                {/* CA2: vista previa con archivo de muestra */}
                <section className="bg-white dark:bg-[#2d3748] rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
                  <h2 className="text-base font-bold text-gray-900 dark:text-white mb-1">Vista previa</h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mb-4 font-light">
                    Carga un archivo .dat de muestra para ver las primeras 10 filas interpretadas. El archivo
                    no se guarda.
                  </p>

                  <div className="flex flex-wrap items-center gap-3">
                    <input
                      type="file"
                      accept=".dat,.csv,.txt"
                      onChange={seleccionarArchivo}
                      className="text-sm text-gray-600 dark:text-gray-300 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-[#ccff00]/10 file:text-[#5a7000] dark:file:text-[#ccff00] hover:file:bg-[#ccff00]/20 file:cursor-pointer"
                    />
                    <button
                      type="button"
                      onClick={handleVistaPrevia}
                      disabled={previsualizando || !archivo}
                      className="px-4 py-2.5 text-sm font-medium text-gray-900 dark:text-white bg-white dark:bg-transparent border border-gray-300 dark:border-gray-600 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                    >
                      {previsualizando ? "Generando…" : "Vista previa"}
                    </button>
                  </div>

                  {vistaPrevia && (
                    <div className="mt-5">
                      <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                        Mostrando {vistaPrevia.filas_mostradas} de {vistaPrevia.total_filas_archivo} filas del
                        archivo.
                      </p>
                      <div className="overflow-x-auto border border-gray-200 dark:border-gray-700 rounded-xl">
                        <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                          <thead className="text-xs uppercase bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                            <tr>
                              <th className="px-4 py-3 font-bold">Fila</th>
                              {vistaPrevia.columnas.map((c) => (
                                <th key={c.indc_clmn} className="px-4 py-3 font-bold whitespace-nowrap">
                                  <div className="text-gray-700 dark:text-gray-200">{c.nombre_columna}</div>
                                  <div className="normal-case font-normal text-[11px] text-[#5a7000] dark:text-[#ccff00]">
                                    {c.parametro_nombre
                                      ? `→ ${c.parametro_nombre} (${c.parametro_unidad})`
                                      : "sin asignar"}
                                  </div>
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {vistaPrevia.filas.map((fila) => (
                              <tr
                                key={fila.numero_fila}
                                className="border-b border-gray-100 dark:border-gray-700 last:border-0"
                              >
                                <td className="px-4 py-2 font-mono text-xs">
                                  {fila.numero_fila}
                                  {fila.error && (
                                    <span className="ml-2 text-red-600 dark:text-red-400" title={fila.error}>
                                      ⚠
                                    </span>
                                  )}
                                </td>
                                {vistaPrevia.columnas.map((c) => (
                                  <td key={c.indc_clmn} className="px-4 py-2 whitespace-nowrap font-mono text-xs">
                                    {fila.valores[c.nombre_columna] ?? ""}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </section>

                {/* CA1: tabla de asignación columna -> parámetro estándar */}
                <section className="bg-white dark:bg-[#2d3748] rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
                  <h2 className="text-base font-bold text-gray-900 dark:text-white mb-1">
                    Asignación de columnas
                  </h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mb-4 font-light">
                    Indica qué parámetro estándar corresponde a cada columna del archivo.
                  </p>

                  {filasAsignacion.length === 0 ? (
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      Genera primero una vista previa para ver las columnas del archivo.
                    </p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                        <thead className="text-xs uppercase bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                          <tr>
                            <th className="px-4 py-3 font-bold w-20">Índice</th>
                            <th className="px-4 py-3 font-bold">Columna del archivo</th>
                            <th className="px-4 py-3 font-bold">Parámetro estándar</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filasAsignacion.map((c) => (
                            <tr key={c.indc_clmn} className="border-b border-gray-100 dark:border-gray-700 last:border-0">
                              <td className="px-4 py-2 font-mono text-xs">{c.indc_clmn}</td>
                              <td className="px-4 py-2 text-gray-900 dark:text-white">{c.nombre_columna}</td>
                              <td className="px-4 py-2">
                                <select
                                  value={asignaciones[c.indc_clmn] ?? ""}
                                  onChange={(e) => {
                                    const valor = e.target.value;
                                    setAsignaciones((prev) => {
                                      const siguiente = { ...prev };
                                      if (valor) siguiente[c.indc_clmn] = Number(valor);
                                      else delete siguiente[c.indc_clmn];
                                      return siguiente;
                                    });
                                  }}
                                  className={inputClase + " cursor-pointer max-w-xs"}
                                >
                                  <option value="">— Sin asignar —</option>
                                  {parametros.map((p) => (
                                    <option key={p.id_prmtr} value={p.id_prmtr}>
                                      {p.nmbr} ({p.undd})
                                    </option>
                                  ))}
                                </select>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>

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

                <div className="flex flex-wrap gap-3">
                  <button
                    type="submit"
                    disabled={guardando}
                    className="px-4 py-2.5 text-sm font-semibold text-[#0c1712] bg-[#ccff00] rounded-xl hover:bg-[#b8e600] disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                  >
                    {guardando ? "Guardando…" : esEdicion ? "Actualizar" : "Guardar"}
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate("/mapeos")}
                    className="px-4 py-2.5 text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-all"
                  >
                    Ver mapeos
                  </button>
                </div>
              </form>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
