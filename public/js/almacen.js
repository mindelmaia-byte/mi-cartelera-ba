// Preferencias en el navegador. localStorage puede no estar (modo privado, bloqueado):
// todo pasa por acá y la página funciona igual sin él.

const PREFIJO = "cartelera-ba:";

export function leer(clave, porDefecto) {
  try {
    const crudo = window.localStorage.getItem(PREFIJO + clave);
    return crudo === null ? porDefecto : JSON.parse(crudo);
  } catch {
    return porDefecto;
  }
}

export function guardar(clave, valor) {
  try {
    window.localStorage.setItem(PREFIJO + clave, JSON.stringify(valor));
  } catch {
    /* sin almacenamiento: la preferencia dura hasta recargar */
  }
}
