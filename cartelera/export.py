"""Exporta la cartelera de los próximos días a un JSON estático para el sitio (public/data/).

El sitio no hace cuentas de zona horaria: cada función trae su fecha, hora y día de la semana
en hora de Buenos Aires, además del instante ISO (para comparar con "ahora" y con el calendario).
"""

import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from cartelera.registro import RAIZ
from cartelera.schema import Cine
from cartelera.texto import normalizar
from cartelera.tiempo import ahora, iso

RUTA_EXPORT = RAIZ / "public" / "data" / "cartelera.json"
RUTA_PESOS = RAIZ / "config" / "pesos.json"
VERSION = 1


def exportar(con: sqlite3.Connection, cines: list[Cine], *, dias: int = 10,
             momento: datetime | None = None, ruta: Path = RUTA_EXPORT) -> dict:
    momento = momento or ahora()
    desde = momento.date()
    hasta = desde + timedelta(days=dias)
    estado = {r["id"]: r for r in con.execute("SELECT * FROM cines")}

    filas = con.execute(
        """SELECT f.*, p.id AS pid, p.match_estado, p.tmdb_id, p.titulo AS titulo_tmdb, p.director,
                  p.anio, p.duracion_min, p.letterboxd_url, p.titulo_original AS titulo_original_tmdb,
                  p.titulo_en, p.directores_ids
           FROM funciones f LEFT JOIN peliculas p ON p.id = f.pelicula_id
           WHERE f.fecha_hora >= ? AND f.fecha_hora < ?
           ORDER BY f.fecha_hora, f.cine_id, f.titulo""",
        (iso(momento), hasta.isoformat()),
    ).fetchall()

    peliculas: dict[str, dict] = {}
    funciones = []
    for f in filas:
        pid = str(f["pid"]) if f["pid"] is not None else None
        if pid and pid not in peliculas:
            ok = f["match_estado"] == "ok"
            peliculas[pid] = {
                "match": f["match_estado"],
                "tmdb_id": f["tmdb_id"] if ok else None,
                "director": f["director"] if ok else None,
                "anio": f["anio"] if ok else None,
                "duracion": f["duracion_min"] if ok else None,
                "letterboxd": f["letterboxd_url"] if ok else None,
                # Para cruzar con el export de Letterboxd (título + año) en el navegador.
                "titulos": list(dict.fromkeys(t for t in (f["titulo_tmdb"], f["titulo_original_tmdb"], f["titulo_en"]) if t))
                           if ok else [],
                "directores_ids": [int(x) for x in (f["directores_ids"] or "").split(",") if x] if ok else [],
            }
        inicio = datetime.fromisoformat(f["fecha_hora"])
        funciones.append({
            "id": f["id"],
            "cine": f["cine_id"],
            "inicio": f["fecha_hora"],
            "fecha": inicio.date().isoformat(),
            "hora": inicio.strftime("%H:%M"),
            "dia_semana": inicio.weekday(),  # 0 = lunes
            "titulo": titulo_a_mostrar(f["titulo"], f["titulo_tmdb"] if f["match_estado"] == "ok" else None),
            "titulo_original": f["titulo_original"],
            "ciclo": f["ciclo"],
            "url_entradas": f["url_entradas"],
            "modo_venta": f["modo_venta"],
            "es_comercial": bool(f["es_comercial"]),
            "pelicula": pid,
            # Solo para calcular el fin de la función contra el calendario (no se muestra como dato):
            # TMDB si hay match, si no la que publica el cine.
            "duracion_aprox": (f["duracion_min"] if f["match_estado"] == "ok" else None) or f["duracion_fuente"],
        })

    ids_directores = {i for p in peliculas.values() for i in p["directores_ids"]}
    directores = {}
    for d in con.execute("SELECT * FROM directores"):
        if d["persona_id"] in ids_directores:
            # Compacto: [tmdb_id, año, [títulos]]
            filmo = [[x["tmdb_id"], x["anio"], x["titulos"]] for x in json.loads(d["filmografia"])]
            directores[str(d["persona_id"])] = {"nombre": d["nombre"], "filmografia": filmo}

    datos = {
        "version": VERSION,
        "generado": iso(momento),
        "desde": desde.isoformat(),
        "dias": dias,
        "cines": [_cine(c, estado.get(c.id)) for c in cines],
        "peliculas": peliculas,
        "directores": directores,
        "pesos": json.loads(RUTA_PESOS.read_text(encoding="utf-8")),
        "funciones": funciones,
    }
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return datos


