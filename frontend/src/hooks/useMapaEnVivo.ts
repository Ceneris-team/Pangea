import { useCallback, useEffect, useRef, useState } from "react";

/**
 * HU17 CA3 - Telemetría en vivo del mapa del Cliente Final.
 *
 * "Cuando llega telemetría nueva, el marcador se actualiza
 * automáticamente, SIN RECARGAR LA PÁGINA."
 *
 * Abre un WebSocket contra /mapa-cliente/ws y entrega cada lectura nueva
 * al llamador. El backend ya filtró qué ubicaciones puede ver este
 * usuario (HU21) al suscribirse a los canales de Redis, así que todo lo
 * que llega por acá es legítimo para este usuario: el hook no vuelve a
 * filtrar.
 *
 * RECONEXIÓN (no es un extra, es un requisito de la infraestructura):
 * el balanceador HTTP de Lightsail Container Service no expone un timeout
 * de conexión configurable y no está documentado cuánto tolera una
 * conexión inactiva. El backend manda un ping cada 25s para que la
 * conexión nunca parezca ociosa, y este hook reconecta con backoff
 * exponencial si aun así se cae. Sin esto, una desconexión silenciosa
 * dejaría el mapa congelado mostrando datos viejos SIN ningún aviso, que
 * es peor que mostrar un error: el usuario no tendría forma de notarlo.
 */

/** Lo que el backend manda por el canal (ver services/mapa/eventos.py). */
export interface EventoLectura {
  id_ubccn: number;
  parametro: string;
  unidad: string;
  valor: number | string | null;
  fch_hr: string | null;
}

export type EstadoConexion = "conectando" | "conectado" | "reconectando" | "sin-conexion";

/** Backoff exponencial: 1s, 2s, 4s, 8s, 16s y de ahí en adelante 30s.
 *  Tope en 30s para que una caída larga del backend no derive en
 *  reintentos cada varios minutos -cuando el servicio vuelva, el mapa
 *  tiene que reconectar en un tiempo razonable, no cuando le toque-. */
const RETARDO_BASE_MS = 1000;
const RETARDO_MAXIMO_MS = 30000;

/** Si pasa este tiempo sin recibir NADA (ni evento ni ping del servidor),
 *  se asume que la conexión está muerta aunque el navegador no lo haya
 *  notado y se fuerza la reconexión.
 *
 *  Por qué hace falta: una conexión TCP cortada por un intermediario
 *  (balanceador, NAT, proxy) puede quedar "abierta" del lado del cliente
 *  indefinidamente -el navegador nunca dispara onclose porque nadie le
 *  mandó un FIN-. El ping del servidor cada 25s es el latido; 70s sin
 *  latido son casi tres pings perdidos, margen de sobra para no
 *  reconectar por una demora puntual de la red. */
const TIMEOUT_SIN_LATIDO_MS = 70000;

