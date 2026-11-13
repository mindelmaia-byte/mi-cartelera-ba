"""Persistencia en SQLite."""

import sqlite3
from datetime import datetime
from pathlib import Path

from cartelera.registro import RAIZ
from cartelera.schema import Cine, FuncionCruda
from cartelera.tiempo import iso

RUTA_DB = RAIZ / "data" / "cartelera.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS cines (
    id                   TEXT PRIMARY KEY,
    nombre               TEXT NOT NULL,
    direccion            TEXT,
    tanda                INTEGER NOT NULL,
    es_comercial         INTEGER NOT NULL,
    adaptador            TEXT,
    ultima_actualizacion TEXT,   -- último ingest exitoso (ISO, hora BA)
    ultimo_intento       TEXT,
    ultimo_estado        TEXT,   -- ok | error | sin_funciones
    ultimo_error         TEXT
);

CREATE TABLE IF NOT EXISTS funciones (
    id              INTEGER PRIMARY KEY,
    cine_id         TEXT NOT NULL REFERENCES cines(id),
    fecha_hora      TEXT NOT NULL,          -- ISO con offset -03:00, ordenable como texto
    titulo          TEXT NOT NULL,
    titulo_original TEXT,
    ciclo           TEXT,
    url_entradas    TEXT,
    modo_venta      TEXT NOT NULL CHECK (modo_venta IN ('online', 'boleteria', 'gratis')),
    es_comercial    INTEGER NOT NULL,
    fuente_url      TEXT NOT NULL,
    director_fuente TEXT,
    anio_fuente     INTEGER,
    duracion_fuente INTEGER,
    UNIQUE (cine_id, fecha_hora, titulo)
);
CREATE INDEX IF NOT EXISTS funciones_fecha ON funciones (fecha_hora);

-- Una fila por película "tal como la publica un cine". La clave junta título, título original,
-- año y director de la fuente; si dos cines publican la misma película con pistas distintas
-- quedan dos filas, cada una con su propio cruce (y normalmente el mismo tmdb_id).
CREATE TABLE IF NOT EXISTS peliculas (
    id                     INTEGER PRIMARY KEY,
    clave                  TEXT NOT NULL UNIQUE,
    titulo_fuente          TEXT NOT NULL,
    titulo_original_fuente TEXT,
    anio_fuente            INTEGER,
    director_fuente        TEXT,
    duracion_fuente        INTEGER,
    match_estado           TEXT NOT NULL DEFAULT 'pendiente'
                           CHECK (match_estado IN ('pendiente', 'ok', 'sin_match', 'ambiguo')),
    match_motivo           TEXT,
    candidatos             TEXT,     -- ids de TMDB separados por coma cuando es ambiguo
    consultado             TEXT,
    tmdb_id                INTEGER,
    titulo                 TEXT,     -- título en castellano según TMDB
    titulo_original        TEXT,
    anio                   INTEGER,
    director               TEXT,
    duracion_min           INTEGER,
    letterboxd_url         TEXT
);

