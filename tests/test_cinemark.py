import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from cartelera.adapters.cinemark import Cinemark
from cartelera.adapters.cinemark_abasto import ADAPTADOR as ABASTO
from cartelera.adapters.cinemark_dot import ADAPTADOR as DOT
from cartelera.adapters.cinemark_palermo import ADAPTADOR as PALERMO
from cartelera.tiempo import TZ

FIXTURES = Path(__file__).parent / "fixtures"
HOY = date(2026, 11, 23)


def _crudo(cine):
    return json.loads((FIXTURES / cine / "crudo-2026-11-23.json").read_text(encoding="utf-8"))


def test_cantidades():
    palermo = PALERMO.parse(_crudo("cinemark-palermo"), HOY)
    assert len(palermo) == 145
    assert len(ABASTO.parse(_crudo("cinemark-abasto"), HOY)) == 184
    assert len(DOT.parse(_crudo("cinemark-dot"), HOY)) == 137
    por_dia = Counter(f.fecha_hora.date() for f in palermo)
    assert por_dia[date(2026, 11, 23)] == 22 and por_dia[date(2026, 12, 2)] == 7
    assert not PALERMO.avisos


def test_la_z_es_hora_local():
    # La página de Palermo muestra Yo soy Rocky a las 16:35; la API dice "2026-11-23T16:35:00.000Z".
    f = next(x for x in PALERMO.parse(_crudo("cinemark-palermo"), HOY) if x.titulo == "YO SOY ROCKY")
    assert f.fecha_hora == datetime(2026, 11, 23, 16, 35, tzinfo=TZ)
    assert f.fecha_hora.utcoffset().total_seconds() == -3 * 3600
    assert f.url_entradas == "https://www.cinemark.com.ar/pelicula/yo-soy-rocky"
    assert f.modo_venta == "online"
    assert f.anio_fuente == 2026 and f.duracion_fuente == 127


def test_titulo_completo_desde_movies():
    titulos = {f.titulo for f in PALERMO.parse(_crudo("cinemark-palermo"), HOY)}
    assert "LOS JUEGOS DEL HAMBRE: AMANECER EN LA COSECHA" in titulos  # showtimes lo trae cortado
    assert "LOS JUEGOS DEL HAMBRE: AMANECER" not in titulos


def test_trasnoche_ya_viene_con_la_fecha_real():
    crudo = {"theater": "733", "hoy": "2026-12-15", "dias": 10, "movies": [], "showtimes": [{
        "theaterId": "733", "movieName": "AVENGERS: DOOMSDAY", "corporateId": "1",
        "sessionDateTime": "2026-12-16T00:15:00.000Z", "sessionDisplayDate": "2026-12-15",
        "isLateNightSession": True}]}
    a = Cinemark("733")
    (f,) = a.parse(crudo, date(2026, 12, 15))
    assert f.fecha_hora == datetime(2026, 12, 16, 0, 15, tzinfo=TZ)  # sin correr otro día
    assert f.url_entradas is None and a.avisos  # sin ficha en /movies: se avisa
