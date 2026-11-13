"""TMDB: reglas de aceptación (con respuestas armadas a mano) y cruce real de Gaumont
(con respuestas de TMDB grabadas en tests/fixtures/tmdb/respuestas.json)."""

import json
from datetime import date, datetime
from pathlib import Path

import httpx
import pytest

from cartelera import db
from cartelera.adapters.gaumont import ADAPTADOR as GAUMONT
from cartelera.enriquecer import enriquecer
from cartelera.ingest import ingestar
from cartelera.schema import Cine
from cartelera.texto import algun_director_coincide, normalizar
from cartelera.tiempo import TZ
from cartelera.tmdb import BASE, ClienteTMDB, Pistas, clave_grabacion, resolver

FIXTURES = Path(__file__).parent / "fixtures"
MOMENTO = datetime(2026, 11, 13, 12, 0, tzinfo=TZ)


def _cliente_desde(respuestas: dict) -> ClienteTMDB:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix(httpx.URL(BASE).path)
        clave = clave_grabacion(path, dict(request.url.params))
        if clave not in respuestas:
            return httpx.Response(404, json={"status_message": f"no grabado: {clave}"})
        return httpx.Response(200, json=respuestas[clave])

    return ClienteTMDB("clave-de-test", httpx.Client(transport=httpx.MockTransport(handler)), pausa=0)


# ---------- reglas, con respuestas armadas a mano ----------

def _busqueda(q, *resultados, anio=None):
    params = {"query": q, "language": "es-MX", "include_adult": "false"}
    if anio is not None:
        params["year"] = anio
    return {clave_grabacion("/search/movie", params): {"results": list(resultados)}}


def _detalle(id_, titulo, original, fecha, directores, runtime=100, traducciones=()):
    return {clave_grabacion(f"/movie/{id_}", {"language": "es-MX",
                                              "append_to_response": "credits,translations,alternative_titles"}): {
        "id": id_, "title": titulo, "original_title": original, "release_date": fecha, "runtime": runtime,
        "credits": {"crew": [{"job": "Director", "name": d} for d in directores]},
        "translations": {"translations": [{"iso_639_1": "es", "iso_3166_1": p, "data": {"title": t}}
                                          for p, t in traducciones]},
        "alternative_titles": {"titles": []},
    }}


def test_acepta_por_anio():
    r = {**_busqueda("La casa", {"id": 1, "title": "La casa", "original_title": "La casa"}),
         **_detalle(1, "La casa", "La casa", "2025-03-01", ["X Y"])}
    m = resolver(_cliente_desde(r), Pistas("La casa", anio=2026))
    assert (m.estado, m.tmdb_id, m.motivo) == ("ok", 1, "año")
    assert m.letterboxd_url == "https://letterboxd.com/tmdb/1/"


def test_rechaza_anio_lejano():
    r = {**_busqueda("La casa", {"id": 1, "title": "La casa", "original_title": "La casa"}),
         **_busqueda("La casa", {"id": 1, "title": "La casa", "original_title": "La casa"}, anio=2026),
         **_detalle(1, "La casa", "La casa", "1990-01-01", ["X Y"])}
    m = resolver(_cliente_desde(r), Pistas("La casa", anio=2026))
    assert m.estado == "sin_match" and m.tmdb_id is None and m.titulo is None
    assert m.motivo == "1: año 1990 vs 2026"  # el candidato ya revisado no se vuelve a pedir


def test_sin_anio_ni_director_no_confirma():
    r = {**_busqueda("La casa", {"id": 1, "title": "La casa", "original_title": "La casa"}),
         **_detalle(1, "La casa", "La casa", "2026-01-01", ["X Y"])}
    m = resolver(_cliente_desde(r), Pistas("La casa"))
    assert m.estado == "sin_match" and "sin año ni director" in m.motivo


def test_ambiguo_si_dos_pasan_y_el_director_no_desempata():
    r = {**_busqueda("Olivia", {"id": 1, "title": "Olivia", "original_title": "Olivia"},
                     {"id": 2, "title": "Olivia", "original_title": "Olivia"}),
         **_detalle(1, "Olivia", "Olivia", "2025-01-01", ["Ana Paz"]),
         **_detalle(2, "Olivia", "Olivia", "2026-01-01", ["Luis Rey"])}
    m = resolver(_cliente_desde(r), Pistas("Olivia", anio=2025))
    assert (m.estado, sorted(m.candidatos)) == ("ambiguo", [1, 2])
    m2 = resolver(_cliente_desde(r), Pistas("Olivia", anio=2025, director="Luis Rey"))
    assert (m2.estado, m2.tmdb_id) == ("ok", 2)


def test_titulo_traducido_y_preferencia_argentina():
    r = {**_busqueda("LOS OTROS", {"id": 9, "title": "Los otros", "original_title": "The Others"}),
         **_detalle(9, "Los otros", "The Others", "2001-08-02", ["Alejandro Amenábar"],
                    traducciones=[("ES", "Los otros"), ("AR", "Los Otros (AR)")])}
    m = resolver(_cliente_desde(r), Pistas("LOS OTROS", director="Alejandro Amenabar"))
    assert m.estado == "ok" and m.titulo == "Los Otros (AR)" and m.titulo_original == "The Others"


