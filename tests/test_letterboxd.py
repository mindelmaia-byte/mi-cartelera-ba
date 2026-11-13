from pathlib import Path

import httpx
import pytest

from cartelera.letterboxd import leer_rss, parsear_rss, usuario_valido

RSS = (Path(__file__).parent / "fixtures" / "letterboxd" / "rss.xml").read_bytes()


def test_parsea_entradas_e_ignora_listas():
    entradas = parsear_rss(RSS)
    assert len(entradas) == 2
    fitz, otra = entradas
    assert fitz == {"titulo": "Fitzcarraldo", "anio": 1982, "tmdb_id": 9343, "fecha_vista": "2026-11-03",
                    "puntaje": 4.5, "rewatch": False}
    assert otra["titulo"] == "Película Inventada & Cía" and otra["puntaje"] is None and otra["rewatch"] is True


def test_usuario_valido():
    assert usuario_valido("usuaria_prueba")
    assert not usuario_valido("") and not usuario_valido("../etc") and not usuario_valido("a b") and not usuario_valido("x" * 41)


def test_leer_rss_con_transporte_falso():
    def handler(req):
        if req.url.path == "/usuaria_prueba/rss/":
            return httpx.Response(200, content=RSS)
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        assert len(leer_rss("usuaria_prueba", c)["entradas"]) == 2
        with pytest.raises(LookupError):
            leer_rss("no_existe", c)
        with pytest.raises(ValueError):
            leer_rss("../x", c)
