import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from cartelera.adapters.gaumont import ADAPTADOR, _limpiar_titulo
from cartelera.tiempo import TZ

FIXTURE = Path(__file__).parent / "fixtures" / "gaumont" / "crudo-2026-11-13.json"
HOY = date(2026, 11, 13)


def _parsear():
    return ADAPTADOR.parse(json.loads(FIXTURE.read_text(encoding="utf-8")), HOY)


def test_cantidad_por_dia():
    por_dia = Counter(f.fecha_hora.date() for f in _parsear())
    assert por_dia[date(2026, 11, 13)] == 12
    assert por_dia[date(2026, 11, 17)] == 11
    assert por_dia[date(2026, 11, 19)] == 0  # la grilla nueva sale los martes
    assert por_dia[date(2026, 11, 24)] == 1
    assert sum(por_dia.values()) == 75


def test_funcion_concreta():
    llanto = [f for f in _parsear() if f.titulo == "EL LLANTO DEL PERRO"]
    assert llanto, "falta El llanto del perro"
    f = next(x for x in llanto if x.fecha_hora.date() == date(2026, 11, 14))
    assert f.fecha_hora == datetime(2026, 11, 14, 21, 30, tzinfo=TZ)
    assert f.fecha_hora.utcoffset().total_seconds() == -3 * 3600
    assert f.url_entradas == "https://www.cinegaumont.ar/es-AR/programacion/6412"
    assert f.modo_venta == "online"
    assert f.director_fuente == "FEDERICO VENZI"
    assert f.titulo_original is None and f.ciclo is None


def test_duracion_y_fuente():
    otros = next(f for f in _parsear() if f.titulo == "LOS OTROS")
    assert otros.duracion_fuente == 105
    assert otros.fuente_url.startswith("https://apifront.cinexo.com.ar/")


def test_limpia_coma_sin_espacio():
    assert _limpiar_titulo("RETRATO,ELOGIO AL  DUELO") == "RETRATO, ELOGIO AL DUELO"
    assert _limpiar_titulo("1,5 GRADOS") == "1,5 GRADOS"


def test_trasnoche_pasa_al_dia_siguiente():
    crudo = {
        "dias": [{
            "fecha": "2026-11-13",
            "url": "x",
            "respuesta": {"success": True, "data": {
                "datos": [{"peliculas_codigo": "1", "peliculas_nombre": "A", "peliculas_duracion": "0", "director": " "}],
                "funciones": [{"codPelicula": "1", "hora": "00:30"}, {"codPelicula": "9", "hora": "20:00"}],
            }},
        }]
    }
    [f] = ADAPTADOR.parse(crudo, HOY)  # la función sin película se descarta
    assert f.fecha_hora == datetime(2026, 11, 14, 0, 30, tzinfo=TZ)
    assert f.duracion_fuente is None and f.director_fuente is None
