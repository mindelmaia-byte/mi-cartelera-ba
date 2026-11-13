// Función de Vercel: GET /api/letterboxd?user=<usuario>
// Proxy del RSS público de Letterboxd (que no habilita CORS). Devuelve el mismo JSON que
// cartelera/letterboxd.py (que imita esto en local con `cartelera servir`).
// No guarda nada: solo deja que la CDN de Vercel cachee la respuesta 1 hora por usuario.

import { RE_USUARIO, parsearRss } from "./_letterboxd-rss.mjs";

function json(cuerpo, status = 200, cache = "public, s-maxage=3600, max-age=600") {
  return new Response(JSON.stringify(cuerpo), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": cache },
  });
}

export async function GET(request) {
  const usuario = new URL(request.url).searchParams.get("user") || "";
  if (!RE_USUARIO.test(usuario)) return json({ error: "usuario inválido" }, 400, "no-store");
  let r;
  try {
    r = await fetch(`https://letterboxd.com/${usuario}/rss/`, {
      headers: { "user-agent": "cartelera-ba/0.1 (proyecto educativo)" },
    });
  } catch {
    return json({ error: "no se pudo contactar a Letterboxd" }, 502, "no-store");
  }
  if (r.status === 404) return json({ error: "no existe ese usuario de Letterboxd (o su perfil no es público)" }, 404, "no-store");
  if (!r.ok) return json({ error: `Letterboxd respondió ${r.status}` }, 502, "no-store");
  return json({ usuario, entradas: parsearRss(await r.text()) });
}