function urlDelWebSocket(token: string): string {
  const base = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
  // http -> ws y https -> wss. Se deriva de la URL de la API en vez de
  // tener su propia variable de entorno: son el mismo servicio, y dos
  // variables que hay que mantener sincronizadas a mano es una de esas
  // cosas que se desincronizan en el primer despliegue.
  const url = new URL("/mapa-cliente/ws", base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("token", token);
  return url.toString();
}

function leerToken(): string | null {
  // Mismo criterio que services/api.ts: la sesión puede estar en
  // localStorage ("recordarme") o en sessionStorage.
  return localStorage.getItem("pangea_token") ?? sessionStorage.getItem("pangea_token");
}

export function useMapaEnVivo(onLectura: (evento: EventoLectura) => void) {
  const [estado, setEstado] = useState<EstadoConexion>("conectando");

  // onLectura vive en una ref para que el efecto que abre el WebSocket NO
  // dependa de ella: si dependiera, cada render del componente padre
  // cerraría y reabriría la conexión (el callback es una función nueva en
  // cada render), y el mapa pasaría más tiempo reconectando que conectado.
  const onLecturaRef = useRef(onLectura);
  useEffect(() => {
    onLecturaRef.current = onLectura;
  }, [onLectura]);

  const socketRef = useRef<WebSocket | null>(null);
  const intentosRef = useRef(0);
  const timerReconexionRef = useRef<number | null>(null);
  const timerLatidoRef = useRef<number | null>(null);
  // Evita que una reconexión programada se dispare después de que el
  // componente se desmontó (cambio de pantalla, logout).
  const desmontadoRef = useRef(false);

  const limpiarTimers = useCallback(() => {
    if (timerReconexionRef.current !== null) {
      window.clearTimeout(timerReconexionRef.current);
      timerReconexionRef.current = null;
    }
    if (timerLatidoRef.current !== null) {
      window.clearTimeout(timerLatidoRef.current);
      timerLatidoRef.current = null;
    }
  }, []);

  const conectar = useCallback(() => {
    if (desmontadoRef.current) return;

    const token = leerToken();
    if (!token) {
      // Sin sesión no tiene sentido reintentar: apiFetch ya redirige al
      // login cuando el token expira, así que acá solo se deja de
      // insistir en vez de golpear el backend con handshakes que van a
      // ser rechazados igual.
      setEstado("sin-conexion");
      return;
    }

    const socket = new WebSocket(urlDelWebSocket(token));
    socketRef.current = socket;

    /** Reinicia el vigilante de latido. Se llama con CADA mensaje
     *  recibido, sea un evento real o un ping. */
    const reiniciarVigilanteDeLatido = () => {
      if (timerLatidoRef.current !== null) window.clearTimeout(timerLatidoRef.current);
      timerLatidoRef.current = window.setTimeout(() => {
        // close() dispara onclose, que es quien programa la reconexión:
        // así hay UN solo camino de reconexión y no dos que puedan
        // pisarse entre sí.
        socket.close();
      }, TIMEOUT_SIN_LATIDO_MS);
    };

    socket.onopen = () => {
      if (desmontadoRef.current) return;
      intentosRef.current = 0;
      setEstado("conectado");
      reiniciarVigilanteDeLatido();
    };

    socket.onmessage = (evento) => {
      if (desmontadoRef.current) return;
      reiniciarVigilanteDeLatido();

      try {
        const mensaje = JSON.parse(evento.data);
        // "ping" es solo keep-alive: mantiene viva la conexión a través
        // del balanceador y alimenta el vigilante de latido de arriba.
        if (mensaje.tipo === "lectura" && mensaje.evento) {
          onLecturaRef.current(mensaje.evento as EventoLectura);
        }
      } catch {
        // Un mensaje ilegible no debe tumbar la conexión: se descarta y
        // se sigue escuchando.
      }
    };

    socket.onclose = (evento) => {
      if (desmontadoRef.current) return;
      limpiarTimers();

      // 1008 = policy violation: el backend rechazó el token o el permiso.
      // Reintentar con el MISMO token daría exactamente el mismo
      // resultado, así que se deja de insistir.
      if (evento.code === 1008) {
        setEstado("sin-conexion");
        return;
      }

      const intento = intentosRef.current;
      const retardo = Math.min(RETARDO_BASE_MS * 2 ** intento, RETARDO_MAXIMO_MS);
      intentosRef.current = intento + 1;
      setEstado("reconectando");
      timerReconexionRef.current = window.setTimeout(conectar, retardo);
    };

    socket.onerror = () => {
      // No se hace nada acá a propósito: el navegador dispara onclose
      // justo después de onerror, y toda la lógica de reconexión vive
      // ahí. Manejarlo en los dos lados provocaría reconexiones dobles.
    };
  }, [limpiarTimers]);

  useEffect(() => {
    desmontadoRef.current = false;
    conectar();

    return () => {
      desmontadoRef.current = true;
      limpiarTimers();
      // 1000 = cierre normal: le dice al backend que esto es una salida
      // limpia (cambio de pantalla), no una caída.
      socketRef.current?.close(1000, "Salida de la vista de mapa");
      socketRef.current = null;
    };
  }, [conectar, limpiarTimers]);

  return { estado };
}
