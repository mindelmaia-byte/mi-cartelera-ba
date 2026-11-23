import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from cartelera.adapters.multiplex import Multiplex, ficha, items_de_home
from cartelera.adapters.multiplex_belgrano import ADAPTADOR as BELGRANO
from cartelera.adapters.multiplex_lavalle import ADAPTADOR as LAVALLE
from cartelera.tiempo import TZ

FIXTURES = Path(__file__).parent / "fixtures"
HOY = date(2026, 11, 23)


def _crudo(cine):
    return json.loads((FIXTURES / cine / "crudo-2026-11-23.json").read_text(encoding="utf-8"))


def test_cantidades():
    lavalle = LAVALLE.parse(_crudo("multiplex-lavalle"), HOY)
    belgrano = BELGRANO.parse(_crudo("multiplex-belgrano"), HOY)
    assert len(lavalle) == 148 and len(belgrano) == 162
    por_dia = Counter(f.fecha_hora.date() for f in lavalle)
    assert por_dia[date(2026, 11, 23)] == 33
    assert por_dia[date(2026, 12, 2)] == 7
    assert min(por_dia) >= HOY and max(por_dia) < date(2026, 12, 3)
    assert not LAVALLE.avisos and not BELGRANO.avisos


def test_funcion_concreta():
    f = next(x for x in BELGRANO.parse(_crudo("multiplex-belgrano"), HOY) if x.titulo == "Puedes Verlo Todo")
    assert f.fecha_hora == datetime(2026, 11, 26, 13, 0, tzinfo=TZ)
    assert f.url_entradas == "https://ventas.cinemultiplex.com.ar/funcion?df=182-257-228189-20261126-5"
    assert f.modo_venta == "online"
    assert f.duracion_fuente == 174 and f.anio_fuente == 2026
    assert f.director_fuente is None and f.ciclo is None


def test_cada_complejo_solo_lo_suyo():
    crudo = _crudo("multiplex-lavalle")
    assert all("df=184-" in f.url_entradas for f in LAVALLE.parse(crudo, HOY))
    assert BELGRANO.parse(crudo, HOY) == []  # el crudo de Lavalle no tiene funciones de Belgrano


def test_trasnoche_usa_la_fecha_real():
    # La grilla del lunes 23 incluye la función de las 00:10, que en realidad es el martes 24.
    crudo = {"complejo": "184", "url": "x", "desde": "2026-11-23", "hasta": "2026-12-03", "peliculas": [{
        "url": None, "titulo": "Prueba", "ficha": None,
        "funciones": [{"complejo": "184", "dia": "11.23.2026", "dia_real": "11.24.2026", "hora": "00:10",
                       "tech_code": "", "pelicula_id": "1", "id": "2"}],
    }]}
    (f,) = Multiplex("184").parse(crudo, HOY)
    assert f.fecha_hora == datetime(2026, 11, 24, 0, 10, tzinfo=TZ)
    assert f.url_entradas.endswith("-1-2-20261124")


def test_lectura_del_html():
    home = ("<div class='funcion-item visible' data-funciones='[{&quot;complejo&quot;:&quot;184&quot;}]'>"
            "<div class='pelicula-cabecera'><a href='https://multiplex.com.ar/peliculas/x/' class='titulo-link'>"
            "<h4 class='no-link-style'>Tierra De Mi Padre</h4></a></div>")
    assert items_de_home(home) == [{"url": "https://multiplex.com.ar/peliculas/x/",
                                    "titulo": "Tierra De Mi Padre", "funciones": '[{"complejo":"184"}]'}]
    pagina = "<p>Duración</p><script>x</script><div>93</div><p>Estreno</p><span>15/01/2026</span>"
    assert ficha(pagina) == {"duracion": "93", "estreno": "15/01/2026"}
