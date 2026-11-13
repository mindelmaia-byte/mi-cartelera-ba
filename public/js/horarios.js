// Filtro de horarios. Filtra por HORA DE INICIO. Los presets y el personalizado se suman (unión);
// sin ninguno activo = "Todos".

export const DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
export const DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

// Se pueden elegir los dos: se suman.
export const PRESETS = {
  trabajo: { etiqueta: "Después del trabajo", detalle: "lun a vie, desde las 18",
             coincide: (f) => f.dia_semana <= 4 && f.hora >= "18:00" },
  finde: { etiqueta: "Fin de semana", detalle: "sáb y dom",
           coincide: (f) => f.dia_semana >= 5 },
};

export function estadoInicial() {
  return {
    presets: [],
    personalizado: {
      activo: false,
      // por día de la semana (0 = lunes): null = no incluido
      dias: Array.from({ length: 7 }, () => null),
    },
  };
}

// Normaliza lo que venga de localStorage (versiones viejas, datos rotos).
export function sanear(e) {
  const base = estadoInicial();
  if (!e || typeof e !== "object") return base;
  const presets = Array.isArray(e.presets) ? e.presets.filter((p) => p in PRESETS) : [];
  const dias = Array.isArray(e.personalizado?.dias) && e.personalizado.dias.length === 7
    ? e.personalizado.dias.map((d) => (d && esHora(d.desde) && esHora(d.hasta) ? { desde: d.desde, hasta: d.hasta } : null))
    : base.personalizado.dias;
  return { presets, personalizado: { activo: !!e.personalizado?.activo, dias } };
}

function esHora(h) {
  return typeof h === "string" && /^([01]\d|2[0-3]):[0-5]\d$/.test(h);
}

export function esTodos(e) {
  return e.presets.length === 0 && !e.personalizado.activo;
}

// Hora estimada de fin: inicio + duración, redondeada al cuarto de hora más cercano
// ("19:00" + 106 min = 20:46 -> "20:45"). Sin duración conocida no se estima nada.
export function finEstimado(hora, duracionMin) {
  if (!duracionMin || !/^\d{2}:\d{2}$/.test(hora)) return null;
  const [h, m] = hora.split(":").map(Number);
  const total = Math.round((h * 60 + m + duracionMin) / 15) * 15;
  const enElDia = ((total % 1440) + 1440) % 1440;
  return `${String(Math.floor(enElDia / 60)).padStart(2, "0")}:${String(enElDia % 60).padStart(2, "0")}`;
}

export function coincide(e, funcion) {
  if (esTodos(e)) return true;
  if (e.presets.some((p) => PRESETS[p].coincide(funcion))) return true;
  if (e.personalizado.activo) {
    const r = e.personalizado.dias[funcion.dia_semana];
    if (r && funcion.hora >= r.desde && funcion.hora <= r.hasta) return true;
  }
  return false;
}
