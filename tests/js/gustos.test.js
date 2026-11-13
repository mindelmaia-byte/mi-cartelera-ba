// Tests de public/js/gustos.js, horarios.js y calendario.js (y del parser del proxy). Datos INVENTADOS
// en tests/fixtures/letterboxd/ (mismas columnas que el export real de Letterboxd).
import * as G from "/js/gustos.js";
import * as H from "/js/horarios.js";
import { evaluarIntervalo } from "/js/calendario.js";
import { parsearRss } from "/_api/_letterboxd-rss.mjs";

const FIX = "/pruebas/fixtures/letterboxd/";
const resultados = [];
const igual = (a, b) => JSON.stringify(a) === JSON.stringify(b);
function esperar(cond, msg, detalle) { if (!cond) throw new Error(msg + (detalle !== undefined ? `\n${JSON.stringify(detalle)}` : "")); }

async function test(nombre, fn) {
  try { await fn(); resultados.push({ nombre, ok: true }); }
  catch (e) { resultados.push({ nombre, ok: false, error: e.message }); }
}

const texto = async (ruta) => (await fetch(FIX + ruta)).text();

await test("CSV: comillas, comas, saltos de línea y BOM", () => {
  const filas = G.parsearCsv('﻿A,B\r\n"uno, dos","con ""comillas""\nen dos líneas"\r\nx,y\n');
  esperar(igual(filas, [{ A: "uno, dos", B: 'con "comillas"\nen dos líneas' }, { A: "x", B: "y" }]), "parseo", filas);
});

await test("normalizar igual que en Python", () => {
  esperar(G.normalizar("¿QUERES SER MI HIJO?") === "queres ser mi hijo", "tildes y signos");
  esperar(G.normalizar("Orar Orbil & viceversa") === G.normalizar("ORAR, ORBIL Y VICEVERSA"), "& = y");
  esperar(G.normalizar("Nosferatu: Phantom der Nacht") === "nosferatu phantom der nacht", "dos puntos");
});

await test("carpeta descomprimida: usa la raíz e ignora deleted/", async () => {
  const nombres = ["watchlist.csv", "ratings.csv", "diary.csv", "watched.csv", "reviews.csv", "deleted/diary.csv"];
  const archivos = await Promise.all(nombres.map(async (n) => {
    const f = new File([await texto("export/" + n)], n.split("/").pop(), { type: "text/csv" });
    Object.defineProperty(f, "webkitRelativePath", { value: "letterboxd-usuaria_prueba-2026/" + n });
    return f;
  }));
  const d = await G.leerCarpeta(archivos);
  esperar(d.watchlist.length === 3 && d.ratings.length === 4, "cantidades", d);
  esperar(!d.vistas.some((v) => v[0] === "Borrada No Debe Contar"), "no tiene que leer deleted/");
  esperar(igual(d.ratings[3], ['Una, con "comillas" y comas', 2001, 5]), "campo con comillas", d.ratings[3]);
  esperar(d.vistas.some((v) => igual(v, ["Fat City", 1972, "2026-10-19"])), "fecha de visionado del diario", d.vistas);
});

await test("zip del export (mismo contenido que la carpeta)", async () => {
  const blob = await (await fetch(FIX + "export.zip")).blob();
  const d = await G.leerZip(blob);
  esperar(d.watchlist.length === 3 && d.ratings.length === 4 && d.vistas.length === 4, "cantidades", d);
});

await test("zip que no es de Letterboxd: error claro", async () => {
  let error = null;
  try { await G.leerZip(new Blob(["no soy un zip"])); } catch (e) { error = e; }
  esperar(error !== null, "tenía que fallar");
});

await test("parser del proxy de Vercel (api/_letterboxd-rss.mjs) igual al de Python", async () => {
  const e = parsearRss(await texto("rss.xml"));
  esperar(e.length === 2, "ignora listas", e);
  esperar(igual(e[0], { titulo: "Fitzcarraldo", anio: 1982, tmdb_id: 9343, fecha_vista: "2026-11-03", puntaje: 4.5, rewatch: false }), "campos", e[0]);
  esperar(e[1].titulo === "Película Inventada & Cía" && e[1].puntaje === null && e[1].rewatch === true, "entidades y sin puntaje", e[1]);
});

