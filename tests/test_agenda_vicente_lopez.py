import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from cartelera.adapters.agenda_vicente_lopez import AgendaVicenteLopez, articulos, separar_formato
from cartelera.adapters.lumiton import ADAPTADOR as LUMITON
from cartelera.adapters.munro import ADAPTADOR as MUNRO
from cartelera.adapters.york import ADAPTADOR as YORK
from cartelera.tiempo import TZ

FIXTURES = Path(__file__).parent / "fixtures"
HOY = date(2026, 11, 23)


def _crudo(cine):
    return json.loads((FIXTURES / cine / "crudo-2026-11-23.json").read_text(encoding="utf-8"))


def test_cantidades_por_sala():
    york = YORK.parse(_crudo("york"), HOY)
    assert len(york) == 10
    assert Counter(f.fecha_hora.date() for f in york)[date(2026, 11, 29)] == 2
    assert len(MUNRO.parse(_crudo("munro"), HOY)) == 3
    # En Lumiton solo hay una charla (sin tipo "cine"): no es una función.
    assert LUMITON.parse(_crudo("lumiton"), HOY) == []
    assert not YORK.avisos and not MUNRO.avisos


def test_funcion_concreta():
    f = next(x for x in YORK.parse(_crudo("york"), HOY) if x.titulo == "DRÁCULA")
    assert f.fecha_hora == datetime(2026, 11, 29, 20, 30, tzinfo=TZ)
    assert f.fecha_hora.utcoffset().total_seconds() == -3 * 3600
    assert f.modo_venta == "gratis" and f.url_entradas is None
    assert f.director_fuente == "Tod Browning" and f.anio_fuente == 1931 and f.duracion_fuente == 75
    assert f.fuente_url == "https://lumiton.ar/evento/dracula-2-2/"


def test_programa_de_cortos_sin_pistas():
    f = next(x for x in YORK.parse(_crudo("york"), HOY) if x.titulo.startswith("CONVOCATORIA DE CORTOS"))
    # "duración total aprox. 110 min" y "2022 - 2026" no son una duración ni un año de película.
    assert f.director_fuente is None and f.anio_fuente is None and f.duracion_fuente is None


def test_formato_en_el_titulo():
    assert separar_formato("VLADIMIR EN BUENOS AIRES EN 35 MM") == ("VLADIMIR EN BUENOS AIRES", "En 35 mm")
    assert separar_formato("EN LAS RUTAS") == ("EN LAS RUTAS", None)
    f = next(x for x in YORK.parse(_crudo("york"), HOY) if x.titulo == "VLADIMIR EN BUENOS AIRES")
    assert f.ciclo == "En 35 mm"


def test_ventana_de_dias():
    crudo = {**_crudo("munro"), "dias": 5}  # hasta el 27: queda afuera todo lo del 29
    assert [f.fecha_hora.day for f in AgendaVicenteLopez("centro-cultural-munro").parse(crudo, HOY)] == [26]


def test_lectura_del_html():
    pagina = ('<article class="g-item post-7 evento tipo-proyecciones tipo-cine" data-date="2026-11-25" '
              "data-locations='[\"cine-york\"]'><div>miércoles 25 nov 20:30hs</div><h3>OLIVIA</h3>"
              '<a href="https://lumiton.ar/evento/olivia/">Ver más</a></article>')
    assert articulos(pagina) == [{"id": "7", "tipos": ["proyecciones", "cine"], "fecha": "2026-11-25",
                                  "hora": "20:30", "lugares": ["cine-york"], "titulo": "OLIVIA",
                                  "url": "https://lumiton.ar/evento/olivia/"}]