def test_duracion_muy_distinta_descarta():
    r = {**_busqueda("Corto", {"id": 5, "title": "Corto", "original_title": "Corto"}),
         **_detalle(5, "Corto", "Corto", "2022-01-01", ["Ana Paz"], runtime=19)}
    m = resolver(_cliente_desde(r), Pistas("Corto", director="Ana Paz", duracion=64))
    assert m.estado == "sin_match" and "duración" in m.motivo


def test_nombres():
    assert normalizar("¿QUERES SER MI HIJO?") == normalizar("¿Querés ser mi hijo?") == "queres ser mi hijo"
    assert algun_director_coincide("Enrique Fernández y César Charlone", ["César Charlone"])
    assert algun_director_coincide("GLORIA PEIRANO, GUSTAVO FONTÁN.", ["Gustavo Fontán"])
    assert algun_director_coincide("HERNAN GOLDFRIND", ["Hernán Goldfrid"])  # errata de una letra
    assert algun_director_coincide("Alejandro Amenábar", ["Alejandro Fernando Amenábar"])
    assert not algun_director_coincide("Juan", ["Juan Pérez"])
    assert not algun_director_coincide("Ana Paz", ["Ana Ruiz"])


# ---------- cruce real del fixture de Gaumont ----------

@pytest.fixture(scope="module")
def con_gaumont():
    crudo = json.loads((FIXTURES / "gaumont" / "crudo-2026-11-13.json").read_text(encoding="utf-8"))
    respuestas = json.loads((FIXTURES / "tmdb" / "respuestas.json").read_text(encoding="utf-8"))

    class Fixture:
        def fetch(self, cliente, hoy, dias):
            return crudo

        def parse(self, c, hoy):
            return GAUMONT.parse(c, hoy)

    con = db.conectar(":memory:")
    cine = Cine(id="gaumont", nombre="Gaumont", direccion="Av. Rivadavia 1635", verificada=True,
                tanda=1, es_comercial=False, adaptador="gaumont")
    ingestar(con, [cine], momento=MOMENTO, cliente=object(), cargar=lambda n: Fixture())
    resumen = enriquecer(con, _cliente_desde(respuestas), momento=MOMENTO)
    yield con, resumen
    con.close()


def _peli(con, titulo_fuente):
    return con.execute("SELECT * FROM peliculas WHERE titulo_fuente = ?", (titulo_fuente,)).fetchone()


def test_gaumont_resumen(con_gaumont):
    _, r = con_gaumont
    assert (r.consultadas, r.ok, r.sin_match, r.ambiguo, r.errores) == (18, 15, 3, 0, 0)


def test_gaumont_matches(con_gaumont):
    con, _ = con_gaumont
    otros = _peli(con, "LOS OTROS")
    assert (otros["tmdb_id"], otros["anio"], otros["director"]) == (1933, 2001, "Alejandro Amenábar")
    assert otros["letterboxd_url"] == "https://letterboxd.com/tmdb/1933/"
    dejamos = _peli(con, "LO DEJAMOS ACA")
    assert (dejamos["match_estado"], dejamos["titulo"]) == ("ok", "Lo dejamos acá")


def test_gaumont_sin_match_queda_vacio(con_gaumont):
    con, _ = con_gaumont
    for titulo in ("ABUELO GAUCHO", "RETRATO, ELOGIO AL DUELO", "LA YEGUA DE TROYA"):
        p = _peli(con, titulo)
        assert p["match_estado"] == "sin_match" and p["match_motivo"]
        assert p["tmdb_id"] is None and p["director"] is None and p["anio"] is None


def test_todas_las_funciones_vinculadas(con_gaumont):
    con, _ = con_gaumont
    assert con.execute("SELECT COUNT(*) FROM funciones WHERE pelicula_id IS NULL").fetchone()[0] == 0


def test_titulo_comun_se_resuelve_con_segunda_ronda_por_anio():
    """'Freud' devuelve otras películas homónimas primero; la de Huston figura solo con su
    título original en inglés y la traducción al castellano está en translations."""
    respuestas = json.loads((FIXTURES / "tmdb" / "respuestas.json").read_text(encoding="utf-8"))
    m = resolver(_cliente_desde(respuestas), Pistas("Freud, pasión secreta", "Freud", 1962, "John Huston", 140))
    assert (m.estado, m.tmdb_id, m.anio, m.duracion) == ("ok", 35806, 1962, 140)


def test_no_reconsulta_resueltas(con_gaumont):
    con, _ = con_gaumont
    r = enriquecer(con, _cliente_desde({}), momento=MOMENTO)  # sin respuestas: no debería pedir nada
    assert r.consultadas == 0 and r.errores == 0