// Mini cartelera inventada para el cruce.
const datos = {
  pesos: { watchlist: 3, director_favorito: 2, director_favorito_min_peliculas: 2, director_favorito_min_estrellas: 4,
           escasez: { 1: 2, 2: 1, 3: 0.5 }, vista_hace_poco: -3, vista_antes: 0, meses_vista_reciente: 6, cantidad_para_vos: 5 },
  peliculas: {
    p1: { match: "ok", tmdb_id: 963, anio: 1941, titulos: ["El halcón maltés", "The Maltese Falcon"], directores_ids: [100] },
    p2: { match: "ok", tmdb_id: 2000, anio: 1972, titulos: ["Aguirre, la ira de Dios", "Aguirre, der Zorn Gottes", "Aguirre, the Wrath of God"], directores_ids: [200] },
    p3: { match: "ok", tmdb_id: 9343, anio: 1982, titulos: ["Fitzcarraldo"], directores_ids: [200] },
    p4: { match: "ok", tmdb_id: 16993, anio: 1972, titulos: ["Ciudad dorada", "Fat City"], directores_ids: [100] },
    p5: { match: "sin_match", titulos: [], directores_ids: [] },
  },
  directores: {
    200: { nombre: "Werner Herzog", filmografia: [[10319, 1979, ["Woyzeck"]], [6404, 1979, ["Nosferatu the Vampyre", "Nosferatu: Phantom der Nacht"]], [9343, 1982, ["Fitzcarraldo"]]] },
    100: { nombre: "John Huston", filmografia: [[963, 1941, ["The Maltese Falcon"]], [16993, 1972, ["Fat City"]]] },
  },
};

await test("cruce: watchlist, vistas (RSS por tmdb, diario por título) y directores favoritos", async () => {
  const blob = await (await fetch(FIX + "export.zip")).blob();
  const perfil = { zip: await G.leerZip(blob), rss: { entradas: parsearRss(await texto("rss.xml")) } };
  const g = G.analizar(datos, perfil);
  esperar(g.get("p1").watchlist === true, "Maltese Falcon (título en inglés) en watchlist", g.get("p1"));
  esperar(g.get("p2").watchlist === true, "Aguirre en watchlist");
  esperar(igual(g.get("p2").directores, [{ nombre: "Werner Herzog", n: 3 }]), "Herzog: Woyzeck 4, Nosferatu 4.5 (zip) + Fitzcarraldo 4.5 (RSS)", g.get("p2"));
  esperar(g.get("p3").vista === "2026-11-03", "Fitzcarraldo vista por tmdb_id del RSS", g.get("p3"));
  esperar(g.get("p4").vista === "2026-10-19" && g.get("p4").directores.length === 0, "Fat City vista; Huston no es favorito (3 estrellas)", g.get("p4"));
  esperar(!g.has("p5"), "sin match no se cruza");
  esperar(g.get("p3").puntaje === 4.5 && g.get("p4").puntaje === 3, "tu puntaje: RSS (Fitzcarraldo) y ratings.csv (Fat City)", [g.get("p3"), g.get("p4")]);
  esperar(G.estrellas(4.5) === "★★★★½" && G.estrellas(3) === "★★★" && G.estrellas(null) === "", "estrellas");
});

await test("puntaje y motivos", () => {
  const ahora = new Date("2026-11-13T12:00:00-03:00");
  const r = G.puntuar({ watchlist: true, vista: null, directores: [{ nombre: "Werner Herzog", n: 3 }] }, 1, datos.pesos, ahora);
  esperar(r.puntaje === 7 && r.motivos.length === 3, "3 + 2 + 2", r);
  const vista = G.puntuar({ watchlist: false, vista: "2026-11-03", directores: [{ nombre: "Werner Herzog", n: 3 }] }, 4, datos.pesos, ahora);
  esperar(vista.puntaje === -1 && vista.motivos.includes("ojo: la viste hace poco"), "vista hace poco resta", vista);
  esperar(G.puntuar({ watchlist: false, vista: "2026-10-19", directores: [] }, 1, datos.pesos, ahora) === null, "sin señal de gusto no se recomienda");
  esperar(G.esReciente("2026-06-01", 6, ahora) && !G.esReciente("2026-05-01", 6, ahora), "umbral de 6 meses");
});

