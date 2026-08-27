import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

/**
 * HU11 - Añadir dispositivo.
 *
 *   CA1  formulario con Nombre, Marca, Modelo (opcional), Ubicación y
 *        Conexión FTP
 *   CA2  "Guardar" -> POST /dispositivos -> "Dispositivo añadido correctamente"
 *   CA3  tras guardar, vuelve al listado (HU10) con el nuevo dispositivo
 *   CA4  "Cancelar" descarta el formulario sin llamar al backend
 *
 * DEC-28: Latitud/Longitud son el punto GPS PROPIO del dispositivo, no una
 * copia del centro de su Ubicación. Son opcionales: si se dejan vacías, no
 * se mandan al backend y crear_dispositivo cae al centro de la Ubicación
 * (el comportamiento de siempre).
 *
 * DEC-09: el dispositivo ya no necesita un mapeo de formato previo para
 * crearse. El mapeo (marca/tipo de trama/columnas) se configura después,
 * en Mapeo de Formatos (HU06), y cuelga de este dispositivo.
 */

interface UbicacionOption {
  id_ubccn: number;
  nmbr: string;
}

interface ConexionFTPOption {
  id_cnxn: number;
  nmbr: string;
}

interface DispositivoForm {
  nmbr: string;
  mrc: string;
  mdl: string;
  id_ubccn: string;
  id_cnxn: string;
  lttd: string;
  lngtd: string;
}

const FORM_VACIO: DispositivoForm = {
  nmbr: "",
  mrc: "",
  mdl: "",
  id_ubccn: "",
  id_cnxn: "",
  lttd: "",
  lngtd: "",
};

/** Devuelve el número solo si el texto es un número válido: "" y "-" dan
 *  NaN y no deben viajar al backend como coordenada 0,0. Mismo helper que
 *  AgregarUbicacion.tsx usa para sus propios lttd/lngtd. */
function aNumero(texto: string): number | null {
  if (texto.trim() === "") return null;
  const valor = Number(texto);
  return Number.isFinite(valor) ? valor : null;
}

