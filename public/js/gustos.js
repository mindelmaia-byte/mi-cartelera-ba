// Gustos de Letterboxd. Todo se procesa en el navegador: el zip/carpeta nunca se sube, y lo único
// que sale es el pedido del RSS público (por el proxy /api/letterboxd, porque Letterboxd no tiene CORS).

import { URL_LETTERBOXD } from "../config.js";

const URL_JSZIP = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js";
const ARCHIVOS = ["watchlist.csv", "ratings.csv", "diary.csv", "watched.csv"];

// ---------- texto ----------

// Igual que cartelera/texto.py:normalizar.
export function normalizar(s) {
  if (!s) return "";
  return s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/&/g, " y ")
    .replace(/[^\p{L}\p{N}_\s]/gu, " ").split(/\s+/).filter(Boolean).join(" ");
}

// CSV RFC 4180 (comillas, comas y saltos de línea dentro de campos: las reseñas los tienen).
export function parsearCsv(texto) {
  const filas = [];
  let fila = [], campo = "", comillas = false;
  texto = texto.replace(/^﻿/, "");
  for (let i = 0; i < texto.length; i++) {
    const c = texto[i];
    if (comillas) {
      if (c === '"') {
        if (texto[i + 1] === '"') { campo += '"'; i++; } else comillas = false;
      } else campo += c;
    } else if (c === '"') comillas = true;
    else if (c === ",") { fila.push(campo); campo = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && texto[i + 1] === "\n") i++;
      fila.push(campo); filas.push(fila); fila = []; campo = "";
    } else campo += c;
  }
  if (campo !== "" || fila.length) { fila.push(campo); filas.push(fila); }
  const [cabecera, ...resto] = filas.filter((f) => f.length > 1 || f[0] !== "");
  if (!cabecera) return [];
  return resto.map((f) => Object.fromEntries(cabecera.map((h, i) => [h.trim(), f[i] ?? ""])));
}

const anio = (s) => (/^\d{4}$/.test((s || "").trim()) ? Number(s) : null);

// De los CSV del export a una forma compacta (es lo que se guarda en el navegador).
export function desdeCsv({ watchlist = "", ratings = "", diary = "", watched = "" }) {
  const vistas = [];
  for (const r of parsearCsv(diary)) vistas.push([r.Name, anio(r.Year), r["Watched Date"] || r.Date || null]);
  for (const r of parsearCsv(watched)) vistas.push([r.Name, anio(r.Year), r.Date || null]);
  return {
    watchlist: parsearCsv(watchlist).map((r) => [r.Name, anio(r.Year)]).filter((x) => x[0]),
    ratings: parsearCsv(ratings).map((r) => [r.Name, anio(r.Year), Number(r.Rating) || null]).filter((x) => x[0] && x[2]),
    vistas: vistas.filter((x) => x[0]),
  };
}

