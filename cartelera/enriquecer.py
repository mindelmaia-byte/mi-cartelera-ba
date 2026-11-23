"""Vincula cada función con una película y cruza las películas con TMDB.

Corre después del ingest. Las películas ya resueltas no se vuelven a consultar; las que
quedaron sin match o ambiguas se reintentan cada REINTENTO_DIAS (TMDB suma estrenos).
"""

import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from cartelera.texto import normalizar
from cartelera.tiempo import ahora, iso
from cartelera.tmdb import TOLERANCIA_DURACION, ClienteTMDB, Pistas, es_latino, nombre_latino, resolver

log = logging.getLogger(__name__)

REINTENTO_DIAS = 7
DIRECTORES_DIAS = 30


@dataclass
class Resumen:
    consultadas: int = 0
    ok: int = 0
    sin_match: int = 0
    ambiguo: int = 0
    errores: int = 0
    directores: int = 0  # filmografías traídas en esta corrida


def clave_pelicula(titulo: str, titulo_original: str | None, anio: int | None, director: str | None) -> str:
    return "|".join([normalizar(titulo), normalizar(titulo_original), str(anio or ""), normalizar(director)])


def vincular(con: sqlite3.Connection) -> int:
    """Asigna pelicula_id a las funciones que no lo tienen (crea la película si hace falta)."""
    filas = con.execute(
        """SELECT id, titulo, titulo_original, anio_fuente, director_fuente, duracion_fuente, idioma_fuente
           FROM funciones WHERE pelicula_id IS NULL"""
    ).fetchall()
    with con:
        for f in filas:
            clave = clave_pelicula(f["titulo"], f["titulo_original"], f["anio_fuente"], f["director_fuente"])
            con.execute(
                """INSERT OR IGNORE INTO peliculas
                   (clave, titulo_fuente, titulo_original_fuente, anio_fuente, director_fuente, duracion_fuente,
                    idioma_fuente)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (clave, f["titulo"], f["titulo_original"], f["anio_fuente"], f["director_fuente"],
                 f["duracion_fuente"], f["idioma_fuente"]),
            )
            # Una película ya creada sin idioma lo gana si una fuente lo trae después.
            con.execute("UPDATE peliculas SET idioma_fuente = COALESCE(idioma_fuente, ?) WHERE clave = ?",
                        (f["idioma_fuente"], clave))
            con.execute("UPDATE funciones SET pelicula_id = (SELECT id FROM peliculas WHERE clave = ?) WHERE id = ?",
                        (clave, f["id"]))
    return len(filas)


def pendientes(con: sqlite3.Connection, momento: datetime, forzar: bool = False) -> list[sqlite3.Row]:
    """Películas con funciones futuras que hay que consultar."""
    limite = iso(momento - timedelta(days=REINTENTO_DIAS))
    condicion = "1" if forzar else "(p.match_estado = 'pendiente' OR (p.match_estado != 'ok' AND p.consultado < ?))"
    params = (iso(momento),) if forzar else (iso(momento), limite)
    return con.execute(
        f"""SELECT p.* FROM peliculas p
            WHERE EXISTS (SELECT 1 FROM funciones f WHERE f.pelicula_id = p.id AND f.fecha_hora >= ?)
              AND {condicion}
            ORDER BY p.id""",
        params,
    ).fetchall()


def enriquecer(con: sqlite3.Connection, tmdb: ClienteTMDB, momento: datetime | None = None,
               forzar: bool = False) -> Resumen:
    momento = momento or ahora()
    vincular(con)
    resumen = Resumen()
    for p in pendientes(con, momento, forzar):
        pistas = Pistas(p["titulo_fuente"], p["titulo_original_fuente"], p["anio_fuente"],
                        p["director_fuente"], p["duracion_fuente"], p["idioma_fuente"], momento.year)
        try:
            m = resolver(tmdb, pistas)
        except (httpx.HTTPError, KeyError, ValueError) as e:
            log.warning("TMDB falló para %r: %s", p["titulo_fuente"], e)
            resumen.errores += 1
            continue  # queda pendiente, se reintenta en el próximo ingest
        resumen.consultadas += 1
        setattr(resumen, m.estado, getattr(resumen, m.estado) + 1)
        with con:
            con.execute(
                """UPDATE peliculas SET match_estado = ?, match_motivo = ?, candidatos = ?, consultado = ?,
                       tmdb_id = ?, titulo = ?, titulo_original = ?, anio = ?, director = ?,
                       duracion_min = ?, letterboxd_url = ?, titulo_en = ?, directores_ids = ?
                   WHERE id = ?""",
                (m.estado, m.motivo, ",".join(map(str, m.candidatos)) or None, iso(momento),
                 m.tmdb_id, m.titulo, m.titulo_original, m.anio, m.director, m.duracion, m.letterboxd_url,
                 m.titulo_en, ",".join(map(str, m.directores_ids)) or None, p["id"]),
            )
    resumen.ok += corroborar(con, momento)
    latinizar_directores(con, tmdb, momento)
    if forzar:
        with con:
            con.execute("DELETE FROM directores")
    resumen.directores = actualizar_directores(con, tmdb, momento)
    return resumen


def actualizar_directores(con: sqlite3.Connection, tmdb: ClienteTMDB, momento: datetime) -> int:
    """Filmografías de los directores de las películas en cartelera (con match ok). Se renuevan cada 30 días."""
    filas = con.execute(
        """SELECT DISTINCT p.directores_ids, p.director FROM peliculas p
           WHERE p.match_estado = 'ok' AND p.directores_ids IS NOT NULL
             AND EXISTS (SELECT 1 FROM funciones f WHERE f.pelicula_id = p.id AND f.fecha_hora >= ?)""",
        (iso(momento),),
    ).fetchall()
    limite = iso(momento - timedelta(days=DIRECTORES_DIAS))
    nombres: dict[int, str] = {}
    for f in filas:
        ids = [int(x) for x in f["directores_ids"].split(",")]
        partes = (f["director"] or "").split(", ")
        for i, pid in enumerate(ids):
            nombres.setdefault(pid, partes[i] if i < len(partes) and len(partes) == len(ids) else None)
    n = 0
    for pid, nombre in nombres.items():
        fila = con.execute("SELECT consultado FROM directores WHERE persona_id = ?", (pid,)).fetchone()
        if fila and fila["consultado"] >= limite:
            continue
        try:
            filmo = tmdb.filmografia_director(pid)
        except (httpx.HTTPError, KeyError, ValueError) as e:
            log.warning("TMDB: no se pudo traer la filmografía de %s: %s", pid, e)
            continue
        with con:
            con.execute(
                """INSERT INTO directores (persona_id, nombre, filmografia, consultado) VALUES (?, ?, ?, ?)
                   ON CONFLICT(persona_id) DO UPDATE SET nombre = COALESCE(excluded.nombre, nombre),
                       filmografia = excluded.filmografia, consultado = excluded.consultado""",
                (pid, nombre, json.dumps(filmo, ensure_ascii=False), iso(momento)),
            )
        n += 1
    return n


def corroborar(con: sqlite3.Connection, momento: datetime) -> int:
    """Una película sin match en un cine (p. ej. la grilla del Lorca, sin año ni director) se acepta
    si otro cine ya la confirmó con año o director y el mismo candidato de TMDB:
      - el título del cine coincide (normalizado) con el de la otra fuente o con alguno de TMDB;
      - ese tmdb_id fue un candidato con título coincidente en la búsqueda propia (figura en los
        descartes: solo se descarta después de que el título coincide);
      - el descarte no fue por más de TOLERANCIA_DURACION minutos de diferencia ni por año.
    No hace pedidos a TMDB."""
    futuras = "EXISTS (SELECT 1 FROM funciones f WHERE f.pelicula_id = p.id AND f.fecha_hora >= ?)"
    confirmadas = con.execute(
        f"""SELECT * FROM peliculas p WHERE match_estado = 'ok' AND tmdb_id IS NOT NULL
              AND match_motivo NOT LIKE 'corroborada%' AND {futuras}""", (iso(momento),)).fetchall()
    sin = con.execute(
        f"SELECT * FROM peliculas p WHERE match_estado IN ('sin_match', 'ambiguo') AND {futuras}",
        (iso(momento),)).fetchall()
    n = 0
    for p in sin:
        titulo = normalizar(p["titulo_fuente"])
        descartes = {int(m.group(1)): m.group(2) for m in re.finditer(r"(\d+): ([^;]*)", p["match_motivo"] or "")}
        for c in confirmadas:
            if titulo not in {normalizar(c["titulo_fuente"]), normalizar(c["titulo"]), normalizar(c["titulo_original"])}:
                continue
            motivo = descartes.get(c["tmdb_id"])
            if motivo is None or motivo.startswith("año"):
                continue
            dur = re.match(r"duración (\d+) vs (\d+)", motivo)
            if dur and abs(int(dur.group(1)) - int(dur.group(2))) > TOLERANCIA_DURACION:
                continue
            with con:
                con.execute(
                    """UPDATE peliculas SET match_estado = 'ok', match_motivo = ?, tmdb_id = ?, titulo = ?,
                           titulo_original = ?, anio = ?, director = ?, duracion_min = ?, letterboxd_url = ?,
                           titulo_en = ?, directores_ids = ?, consultado = ? WHERE id = ?""",
                    (f"corroborada por otra fuente con {c['match_motivo']} (película {c['id']}); acá: {motivo}",
                     c["tmdb_id"], c["titulo"], c["titulo_original"], c["anio"], c["director"], c["duracion_min"],
                     c["letterboxd_url"], c["titulo_en"], c["directores_ids"], iso(momento), p["id"]),
                )
            n += 1
            break
    return n


def latinizar_directores(con: sqlite3.Connection, tmdb: ClienteTMDB, momento: datetime) -> int:
    """Corrige los nombres de director que quedaron en otro alfabeto (matches anteriores a la regla)."""
    filas = con.execute(
        """SELECT id, director, directores_ids FROM peliculas p
           WHERE match_estado = 'ok' AND director IS NOT NULL AND directores_ids IS NOT NULL
             AND EXISTS (SELECT 1 FROM funciones f WHERE f.pelicula_id = p.id AND f.fecha_hora >= ?)""",
        (iso(momento),)).fetchall()
    n = 0
    for f in filas:
        nombres = f["director"].split(", ")
        ids = [int(x) for x in f["directores_ids"].split(",")]
        if all(es_latino(x) for x in nombres) or len(nombres) != len(ids):
            continue
        nuevos = [nombre_latino(tmdb, pid, nom) for pid, nom in zip(ids, nombres)]
        if nuevos == nombres:
            continue
        with con:
            con.execute("UPDATE peliculas SET director = ? WHERE id = ?", (", ".join(nuevos), f["id"]))
            for pid, nom in zip(ids, nuevos):
                con.execute("UPDATE directores SET nombre = ? WHERE persona_id = ?", (nom, pid))
        n += 1
    return n

