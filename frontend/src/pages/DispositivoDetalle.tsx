import { useCallback, useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiFetch, apiUpload, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

/**
 * DEC-09 - Ficha del Dispositivo.
 *
 * Reemplaza al módulo "Mapeos de Formato", que resolvía el formato por
 * sede+marca: dos dataloggers de la misma marca en la misma sede, pero
 * con distintos sensores cableados, compartían mapeo y las lecturas del
 * segundo se guardaban bajo el parámetro equivocado sin error visible.
 * Acá el formato se configura para ESTE dispositivo.
 *
 * Pestañas:
 *   FORMATO        delimitadores, saltos y formato de fecha (mp_frmt)
 *   DATOS          tabla columna -> parámetro estándar (mp_clmn)
 *   CARGA DE DATOS sube un .dat y lo procesa por el pipeline real (IMP-06)
 *   CARGA MANUAL   un punto de telemetría a mano, sin archivo (IMP-06)
 *   LOGS           archivos procesados de este dispositivo (archv_ingst)
 *
 * El selector de Tipo de trama (H/E) es COMPARTIDO entre Formato y Datos:
 * un mismo datalogger manda los dos tipos con distintas columnas, y cada
 * uno es un registro separado en mp_frmt (mismo id_dspstv, distinto
 * tp_trm). Por eso vive en el componente padre y no dentro de cada
 * pestaña.
 */

type TipoTrama = "H" | "E";
type Pestana = "formato" | "datos" | "carga" | "manual" | "logs";

interface DispositivoDetalleResponse {
  id_dspstv: number;
  nmbr: string;
  mrc: string;
  mdl: string | null;
  estd: string;
  id_ubccn: number;
  ubicacion_nombre: string;
  id_sd: number;
  id_cnxn: number;
  conexion_nombre: string;
  conexion_frcnc_mnts: number;
}

interface Parametro {
  id_prmtr: number;
  nmbr: string;
  undd: string;
  dscrpcn: string | null;
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
  dlmtdr_dcml: string;
  fl_inc_dts: number;
  frmt_fch: string;
  estd: string;
  total_columnas: number;
  columnas: MapeoColumnaDetalle[];
}

interface LogIngesta {
  id_archv: number;
  nmbr_archv: string;
  estd: string;
  fch_dtccn: string;
  fch_prcsd: string | null;
  mnsj_errr: string | null;
  rgstrs_prcsds: number | null;
}

/** Estado editable de la pestaña Formato, en las unidades del formulario
 *  (todo string, como lo entrega un <input>). */
interface FormatoForm {
  dlmtdr: string;
  dlmtdr_dcml: string;
  fl_inc_dts: string;
  saltar_al_final: string;
  frmt_fch: string;
  columna_fecha: string;
  indice_columna_fecha: string;
}

// Regla de negocio HU06: el delimitador de columna acepta solo estos cuatro.
const DELIMITADORES = [
  { valor: ",", etiqueta: "Coma (,)" },
  { valor: ";", etiqueta: "Punto y coma (;)" },
  { valor: "tab", etiqueta: "Tabulador" },
  { valor: "espacio", etiqueta: "Espacio" },
];

// DEC-09: separador del dato numérico, distinto del de columnas. El motor
// lo normaliza antes de float() (services/ingesta/validador.py).
const DELIMITADORES_DECIMALES = [
  { valor: ".", etiqueta: "Punto (.)" },
  { valor: ",", etiqueta: "Coma (,)" },
];

const FORMATO_VACIO: FormatoForm = {
  dlmtdr: ",",
  dlmtdr_dcml: ".",
  fl_inc_dts: "1",
  saltar_al_final: "0",
  frmt_fch: "YYYY-MM-DD HH:mm:ss",
  columna_fecha: "Fecha",
  indice_columna_fecha: "0",
};

const ROLES_PUEDEN_EDITAR: readonly string[] = [ROLES.ADMINISTRADOR, ROLES.TECNICO_CENERIS];

const PESTANAS: { clave: Pestana; etiqueta: string }[] = [
  { clave: "formato", etiqueta: "Formato" },
  { clave: "datos", etiqueta: "Datos" },
  { clave: "carga", etiqueta: "Carga de datos" },
  { clave: "manual", etiqueta: "Carga manual" },
  { clave: "logs", etiqueta: "Logs" },
];

export default function DispositivoDetalle() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { nombreCompleto, rol, logout } = useAuth();

  const puedeEditar = ROLES_PUEDEN_EDITAR.includes(rol ?? "");

  const [pestana, setPestana] = useState<Pestana>("formato");
  // Compartido por Formato y Datos: son dos vistas del MISMO registro de
  // mp_frmt, elegido por (este dispositivo, este tipo de trama).
  const [tipoTrama, setTipoTrama] = useState<TipoTrama>("H");

  const [dispositivo, setDispositivo] = useState<DispositivoDetalleResponse | null>(null);
  const [parametros, setParametros] = useState<Parametro[]>([]);

  const [mapeo, setMapeo] = useState<MapeoDetalle | null>(null);
  const [formato, setFormato] = useState<FormatoForm>(FORMATO_VACIO);
  // indice de columna -> id_prmtr. Es la tabla de asignación de la
  // pestaña Datos, misma estructura que usaba ConfigurarMapeo (HU06).
  const [asignaciones, setAsignaciones] = useState<Record<number, number>>({});

  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [mensaje, setMensaje] = useState("");
  const [mensajeOk, setMensajeOk] = useState(false);

  function avisar(texto: string, ok: boolean) {
    setMensajeOk(ok);
    setMensaje(texto);
  }

  useEffect(() => {
    apiFetch<Parametro[]>("/parametros")
      .then(setParametros)
      .catch(() => setParametros([]));
  }, []);

  useEffect(() => {
    if (!id) return;
    apiFetch<DispositivoDetalleResponse>(`/dispositivos/${id}`)
      .then(setDispositivo)
      .catch((err) =>
        avisar(
          err instanceof ApiError ? err.message : "No se pudo cargar el dispositivo",
          false
        )
      );
  }, [id]);

  /** Carga el mapeo de (este dispositivo, tipo de trama actual). Que no
   *  exista es un estado válido -el dispositivo todavía no se configuró
   *  para ese tipo-, así que deja el formulario en blanco sin error. */
  const cargarMapeo = useCallback(() => {
    if (!id) return;
    setCargando(true);
    apiFetch<{ items: MapeoDetalle[] }>("/mapeos", {
      params: { id_dspstv: id },
    })
      .then(async (res) => {
        const enLista = res.items.find(
          (m) => m.tp_trm === tipoTrama && m.estd === "Activo"
        );
        if (!enLista) {
          setMapeo(null);
          setFormato(FORMATO_VACIO);
          setAsignaciones({});
          return;
        }
        // El listado no trae las columnas; el detalle sí.
        const detalle = await apiFetch<MapeoDetalle>(`/mapeos/${enLista.id_mp}`);
        setMapeo(detalle);
        setFormato({
          dlmtdr: detalle.dlmtdr,
          dlmtdr_dcml: detalle.dlmtdr_dcml,
          fl_inc_dts: String(detalle.fl_inc_dts),
          saltar_al_final: "0",
          frmt_fch: detalle.frmt_fch,
          columna_fecha: FORMATO_VACIO.columna_fecha,
          indice_columna_fecha: FORMATO_VACIO.indice_columna_fecha,
        });
        setAsignaciones(
          Object.fromEntries(detalle.columnas.map((c) => [c.indc_clmn, c.id_prmtr]))
        );
      })
      .catch((err) =>
        avisar(err instanceof ApiError ? err.message : "No se pudo cargar el mapeo", false)
      )
      .finally(() => setCargando(false));
  }, [id, tipoTrama]);

  useEffect(() => {
    cargarMapeo();
  }, [cargarMapeo]);

  /** Guarda Formato y Datos juntos: los dos editan el mismo registro de
   *  mp_frmt, así que un solo POST/PUT evita dejarlos desincronizados. */
  async function guardarMapeo(e: FormEvent) {
    e.preventDefault();
    if (!id) return;

    if (formato.dlmtdr === "," && formato.dlmtdr_dcml === ",") {
      avisar(
        "El delimitador de columna y el decimal no pueden ser ambos coma: no se podría distinguir 23,5 de dos columnas",
        false
      );
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

      const comun = {
        tp_trm: tipoTrama,
        dlmtdr: formato.dlmtdr,
        dlmtdr_dcml: formato.dlmtdr_dcml,
        fl_inc_dts: Number(formato.fl_inc_dts),
        frmt_fch: formato.frmt_fch.trim(),
        columnas,
      };

      const res = mapeo
        ? await apiFetch<{ mensaje: string }>(`/mapeos/${mapeo.id_mp}`, {
            method: "PUT",
            body: comun,
          })
        : await apiFetch<{ mensaje: string }>("/mapeos", {
            method: "POST",
            body: { ...comun, id_dspstv: Number(id) },
          });

      avisar(res.mensaje, true);
      cargarMapeo();
    } catch (err) {
      avisar(err instanceof ApiError ? err.message : "No se pudo guardar el mapeo", false);
    } finally {
      setGuardando(false);
    }
  }

  const inputClase =
    "bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none";
  const labelClase = "block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1";
  const botonPrimario =
    "inline-flex items-center px-4 py-2 text-sm font-bold rounded-xl bg-[#ccff00] text-[#1a202c] hover:bg-[#b8e600] transition-colors disabled:opacity-50";

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="dispositivos" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
            nombreCompleto={nombreCompleto}
            rol={rol}
            />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <button
              onClick={() => navigate("/dispositivos")}
              className="mb-4 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
            >
              &larr; Volver a Gestión de Dispositivos
            </button>

            <header className="mb-6">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                {dispositivo?.nmbr ?? "Dispositivo"}
              </h1>
              <p className="text-sm text-gray-600 dark:text-gray-300">
                {dispositivo
                  ? `${dispositivo.mrc}${dispositivo.mdl ? ` · ${dispositivo.mdl}` : ""} · ${dispositivo.ubicacion_nombre}`
                  : "Cargando..."}
              </p>
            </header>

            {mensaje && (
              <div
                className={
                  "mb-4 p-4 rounded-xl text-sm border " +
                  (mensajeOk
                    ? "bg-[#ccff00]/20 border-[#ccff00]/40 text-[#5a7000] dark:text-[#ccff00]"
                    : "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800/30 text-red-600 dark:text-red-400")
                }
              >
                {mensaje}
              </div>
            )}

            {/* Pestañas */}
            <div className="border-b border-black/10 dark:border-white/10 mb-6 flex gap-1 overflow-x-auto">
              {PESTANAS.map((p) => (
                <button
                  key={p.clave}
                  onClick={() => {
                    setPestana(p.clave);
                    setMensaje("");
                  }}
                  className={
                    "px-4 py-2.5 text-sm font-medium border-b-2 whitespace-nowrap transition-colors " +
                    (pestana === p.clave
                      ? "border-[#ccff00] text-gray-900 dark:text-white"
                      : "border-transparent text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white")
                  }
                >
                  {p.etiqueta}
                </button>
              ))}
            </div>

            {/* Selector de tipo de trama: compartido por Formato y Datos.
                No aplica a Carga de datos (el tipo lo decide el prefijo
                H_/E_ del archivo) ni a Logs. */}
            {(pestana === "formato" || pestana === "datos") && (
              <div className="mb-6">
                <span className={labelClase}>Tipo de trama</span>
                <div className="inline-flex rounded-xl border border-black/20 dark:border-white/20 overflow-hidden">
                  {(
                    [
                      { valor: "H" as TipoTrama, etiqueta: "Datos periódicos (H)" },
                      { valor: "E" as TipoTrama, etiqueta: "Estados y eventos (E)" },
                    ]
                  ).map((opcion) => (
                    <button
                      key={opcion.valor}
                      type="button"
                      onClick={() => setTipoTrama(opcion.valor)}
                      className={
                        "px-4 py-2 text-sm font-medium transition-colors " +
                        (tipoTrama === opcion.valor
                          ? "bg-[#ccff00] text-[#1a202c]"
                          : "bg-white/70 dark:bg-white/[0.04] backdrop-blur-md text-gray-700 dark:text-gray-200")
                      }
                    >
                      {opcion.etiqueta}
                    </button>
                  ))}
                </div>
                <p className="mt-2 text-xs text-gray-600 dark:text-gray-300">
                  {cargando
                    ? "Cargando configuración..."
                    : mapeo
                      ? `Editando el mapeo activo de este dispositivo para la trama '${tipoTrama}'.`
                      : `Este dispositivo todavía no tiene mapeo para la trama '${tipoTrama}'. Al guardar se creará.`}
                </p>
              </div>
            )}

            <div className="bg-white/70 dark:bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-6">
              {pestana === "formato" && (
                <PestanaFormato
                  formato={formato}
                  setFormato={setFormato}
                  dispositivo={dispositivo}
                  puedeEditar={puedeEditar}
                  guardando={guardando}
                  onGuardar={guardarMapeo}
                  inputClase={inputClase}
                  labelClase={labelClase}
                  botonPrimario={botonPrimario}
                />
              )}

              {pestana === "datos" && (
                <PestanaDatos
                  formato={formato}
                  setFormato={setFormato}
                  asignaciones={asignaciones}
                  setAsignaciones={setAsignaciones}
                  parametros={parametros}
                  puedeEditar={puedeEditar}
                  guardando={guardando}
                  onGuardar={guardarMapeo}
                  inputClase={inputClase}
                  labelClase={labelClase}
                  botonPrimario={botonPrimario}
                />
              )}

              {pestana === "carga" && (
                <PestanaCargaArchivo
                  idDispositivo={id ?? ""}
                  puedeEditar={puedeEditar}
                  avisar={avisar}
                  botonPrimario={botonPrimario}
                />
              )}

              {pestana === "manual" && (
                <PestanaCargaManual
                  idDispositivo={id ?? ""}
                  asignaciones={asignaciones}
                  parametros={parametros}
                  tipoTrama={tipoTrama}
                  puedeEditar={puedeEditar}
                  avisar={avisar}
                  inputClase={inputClase}
                  labelClase={labelClase}
                  botonPrimario={botonPrimario}
                />
              )}

              {pestana === "logs" && <PestanaLogs idDispositivo={id ?? ""} avisar={avisar} />}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- */
/* 3a. FORMATO                                                       */
/* ---------------------------------------------------------------- */

function PestanaFormato({
  formato,
  setFormato,
  dispositivo,
  puedeEditar,
  guardando,
  onGuardar,
  inputClase,
  labelClase,
  botonPrimario,
}: {
  formato: FormatoForm;
  setFormato: React.Dispatch<React.SetStateAction<FormatoForm>>;
  dispositivo: DispositivoDetalleResponse | null;
  puedeEditar: boolean;
  guardando: boolean;
  onGuardar: (e: FormEvent) => void;
  inputClase: string;
  labelClase: string;
  botonPrimario: string;
}) {
  function campo<K extends keyof FormatoForm>(clave: K, valor: FormatoForm[K]) {
    setFormato((prev) => ({ ...prev, [clave]: valor }));
  }

  return (
    <form onSubmit={onGuardar}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <div>
          <label className={labelClase}>Delimitador de columna CSV</label>
          <select
            value={formato.dlmtdr}
            onChange={(e) => campo("dlmtdr", e.target.value)}
            disabled={!puedeEditar}
            className={inputClase}
          >
            {DELIMITADORES.map((d) => (
              <option key={d.valor} value={d.valor}>
                {d.etiqueta}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={labelClase}>Delimitador decimal</label>
          <select
            value={formato.dlmtdr_dcml}
            onChange={(e) => campo("dlmtdr_dcml", e.target.value)}
            disabled={!puedeEditar}
            className={inputClase}
          >
            {DELIMITADORES_DECIMALES.map((d) => (
              <option key={d.valor} value={d.valor}>
                {d.etiqueta}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={labelClase}>Saltar al principio</label>
          <input
            type="number"
            min={1}
            value={formato.fl_inc_dts}
            onChange={(e) => campo("fl_inc_dts", e.target.value)}
            disabled={!puedeEditar}
            className={inputClase}
          />
          <p className="mt-1 text-xs text-gray-600 dark:text-gray-300">
            Filas de encabezado que el motor omite antes de leer datos.
          </p>
        </div>

        <div>
          <label className={labelClase}>Saltar al final</label>
          <input
            type="number"
            min={0}
            value={formato.saltar_al_final}
            onChange={(e) => campo("saltar_al_final", e.target.value)}
            disabled
            className={inputClase + " opacity-60"}
          />
          <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
            Pendiente: el motor de parseo todavía no descarta filas del
            final; el valor no se guarda.
          </p>
        </div>

        <div>
          <label className={labelClase}>Formato de fecha y hora</label>
          <input
            type="text"
            value={formato.frmt_fch}
            onChange={(e) => campo("frmt_fch", e.target.value)}
            disabled={!puedeEditar}
            placeholder="YYYY-MM-DD HH:mm:ss"
            className={inputClase}
          />
        </div>

        {/* El intervalo de polling NO se edita acá: su fuente de verdad es
            la Conexión FTP (HU05). Se muestra solo como referencia. */}
        <div>
          <label className={labelClase}>Frecuencia de polling (referencia)</label>
          <input
            type="text"
            value={
              dispositivo
                ? `${dispositivo.conexion_frcnc_mnts} min · ${dispositivo.conexion_nombre}`
                : ""
            }
            disabled
            className={inputClase + " opacity-60"}
          />
          <p className="mt-1 text-xs text-gray-600 dark:text-gray-300">
            Se configura en la Conexión FTP de este dispositivo.
          </p>
        </div>
      </div>

      <div className="mt-6 flex items-center gap-3">
        <button type="submit" disabled={!puedeEditar || guardando} className={botonPrimario}>
          {guardando ? "Guardando..." : "Guardar"}
        </button>
        {!puedeEditar && (
          <span className="text-xs text-gray-600 dark:text-gray-300">
            Tu rol no permite modificar la configuración de formato.
          </span>
        )}
      </div>
    </form>
  );
}

/* ---------------------------------------------------------------- */
/* 3b. DATOS                                                         */
/* ---------------------------------------------------------------- */

function PestanaDatos({
  formato,
  setFormato,
  asignaciones,
  setAsignaciones,
  parametros,
  puedeEditar,
  guardando,
  onGuardar,
  inputClase,
  labelClase,
  botonPrimario,
}: {
  formato: FormatoForm;
  setFormato: React.Dispatch<React.SetStateAction<FormatoForm>>;
  asignaciones: Record<number, number>;
  setAsignaciones: React.Dispatch<React.SetStateAction<Record<number, number>>>;
  parametros: Parametro[];
  puedeEditar: boolean;
  guardando: boolean;
  onGuardar: (e: FormEvent) => void;
  inputClase: string;
  labelClase: string;
  botonPrimario: string;
}) {
  const [nuevoIndice, setNuevoIndice] = useState("");

  const indices = Object.keys(asignaciones)
    .map(Number)
    .sort((a, b) => a - b);

  function asignar(indice: number, idParametro: number) {
    setAsignaciones((prev) => ({ ...prev, [indice]: idParametro }));
  }

  function quitar(indice: number) {
    setAsignaciones((prev) => {
      const copia = { ...prev };
      delete copia[indice];
      return copia;
    });
  }

  function agregarFila() {
    const indice = Number(nuevoIndice);
    if (!nuevoIndice || Number.isNaN(indice) || indice < 0) return;
    if (indice in asignaciones) return;
    // 0 = "sin asignar todavía": el guardado filtra los que sigan en 0.
    setAsignaciones((prev) => ({ ...prev, [indice]: 0 }));
    setNuevoIndice("");
  }

  return (
    <form onSubmit={onGuardar}>
      {/* Fila especial de Fecha y Hora: no pasa por mp_clmn/prmtr -la
          fecha no es una medición y no tiene parámetro estándar-, el motor
          la lee directo con estos dos campos. */}
      <div className="mb-6 p-4 rounded-xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5">
        <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-3">Fecha y hora</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={labelClase}>Formato</label>
            <input
              type="text"
              value={formato.frmt_fch}
              onChange={(e) => setFormato((p) => ({ ...p, frmt_fch: e.target.value }))}
              disabled={!puedeEditar}
              placeholder="YYYY-MM-DD HH:mm:ss"
              className={inputClase}
            />
          </div>
          <div>
            <label className={labelClase}>Columna de fecha (nombre en el header)</label>
            <input
              type="text"
              value={formato.columna_fecha}
              onChange={(e) => setFormato((p) => ({ ...p, columna_fecha: e.target.value }))}
              disabled={!puedeEditar}
              className={inputClase}
            />
          </div>
        </div>
      </div>

      <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-3">
        Asignación de columnas
      </h3>

      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left text-gray-600 dark:text-gray-300">
          <thead className="text-xs uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
            <tr>
              <th className="px-4 py-3 font-bold">N° de columna</th>
              <th className="px-4 py-3 font-bold">Parámetro estándar</th>
              <th className="px-4 py-3 font-bold text-right">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {indices.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-6 text-center">
                  Todavía no hay columnas asignadas para esta trama.
                </td>
              </tr>
            )}
            {indices.map((indice) => (
              <tr
                key={indice}
                className="border-b border-black/10 dark:border-white/10"
              >
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                  {indice}
                </td>
                <td className="px-4 py-3">
                  <select
                    value={asignaciones[indice] || ""}
                    onChange={(e) => asignar(indice, Number(e.target.value))}
                    disabled={!puedeEditar}
                    className={inputClase}
                  >
                    <option value="">Sin asignar</option>
                    {parametros.map((p) => (
                      <option key={p.id_prmtr} value={p.id_prmtr}>
                        {p.nmbr} ({p.undd})
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    type="button"
                    onClick={() => quitar(indice)}
                    disabled={!puedeEditar}
                    className="text-xs font-medium text-red-600 dark:text-red-400 hover:underline disabled:opacity-50"
                  >
                    Quitar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-end gap-3">
        <div className="w-40">
          <label className={labelClase}>Añadir columna N°</label>
          <input
            type="number"
            min={0}
            value={nuevoIndice}
            onChange={(e) => setNuevoIndice(e.target.value)}
            disabled={!puedeEditar}
            className={inputClase}
          />
        </div>
        <button
          type="button"
          onClick={agregarFila}
          disabled={!puedeEditar}
          className="px-3 py-2.5 text-sm font-medium rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 hover:bg-black/10 dark:hover:bg-white/10 disabled:opacity-50"
        >
          Añadir
        </button>
      </div>

      <div className="mt-6">
        <button type="submit" disabled={!puedeEditar || guardando} className={botonPrimario}>
          {guardando ? "Guardando..." : "Guardar"}
        </button>
      </div>
    </form>
  );
}

/* ---------------------------------------------------------------- */
/* 3c. CARGA DE DATOS                                                */
/* ---------------------------------------------------------------- */

function PestanaCargaArchivo({
  idDispositivo,
  puedeEditar,
  avisar,
  botonPrimario,
}: {
  idDispositivo: string;
  puedeEditar: boolean;
  avisar: (texto: string, ok: boolean) => void;
  botonPrimario: string;
}) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [resultado, setResultado] = useState<{
    tipo_trama: string;
    guardadas: number;
    omitidas_sin_valor: number;
    errores_validacion: number;
  } | null>(null);

  async function subir() {
    if (!archivo) {
      avisar("Selecciona un archivo .dat para cargar", false);
      return;
    }
    setSubiendo(true);
    setResultado(null);
    try {
      const formData = new FormData();
      formData.append("archivo", archivo);
      const res = await apiUpload<{
        mensaje: string;
        tipo_trama: string;
        guardadas: number;
        omitidas_sin_valor: number;
        errores_validacion: number;
      }>(`/dispositivos/${idDispositivo}/carga-archivo`, formData);
      setResultado(res);
      avisar(res.mensaje, true);
    } catch (err) {
      avisar(err instanceof ApiError ? err.message : "No se pudo procesar el archivo", false);
    } finally {
      setSubiendo(false);
    }
  }

  return (
    <div>
      <p className="text-sm text-gray-600 dark:text-gray-300 mb-4">
        El archivo se procesa con el mismo pipeline que la ingesta automática por
        FTP. El tipo de trama sale del prefijo del nombre del archivo:{" "}
        <code className="font-mono">H_*.dat</code> para datos periódicos y{" "}
        <code className="font-mono">E_*.dat</code> para estados y eventos.
      </p>

      <input
        type="file"
        accept=".dat,.csv,.txt"
        onChange={(e: ChangeEvent<HTMLInputElement>) =>
          setArchivo(e.target.files?.[0] ?? null)
        }
        disabled={!puedeEditar}
        className="block w-full text-sm text-gray-600 dark:text-gray-300 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-bold file:bg-[#ccff00] file:text-[#1a202c] hover:file:bg-[#b8e600]"
      />

      <div className="mt-5">
        <button
          type="button"
          onClick={subir}
          disabled={!puedeEditar || subiendo}
          className={botonPrimario}
        >
          {subiendo ? "Procesando..." : "Cargar y procesar"}
        </button>
      </div>

      {resultado && (
        <dl className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <dt className="text-gray-600 dark:text-gray-300">Tipo de trama</dt>
            <dd className="font-bold text-gray-900 dark:text-white">{resultado.tipo_trama}</dd>
          </div>
          <div>
            <dt className="text-gray-600 dark:text-gray-300">Lecturas guardadas</dt>
            <dd className="font-bold text-gray-900 dark:text-white">{resultado.guardadas}</dd>
          </div>
          <div>
            <dt className="text-gray-600 dark:text-gray-300">Sin valor</dt>
            <dd className="font-bold text-gray-900 dark:text-white">
              {resultado.omitidas_sin_valor}
            </dd>
          </div>
          <div>
            <dt className="text-gray-600 dark:text-gray-300">Errores de validación</dt>
            <dd className="font-bold text-gray-900 dark:text-white">
              {resultado.errores_validacion}
            </dd>
          </div>
        </dl>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- */
/* 3d. CARGA MANUAL                                                  */
/* ---------------------------------------------------------------- */

function PestanaCargaManual({
  idDispositivo,
  asignaciones,
  parametros,
  tipoTrama,
  puedeEditar,
  avisar,
  inputClase,
  labelClase,
  botonPrimario,
}: {
  idDispositivo: string;
  asignaciones: Record<number, number>;
  parametros: Parametro[];
  tipoTrama: TipoTrama;
  puedeEditar: boolean;
  avisar: (texto: string, ok: boolean) => void;
  inputClase: string;
  labelClase: string;
  botonPrimario: string;
}) {
  const [fechaHora, setFechaHora] = useState("");
  const [valores, setValores] = useState<Record<number, string>>({});
  const [guardando, setGuardando] = useState(false);

  // La carga manual es de datos periódicos: un punto con un valor por
  // parámetro. Un evento 'E' no es eso, así que la pestaña solo opera
  // sobre el mapeo H aunque el selector de arriba esté en E.
  const idsMapeados = Array.from(
    new Set(Object.values(asignaciones).filter((v) => Boolean(v)))
  );
  const parametrosMapeados = parametros.filter((p) => idsMapeados.includes(p.id_prmtr));

  async function guardar() {
    if (!fechaHora) {
      avisar("Indica la fecha y hora de la medición", false);
      return;
    }
    const items = Object.entries(valores)
      .filter(([, v]) => v.trim() !== "")
      .map(([idParametro, v]) => ({ id_prmtr: Number(idParametro), vlr: Number(v) }));

    if (items.length === 0) {
      avisar("Ingresa al menos un valor", false);
      return;
    }
    if (items.some((i) => Number.isNaN(i.vlr))) {
      avisar("Hay un valor que no es numérico", false);
      return;
    }

    setGuardando(true);
    try {
      const res = await apiFetch<{ mensaje: string }>(
        `/dispositivos/${idDispositivo}/carga-manual`,
        {
          method: "POST",
          // El input datetime-local no lleva zona; el backend lo
          // interpreta como UTC, igual que el validador del pipeline.
          body: { fch_hr: fechaHora, valores: items },
        }
      );
      avisar(res.mensaje, true);
      setValores({});
    } catch (err) {
      avisar(err instanceof ApiError ? err.message : "No se pudo registrar la medición", false);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div>
      {tipoTrama === "E" && (
        <div className="mb-4 p-3 rounded-xl bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400 text-sm">
          La carga manual aplica solo a datos periódicos (H). El formulario usa
          los parámetros mapeados para la trama H de este dispositivo.
        </div>
      )}

      <div className="max-w-sm mb-6">
        <label className={labelClase}>Fecha y hora de la medición</label>
        <input
          type="datetime-local"
          value={fechaHora}
          onChange={(e) => setFechaHora(e.target.value)}
          disabled={!puedeEditar}
          className={inputClase}
        />
      </div>

      {parametrosMapeados.length === 0 ? (
        <p className="text-sm text-gray-600 dark:text-gray-300">
          Este dispositivo todavía no tiene parámetros mapeados. Configúralos en
          la pestaña Datos (trama H) antes de cargar mediciones a mano.
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {parametrosMapeados.map((p) => (
            <div key={p.id_prmtr}>
              <label className={labelClase}>
                {p.nmbr} <span className="text-gray-500 dark:text-gray-400">({p.undd})</span>
              </label>
              <input
                type="number"
                step="any"
                value={valores[p.id_prmtr] ?? ""}
                onChange={(e) =>
                  setValores((prev) => ({ ...prev, [p.id_prmtr]: e.target.value }))
                }
                disabled={!puedeEditar}
                className={inputClase}
              />
            </div>
          ))}
        </div>
      )}

      <div className="mt-6">
        <button
          type="button"
          onClick={guardar}
          disabled={!puedeEditar || guardando || parametrosMapeados.length === 0}
          className={botonPrimario}
        >
          {guardando ? "Guardando..." : "Registrar medición"}
        </button>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- */
/* 3e. LOGS                                                          */
/* ---------------------------------------------------------------- */

function PestanaLogs({
  idDispositivo,
  avisar,
}: {
  idDispositivo: string;
  avisar: (texto: string, ok: boolean) => void;
}) {
  const [logs, setLogs] = useState<LogIngesta[]>([]);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    if (!idDispositivo) return;
    setCargando(true);
    apiFetch<LogIngesta[]>(`/dispositivos/${idDispositivo}/logs`)
      .then(setLogs)
      .catch((err) =>
        avisar(err instanceof ApiError ? err.message : "No se pudieron cargar los logs", false)
      )
      .finally(() => setCargando(false));
    // avisar viene del padre y cambia en cada render; incluirla dispararía
    // el efecto en bucle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idDispositivo]);

  const colorEstado: Record<string, string> = {
    Exitoso: "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#ccff00]/30",
    Fallido: "bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 border-red-200",
    Procesando: "bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-800/30",
    Pendiente: "bg-black/5 dark:bg-white/10 text-gray-600 dark:text-gray-300 border-gray-200",
  };

  return (
    <div>
      <p className="text-sm text-gray-600 dark:text-gray-300 mb-4">
        Archivos procesados para este dispositivo, tanto los recibidos por FTP
        como los subidos desde la pestaña Carga de datos.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left text-gray-600 dark:text-gray-300">
          <thead className="text-xs uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
            <tr>
              <th className="px-4 py-3 font-bold">Archivo</th>
              <th className="px-4 py-3 font-bold">Estado</th>
              <th className="px-4 py-3 font-bold">Detectado</th>
              <th className="px-4 py-3 font-bold">Procesado</th>
              <th className="px-4 py-3 font-bold">Registros</th>
              <th className="px-4 py-3 font-bold">Mensaje</th>
            </tr>
          </thead>
          <tbody>
            {cargando && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center">
                  Cargando...
                </td>
              </tr>
            )}
            {!cargando && logs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center">
                  Todavía no hay archivos procesados para este dispositivo.
                </td>
              </tr>
            )}
            {!cargando &&
              logs.map((log) => (
                <tr key={log.id_archv} className="border-b border-black/10 dark:border-white/10">
                  <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                    {log.nmbr_archv}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={
                        "inline-flex px-2.5 py-1 rounded-full text-xs font-bold border " +
                        (colorEstado[log.estd] ?? colorEstado.Pendiente)
                      }
                    >
                      {log.estd}
                    </span>
                  </td>
                  <td className="px-4 py-3">{new Date(log.fch_dtccn).toLocaleString()}</td>
                  <td className="px-4 py-3">
                    {log.fch_prcsd ? new Date(log.fch_prcsd).toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-3">{log.rgstrs_prcsds ?? "—"}</td>
                  <td className="px-4 py-3 max-w-xs truncate" title={log.mnsj_errr ?? ""}>
                    {log.mnsj_errr ?? "—"}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
