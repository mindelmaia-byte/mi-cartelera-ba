import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from cartelera.adapters.cacodelphia import ADAPTADOR, Cacodelphia, separar_ciclo
from cartelera.tiempo import TZ

FIXTURE = Path(__file__).parent / "fixtures" / "cacodelphia" / "crudo-2026-11-23.json"
HOY = date(2026, 11, 23)


def _crudo():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_cantidades():
    fs = ADAPTADOR.parse(_crudo(), HOY)
    assert len(fs) == 36
    assert Counter(f.fecha_hora.date() for f in fs)[date(2026, 11, 23)] == 11
    assert not ADAPTADOR.avisos


def test_funcion_concreta_hora_local():
    # La página muestra El sonido al caer a las 16:10; la API dice "2026-11-23 16:10:00" con timezone "UTC".
    f = next(x for x in ADAPTADOR.parse(_crudo(), HOY) if x.titulo == "EL SONIDO AL CAER")
    assert f.fecha_hora == datetime(2026, 11, 23, 16, 10, tzinfo=TZ)
    assert f.fecha_hora.utcoffset().total_seconds() == -3 * 3600
    assert f.modo_venta == "online"
    assert f.url_entradas == "https://cineartecacodelphia.com.ar/pelicula/86/9c4179165d882c836339694f6438d5dd"
    assert f.duracion_fuente == 155 and f.anio_fuente == 2026 and f.ciclo is None


def test_ciclo_sin_anio():
    f = next(x for x in ADAPTADOR.parse(_crudo(), HOY) if x.titulo == "PLATA QUEMADA")
    # En el ciclo, "FechaEstreno" (2026) es cuándo la sumó el cine, no el año de la película (2000).
    assert f.ciclo == "Ciclo SOY" and f.anio_fuente is None and f.duracion_fuente == 125


def test_separar_ciclo():
    assert separar_ciclo("CICLO SOY - LA MUJER SIN CABEZA") == ("LA MUJER SIN CABEZA", "Ciclo SOY")
    assert separar_ciclo("CABALLO SALVAJE NUEVE") == ("CABALLO SALVAJE NUEVE", None)


def test_oculta_y_ventana():
    crudo = {"hoy": "2026-11-23", "dias": 3, "peliculas": [{
        "pref": "x", "nombre": "PRUEBA", "duracion": "90", "estreno": "2026-11-20",
        "funciones": [{"fechaHora": "2026-11-23 20:00:00.000000", "mostrar": "1"},
                      {"fechaHora": "2026-11-24 20:00:00.000000", "mostrar": "0"},   # no se muestra
                      {"fechaHora": "2026-11-27 20:00:00.000000", "mostrar": "1"}]}]}  # fuera de la ventana
    assert [f.fecha_hora.day for f in Cacodelphia().parse(crudo, HOY)] == [23]