export default function AgregarDispositivo() {
  const navigate = useNavigate();
  const { nombreCompleto, rol, logout } = useAuth();

  const [form, setForm] = useState<DispositivoForm>(FORM_VACIO);
  const [ubicaciones, setUbicaciones] = useState<UbicacionOption[]>([]);
  const [conexiones, setConexiones] = useState<ConexionFTPOption[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");

  // CA1: el selector de Ubicación solo ofrece ubicaciones Activas.
  useEffect(() => {
    apiFetch<{ items: UbicacionOption[] }>("/ubicaciones", {
      params: { estado: "Activa", por_pagina: 100 },
    })
      .then((res) => setUbicaciones(res.items))
      .catch(() => setUbicaciones([]));
  }, []);

  // CA1: el selector de Conexión FTP reusa GET /conexiones-ftp (HU05).
  useEffect(() => {
    apiFetch<{ items: ConexionFTPOption[] }>("/conexiones-ftp", {
      params: { por_pagina: 100 },
    })
      .then((res) => setConexiones(res.items))
      .catch(() => setConexiones([]));
  }, []);

  function actualizarCampo<K extends keyof DispositivoForm>(campo: K, valor: DispositivoForm[K]) {
    setForm((prev) => ({ ...prev, [campo]: valor }));
  }

  /** CA4: descarta el formulario y vuelve al listado. No llama al backend. */
  function handleCancelar() {
    setForm(FORM_VACIO);
    navigate("/dispositivos");
  }

  /** CA2 + CA3. */
  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    // CA2: campos obligatorios. Comodidad de UI; el schema Pydantic repite
    // las mismas reglas del lado del backend.
    if (!form.nmbr.trim()) {
      setError("El nombre del dispositivo es obligatorio");
      return;
    }
    if (!form.mrc.trim()) {
      setError("La marca es obligatoria");
      return;
    }
    if (!form.id_ubccn) {
      setError("Selecciona la ubicación del dispositivo");
      return;
    }
    if (!form.id_cnxn) {
      setError("Selecciona la conexión FTP del dispositivo");
      return;
    }

    // DEC-28: opcionales, pero si se escribe algo tiene que ser válido -un
    // texto no numérico o fuera de rango se rechaza acá para no gastar un
    // viaje al backend, que repite las mismas reglas en DispositivoCrear.
    const latitud = aNumero(form.lttd);
    const longitud = aNumero(form.lngtd);
    if (form.lttd.trim() !== "" && latitud === null) {
      setError("La latitud debe ser un número válido");
      return;
    }
    if (form.lngtd.trim() !== "" && longitud === null) {
      setError("La longitud debe ser un número válido");
      return;
    }
    if (latitud !== null && (latitud < -90 || latitud > 90)) {
      setError("La latitud debe estar entre -90 y 90");
      return;
    }
    if (longitud !== null && (longitud < -180 || longitud > 180)) {
      setError("La longitud debe estar entre -180 y 180");
      return;
    }

    setGuardando(true);
    setError("");
    try {
      await apiFetch<{ mensaje: string }>("/dispositivos", {
        method: "POST",
        body: {
          nmbr: form.nmbr.trim(),
          mrc: form.mrc.trim(),
          mdl: form.mdl.trim() || null,
          id_ubccn: Number(form.id_ubccn),
          id_cnxn: Number(form.id_cnxn),
          // Si el usuario no las completó no se mandan, y el backend cae
          // al centro de la Ubicación elegida.
          ...(latitud !== null ? { lttd: latitud } : {}),
          ...(longitud !== null ? { lngtd: longitud } : {}),
        },
      });

      // CA3: volver al listado (HU10), que recarga y ya muestra el nuevo
      // dispositivo. El mensaje de éxito viaja en el state, mismo patrón
      // que Ubicaciones.tsx usa tras HU08.
      navigate("/dispositivos", {
        state: { mensaje: "Dispositivo añadido correctamente" },
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo registrar el dispositivo");
    } finally {
      setGuardando(false);
    }
  }

  const inputClase =
    "bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none";
  const labelClase = "block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1";

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="dispositivos" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          {/* TOP NAVBAR */}
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
              nombreCompleto={nombreCompleto}
              rol={rol}
            />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Agregar dispositivo</h1>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Registra un nuevo dispositivo de monitoreo y asócialo a una ubicación y conexión FTP.
              </p>
            </header>

            <form
              onSubmit={handleSubmit}
              className="bg-white dark:bg-[#2d3748] rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700"
            >
              {error && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-100 dark:border-red-800/30 rounded-t-2xl">
                  {error}
                </div>
              )}

              <div className="p-6 space-y-5">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <div>
                    <label className={labelClase} htmlFor="nmbr">
                      Nombre <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="nmbr"
                      type="text"
                      maxLength={150}
                      value={form.nmbr}
                      onChange={(e) => actualizarCampo("nmbr", e.target.value)}
                      placeholder="CR1000-Norte"
                      className={inputClase}
                    />
                  </div>

                  <div>
                    <label className={labelClase} htmlFor="mrc">
                      Marca <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="mrc"
                      type="text"
                      maxLength={100}
                      value={form.mrc}
                      onChange={(e) => actualizarCampo("mrc", e.target.value)}
                      placeholder="Campbell"
                      className={inputClase}
                    />
                  </div>
                </div>

                <div>
                  <label className={labelClase} htmlFor="mdl">
                    Modelo <span className="text-gray-400 font-normal">(opcional)</span>
                  </label>
                  <input
                    id="mdl"
                    type="text"
                    maxLength={100}
                    value={form.mdl}
                    onChange={(e) => actualizarCampo("mdl", e.target.value)}
                    placeholder="CR1000X"
                    className={inputClase}
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <div>
                    <label className={labelClase} htmlFor="id_ubccn">
                      Ubicación <span className="text-red-500">*</span>
                    </label>
                    <select
                      id="id_ubccn"
                      value={form.id_ubccn}
                      onChange={(e) => actualizarCampo("id_ubccn", e.target.value)}
                      className={inputClase + " cursor-pointer"}
                    >
                      <option value="">Selecciona una ubicación...</option>
                      {ubicaciones.map((u) => (
                        <option key={u.id_ubccn} value={u.id_ubccn}>
                          {u.nmbr}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className={labelClase} htmlFor="id_cnxn">
                      Conexión FTP <span className="text-red-500">*</span>
                    </label>
                    <select
                      id="id_cnxn"
                      value={form.id_cnxn}
                      onChange={(e) => actualizarCampo("id_cnxn", e.target.value)}
                      className={inputClase + " cursor-pointer"}
                    >
                      <option value="">Selecciona una conexión FTP...</option>
                      {conexiones.map((c) => (
                        <option key={c.id_cnxn} value={c.id_cnxn}>
                          {c.nmbr}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* DEC-28: punto GPS propio del dispositivo. Opcional: en
                    blanco, el backend usa el centro de la Ubicación. */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <div>
                    <label className={labelClase} htmlFor="lttd">
                      Latitud <span className="text-gray-400 font-normal">(opcional)</span>
                    </label>
                    <input
                      id="lttd"
                      type="number"
                      step="any"
                      min={-90}
                      max={90}
                      value={form.lttd}
                      onChange={(e) => actualizarCampo("lttd", e.target.value)}
                      placeholder="-12.046400"
                      className={inputClase}
                    />
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      Entre -90 y 90. En blanco: se usa el centro de la ubicación.
                    </p>
                  </div>
                  <div>
                    <label className={labelClase} htmlFor="lngtd">
                      Longitud <span className="text-gray-400 font-normal">(opcional)</span>
                    </label>
                    <input
                      id="lngtd"
                      type="number"
                      step="any"
                      min={-180}
                      max={180}
                      value={form.lngtd}
                      onChange={(e) => actualizarCampo("lngtd", e.target.value)}
                      placeholder="-77.042800"
                      className={inputClase}
                    />
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      Entre -180 y 180. En blanco: se usa el centro de la ubicación.
                    </p>
                  </div>
                </div>
              </div>

              <div className="p-6 border-t border-gray-100 dark:border-gray-700 flex justify-end gap-3">
                {/* CA4: no toca el backend, solo descarta y vuelve. */}
                <button
                  type="button"
                  onClick={handleCancelar}
                  className="px-4 py-2 text-sm font-medium rounded-xl border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardando}
                  className="px-4 py-2 text-sm font-bold rounded-xl bg-[#ccff00] text-[#1a202c] hover:bg-[#b8e600] disabled:opacity-50 transition-colors"
                >
                  {guardando ? "Guardando..." : "Guardar dispositivo"}
                </button>
              </div>
            </form>
          </main>
        </div>
      </div>
    </div>
  );
}
