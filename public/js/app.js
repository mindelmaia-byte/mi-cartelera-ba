import { leer, guardar } from "./almacen.js";
import * as H from "./horarios.js";
import * as Cal from "./calendario.js";
import * as G from "./gustos.js";

const RUTA_DATOS = "data/cartelera.json";
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

const estado = {
  datos: null,
  cines: new Map(),
  horario: H.sanear(leer("horario", null)),
  cinesExcluidos: new Set(leer("cines-excluidos", [])),
  comerciales: !!leer("comerciales", false),
  dia: null, // "AAAA-MM-DD" o "todos"
  orden: { columna: "hora", asc: true },
  margenes: sanearMargenes(leer("margenes", null)),
  soloEntran: !!leer("solo-entran", false),
  calendario: { cargando: false, error: null },
  // Letterboxd: {usuario, rss: {cargado, entradas}, zip: {cargado, watchlist, ratings, vistas}}
  perfil: sanearPerfil(leer("letterboxd", null)),
  letterboxd: { cargando: false, error: null },
  gustos: new Map(), // pid -> {watchlist, vista, directores}
};

function sanearPerfil(p) {
  if (!p || typeof p !== "object") return { usuario: null, rss: null, zip: null };
  return {
    usuario: typeof p.usuario === "string" && /^[A-Za-z0-9_]{1,40}$/.test(p.usuario) ? p.usuario : null,
    rss: p.rss && Array.isArray(p.rss.entradas) ? p.rss : null,
    zip: p.zip && Array.isArray(p.zip.watchlist) && Array.isArray(p.zip.ratings) && Array.isArray(p.zip.vistas) ? p.zip : null,
  };
}

const hayGustos = () => !!(estado.perfil.rss || estado.perfil.zip);

function sanearMargenes(m) {
  const n = (v, d) => (Number.isFinite(Number(v)) && Number(v) >= 0 && Number(v) <= 240 ? Number(v) : d);
  return { antes: n(m?.antes, 30), despues: n(m?.despues, 15) };
}

const $ = (sel) => document.querySelector(sel);

// replaceChildren convierte null en el texto "null": acá se filtran los vacíos.
function reemplazar(nodo, ...hijos) {
  nodo.replaceChildren(...hijos.flat().filter((h) => h !== null && h !== undefined && h !== false));
}

function el(tag, attrs = {}, ...hijos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const h of hijos.flat()) if (h !== null && h !== undefined && h !== false) n.append(h);
  return n;
}

// ---------- datos ----------