def titulo_a_mostrar(titulo_fuente: str, titulo_tmdb: str | None) -> str:
    """Se muestra el título del cine, pero nunca TODO EN MAYÚSCULAS:
      1. si TMDB tiene exactamente las mismas palabras, su grafía (trae tildes: "4 historias increíbles");
      2. si no, el mismo título en formato título ("TIERRA DE MI PADRE" -> "Tierra de Mi Padre").
    Si el cine ya lo publica con mayúsculas y minúsculas, queda como está (aunque TMDB use otro título
    de otro país, como "Cayo Largo")."""
    letras = [c for c in titulo_fuente if c.isalpha()]
    en_mayusculas = bool(letras) and all(c.isupper() for c in letras)
    if not (en_mayusculas or _cada_palabra_capitalizada(titulo_fuente)):
        return titulo_fuente
    if titulo_tmdb and normalizar(titulo_tmdb) == normalizar(titulo_fuente):
        return titulo_tmdb
    return formato_titulo(titulo_fuente)


def _cada_palabra_capitalizada(titulo: str) -> bool:
    """ "Tierra De Mi Padre" (Multiplex): todas las palabras con mayúscula inicial, incluidas
    las que en castellano van en minúscula. Se trata igual que un título en mayúsculas."""
    palabras = [p for p in re.findall(r"[^\W\d_]+", titulo)]
    return (len(palabras) > 1 and all(p[0].isupper() for p in palabras)
            and any(p.lower() in MENORES for p in palabras[1:]))


# Palabras que van en minúscula salvo al principio del título o después de ":".
MENORES = {"a", "al", "de", "del", "e", "el", "en", "la", "las", "lo", "los", "o", "u", "y", "un", "una",
           "unos", "unas", "con", "por", "para", "sin", "sobre", "que", "se", "the", "of", "and"}
ROMANOS = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"}


def formato_titulo(titulo: str) -> str:
    def palabra(p: str, primera: bool) -> str:
        if "-" in p:  # "HERZOG-KINSKI" -> "Herzog-Kinski"
            return "-".join(palabra(x, primera or i > 0) for i, x in enumerate(p.split("-")))
        inicio = 0
        while inicio < len(p) and not p[inicio].isalnum():
            inicio += 1  # signos de apertura: "¿", "¡", comillas
        cuerpo = p[inicio:]
        nucleo = "".join(c for c in cuerpo if c.isalpha()).lower()
        if any(c.isdigit() for c in cuerpo) or nucleo in ROMANOS:
            return p  # "LS83", "II"
        if not primera and nucleo in MENORES:
            return p.lower()
        return p[:inicio] + cuerpo[:1].upper() + cuerpo[1:].lower()

    partes = titulo.split(" ")
    resultado, primera = [], True
    for p in partes:
        if not p:
            continue
        resultado.append(palabra(p, primera))
        primera = p.endswith((":", ".", "?", "!"))
    return " ".join(resultado)


def _cine(c: Cine, fila: sqlite3.Row | None) -> dict:
    return {
        "id": c.id,
        "nombre": c.nombre,
        "direccion": c.direccion,
        "tanda": c.tanda,
        "es_comercial": c.es_comercial,
        "activo": bool(c.adaptador),
        "ultima_actualizacion": fila["ultima_actualizacion"] if fila else None,
        "estado": fila["ultimo_estado"] if fila else None,
        "error": fila["ultimo_error"] if fila else None,
        "avisos": (fila["ultimos_avisos"] or "").splitlines() if fila and "ultimos_avisos" in fila.keys() else [],
    }
