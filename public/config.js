// Configuración pública del sitio. Nada de esto es secreto.
// GOOGLE_CLIENT_ID: el ID de cliente OAuth "Aplicación web" de Google Cloud (ver docs/google-calendar.md).
// Vacío = el bloque de Google Calendar no se muestra y la cartelera funciona igual.
export const GOOGLE_CLIENT_ID = "";

// Proxy del RSS de Letterboxd (Cloudflare Pages Function en producción; `cartelera servir` en local).
export const URL_LETTERBOXD = "api/letterboxd";