-- Filmografía (como director) de los directores que están en cartelera. Se publica en el export
-- para que el navegador detecte "directores que te gustan" sin mandar tus datos a ningún lado.
CREATE TABLE IF NOT EXISTS directores (
    persona_id  INTEGER PRIMARY KEY,
    nombre      TEXT,
    filmografia TEXT NOT NULL,   -- JSON: [{tmdb_id, anio, titulos: [inglés, original]}]
    consultado  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id          INTEGER PRIMARY KEY,
    inicio      TEXT NOT NULL,
    cine_id     TEXT NOT NULL,
    estado      TEXT NOT NULL,
    n_funciones INTEGER NOT NULL,
    error       TEXT
);
"""


def conectar(ruta: Path | str = RUTA_DB) -> sqlite3.Connection:
    if ruta != ":memory:":
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    _migrar(con)
    return con


def _migrar(con: sqlite3.Connection) -> None:
    """Columnas agregadas después de crear la base (CREATE TABLE IF NOT EXISTS no las suma)."""
    agregar = [
        ("funciones", "pelicula_id", "INTEGER REFERENCES peliculas(id)"),
        ("cines", "ultimos_avisos", "TEXT"),
        ("ingest_runs", "avisos", "TEXT"),
        ("funciones", "idioma_fuente", "TEXT"),
        ("peliculas", "idioma_fuente", "TEXT"),
        ("peliculas", "titulo_en", "TEXT"),
        ("peliculas", "directores_ids", "TEXT"),  # ids de persona de TMDB separados por coma
    ]
    for tabla, columna, tipo in agregar:
        columnas = {r["name"] for r in con.execute(f"PRAGMA table_info({tabla})")}
        if columna not in columnas:
            con.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
    con.commit()


def sincronizar_cines(con: sqlite3.Connection, cines: list[Cine]) -> None:
    """Copia el registro del YAML a la tabla, conservando el estado de ingest."""
    with con:
        for c in cines:
            con.execute(
                """INSERT INTO cines (id, nombre, direccion, tanda, es_comercial, adaptador)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET nombre=excluded.nombre, direccion=excluded.direccion,
                       tanda=excluded.tanda, es_comercial=excluded.es_comercial, adaptador=excluded.adaptador""",
                (c.id, c.nombre, c.direccion, c.tanda, int(c.es_comercial), c.adaptador),
            )


def contar_futuras(con: sqlite3.Connection, cine_id: str, desde: datetime) -> int:
    return con.execute(
        "SELECT COUNT(*) FROM funciones WHERE cine_id = ? AND fecha_hora >= ?", (cine_id, iso(desde))
    ).fetchone()[0]


def reemplazar_futuras(
    con: sqlite3.Connection, cine: Cine, funciones: list[FuncionCruda], desde: datetime
) -> int:
    """Borra las funciones futuras del cine e inserta las nuevas, en una sola transacción.
    Las funciones anteriores a `desde` no se tocan. Devuelve cuántas se insertaron."""
    futuras = [f for f in funciones if f.fecha_hora >= desde]
    with con:
        con.execute("DELETE FROM funciones WHERE cine_id = ? AND fecha_hora >= ?", (cine.id, iso(desde)))
        con.executemany(
            """INSERT OR IGNORE INTO funciones
               (cine_id, fecha_hora, titulo, titulo_original, ciclo, url_entradas, modo_venta,
                es_comercial, fuente_url, director_fuente, anio_fuente, duracion_fuente, idioma_fuente)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (cine.id, iso(f.fecha_hora), f.titulo, f.titulo_original, f.ciclo, f.url_entradas,
                 f.modo_venta, int(cine.es_comercial), f.fuente_url, f.director_fuente,
                 f.anio_fuente, f.duracion_fuente, f.idioma_fuente)
                for f in futuras
            ],
        )
    return contar_futuras(con, cine.id, desde)


def registrar_resultado(
    con: sqlite3.Connection, cine_id: str, inicio: datetime, estado: str, n: int, error: str | None,
    avisos: list[str] | None = None,
) -> None:
    texto_avisos = "\n".join(avisos) if avisos else None
    with con:
        con.execute(
            "INSERT INTO ingest_runs (inicio, cine_id, estado, n_funciones, error, avisos) VALUES (?, ?, ?, ?, ?, ?)",
            (iso(inicio), cine_id, estado, n, error, texto_avisos),
        )
        if estado == "ok":
            con.execute(
                """UPDATE cines SET ultima_actualizacion = ?, ultimo_intento = ?, ultimo_estado = ?,
                       ultimo_error = NULL, ultimos_avisos = ? WHERE id = ?""",
                (iso(inicio), iso(inicio), estado, texto_avisos, cine_id),
            )
        else:
            con.execute(
                "UPDATE cines SET ultimo_intento = ?, ultimo_estado = ?, ultimo_error = ?, ultimos_avisos = ? WHERE id = ?",
                (iso(inicio), estado, error, texto_avisos, cine_id),
            )