async function cargar() {
  try {
    const r = await fetch(RUTA_DATOS, { cache: "no-cache" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    estado.datos = await r.json();
  } catch (e) {
    $("#resumen").textContent = `No se pudo cargar la cartelera (${e.message}).`;
    return;
  }
  for (const c of estado.datos.cines) estado.cines.set(c.id, c);
  const dias = diasVentana();
  estado.dia = dias.find((d) => contarDia(d) > 0) ?? dias[0];
  pintarTodo();
  refrescarRssSiHaceFalta();
  bienvenida();
}

// Una sola pantalla al primer ingreso; se puede volver a abrir desde "¿Cómo funciona?".
function bienvenida(forzar = false) {
  const d = $("#bienvenida");
  $("#bienvenida-paso-calendario").hidden = !Cal.configurado();
  if (!forzar && leer("bienvenida-vista", false)) return;
  d.addEventListener("close", () => guardar("bienvenida-vista", true), { once: true });
  if (typeof d.showModal === "function") d.showModal();
}
$("#abrir-bienvenida").addEventListener("click", () => bienvenida(true));

function diasVentana() {
  const [a, m, d] = estado.datos.desde.split("-").map(Number);
  return Array.from({ length: estado.datos.dias }, (_, i) => {
    const f = new Date(Date.UTC(a, m - 1, d + i));
    return f.toISOString().slice(0, 10);
  });
}

function etiquetaDia(iso) {
  const [a, m, d] = iso.split("-").map(Number);
  const dow = (new Date(Date.UTC(a, m - 1, d)).getUTCDay() + 6) % 7; // 0 = lunes
  return { corto: H.DIAS_CORTOS[dow], numero: d, mes: MESES[m - 1] };
}

// Funciones que pasan horario + cines (todas las de la ventana, sin filtrar por día).
function funcionesFiltradas() {
  const ahora = Date.now();
  return estado.datos.funciones.filter((f) => {
    if (Date.parse(f.inicio) < ahora) return false; // ya empezó
    const cine = estado.cines.get(f.cine);
    if (!cine) return false;
    if (cine.es_comercial && !estado.comerciales) return false;
    if (estado.cinesExcluidos.has(f.cine)) return false;
    if (!H.coincide(estado.horario, f)) return false;
    if (estado.soloEntran && Cal.conectado() && Cal.evaluar(f, estado.margenes).estado === "no-entra") return false;
    return true;
  });
}

// ---------- calendario ----------

function ventanaIso() {
  const desde = new Date(Math.max(Date.now(), Date.parse(estado.datos.desde + "T00:00:00-03:00")));
  const hasta = new Date(Date.parse(estado.datos.desde + "T00:00:00-03:00") + estado.datos.dias * 86_400_000);
  return [desde.toISOString(), hasta.toISOString()];
}

function pintarCalendario() {
  const sec = $("#calendario");
  if (!Cal.configurado()) { sec.hidden = true; return; }
  sec.hidden = false;
  const con = Cal.conectado();
  const c = estado.calendario;
  const margen = (campo, texto) => el("label", { class: "margen" }, texto, " ",
    el("input", {
      type: "number", min: "0", max: "240", step: "5", value: String(estado.margenes[campo]),
      "aria-label": `${texto} (minutos)`,
      onchange: (ev) => {
        estado.margenes = sanearMargenes({ ...estado.margenes, [campo]: ev.target.value });
        guardar("margenes", estado.margenes);
        pintarDias(); pintarTabla();
      },
    }), " min");

  reemplazar(sec, 
    el("div", { class: "cal-fila" },
      el("span", { class: con ? "cal-estado conectado" : "cal-estado" },
        el("span", { class: "punto", "aria-hidden": "true" }),
        con ? "Google Calendar conectado" : "Google Calendar desconectado"),
      con
        ? el("span", { class: "cal-acciones" },
            el("button", { type: "button", class: "boton", onclick: refrescarCalendario, disabled: c.cargando }, "Actualizar"),
            el("button", { type: "button", class: "boton secundario", onclick: desconectarCalendario }, "Desconectar"))
        : el("button", { type: "button", class: "boton", onclick: conectarCalendario, disabled: c.cargando },
            c.cargando ? "Conectando…" : "Conectar Google Calendar")),
    con ? el("div", { class: "cal-fila cal-opciones" },
      margen("antes", "Margen antes"), margen("despues", "después"),
      el("label", { class: "interruptor-linea" },
        el("input", { type: "checkbox", checked: estado.soloEntran, onchange: (ev) => {
          estado.soloEntran = ev.target.checked; guardar("solo-entran", estado.soloEntran);
          pintarDias(); pintarTabla();
        } }),
        " Solo las que me entran")) : null,
    c.error ? el("p", { class: "cal-error" }, c.error) : null,
    !con ? el("p", { class: "ayuda" }, "Opcional. Solo lee tus horarios ocupados del calendario principal (no ve títulos ni detalles) y nada se guarda fuera de este navegador.") : null,
  );
}

async function conectarCalendario() {
  estado.calendario = { cargando: true, error: null };
  pintarCalendario();
  try {
    await Cal.conectar(...ventanaIso());
  } catch (e) {
    estado.calendario.error = `No se pudo conectar: ${e.message}.`;
  }
  estado.calendario.cargando = false;
  pintarCalendario(); pintarDias(); pintarTabla();
}

async function refrescarCalendario() {
  estado.calendario = { cargando: true, error: null };
  pintarCalendario();
  try {
    await Cal.actualizar(...ventanaIso());
  } catch (e) {
    estado.calendario.error = `${e.message}.`;
  }
  estado.calendario.cargando = false;
  pintarCalendario(); pintarDias(); pintarTabla();
}

function desconectarCalendario() {
  Cal.desconectar();
  estado.calendario = { cargando: false, error: null };
  pintarCalendario(); pintarDias(); pintarTabla();
}

// ---------- Letterboxd ----------

const FECHA = (iso) => {
  const [a, m, d] = iso.split("-");
  return `${Number(d)}/${Number(m)}/${a}`;
};

function recalcularGustos() {
  estado.gustos = hayGustos() ? G.analizar(estado.datos, estado.perfil) : new Map();
}

function guardarPerfil() {
  guardar("letterboxd", estado.perfil);
  recalcularGustos();
  pintarLetterboxd(); pintarParaVos(); pintarTabla();
}

function pintarLetterboxd() {
  const sec = $("#letterboxd");
  const p = estado.perfil;
  const lb = estado.letterboxd;
  const entradaZip = el("input", { type: "file", accept: ".zip,application/zip", hidden: true, onchange: (ev) => importar(() => G.leerZip(ev.target.files[0])) });
  const entradaCarpeta = el("input", { type: "file", webkitdirectory: true, multiple: true, hidden: true, onchange: (ev) => importar(() => G.leerCarpeta(ev.target.files)) });
  const botonesExport = [
    el("button", { type: "button", class: "boton secundario", onclick: () => entradaZip.click(), disabled: lb.cargando }, p.zip ? "Reemplazar zip" : "Subir zip del export"),
    el("button", { type: "button", class: "enlace", onclick: () => entradaCarpeta.click(), disabled: lb.cargando }, "o la carpeta descomprimida"),
    entradaZip, entradaCarpeta,
  ];

  let cuerpo;
  if (!p.usuario && !p.zip) {
    const campo = el("input", { type: "text", id: "lb-usuario", placeholder: "tu usuario", autocomplete: "off", spellcheck: "false",
      "aria-label": "Usuario de Letterboxd", pattern: "[A-Za-z0-9_]{1,40}" });
    cuerpo = [
      el("form", { class: "cal-fila lb-form", onsubmit: (ev) => { ev.preventDefault(); conectarLetterboxd(campo.value.trim()); } },
        el("span", { class: "cal-estado" }, el("span", { class: "punto", "aria-hidden": "true" }), "Letterboxd"),
        el("span", { class: "cal-acciones" }, campo,
          el("button", { type: "submit", class: "boton", disabled: lb.cargando }, lb.cargando ? "Cargando…" : "Cargar"))),
      el("div", { class: "cal-fila cal-opciones" }, ...botonesExport),
      el("p", { class: "ayuda" }, "Opcional. Con tu usuario leemos tus vistas recientes (feed público); con el zip, también tu watchlist y tu historial. Todo queda en este navegador."),
    ];
  } else {
    const partes = [];
    if (p.usuario) partes.push(`@${p.usuario}${p.rss ? ` · ${p.rss.entradas.length} vistas recientes` : ""}`);
    if (p.zip) partes.push(`export: ${p.zip.watchlist.length} en watchlist, ${p.zip.ratings.length} puntajes, ${p.zip.vistas.length} vistas`);
    cuerpo = [
      el("div", { class: "cal-fila" },
        el("span", { class: "cal-estado conectado" }, el("span", { class: "punto", "aria-hidden": "true" }), "Letterboxd ", el("span", { class: "lb-detalle" }, partes.join(" · "))),
        el("span", { class: "cal-acciones" },
          p.usuario ? el("button", { type: "button", class: "boton secundario", onclick: () => conectarLetterboxd(p.usuario), disabled: lb.cargando }, lb.cargando ? "Cargando…" : "Actualizar") : null,
          el("button", { type: "button", class: "boton secundario", onclick: olvidarLetterboxd }, "Olvidar"))),
      el("div", { class: "cal-fila cal-opciones" }, ...botonesExport),
    ];
  }
  reemplazar(sec, ...cuerpo, lb.error ? el("p", { class: "cal-error" }, lb.error) : null);
}

async function conectarLetterboxd(usuario) {
  if (!/^[A-Za-z0-9_]{1,40}$/.test(usuario)) {
    estado.letterboxd.error = "Ese usuario no es válido (solo letras, números y _).";
    pintarLetterboxd();
    return;
  }
  estado.letterboxd = { cargando: true, error: null };
  pintarLetterboxd();
  try {
    const entradas = await G.leerRss(usuario);
    estado.perfil.usuario = usuario;
    estado.perfil.rss = { cargado: new Date().toISOString(), entradas };
  } catch (e) {
    estado.letterboxd.error = `No se pudo leer el perfil de Letterboxd: ${e.message}.`;
  }
  estado.letterboxd.cargando = false;
  guardarPerfil();
}

async function importar(leerExport) {
  estado.letterboxd = { cargando: true, error: null };
  pintarLetterboxd();
  try {
    estado.perfil.zip = { cargado: new Date().toISOString(), ...(await leerExport()) };
  } catch (e) {
    estado.letterboxd.error = `No se pudo leer el export: ${e.message}.`;
  }
  estado.letterboxd.cargando = false;
  guardarPerfil();
}

function olvidarLetterboxd() {
  estado.perfil = { usuario: null, rss: null, zip: null };
  estado.letterboxd = { cargando: false, error: null };
  guardarPerfil();
}

// RSS de más de una hora: se vuelve a pedir en segundo plano.
function refrescarRssSiHaceFalta() {
  const p = estado.perfil;
  if (p.usuario && (!p.rss || Date.now() - Date.parse(p.rss.cargado) > 3_600_000)) conectarLetterboxd(p.usuario);
}

// ---------- Para vos ----------

const clavePeli = (f) => {
  const p = peli(f);
  return p.tmdb_id ? `t${p.tmdb_id}` : `p${f.pelicula}`;
};

function pintarParaVos() {
  const sec = $("#para-vos");
  if (!hayGustos()) { sec.hidden = true; return; }
  sec.hidden = false;
  const pesos = estado.datos.pesos;
  const ahora = Date.now();
  const cuantas = new Map();
  for (const f of estado.datos.funciones) {
    if (Date.parse(f.inicio) < ahora) continue;
    cuantas.set(clavePeli(f), (cuantas.get(clavePeli(f)) ?? 0) + 1);
  }
  // Candidatas: pasan horario y cines; con el calendario conectado, también tienen que entrar.
  const mejores = new Map(); // película -> {f, puntaje, motivos}
  for (const f of funcionesFiltradas()) {
    if (Cal.conectado() && Cal.evaluar(f, estado.margenes).estado === "no-entra") continue;
    const r = G.puntuar(estado.gustos.get(f.pelicula), cuantas.get(clavePeli(f)), pesos);
    if (!r || r.puntaje <= 0) continue;
    const k = clavePeli(f);
    if (!mejores.has(k)) mejores.set(k, { f, ...r }); // la más temprana (funcionesFiltradas viene ordenada)
  }
  const top = [...mejores.values()].sort((a, b) => b.puntaje - a.puntaje || a.f.inicio.localeCompare(b.f.inicio))
    .slice(0, pesos.cantidad_para_vos);

  reemplazar(sec, 
    el("h2", { id: "t-para-vos", class: "rotulo" }, "Para vos"),
    top.length
      ? el("ol", { class: "para-vos" }, ...top.map(({ f, motivos }) => {
          const cine = estado.cines.get(f.cine);
          const e = etiquetaDia(f.fecha);
          return el("li", { class: "recomendada" },
            el("span", { class: "titulo" }, f.titulo),
            el("span", { class: "rec-cuando" }, `${e.corto} ${e.numero} · ${f.hora} · ${cine.nombre}`),
            el("span", { class: "rec-motivo" }, motivos.join(" · ")),
            el("span", { class: "rec-acciones" }, entradas(f)));
        }))
      : el("p", { class: "ayuda" }, "Con estos filtros no encontramos funciones de tu watchlist ni de directores que te gustan. Probá con otros horarios o cines."),
  );
}

function celdaVista(f) {
  const g = estado.gustos.get(f.pelicula);
  if (!g?.vista) return "";
  const reciente = G.esReciente(g.vista, estado.datos.pesos.meses_vista_reciente);
  const titulo = g.vista === "sin fecha" ? "La registraste como vista" : `La viste el ${FECHA(g.vista)}`;
  return el("span", { class: reciente ? "vista reciente" : "vista", title: titulo }, reciente ? "vista hace poco" : "vista");
}

function contarDia(dia) {
  return funcionesFiltradas().filter((f) => f.fecha === dia).length;
}

// ---------- horarios ----------

function pintarHorarios() {
  const cont = $("#chips-horario");
  const e = estado.horario;
  const chip = (texto, activo, onclick) =>
    el("button", { type: "button", class: "chip", "aria-pressed": String(activo), onclick }, texto);

  reemplazar(cont, 
    chip("Todos", H.esTodos(e), () => {
      e.presets = [];
      e.personalizado.activo = false;
      cambioHorario();
    }),
    ...Object.entries(H.PRESETS).map(([id, p]) =>
      chip(p.etiqueta, e.presets.includes(id), () => {
        e.presets = e.presets.includes(id) ? e.presets.filter((x) => x !== id) : [...e.presets, id];
        cambioHorario();
      })),
    chip("Personalizar", e.personalizado.activo, () => {
      e.personalizado.activo = !e.personalizado.activo;
      if (e.personalizado.activo && e.personalizado.dias.every((d) => d === null)) {
        e.personalizado.dias = e.personalizado.dias.map(() => ({ desde: "18:00", hasta: "23:59" }));
      }
      cambioHorario();
    }),
  );

  const panel = $("#panel-personalizado");
  panel.hidden = !e.personalizado.activo;
  if (!e.personalizado.activo) return;
  reemplazar($("#filas-personalizado"), ...H.DIAS.map((nombre, i) => {
    const r = e.personalizado.dias[i];
    const id = `dia-${i}`;
    const hora = (campo) => el("input", {
      type: "time", value: r ? r[campo] : "18:00", disabled: !r, "aria-label": `${nombre}, ${campo}`,
      onchange: (ev) => {
        if (!e.personalizado.dias[i]) return;
        e.personalizado.dias[i][campo] = ev.target.value || (campo === "desde" ? "00:00" : "23:59");
        cambioHorario(false);
      },
    });
    return el("div", { class: "fila-dia" },
      el("label", { for: id },
        el("input", { type: "checkbox", id, checked: !!r, onchange: (ev) => {
          e.personalizado.dias[i] = ev.target.checked ? { desde: "18:00", hasta: "23:59" } : null;
          cambioHorario();
        } }),
        " ", nombre),
      el("span", { class: "rango" }, "de ", hora("desde"), " a ", hora("hasta")));
  }));
}

function cambioHorario(repintarPanel = true) {
  guardar("horario", estado.horario);
  if (repintarPanel) pintarHorarios();
  pintarDias();
  pintarTabla();
}

// ---------- días ----------

function pintarDias() {
  const fs = funcionesFiltradas();
  const porDia = new Map();
  for (const f of fs) porDia.set(f.fecha, (porDia.get(f.fecha) ?? 0) + 1);
  const boton = (valor, arriba, abajo, n) =>
    el("button", {
      type: "button", class: "dia", "aria-pressed": String(estado.dia === valor),
      "aria-label": `${arriba} ${abajo}: ${n} ${n === 1 ? "función" : "funciones"}`,
      onclick: () => { estado.dia = valor; pintarDias(); pintarTabla(); },
    },
    el("span", { class: "dia-nombre" }, arriba),
    el("span", { class: "dia-numero" }, abajo),
    el("span", { class: n ? "cuenta" : "cuenta cero" }, String(n)));
  reemplazar($("#selector-dias"), 
    boton("todos", "10 días", "Todos", fs.length),
    ...diasVentana().map((d) => {
      const e = etiquetaDia(d);
      return boton(d, e.corto, `${e.numero} ${e.mes}`, porDia.get(d) ?? 0);
    }),
  );
}

// ---------- cines ----------

function pintarCines() {
  $("#toggle-comerciales").checked = estado.comerciales;
  const conDatos = new Set(estado.datos.funciones.map((f) => f.cine));
  const visibles = estado.datos.cines.filter((c) => conDatos.has(c.id) && (!c.es_comercial || estado.comerciales));
  reemplazar($("#chips-cines"), ...visibles.map((c) =>
    el("button", {
      type: "button", class: "chip", "aria-pressed": String(!estado.cinesExcluidos.has(c.id)),
      onclick: () => {
        estado.cinesExcluidos.has(c.id) ? estado.cinesExcluidos.delete(c.id) : estado.cinesExcluidos.add(c.id);
        cambioCines();
      },
    }, c.nombre)));
  if (estado.comerciales && !estado.datos.cines.some((c) => c.es_comercial && conDatos.has(c.id))) {
    $("#chips-cines").append(el("span", { class: "nota" }, "Los complejos comerciales todavía no tienen datos."));
  }
}

function cambioCines() {
  guardar("cines-excluidos", [...estado.cinesExcluidos]);
  guardar("comerciales", estado.comerciales);
  pintarCines();
  pintarDias();
  pintarTabla();
}

// ---------- tabla ----------

const COLUMNAS = [
  { id: "hora", titulo: "Hora", clave: (f) => f.inicio },
  { id: "cine", titulo: "Cine", clave: (f) => estado.cines.get(f.cine).nombre },
  { id: "pelicula", titulo: "Película", clave: (f) => f.titulo.toLocaleLowerCase("es") },
  { id: "ciclo", titulo: "Ciclo", clave: (f) => f.ciclo ?? null },
  { id: "director", titulo: "Director", clave: (f) => peli(f).director ?? null },
  { id: "anio", titulo: "Año", clave: (f) => peli(f).anio ?? null, numerica: true },
  { id: "duracion", titulo: "Duración", clave: (f) => peli(f).duracion ?? null, numerica: true },
  { id: "entradas", titulo: "Entradas", clave: (f) => f.modo_venta },
  { id: "letterboxd", titulo: "Letterboxd", clave: (f) => (peli(f).letterboxd ? 0 : null), numerica: true },
  { id: "vista", titulo: "Vista", visible: () => hayGustos(),
    clave: (f) => estado.gustos.get(f.pelicula)?.vista ?? null },
  { id: "calendario", titulo: "Calendario", visible: () => Cal.conectado(),
    clave: (f) => ({ entra: 0, justo: 1, "no-entra": 2 })[Cal.evaluar(f, estado.margenes).estado], numerica: true },
];

const columnasVisibles = () => COLUMNAS.filter((c) => !c.visible || c.visible());

const HORA = new Intl.DateTimeFormat("es-AR", { timeZone: "America/Argentina/Buenos_Aires", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const DIA_CORTO = new Intl.DateTimeFormat("es-AR", { timeZone: "America/Argentina/Buenos_Aires", weekday: "short", day: "numeric" });

function textoBloque(b, f) {
  const mismoDia = DIA_CORTO.format(b.inicio) === DIA_CORTO.format(Date.parse(f.inicio));
  const prefijo = mismoDia ? "" : `${DIA_CORTO.format(b.inicio)} `;
  return `ocupado ${prefijo}${HORA.format(b.inicio)}–${HORA.format(b.fin)}`;
}

function celdaCalendario(f) {
  const r = Cal.evaluar(f, estado.margenes);
  const texto = { entra: "entra", justo: "justo", "no-entra": "no entra" }[r.estado];
  const estimada = !f.duracion_aprox ? ` (duración supuesta: ${Cal.DURACION_SUPUESTA} min)` : "";
  return el("span", { class: `cal ${r.estado}`, title: (r.bloque ? textoBloque(r.bloque, f) : "sin choques") + estimada },
    texto, r.bloque ? el("span", { class: "secundario" }, textoBloque(r.bloque, f)) : null);
}

function peli(f) {
  return (f.pelicula && estado.datos.peliculas[f.pelicula]) || {};
}

function pintarTabla() {
  pintarParaVos();
  const todos = estado.dia === "todos";
  const fs = funcionesFiltradas().filter((f) => todos || f.fecha === estado.dia);
  const col = COLUMNAS.find((c) => c.id === estado.orden.columna) ?? COLUMNAS[0];
  const signo = estado.orden.asc ? 1 : -1;
  fs.sort((a, b) => {
    const ka = col.clave(a), kb = col.clave(b);
    // Los datos que faltan van siempre al final, en cualquier sentido de orden.
    if ((ka === null) !== (kb === null)) return ka === null ? 1 : -1;
    const c = ka === null ? 0 : col.numerica ? ka - kb : String(ka).localeCompare(String(kb), "es");
    return c * signo || a.inicio.localeCompare(b.inicio);
  });

  reemplazar($("#tabla thead tr"), ...columnasVisibles().map((c) => {
    const activa = c.id === estado.orden.columna;
    return el("th", { scope: "col", "aria-sort": activa ? (estado.orden.asc ? "ascending" : "descending") : "none" },
      el("button", {
        type: "button", class: "orden",
        onclick: () => {
          estado.orden = { columna: c.id, asc: activa ? !estado.orden.asc : true };
          pintarTabla();
        },
      }, c.titulo, el("span", { class: "flecha", "aria-hidden": "true" }, activa ? (estado.orden.asc ? "▲" : "▼") : "")));
  }));

  reemplazar($("#tabla tbody"), ...fs.map((f) => fila(f, todos)));
  $("#vacio").hidden = fs.length > 0;
  $("#tabla").hidden = fs.length === 0;

  const nCines = new Set(fs.map((f) => f.cine)).size;
  const cuando = todos ? "en los próximos 10 días" : (() => {
    const e = etiquetaDia(estado.dia);
    return `el ${H.DIAS[H.DIAS_CORTOS.indexOf(e.corto)].toLowerCase()} ${e.numero} de ${nombreMes(estado.dia)}`;
  })();
  $("#resumen").textContent = `${fs.length} ${fs.length === 1 ? "función" : "funciones"} en ${nCines} ${nCines === 1 ? "cine" : "cines"} ${cuando}.`;
}

function nombreMes(iso) {
  return new Date(iso + "T12:00:00Z").toLocaleDateString("es-AR", { month: "long", timeZone: "UTC" });
}

function fila(f, conFecha) {
  const cine = estado.cines.get(f.cine);
  const p = peli(f);
  const e = etiquetaDia(f.fecha);
  const sinMatch = f.pelicula && p.match && p.match !== "ok";
  const td = (col, ...contenido) => el("td", { "data-col": col }, ...contenido);

  return el("tr", {},
    td("Hora",
      conFecha ? el("span", { class: "fecha" }, `${e.corto} ${e.numero} `) : null,
      el("strong", { class: "hora" }, f.hora)),
    td("Cine",
      el("span", { class: "cine" }, cine.nombre),
      cine.direccion ? el("span", { class: "secundario" }, cine.direccion) : null),
    td("Película",
      el("span", { class: "titulo" }, f.titulo),
      f.titulo_original ? el("span", { class: "secundario" }, f.titulo_original) : null,
      sinMatch ? el("span", { class: "marca", title: "No encontramos esta película en TMDB con seguridad: no mostramos director, año ni duración para no inventar datos." }, "sin datos de TMDB") : null),
    td("Ciclo", f.ciclo ?? ""),
    td("Director", p.director ?? ""),
    td("Año", p.anio ? String(p.anio) : ""),
    td("Duración", p.duracion ? `${p.duracion} min` : ""),
    td("Entradas", entradas(f),
      el("a", { href: Cal.linkAgendar(f, cine, f.duracion_aprox), target: "_blank", rel: "noopener", class: "agendar",
                title: "Abre Google Calendar con la función cargada" }, "+ agendar")),
    td("Letterboxd", p.letterboxd
      ? el("a", { href: p.letterboxd, target: "_blank", rel: "noopener", class: "externo" }, "Letterboxd")
      : ""),
    hayGustos() ? td("Vista", celdaVista(f)) : null,
    Cal.conectado() ? td("Calendario", celdaCalendario(f)) : null,
  );
}

function entradas(f) {
  if (f.modo_venta === "gratis") return el("span", { class: "venta gratis" }, "gratis, se retira en el lugar");
  if (f.modo_venta === "boleteria") return el("span", { class: "venta" }, "solo boletería");
  if (f.url_entradas) return el("a", { href: f.url_entradas, target: "_blank", rel: "noopener", class: "boton-entradas" }, "Comprar");
  return el("span", { class: "venta" }, "online");
}

// ---------- pie ----------

function pintarEstado() {
  const formato = new Intl.DateTimeFormat("es-AR", {
    timeZone: "America/Argentina/Buenos_Aires", weekday: "short", day: "numeric", month: "short",
    hour: "2-digit", minute: "2-digit",
  });
  const activos = estado.datos.cines.filter((c) => c.activo);
  const pendientes = estado.datos.cines.filter((c) => !c.activo);
  const lista = el("ul", { class: "estado" }, ...activos.map((c) => {
    const problema = c.estado && c.estado !== "ok";
    return el("li", { class: problema ? "con-problema" : "" },
      el("strong", {}, c.nombre), " · ",
      c.ultima_actualizacion ? `actualizado ${formato.format(new Date(c.ultima_actualizacion))}` : "sin datos todavía",
      problema ? el("span", { class: "alerta" }, " · el último intento falló, se muestran los datos anteriores") : null,
      c.avisos.length ? el("span", { class: "secundario" }, ` · ${c.avisos.length} ${c.avisos.length === 1 ? "aviso" : "avisos"}`) : null);
  }));
  reemplazar($("#lista-estado"), 
    lista,
    el("p", { class: "secundario" }, `Cartelera generada el ${formato.format(new Date(estado.datos.generado))}`),
    pendientes.length ? el("p", { class: "secundario" }, `Todavía sin datos: ${pendientes.map((c) => c.nombre).join(", ")}.`) : null,
  );
}

// ---------- arranque ----------

function pintarTodo() {
  recalcularGustos();
  pintarCalendario();
  pintarLetterboxd();
  pintarHorarios();
  pintarCines();
  pintarDias();
  pintarTabla();
  pintarEstado();
}

$("#toggle-comerciales").addEventListener("change", (ev) => {
  estado.comerciales = ev.target.checked;
  cambioCines();
});
$("#cines-todos").addEventListener("click", () => { estado.cinesExcluidos.clear(); cambioCines(); });
$("#cines-ninguno").addEventListener("click", () => {
  for (const c of estado.datos.cines) estado.cinesExcluidos.add(c.id);
  cambioCines();
});

cargar();
