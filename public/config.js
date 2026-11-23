// Configuración pública del sitio. Nada de esto es secreto.
// GOOGLE_CLIENT_ID: el ID de cliente OAuth "Aplicación web" de Google Cloud (ver docs/google-calendar.md).
// Vacío = el bloque de Google Calendar no se muestra y la cartelera funciona igual.
export const GOOGLE_CLIENT_ID = "317835085778-u46pg7luom5frnogram96btrp4q6bv69.apps.googleusercontent.com";

// Proxy del RSS de Letterboxd (función de Vercel api/letterboxd.mjs en producción; `cartelera servir` en local).
export const URL_LETTERBOXD = "api/letterboxd";
