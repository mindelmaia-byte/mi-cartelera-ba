// Cloudflare Pages Function: GET /api/letterboxd?user=<usuario>
// Proxy del RSS público de Letterboxd (no habilita CORS). Devuelve el mismo JSON que
// cartelera/letterboxd.py. No guarda nada: solo una caché HTTP de 1 hora por usuario.

const RE_USUARIO = /^[A-Za-z0-9_]{1,40}$/;

function json(cuerpo, status = 200, extra = {}) {
  return new Response(JSON.stringify(cuerpo), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "public, max-age=3600", ...extra },
  });
}

function campo(item, etiqueta) {
  const m = item.match(new RegExp(`<${etiqueta}>([\\s\\S]*?)</${etiqueta}>`));
  if (!m) return null;
  return m[1].replace(/^<!\[CDATA\[|\]\]>$/g, "").trim()
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'");
}

export function parsearRss(xml) {
  const entradas = [];
  for (const [, item] of xml.matchAll(/<item>([\s\S]*?)<\/item>/g)) {
    const titulo = campo(item, "letterboxd:filmTitle");
    if (!titulo) continue; // listas
    const anio = campo(item, "letterboxd:filmYear");
    const tmdb = campo(item, "tmdb:movieId");
    const puntaje = campo(item, "letterboxd:memberRating");
    entradas.push({
      titulo,
      anio: anio && /^\d+$/.test(anio) ? Number(anio) : null,
      tmdb_id: tmdb && /^\d+$/.test(tmdb) ? Number(tmdb) : null,
      fecha_vista: campo(item, "letterboxd:watchedDate") || null,
      puntaje: puntaje ? Number(puntaje) : null,
      rewatch: campo(item, "letterboxd:rewatch") === "Yes",
    });
  }
  return entradas;
}

export async function onRequestGet({ request }) {
  const usuario = new URL(request.url).searchParams.get("user") || "";
  if (!RE_USUARIO.test(usuario)) return json({ error: "usuario inválido" }, 400);
  const r = await fetch(`https://letterboxd.com/${usuario}/rss/`, {
    headers: { "user-agent": "cartelera-ba/0.1 (proyecto educativo)" },
    cf: { cacheTtl: 3600, cacheEverything: true },
  });
  if (r.status === 404) return json({ error: "no existe ese usuario de Letterboxd (o su perfil no es público)" }, 404);
  if (!r.ok) return json({ error: `Letterboxd respondió ${r.status}` }, 502, { "cache-control": "no-store" });
  return json({ usuario, entradas: parsearRss(await r.text()) });
}
