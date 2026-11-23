import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from cartelera.adapters.showcase import Showcase, ficha
from cartelera.adapters.showcase_belgrano import ADAPTADOR as BELGRANO
from cartelera.tiempo import TZ

FIXTURE = Path(__file__).parent / "fixtures" / "showcase-belgrano" / "crudo-2026-11-23.json"
HOY = date(2026, 11, 23)


def _crudo():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_cantidades():
    fs = BELGRANO.parse(_crudo(), HOY)
    assert Counter(f.fecha_hora.date() for f in fs) == {
        date(2026, 11, 23): 26, date(2026, 11, 24): 37, date(2026, 11, 25): 36}
    assert not BELGRANO.avisos


def test_funcion_concreta():
    fs = [f for f in BELGRANO.parse(_crudo(), HOY) if f.titulo == "Yo soy Rocky"]
    f = min(fs, key=lambda x: x.fecha_hora)
    assert f.fecha_hora == datetime(2026, 11, 23, 17, 5, tzinfo=TZ)
    assert f.titulo_original == "I PLAY ROCKY" and f.director_fuente == "Peter Farrelly"
    assert f.duracion_fuente == 127 and f.anio_fuente is None
    assert f.modo_venta == "online"
    assert f.url_entradas == "https://entradas.todoshowcase.com/showcase/pelicula?filmid=6325&house_id=3206"


def test_original_igual_al_titulo_no_se_repite():
    f = next(x for x in BELGRANO.parse(_crudo(), HOY) if x.titulo.startswith("Recen por mí"))
    assert f.titulo_original is None  # "RECEN POR MI: ..." es el mismo título


def test_solo_el_complejo_y_trasnoche():
    crudo = {"complejo": 14, "hoy": "2026-11-23", "dias": 10, "peliculas": [{
        "filmid": "1", "nombre": "Prueba", "ficha": {},
        "dias": {"2026-11-27": [
            {"id": 14, "ewaveId": 3206, "formats": [{"performances": [{"showTime": "00:30"}]}]},
            {"id": 11, "ewaveId": 3200, "formats": [{"performances": [{"showTime": "18:00"}]}]}]}}]}
    (f,) = Showcase(14).parse(crudo, HOY)
    assert f.fecha_hora == datetime(2026, 11, 28, 0, 30, tzinfo=TZ)  # regla general de trasnoche


def test_ficha():
    pagina = ("<li><strong>Título Original: </strong>THE MORTUARY ASSISTANT</li>"
              "<li><strong>Director:</strong> Jeremiah Kipp</li><li><strong>Duración:</strong> 91 minutos</li>")
    assert ficha(pagina) == {"Título Original": "THE MORTUARY ASSISTANT", "Director": "Jeremiah Kipp",
                             "Duración": "91 minutos"}