await test("filtro de horarios: presets y personalizado (unión)", () => {
  const f = (dia_semana, hora) => ({ dia_semana, hora });
  const trabajo = H.sanear({ presets: ["trabajo"] });
  esperar(H.coincide(trabajo, f(0, "18:00")) && !H.coincide(trabajo, f(0, "17:59")), "lunes desde las 18");
  esperar(H.coincide(trabajo, f(4, "19:00")) && !H.coincide(trabajo, f(4, "16:00")), "viernes desde las 18");
  esperar(!H.coincide(trabajo, f(5, "20:00")), "después del trabajo no incluye el sábado");
  const finde = H.sanear({ presets: ["finde"] });
  esperar(H.coincide(finde, f(5, "11:00")) && H.coincide(finde, f(6, "23:00")) && !H.coincide(finde, f(4, "21:00")), "sábado y domingo completos");
  const ambos = H.sanear({ presets: ["trabajo", "finde"] });
  esperar(H.coincide(ambos, f(2, "20:00")) && H.coincide(ambos, f(6, "10:00")) && !H.coincide(ambos, f(2, "15:00")), "los dos juntos se suman");
  const mezcla = H.sanear({ presets: ["finde"], personalizado: { activo: true, dias: [null, null, { desde: "14:00", hasta: "16:00" }, null, null, null, null] } });
  esperar(H.coincide(mezcla, f(2, "15:00")) && !H.coincide(mezcla, f(2, "17:00")) && H.coincide(mezcla, f(6, "10:00")), "finde + miércoles 14 a 16");
  esperar(H.coincide(H.estadoInicial(), f(4, "03:00")), "sin filtros = todos");
  esperar(igual(H.sanear({ presets: ["semana18", "tardes", "inventado"] }).presets, []), "descarta presets viejos o basura de localStorage");
});

await test("fin estimado redondeado a 15 minutos", () => {
  esperar(H.finEstimado("19:00", 106) === "20:45", "20:46 -> 20:45");
  esperar(H.finEstimado("19:00", 98) === "20:45", "20:38 -> 20:45");
  esperar(H.finEstimado("18:10", 82) === "19:30", "19:32 -> 19:30");
  esperar(H.finEstimado("22:15", 120) === "00:15", "pasa la medianoche");
  esperar(H.finEstimado("17:52", 0) === null && H.finEstimado("17:52", null) === null, "sin duración, nada");
  esperar(H.finEstimado("14:00", 7) === "14:00", "redondea al más cercano aunque sea el mismo cuarto");
});

await test("calendario: entra / justo / no entra", () => {
  const t = (h) => Date.parse(`2026-11-14T${h}:00-03:00`);
  const M = { antes: 30, despues: 15 };
  const b = (i, f) => [{ inicio: t(i), fin: t(f) }];
  esperar(evaluarIntervalo(t("20:00"), 100, M, b("10:00", "11:00")).estado === "entra", "libre");
  esperar(evaluarIntervalo(t("20:00"), 100, M, b("21:00", "22:00")).estado === "no-entra", "pisa la película");
  esperar(evaluarIntervalo(t("20:00"), 100, M, b("19:00", "19:45")).estado === "justo", "pisa el margen antes");
  esperar(evaluarIntervalo(t("20:00"), 100, M, b("21:50", "23:00")).estado === "justo", "pisa el margen después");
});

const salida = document.getElementById("salida");
for (const r of resultados) {
  const li = document.createElement("li");
  li.className = r.ok ? "ok" : "mal";
  li.textContent = r.ok ? `✓ ${r.nombre}` : `✗ ${r.nombre}: ${r.error}`;
  salida.append(li);
}
const fallas = resultados.filter((r) => !r.ok).length;
document.getElementById("total").textContent = `${resultados.length - fallas}/${resultados.length} pasan`;
window.__resultados = resultados;
