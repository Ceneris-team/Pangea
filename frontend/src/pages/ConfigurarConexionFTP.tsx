import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";

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

interface ConexionFTPDetalle {
  id_cnxn: number;
  nmbr: string;
  hst: string;
  prt: number;
  usr_ftp: string | null;
  rt_rmt: string | null;
  frcnc_mnts: number;
  estd: string;
}

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

export default function ConfigurarConexionFTP() {
  const { id } = useParams(); // si existe, estamos editando una conexión ya registrada
  const esEdicion = Boolean(id);
  const navigate = useNavigate();

  const [form, setForm] = useState<ConexionFTPForm>(FORM_VACIO);
  const [sedes, setSedes] = useState<Sede[]>([]);
  const [cargando, setCargando] = useState(false);
  const [probando, setProbando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [conexionValidada, setConexionValidada] = useState(false); // habilita GUARDAR
  const [mensaje, setMensaje] = useState("");
  const [mensajeOk, setMensajeOk] = useState(false);

  // Selector de sede: un usuario con scope "global" (p. ej. Administrador o
  // Técnico CENERIS sin sede única asignada) debe indicar a qué sede
  // pertenece el datalogger (ver _resolver_sede en el backend).
  useEffect(() => {
    apiFetch<Sede[]>("/sedes")
      .then(setSedes)
      .catch((err) => {
        setMensajeOk(false);
        setMensaje(err instanceof ApiError ? err.message : "No se pudieron cargar las sedes");
      });
  }, []);

  // Modo edición: precarga los datos ya guardados. La contraseña NUNCA
  // se devuelve en texto plano (CA de HU05), así que queda vacía -si el
  // usuario no la toca, el PUT la conserva tal cual (ver handleSubmit).
  useEffect(() => {
    if (!id) return;
    setCargando(true);
    apiFetch<ConexionFTPDetalle>(`/conexiones-ftp/${id}`)
      .then((detalle) => {
        setForm({
          id_sd: "",
          nmbr: detalle.nmbr,
          hst: detalle.hst,
          prt: String(detalle.prt),
          usr_ftp: detalle.usr_ftp ?? "",
          contrasena_ftp: "",
          rt_rmt: detalle.rt_rmt ?? "",
          frcnc_mnts: detalle.frcnc_mnts === 60 ? "60" : "1",
        });
        // Sin cambiar la contraseña no hay nada nuevo que probar contra
        // el FTP real: se deja habilitado GUARDAR desde el inicio.
        // Cualquier edición de campo lo vuelve a invalidar (ver
        // actualizarCampo) y exige "Probar conexión" de nuevo.
        setConexionValidada(true);
      })
      .catch((err) => {
        setMensajeOk(false);
        setMensaje(err instanceof ApiError ? err.message : "No se pudo cargar la conexión");
      })
      .finally(() => setCargando(false));
  }, [id]);

  function actualizarCampo<K extends keyof ConexionFTPForm>(campo: K, valor: ConexionFTPForm[K]) {
    setForm((prev) => ({ ...prev, [campo]: valor }));
    // CA: cualquier cambio invalida una prueba de conexión previa
    setConexionValidada(false);
  }

  function camposObligatoriosCompletos(): boolean {
    // La contraseña solo es obligatoria para "Probar conexión" al crear:
    // en edición, dejarla vacía significa "no cambiarla" (ver handleSubmit).
    return Boolean(
      form.nmbr.trim() &&
        form.hst.trim() &&
        form.prt.trim() &&
        form.usr_ftp.trim() &&
        (esEdicion || form.contrasena_ftp.trim()) &&
        form.rt_rmt.trim()
    );
  }

  // CA: "El directorio remoto es una cadena de texto tipo ruta, por ejemplo /datos/estacion01."
  function rutaRemotaValida(): boolean {
    return form.rt_rmt.trim().startsWith("/");
  }

  async function handleProbarConexion() {
    setMensaje("");
    if (!camposObligatoriosCompletos() || !form.contrasena_ftp.trim()) {
      setMensajeOk(false);
      setMensaje(
        esEdicion
          ? "Escribe la contraseña FTP para probar la conexión (queda vacía por seguridad; si no la cambias, se conserva la actual al guardar)"
          : "Completa todos los campos obligatorios antes de probar la conexión"
      );
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
        // Vacía en edición = "no cambiar la contraseña" (el backend
        // conserva la actual cuando el campo llega vacío/ausente).
        ...(form.contrasena_ftp.trim() ? { contrasena_ftp: form.contrasena_ftp } : {}),
        rt_rmt: form.rt_rmt.trim(),
        frcnc_mnts: Number(form.frcnc_mnts),
      };

      const res = esEdicion
        ? await apiFetch<{ mensaje: string }>(`/conexiones-ftp/${id}`, { method: "PUT", body: payload })
        : await apiFetch<{ mensaje: string }>("/conexiones-ftp", { method: "POST", body: payload });

      setMensajeOk(true);
      setMensaje(res.mensaje); // "Conexión FTP configurada correctamente" / "Configuración actualizada correctamente"
    } catch (err) {
      setMensajeOk(false);
      setMensaje(err instanceof ApiError ? err.message : "No se pudo guardar la conexión");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">
      <div className="max-w-2xl mx-auto bg-white dark:bg-[#2d3748] rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-8">
        <header className="mb-6">
          <h1 className="text-2xl font-extrabold text-gray-900 dark:text-white">
            {esEdicion ? "Editar conexión FTP" : "Nueva conexión FTP"}
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 font-light">
            Configura la conexión FTP de un datalogger para iniciar la ingesta automática de telemetría.
          </p>
        </header>

        {cargando ? (
          <div className="text-sm text-gray-500 dark:text-gray-400">Cargando conexión…</div>
        ) : (
        <form onSubmit={handleSubmit} className="space-y-5">
          {!esEdicion && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Sede</label>
              <select
                required
                value={form.id_sd}
                onChange={(e) => actualizarCampo("id_sd", e.target.value)}
                className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none cursor-pointer"
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
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Nombre del datalogger
            </label>
            <input
              type="text"
              required
              value={form.nmbr}
              onChange={(e) => actualizarCampo("nmbr", e.target.value)}
              className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
            />
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Host/IP</label>
              <input
                type="text"
                required
                value={form.hst}
                onChange={(e) => actualizarCampo("hst", e.target.value)}
                className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Puerto</label>
              <input
                type="number"
                required
                value={form.prt}
                onChange={(e) => actualizarCampo("prt", e.target.value)}
                className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Usuario FTP</label>
              <input
                type="text"
                required
                value={form.usr_ftp}
                onChange={(e) => actualizarCampo("usr_ftp", e.target.value)}
                className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Contraseña FTP
              </label>
              <input
                type="password"
                required={!esEdicion}
                placeholder={esEdicion ? "Dejar en blanco para no cambiarla" : undefined}
                value={form.contrasena_ftp}
                onChange={(e) => actualizarCampo("contrasena_ftp", e.target.value)}
                className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Directorio remoto
            </label>
            <input
              type="text"
              required
              placeholder="/datos/estacion01"
              value={form.rt_rmt}
              onChange={(e) => actualizarCampo("rt_rmt", e.target.value)}
              className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Frecuencia de polling
            </label>
            <select
              value={form.frcnc_mnts}
              onChange={(e) => actualizarCampo("frcnc_mnts", e.target.value as "1" | "60")}
              className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none cursor-pointer"
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

          <div className="flex flex-wrap gap-3 pt-2">
            <button
              type="button"
              onClick={handleProbarConexion}
              disabled={probando}
              className="px-4 py-2.5 text-sm font-medium text-gray-900 dark:text-white bg-white dark:bg-transparent border border-gray-300 dark:border-gray-600 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 transition-all"
            >
              {probando ? "Probando..." : "Probar conexión"}
            </button>

            <button
              type="submit"
              disabled={!conexionValidada || guardando}
              className="px-4 py-2.5 text-sm font-semibold text-gray-900 bg-[#ccff00] rounded-xl hover:bg-[#b8e600] disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {guardando ? "Guardando..." : esEdicion ? "Actualizar" : "Guardar"}
            </button>

            <button
              type="button"
              onClick={() => navigate("/conexiones-ftp")}
              className="px-4 py-2.5 text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-all"
            >
              Ver conexiones
            </button>
          </div>
        </form>
        )}
      </div>
    </div>
  );
}