// Archivos de la raíz del export (no los de deleted/, orphaned/, likes/, lists/).
function elegirArchivos(rutas) {
  const elegidos = {};
  for (const nombre of ARCHIVOS) {
    const candidatos = rutas.filter((r) => r.split("/").pop() === nombre && !/(^|\/)(deleted|orphaned|likes|lists)\//.test(r));
    candidatos.sort((a, b) => a.split("/").length - b.split("/").length);
    if (candidatos[0]) elegidos[nombre.replace(".csv", "")] = candidatos[0];
  }
  return elegidos;
}

function cargarJSZip() {
  if (window.JSZip) return Promise.resolve(window.JSZip);
  return new Promise((ok, mal) => {
    const s = document.createElement("script");
    s.src = URL_JSZIP;
    s.onload = () => ok(window.JSZip);
    s.onerror = () => mal(new Error("no se pudo cargar el lector de zip"));
    document.head.append(s);
  });
}

export async function leerZip(archivo) {
  const JSZip = await cargarJSZip();
  const zip = await JSZip.loadAsync(archivo);
  const elegidos = elegirArchivos(Object.keys(zip.files));
  if (!elegidos.ratings && !elegidos.watchlist && !elegidos.diary) throw new Error("el zip no parece un export de Letterboxd");
  const textos = {};
  for (const [clave, ruta] of Object.entries(elegidos)) textos[clave] = await zip.file(ruta).async("string");
  return desdeCsv(textos);
}

// <input type="file" webkitdirectory>: la carpeta ya descomprimida.
export async function leerCarpeta(listaArchivos) {
  const porRuta = new Map([...listaArchivos].map((f) => [f.webkitRelativePath || f.name, f]));
  const elegidos = elegirArchivos([...porRuta.keys()]);
  if (!elegidos.ratings && !elegidos.watchlist && !elegidos.diary) throw new Error("la carpeta no parece un export de Letterboxd");
  const textos = {};
  for (const [clave, ruta] of Object.entries(elegidos)) textos[clave] = await porRuta.get(ruta).text();
  return desdeCsv(textos);
}

export async function leerRss(usuario) {
  const r = await fetch(`${URL_LETTERBOXD}?user=${encodeURIComponent(usuario)}`);
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(cuerpo.error || `el proxy respondió ${r.status}`);
  return cuerpo.entradas;
}

// ---------- cruce con la cartelera ----------

function indiceCartelera(datos) {
  const porTitulo = new Map(); // título normalizado -> [pid]
  const porTmdb = new Map();   // tmdb_id -> [pid]
  for (const [pid, p] of Object.entries(datos.peliculas)) {
    if (p.match !== "ok") continue;
    for (const t of p.titulos) {
      const k = normalizar(t);
      if (!porTitulo.has(k)) porTitulo.set(k, []);
      porTitulo.get(k).push(pid);
    }
    if (!porTmdb.has(p.tmdb_id)) porTmdb.set(p.tmdb_id, []);
    porTmdb.get(p.tmdb_id).push(pid);
  }
  return { porTitulo, porTmdb };
}

// Título + año (±1) contra los títulos de TMDB (castellano, original, inglés) de la película.
function buscar(indice, datos, nombre, anioEntrada) {
  return (indice.porTitulo.get(normalizar(nombre)) ?? []).filter((pid) => {
    const a = datos.peliculas[pid].anio;
    return anioEntrada === null || a === null || Math.abs(a - anioEntrada) <= 1;
  });
}

function coincideFilmo(film, nombre, anioEntrada) {
  const [, a, titulos] = film;
  if (anioEntrada !== null && a !== null && Math.abs(a - anioEntrada) > 1) return false;
  const n = normalizar(nombre);
  return titulos.some((t) => normalizar(t) === n);
}

// Devuelve, por película de la cartelera (pid): {watchlist, vista: "AAAA-MM-DD"|null, directores: [{nombre, n}]}
export function analizar(datos, perfil) {
  const pesos = datos.pesos;
  const indice = indiceCartelera(datos);
  const porPid = new Map();
  const obtener = (pid) => {
    if (!porPid.has(pid)) porPid.set(pid, { watchlist: false, vista: null, directores: [] });
    return porPid.get(pid);
  };
  const marcarVista = (pid, fecha) => {
    const g = obtener(pid);
    const actual = g.vista === "sin fecha" ? null : g.vista;
    if (fecha && (!actual || fecha > actual)) g.vista = fecha;
    else if (!g.vista) g.vista = fecha || "sin fecha";
  };

  const zip = perfil.zip;
  const rss = perfil.rss?.entradas ?? [];
  if (zip) {
    for (const [nombre, a] of zip.watchlist) for (const pid of buscar(indice, datos, nombre, a)) obtener(pid).watchlist = true;
    for (const [nombre, a, fecha] of zip.vistas) for (const pid of buscar(indice, datos, nombre, a)) marcarVista(pid, fecha);
  }
  for (const e of rss) {
    const pids = e.tmdb_id ? indice.porTmdb.get(e.tmdb_id) ?? [] : buscar(indice, datos, e.titulo, e.anio);
    for (const pid of pids) marcarVista(pid, e.fecha_vista);
  }

  // Directores que te gustan: N películas con >= X estrellas en su filmografía.
  const minEstrellas = pesos.director_favorito_min_estrellas;
  const gustadasZip = (zip?.ratings ?? []).filter((r) => r[2] >= minEstrellas);
  const gustadasRss = rss.filter((e) => e.puntaje >= minEstrellas);
  const favoritos = new Map(); // persona_id -> {nombre, n}
  for (const [id, d] of Object.entries(datos.directores)) {
    const vistas = new Set();
    for (const film of d.filmografia) {
      if (gustadasRss.some((e) => e.tmdb_id === film[0]) ||
          gustadasZip.some(([nombre, a]) => coincideFilmo(film, nombre, a))) vistas.add(film[0]);
    }
    if (vistas.size >= pesos.director_favorito_min_peliculas) favoritos.set(Number(id), { nombre: d.nombre, n: vistas.size });
  }
  for (const [pid, p] of Object.entries(datos.peliculas)) {
    const dirs = p.directores_ids.filter((i) => favoritos.has(i)).map((i) => favoritos.get(i));
    if (dirs.length) obtener(pid).directores = dirs;
  }
  return porPid;
}

export function esReciente(fecha, meses, ahora = new Date()) {
  if (!fecha || fecha === "sin fecha") return false;
  const limite = new Date(ahora);
  limite.setMonth(limite.getMonth() - meses);
  return fecha >= limite.toISOString().slice(0, 10);
}

// Puntaje de una película (pid) para "Para vos". Requiere al menos una señal de gusto
// (watchlist o director): la escasez sola no alcanza para recomendar.
export function puntuar(gusto, nFunciones, pesos, ahora = new Date()) {
  if (!gusto || (!gusto.watchlist && !gusto.directores.length)) return null;
  let puntaje = 0;
  const motivos = [];
  if (gusto.watchlist) { puntaje += pesos.watchlist; motivos.push("está en tu watchlist"); }
  for (const d of gusto.directores) {
    puntaje += pesos.director_favorito;
    motivos.push(`te gustaron ${d.n} películas de ${d.nombre}`);
    break; // un solo bono por director aunque haya codirección
  }
  const escasez = pesos.escasez[String(nFunciones)];
  if (escasez) {
    puntaje += escasez;
    motivos.push(nFunciones === 1 ? "es la única función en 10 días" : `solo ${nFunciones} funciones en 10 días`);
  }
  if (gusto.vista) {
    if (esReciente(gusto.vista, pesos.meses_vista_reciente, ahora)) {
      puntaje += pesos.vista_hace_poco;
      motivos.push("ojo: la viste hace poco");
    } else {
      puntaje += pesos.vista_antes;
    }
  }
  return { puntaje, motivos };
}
