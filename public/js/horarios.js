// Filtro de horarios. Filtra por HORA DE INICIO. Los presets y el personalizado se suman (unión);
// sin ninguno activo = "Todos".

export const DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
export const DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

export const PRESETS = {
  semana18: { etiqueta: "Lun a jue desde las 18", coincide: (f) => f.dia_semana <= 3 && f.hora >= "18:00" },
  finde: { etiqueta: "Vie, sáb y dom", coincide: (f) => f.dia_semana >= 4 },
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

export function coincide(e, funcion) {
  if (esTodos(e)) return true;
  if (e.presets.some((p) => PRESETS[p].coincide(funcion))) return true;
  if (e.personalizado.activo) {
    const r = e.personalizado.dias[funcion.dia_semana];
    if (r && funcion.hora >= r.desde && funcion.hora <= r.hasta) return true;
  }
  return false;
}
