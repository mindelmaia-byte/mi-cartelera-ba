"""Nombres de director en alfabeto latino y películas sin match corroboradas por otro cine."""

from datetime import datetime

import httpx

from cartelera import db
from cartelera.enriquecer import corroborar
from cartelera.tiempo import TZ
from cartelera.tmdb import ClienteTMDB, es_latino, nombre_latino

MOMENTO = datetime(2026, 11, 23, 12, 0, tzinfo=TZ)


def _cliente(respuestas: dict) -> ClienteTMDB:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in respuestas:
            return httpx.Response(200, json=respuestas[request.url.path])
        return httpx.Response(404, json={})
    return ClienteTMDB("x", httpx.Client(transport=httpx.MockTransport(handler)), pausa=0)


def test_es_latino():
    assert es_latino("Paweł Pawlikowski") and es_latino("Éric Toledano")
    assert not es_latino("Андрей Звягинцев") and not es_latino("山崎貴")


def test_nombre_latino_desde_los_alias():
    tmdb = _cliente({"/3/person/68519": {"name": "Андрей Звягинцев",
                                         "also_known_as": ["Андрей Петрович Звягинцев", "Andrei Zvyagintsev"]}})
    assert nombre_latino(tmdb, 68519, "Андрей Звягинцев") == "Andrei Zvyagintsev"
    assert nombre_latino(tmdb, 1, "Wim Wenders") == "Wim Wenders"  # ya latino: no pide nada
    assert nombre_latino(tmdb, 2, "山崎貴") == "山崎貴"  # sin respuesta: queda como vino


def _con():
    con = db.conectar(":memory:")
    con.execute("INSERT INTO cines (id, nombre, tanda, es_comercial) VALUES ('a', 'A', 1, 0), ('b', 'B', 1, 0)")
    return con


def _peli(con, pid, titulo, estado, motivo, tmdb_id=None, cine="a"):
    con.execute(
        """INSERT INTO peliculas (id, clave, titulo_fuente, match_estado, match_motivo, tmdb_id, titulo, anio,
               director, duracion_min, letterboxd_url, directores_ids, consultado)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (pid, f"k{pid}", titulo, estado, motivo, tmdb_id, "Minotauro" if tmdb_id else None,
         2026 if tmdb_id else None, "Andrei Zvyagintsev" if tmdb_id else None, 141 if tmdb_id else None,
         f"https://letterboxd.com/tmdb/{tmdb_id}/" if tmdb_id else None, "68519" if tmdb_id else None,
         "2026-11-23T10:00:00-03:00"))
    con.execute(
        """INSERT INTO funciones (cine_id, fecha_hora, titulo, modo_venta, es_comercial, fuente_url, pelicula_id)
           VALUES (?, ?, ?, 'boleteria', 0, 'x', ?)""", (cine, f"2026-11-25T20:{pid:02d}:00-03:00", titulo, pid))


def test_corrobora_con_el_mismo_candidato():
    con = _con()
    _peli(con, 1, "Minotauro", "ok", "año", tmdb_id=848700, cine="b")
    _peli(con, 2, "MINOTAURO", "sin_match", "848700: idioma fr vs ru; 1391948: duración 60 vs 141")
    assert corroborar(con, MOMENTO) == 1
    p = con.execute("SELECT * FROM peliculas WHERE id = 2").fetchone()
    assert (p["match_estado"], p["tmdb_id"], p["director"]) == ("ok", 848700, "Andrei Zvyagintsev")
    assert p["match_motivo"].startswith("corroborada")


def test_no_corrobora_sin_ese_candidato_ni_con_otro_titulo_ni_por_anio():
    con = _con()
    _peli(con, 1, "Minotauro", "ok", "año", tmdb_id=848700, cine="b")
    _peli(con, 2, "MINOTAURO", "sin_match", "1391948: duración 60 vs 141")  # el candidato nunca apareció
    _peli(con, 3, "OTRA COSA", "sin_match", "848700: idioma fr vs ru")      # otro título
    _peli(con, 4, "Minotauro", "sin_match", "848700: año 2026 vs 1990")     # descartado por año
    _peli(con, 5, "Minotauro", "sin_match", "848700: duración 141 vs 95")   # más de 20 min
    assert corroborar(con, MOMENTO) == 0
