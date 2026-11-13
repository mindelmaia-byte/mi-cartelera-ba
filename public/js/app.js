import { leer, guardar } from "./almacen.js";
import * as H from "./horarios.js";

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
};

const $ = (sel) => document.querySelector(sel);

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
}

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
    return H.coincide(estado.horario, f);
  });
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

  cont.replaceChildren(
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
  $("#filas-personalizado").replaceChildren(...H.DIAS.map((nombre, i) => {
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
  $("#selector-dias").replaceChildren(
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
  $("#chips-cines").replaceChildren(...visibles.map((c) =>
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
];

function peli(f) {
  return (f.pelicula && estado.datos.peliculas[f.pelicula]) || {};
}

function pintarTabla() {
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

  $("#tabla thead tr").replaceChildren(...COLUMNAS.map((c) => {
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

  $("#tabla tbody").replaceChildren(...fs.map((f) => fila(f, todos)));
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
    td("Entradas", entradas(f)),
    td("Letterboxd", p.letterboxd
      ? el("a", { href: p.letterboxd, target: "_blank", rel: "noopener", class: "externo" }, "Letterboxd")
      : ""),
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
  $("#lista-estado").replaceChildren(
    lista,
    el("p", { class: "secundario" }, `Cartelera generada el ${formato.format(new Date(estado.datos.generado))}`),
    pendientes.length ? el("p", { class: "secundario" }, `Todavía sin datos: ${pendientes.map((c) => c.nombre).join(", ")}.`) : null,
  );
}

// ---------- arranque ----------

function pintarTodo() {
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
