import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { apiFetch, apiUpload, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

/**
 * HU06 - Mapear formato de dispositivo.
 *
 *   CA1  formulario "Nuevo mapeo" + tabla de asignación columna -> parámetro
 *   CA2  "Vista previa" con un .dat de muestra (el archivo NO se persiste)
 *   CA3  "Guardar"    -> "Mapeo guardado correctamente"
 *   CA4  "Actualizar" -> "Mapeo actualizado correctamente"
 *
 * El mapeo cuelga del DISPOSITIVO (no de la marca): dos dispositivos de la
 * misma marca pueden traer sus columnas en distinto orden en campo, así
 * que ya no hay un mapeo compartido por marca+sede. El dispositivo se
 * elige al crear y no cambia al editar.
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

/** DEC-09: el mapeo se cuelga de un dispositivo concreto. La marca y la
 *  ubicación/sede se muestran en solo-lectura a partir del dispositivo
 *  elegido; ya no se eligen ni se tipean aparte. */
interface DispositivoOption {
  id_dspstv: number;
  nmbr: string;
  mrc: string;
  ubicacion_nombre: string;
  estd: string;
}

interface ColumnaVistaPrevia {
  indc_clmn: number;
  nombre_columna: string;
  parametro_nombre: string | null;
  parametro_unidad: string | null;
  id_prmtr_sugerido: number | null;
}

interface DispositivoParaMapeo {
  id_dspstv: number;
  nmbr: string;
  mrc: string;
  mdl: string | null;
}

interface ArchivoFtpDisponible {
  nombre_archivo: string;
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
  id_dspstv: number;
  dispositivo_nombre: string;
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
  id_dspstv: string;
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
  id_dspstv: "",
  tp_trm: "H",
  dlmtdr: ",",
  fl_inc_dts: "1", // regla de negocio: entero, por defecto 1
  frmt_fch: "YYYY-MM-DD HH:mm:ss",
  columna_fecha: "Fecha",
};

export default function ConfigurarMapeo() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const esEdicion = Boolean(id);
  const navigate = useNavigate();
  const { nombreCompleto, rol, logout } = useAuth();

  // Al llegar desde "Configurar mapeo" en Dispositivos, el dispositivo
  // viene preseleccionado por query param.
  const [form, setForm] = useState<MapeoForm>({
    ...FORM_VACIO,
    id_dspstv: searchParams.get("id_dspstv") ?? "",
  });
  const [parametros, setParametros] = useState<Parametro[]>([]);
  const [dispositivos, setDispositivos] = useState<DispositivoOption[]>([]);

  const [archivo, setArchivo] = useState<File | null>(null);
  const [vistaPrevia, setVistaPrevia] = useState<VistaPreviaResponse | null>(null);
  // indice de columna -> id_prmtr asignado. Es la tabla de asignación de CA1.
  const [asignaciones, setAsignaciones] = useState<Record<number, number>>({});

  // Solo para mostrar en modo edición (id_dspstv no es editable).
  const [dispositivoInfo, setDispositivoInfo] = useState<{ nombre: string; marca: string } | null>(
    null
  );
  // Fuente de la muestra para la vista previa: subir un .dat a mano, o
  // elegir uno ya recibido por FTP para un dispositivo (evita el paso
  // manual de bajarlo del servidor y volverlo a subir).
  const [fuenteMuestra, setFuenteMuestra] = useState<"archivo" | "ftp">("archivo");
  const [dispositivos, setDispositivos] = useState<DispositivoParaMapeo[]>([]);
  const [dispositivoFtp, setDispositivoFtp] = useState("");
  const [archivosFtp, setArchivosFtp] = useState<ArchivoFtpDisponible[]>([]);
  const [archivoFtpElegido, setArchivoFtpElegido] = useState("");
  const [cargandoArchivosFtp, setCargandoArchivosFtp] = useState(false);

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

  // DEC-09 CA1: selector de Dispositivo. Reusa GET /dispositivos (HU10),
  // mismo patrón de fetch que AgregarDispositivo.tsx usa para sus selectores.
  useEffect(() => {
    apiFetch<{ items: DispositivoOption[] }>("/dispositivos", {
      params: { por_pagina: 100 },
    })
      .then((res) => setDispositivos(res.items))
      .catch((err) => {
        setMensajeOk(false);
        setMensaje(
          err instanceof ApiError ? err.message : "No se pudieron cargar los dispositivos"
        );
      });
  }, []);

  // Al elegir un dispositivo, lista los .dat que están ahora mismo en su
  // carpeta remota para poder elegir uno como muestra.
  useEffect(() => {
    if (!dispositivoFtp) {
      setArchivosFtp([]);
      setArchivoFtpElegido("");
      return;
    }
    let cancelado = false;
    setCargandoArchivosFtp(true);
    setArchivosFtp([]);
    setArchivoFtpElegido("");
    apiFetch<ArchivoFtpDisponible[]>(`/mapeos/dispositivos/${dispositivoFtp}/archivos-ftp`)
      .then((res) => {
        if (cancelado) return;
        setArchivosFtp(res);
      })
      .catch((err) => {
        if (cancelado) return;
        setMensajeOk(false);
        setMensaje(err instanceof ApiError ? err.message : "No se pudo listar los archivos del FTP");
      })
      .finally(() => {
        if (!cancelado) setCargandoArchivosFtp(false);
      });
    return () => {
      cancelado = true;
    };
  }, [dispositivoFtp]);

  // CA4: al abrir un mapeo existente se cargan sus datos y su asignación.
  useEffect(() => {
    if (!id) return;
    setCargando(true);
    apiFetch<MapeoDetalle>(`/mapeos/${id}`)
      .then((detalle) => {
        setForm({
          id_dspstv: String(detalle.id_dspstv),
          tp_trm: detalle.tp_trm === "E" ? "E" : "H",
          dlmtdr: detalle.dlmtdr,
          fl_inc_dts: String(detalle.fl_inc_dts),
          frmt_fch: detalle.frmt_fch,
          columna_fecha: FORM_VACIO.columna_fecha,
        });
        setDispositivoInfo({ nombre: detalle.dispositivo_nombre, marca: detalle.dispositivo_marca });
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

  // DEC-09: marca y ubicación se muestran a partir del dispositivo elegido,
  // en vez de ser campos propios del formulario.
  const dispositivoSeleccionado =
    dispositivos.find((d) => String(d.id_dspstv) === form.id_dspstv) ?? null;

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

  /** CA2: interpreta el .dat de muestra (subido a mano o traído por FTP) y
   *  muestra las 10 primeras filas. El archivo es temporal: no se guarda
   *  en la BD. Las columnas sin asignación confirmada llegan con una
   *  sugerencia (id_prmtr_sugerido) que se prellena en la tabla de abajo,
   *  editable antes de guardar. */
  async function handleVistaPrevia() {
    if (fuenteMuestra === "archivo" && !archivo) {
      setMensajeOk(false);
      setMensaje("Selecciona un archivo .dat de muestra para ver la vista previa");
      return;
    }
    if (fuenteMuestra === "ftp" && (!dispositivoFtp || !archivoFtpElegido)) {
      setMensajeOk(false);
      setMensaje("Selecciona un dispositivo y un archivo recibido por FTP");
      return;
    }

    setPrevisualizando(true);
    setMensaje("");
    try {
      const formData = new FormData();
      if (fuenteMuestra === "archivo" && archivo) {
        formData.append("archivo", archivo);
      } else {
        formData.append("id_dspstv", dispositivoFtp);
        formData.append("nombre_archivo", archivoFtpElegido);
      }
      formData.append("dlmtdr", form.dlmtdr);
      formData.append("fl_inc_dts", form.fl_inc_dts);
      formData.append("frmt_fch", form.frmt_fch);
      formData.append("columna_fecha", form.columna_fecha);
      formData.append("asignaciones", serializarAsignaciones());
      // DEC-09: la vista previa no lo necesita para interpretar el archivo,
      // pero se manda para que el request sea consistente con el formulario.
      if (form.id_dspstv) {
        formData.append("id_dspstv", form.id_dspstv);
      }

      const endpoint = fuenteMuestra === "archivo" ? "/mapeos/vista-previa" : "/mapeos/vista-previa-ftp";
      const res = await apiUpload<VistaPreviaResponse>(endpoint, formData);
      setVistaPrevia(res);

      // Prellena solo las columnas que el usuario todavía no asignó a
      // mano: una sugerencia nunca pisa una elección ya hecha.
      setAsignaciones((prev) => {
        const siguiente = { ...prev };
        for (const columna of res.columnas) {
          if (columna.id_prmtr_sugerido && !(columna.indc_clmn in siguiente)) {
            siguiente[columna.indc_clmn] = columna.id_prmtr_sugerido;
          }
        }
        return siguiente;
      });
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

    // Campos obligatorios según la HU: delimitador y tipo de trama (este
    // último ocupa el lugar de "extensión de archivo", ver README).
    // DEC-09: el dispositivo reemplaza a sede+marca y solo se elige al
    // crear; al editar, el mapeo no se mueve de dispositivo.
    if (!form.dlmtdr) {
      setMensajeOk(false);
      setMensaje("El delimitador es obligatorio");
      return;
    }
    if (!esEdicion && !form.id_dspstv) {
      setMensajeOk(false);
      setMensaje("Selecciona el dispositivo al que pertenece este mapeo");
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
        ...(esEdicion ? {} : { id_dspstv: Number(form.id_dspstv) }),
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
    "bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none";
  const labelClase = "block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1";

  // La columna de fecha NO se asigna acá: se configura arriba ("Columna de
  // fecha") y el motor la usa directo, sin pasar por mp_clmn/prmtr. Si se
  // deja en esta tabla parece que hay que elegirle un parámetro estándar,
  // y no hay ninguno que le corresponda (la fecha no es una medición).
  const columnasSinFecha = (vistaPrevia?.columnas ?? []).filter(
    (c) => c.nombre_columna !== form.columna_fecha
  );

  // CA4: al editar, la asignación guardada existe aunque todavía no se
  // haya subido un archivo de muestra en esta sesión. Se muestra igual.
  const filasAsignacion =
    (vistaPrevia ? columnasSinFecha : null) ??
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
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="mapeos" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
            nombreCompleto={nombreCompleto}
            rol={rol}
            />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6">
              <h1 className="text-2xl font-extrabold text-gray-900 dark:text-white">
                {esEdicion ? "Editar mapeo de formato" : "Nuevo mapeo de formato"}
              </h1>
              <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 font-light">
                Define cómo se interpretan los archivos .dat de un dispositivo.
              </p>
            </header>

            {cargando ? (
              <div className="text-sm text-gray-600 dark:text-gray-300">Cargando mapeo…</div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-6">
                {/* CA1: datos del formato */}
                <section className="bg-white/70 dark:bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-6">
                  <h2 className="text-base font-bold text-gray-900 dark:text-white mb-4">Datos del formato</h2>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* DEC-09: el mapeo se cuelga de un dispositivo concreto.
                        Al editar no se puede mover a otro dispositivo: se
                        muestra cuál es, en solo lectura. */}
                    <div className="md:col-span-2">
                      <label className={labelClase}>Dispositivo *</label>
                      {esEdicion ? (
                        <p className="text-sm text-gray-900 dark:text-white py-2.5">
                          {dispositivoSeleccionado
                            ? `${dispositivoSeleccionado.nmbr} · ${dispositivoSeleccionado.mrc}`
                            : "—"}
                        </p>
                      ) : (
                        <select
                          required
                          value={form.id_dspstv}
                          onChange={(e) => actualizarCampo("id_dspstv", e.target.value)}
                          className={inputClase + " cursor-pointer"}
                        >
                          <option value="">— Selecciona un dispositivo —</option>
                          {dispositivos.map((d) => (
                            <option key={d.id_dspstv} value={d.id_dspstv}>
                              {d.nmbr} · {d.mrc}
                            </option>
                          ))}
                        </select>
                      )}

                      {/* Marca y ubicación del dispositivo elegido, en modo
                          solo lectura: ya no se tipean ni se eligen aparte. */}
                      {dispositivoSeleccionado && (
                        <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-600 dark:text-gray-300">
                          <span>
                            Marca:{" "}
                            <span className="font-medium text-gray-700 dark:text-gray-200">
                              {dispositivoSeleccionado.mrc}
                            </span>
                          </span>
                          <span>
                            Ubicación:{" "}
                            <span className="font-medium text-gray-700 dark:text-gray-200">
                              {dispositivoSeleccionado.ubicacion_nombre}
                            </span>
                          </span>
                        </div>
                      )}
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
                      <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">
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
                      <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">
                        Solo afecta la vista previa: el motor de ingesta usa "Fecha" (ver README).
                      </p>
                    </div>
                  </div>
                </section>

                {/* CA2: vista previa con archivo de muestra */}
                <section className="bg-white/70 dark:bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-6">
                  <h2 className="text-base font-bold text-gray-900 dark:text-white mb-1">Vista previa</h2>
                  <p className="text-sm text-gray-600 dark:text-gray-300 mb-4 font-light">
                    Usa un .dat de muestra para ver las primeras 10 filas interpretadas. El archivo no se
                    guarda.
                  </p>

                  <div className="flex flex-wrap gap-2 mb-4">
                    <button
                      type="button"
                      onClick={() => setFuenteMuestra("archivo")}
                      className={`px-3 py-1.5 text-sm font-medium rounded-lg border transition-all ${
                        fuenteMuestra === "archivo"
                          ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#ccff00]/40"
                          : "text-gray-700 dark:text-gray-200 border-black/20 dark:border-white/20 hover:bg-black/10 dark:hover:bg-white/10"
                      }`}
                    >
                      Subir archivo
                    </button>
                    <button
                      type="button"
                      onClick={() => setFuenteMuestra("ftp")}
                      className={`px-3 py-1.5 text-sm font-medium rounded-lg border transition-all ${
                        fuenteMuestra === "ftp"
                          ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#ccff00]/40"
                          : "text-gray-700 dark:text-gray-200 border-black/20 dark:border-white/20 hover:bg-black/10 dark:hover:bg-white/10"
                      }`}
                    >
                      Elegir uno ya recibido por FTP
                    </button>
                  </div>

                  {fuenteMuestra === "archivo" ? (
                    <div className="flex flex-wrap items-center gap-3">
                      <input
                        type="file"
                        accept=".dat,.csv,.txt"
                        onChange={seleccionarArchivo}
                        className="text-sm text-gray-700 dark:text-gray-200 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-[#ccff00]/10 file:text-[#5a7000] dark:file:text-[#ccff00] hover:file:bg-[#ccff00]/20 file:cursor-pointer"
                      />
                      <button
                        type="button"
                        onClick={handleVistaPrevia}
                        disabled={previsualizando || !archivo}
                        className="px-4 py-2.5 text-sm font-medium text-gray-900 dark:text-white bg-transparent border border-black/20 dark:border-white/20 rounded-xl hover:bg-black/10 dark:hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                      >
                        {previsualizando ? "Generando…" : "Vista previa"}
                      </button>
                    </div>
                  ) : (
                    <div className="flex flex-wrap items-center gap-3">
                      <select
                        value={dispositivoFtp}
                        onChange={(e) => setDispositivoFtp(e.target.value)}
                        className={inputClase + " cursor-pointer max-w-xs"}
                      >
                        <option value="">— Selecciona un dispositivo —</option>
                        {dispositivos.map((d) => (
                          <option key={d.id_dspstv} value={d.id_dspstv}>
                            {d.nmbr} — {d.mrc}
                            {d.mdl ? ` (${d.mdl})` : ""}
                          </option>
                        ))}
                      </select>

                      <select
                        value={archivoFtpElegido}
                        onChange={(e) => setArchivoFtpElegido(e.target.value)}
                        disabled={!dispositivoFtp || cargandoArchivosFtp}
                        className={inputClase + " cursor-pointer max-w-xs disabled:opacity-50"}
                      >
                        <option value="">
                          {cargandoArchivosFtp
                            ? "Listando archivos…"
                            : archivosFtp.length === 0
                              ? "— Sin archivos disponibles —"
                              : "— Selecciona un archivo —"}
                        </option>
                        {archivosFtp.map((a) => (
                          <option key={a.nombre_archivo} value={a.nombre_archivo}>
                            {a.nombre_archivo}
                          </option>
                        ))}
                      </select>

                      <button
                        type="button"
                        onClick={handleVistaPrevia}
                        disabled={previsualizando || !dispositivoFtp || !archivoFtpElegido}
                        className="px-4 py-2.5 text-sm font-medium text-gray-900 dark:text-white bg-transparent border border-black/20 dark:border-white/20 rounded-xl hover:bg-black/10 dark:hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                      >
                        {previsualizando ? "Generando…" : "Vista previa"}
                      </button>
                    </div>
                  )}

                  {vistaPrevia && (
                    <div className="mt-5">
                      <p className="text-xs text-gray-600 dark:text-gray-300 mb-2">
                        Mostrando {vistaPrevia.filas_mostradas} de {vistaPrevia.total_filas_archivo} filas del
                        archivo.
                      </p>
                      <div className="overflow-x-auto border border-black/10 dark:border-white/10 rounded-xl">
                        <table className="w-full text-sm text-left text-gray-600 dark:text-gray-300">
                          <thead className="text-xs uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
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
                                className="border-b border-black/10 dark:border-white/10 last:border-0"
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
                <section className="bg-white/70 dark:bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-6">
                  <h2 className="text-base font-bold text-gray-900 dark:text-white mb-1">
                    Asignación de columnas
                  </h2>
                  <p className="text-sm text-gray-600 dark:text-gray-300 mb-1 font-light">
                    Indica qué parámetro estándar corresponde a cada columna del archivo.
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-4 font-light">
                    La columna de fecha ("{form.columna_fecha}") no aparece aquí: se configura arriba, en
                    "Columna de fecha".
                  </p>

                  {filasAsignacion.length === 0 ? (
                    <p className="text-sm text-gray-600 dark:text-gray-300">
                      Genera primero una vista previa para ver las columnas del archivo.
                    </p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm text-left text-gray-600 dark:text-gray-300">
                        <thead className="text-xs uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
                          <tr>
                            <th className="px-4 py-3 font-bold w-20">Índice</th>
                            <th className="px-4 py-3 font-bold">Columna del archivo</th>
                            <th className="px-4 py-3 font-bold">Parámetro estándar</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filasAsignacion.map((c) => (
                            <tr key={c.indc_clmn} className="border-b border-black/10 dark:border-white/10 last:border-0">
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
                    className="px-4 py-2.5 text-sm font-medium text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-all"
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
