// Parser del RSS público de Letterboxd -> la misma salida que cartelera/letterboxd.py.
// Vercel no publica como función los archivos de api/ que empiezan con "_": esto es solo un módulo
// compartido (lo usan api/letterboxd.mjs y los tests de la interfaz en tests/js/).

export const RE_USUARIO = /^[A-Za-z0-9_]{1,40}$/;

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
