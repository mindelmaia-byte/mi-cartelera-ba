// Google Calendar: solo disponibilidad (freeBusy) del calendario principal.
// - OAuth con Google Identity Services, flujo de token en el navegador (sin refresh tokens).
// - El token y los bloques ocupados viven solo en memoria: nada se guarda ni sale a otro servidor.
// - Scope mínimo: calendar.freebusy ("ver tu disponibilidad en tus calendarios").

import { GOOGLE_CLIENT_ID } from "../config.js";

const SCOPE = "https://www.googleapis.com/auth/calendar.freebusy";
const URL_GIS = "https://accounts.google.com/gsi/client";
const URL_FREEBUSY = "https://www.googleapis.com/calendar/v3/freeBusy";
export const DURACION_SUPUESTA = 120; // minutos, si no sabemos cuánto dura la película

let token = null;
let expira = 0;
let ocupados = []; // [{inicio: ms, fin: ms}]
let clienteToken = null;

export const configurado = () => !!GOOGLE_CLIENT_ID;
export const conectado = () => !!token && Date.now() < expira;

function cargarGIS() {
  if (window.google?.accounts?.oauth2) return Promise.resolve();
  return new Promise((ok, mal) => {
    const s = document.createElement("script");
    s.src = URL_GIS;
    s.async = true;
    s.onload = () => ok();
    s.onerror = () => mal(new Error("no se pudo cargar Google Identity Services"));
    document.head.append(s);
  });
}

// Pide permiso (abre el popup de Google) y trae los bloques ocupados de la ventana.
export async function conectar(desdeIso, hastaIso) {
  await cargarGIS();
  const respuesta = await new Promise((ok, mal) => {
    clienteToken = window.google.accounts.oauth2.initTokenClient({
      client_id: GOOGLE_CLIENT_ID,
      scope: SCOPE,
      callback: (r) => (r.error ? mal(new Error(r.error_description || r.error)) : ok(r)),
      error_callback: (e) => mal(new Error(e.message || e.type || "se cerró la ventana de Google")),
    });
    clienteToken.requestAccessToken();
  });
  if (!window.google.accounts.oauth2.hasGrantedAllScopes(respuesta, SCOPE)) {
    throw new Error("no se otorgó el permiso de disponibilidad");
  }
  token = respuesta.access_token;
  expira = Date.now() + (Number(respuesta.expires_in) || 3600) * 1000 - 60_000;
  await actualizar(desdeIso, hastaIso);
}

export async function actualizar(desdeIso, hastaIso) {
  if (!conectado()) throw new Error("la sesión de Google venció; volvé a conectar");
  const r = await fetch(URL_FREEBUSY, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ timeMin: desdeIso, timeMax: hastaIso, items: [{ id: "primary" }] }),
  });
  if (!r.ok) throw new Error(`Google Calendar respondió ${r.status}`);
  const datos = await r.json();
  const cal = datos.calendars?.primary;
  if (cal?.errors?.length) throw new Error(`Google Calendar: ${cal.errors[0].reason}`);
  ocupados = (cal?.busy ?? []).map((b) => ({ inicio: Date.parse(b.start), fin: Date.parse(b.end) }));
}

export function desconectar() {
  if (token && window.google?.accounts?.oauth2) window.google.accounts.oauth2.revoke(token, () => {});
  token = null;
  expira = 0;
  ocupados = [];
}

// "entra" | "justo" (solo se pisa con el margen de traslado) | "no-entra", con el bloque que molesta.
export function evaluar(funcion, margenes) {
  const duracion = funcion.duracion_aprox || DURACION_SUPUESTA;
  return evaluarIntervalo(Date.parse(funcion.inicio), duracion, margenes, ocupados);
}

// Pura, para poder probarla sin Google.
export function evaluarIntervalo(inicio, duracionMin, margenes, bloques) {
  const fin = inicio + duracionMin * 60_000;
  const conMargen = [inicio - margenes.antes * 60_000, fin + margenes.despues * 60_000];
  let justo = null;
  for (const b of bloques) {
    if (b.inicio < fin && b.fin > inicio) return { estado: "no-entra", bloque: b };
    if (!justo && b.inicio < conMargen[1] && b.fin > conMargen[0]) justo = b;
  }
  return justo ? { estado: "justo", bloque: justo } : { estado: "entra", bloque: null };
}

// Link prearmado para agendar (no necesita permisos: abre Google Calendar con el evento cargado).
export function linkAgendar(funcion, cine, duracionMin) {
  const ini = new Date(funcion.inicio);
  const fin = new Date(ini.getTime() + (duracionMin || DURACION_SUPUESTA) * 60_000);
  const utc = (d) => d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const detalles = [
    funcion.ciclo ? `Ciclo: ${funcion.ciclo}` : null,
    funcion.url_entradas ? `Entradas: ${funcion.url_entradas}` : null,
    funcion.modo_venta === "boleteria" ? "Entradas: solo en boletería" : null,
    funcion.modo_venta === "gratis" ? "Gratis, se retira en el lugar" : null,
  ].filter(Boolean).join("\n");
  const p = new URLSearchParams({
    action: "TEMPLATE",
    text: `${funcion.titulo} — ${cine.nombre}`,
    dates: `${utc(ini)}/${utc(fin)}`,
    location: [cine.nombre, cine.direccion].filter(Boolean).join(", "),
    details: detalles,
    ctz: "America/Argentina/Buenos_Aires",
  });
  return `https://calendar.google.com/calendar/render?${p}`;
}
