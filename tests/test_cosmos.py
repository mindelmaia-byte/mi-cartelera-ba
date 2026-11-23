import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from cartelera.adapters.cosmos import Cosmos, fin_de_semana, leer_horarios, tarjetas
from cartelera.tiempo import TZ

FIXTURE = Path(__file__).parent / "fixtures" / "cosmos" / "crudo-2026-11-23.json"
HOY = date(2026, 11, 23)  # lunes


def _crudo():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_hasta_el_miercoles():
    a = Cosmos()
    fs = a.parse(_crudo(), HOY)
    por_dia = Counter(f.fecha_hora.date() for f in fs)
    assert por_dia == {date(2026, 11, 23): 8, date(2026, 11, 24): 8, date(2026, 11, 25): 8}
    assert not a.avisos


def test_funcion_concreta():
    fs = [f for f in Cosmos().parse(_crudo(), HOY) if f.titulo == "Los colores del tiempo"]
    assert [f.fecha_hora for f in fs[:2]] == [datetime(2026, 11, 23, 14, 50, tzinfo=TZ),
                                              datetime(2026, 11, 23, 19, 0, tzinfo=TZ)]
    f = fs[0]
    assert f.director_fuente == "Cédric Klapisch" and f.anio_fuente == 2025 and f.duracion_fuente == 126
    assert f.modo_venta == "boleteria" and f.url_entradas is None
    assert f.fuente_url == "https://cosmos.uba.ar/pelicula?idPelicula=452"


def test_jueves_no_adivina():
    crudo = {**_crudo(), "hoy": "2026-11-26"}
    a = Cosmos()
    assert a.parse(crudo, date(2026, 11, 26)) == []
    assert a.avisos


def test_semana_y_horarios():
    assert fin_de_semana(date(2026, 11, 23)) == date(2026, 11, 25)
    assert fin_de_semana(date(2026, 11, 25)) == date(2026, 11, 25)
    assert fin_de_semana(date(2026, 11, 27)) == date(2026, 12, 2)
    assert leer_horarios("Ju Vi Sá Do Lu Ma Mi | 14:50 - 19:00") == ([3, 4, 5, 6, 0, 1, 2], ["14:50", "19:00"])
    assert leer_horarios("Sá Do | 9:30") == ([5, 6], ["09:30"])
    assert leer_horarios("Ju Vi | 14:50 (sala 2)") is None  # formato desconocido: se avisa
    assert leer_horarios("14:50") is None


def test_trasnoche_y_dias_parciales():
    crudo = {"url": "x", "hoy": "2026-11-27", "dias": 10, "peliculas": [
        {"id": "1", "titulo": "Prueba", "director": None, "duracion": None, "anio": None,
         "horarios": "Vi Sá | 00:30"}]}
    fs = Cosmos().parse(crudo, date(2026, 11, 27))
    # La grilla del viernes 27 a las 00:30 es la madrugada del sábado 28.
    assert [f.fecha_hora for f in fs] == [datetime(2026, 11, 28, 0, 30, tzinfo=TZ),
                                          datetime(2026, 11, 29, 0, 30, tzinfo=TZ)]


def test_lectura_del_html():
    pagina = ('<div class="card"><a href="/pelicula?idPelicula=7"><h4 class="card-title">La casa</h4></a>'
              '<p class="direccion">Dirección: Gustavo Triviño</p><p class="lightText">Argentina / 108m</p></div>'
              '<div class="card-footer"><p><span>Ju Vi | </span>14:55</p></div>')
    assert tarjetas(pagina) == [{"id": "7", "titulo": "La casa", "director": "Gustavo Triviño",
                                 "duracion": 108, "horarios": "Ju Vi | 14:55"}]
