import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import pytest

from cartelera.adapters.malba import (ADAPTADOR, directores_de_programaciones, eventos_de_cine,
                                      fichas_por_pelicula, limpiar_titulo)
from cartelera.tiempo import TZ

FIXTURE = Path(__file__).parent / "fixtures" / "malba" / "crudo-2026-11-13.json"
HOY = date(2026, 11, 13)


@pytest.fixture(scope="module")
def crudo():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def funciones(crudo):
    return ADAPTADOR.parse(crudo, HOY)


def test_total_y_peliculas(funciones):
    assert len(funciones) == 36
    assert len({f.titulo for f in funciones}) == 20


def test_funcion_con_ficha(funciones):
    [f] = [x for x in funciones if x.titulo == "Perfume" and x.fecha_hora.date() == date(2026, 11, 13)]
    assert f.fecha_hora == datetime(2026, 11, 13, 22, 0, tzinfo=TZ)
    assert f.url_entradas == "https://ticketsmalba.liit.ar/?cine=1&m=2552&e=5775"
    assert f.modo_venta == "online" and f.fuente_url == "https://ticketsmalba.liit.ar/api/catalog"
    assert (f.director_fuente, f.anio_fuente, f.duracion_fuente) == ("Lucía S. Ruiz", 2026, 97)


def test_medianoche_usa_la_fecha_del_catalogo(funciones):
    """El Bazofi anuncia 'VIERNES 13 — 24:00 Cliente muerto no paga' y el catálogo dice 14/11 00:00:
    la fecha del catálogo ya es la real, no se corre otro día."""
    [f] = [x for x in funciones if x.titulo == "CLIENTE MUERTO NO PAGA"]
    assert f.fecha_hora == datetime(2026, 11, 14, 0, 0, tzinfo=TZ)
    assert f.director_fuente == "Carl Reiner"  # sale de la programación del festival


def test_titulo_de_la_pagina_del_evento(funciones):
    tren = [f for f in funciones if f.director_fuente == "Lorenzo Ferro y Lucas A. Vignale"]
    assert tren and {f.titulo for f in tren} == {"El tren fluvial"}  # el catálogo dice "TREN FLUVIAL"


def test_ciclo_por_prefijo(funciones):
    nocturna = {f.titulo: f for f in funciones if f.ciclo == "Nocturna"}
    assert set(nocturna) == {"PELÍCULA SORPRESA", "¿QUÉ CLASE DE JOVEN LE ABRE LA PUERTA A UN VAMPIRO?"}
    assert nocturna["¿QUÉ CLASE DE JOVEN LE ABRE LA PUERTA A UN VAMPIRO?"].director_fuente == "Boom Boom Kid y Zurita"


def test_fichas_por_id_de_compra(crudo):
    fichas = fichas_por_pelicula(crudo["eventos"])
    assert fichas["2487"]["director"] == "Pablo Aparo"  # link viejo malba.liit.com.ar/decidir y "Dirección y guión\n"
    assert fichas["2515"]["director"] == "Mariana Sanguinetti"  # "Dirección y guion: ..."
    assert (fichas["484"]["anio"], fichas["484"]["duracion"]) == (1983, 108)
    assert not any("bazofi" in f["url_evento"] for f in fichas.values())  # festival: varias películas


def test_programaciones():
    eventos = [{"texto": "Programación\nJUEVES 19\n19:00 \nLa prisionera\n, de Henri-Georges Clouzot\n"
                         "VIERNES 20\n24:00\n¡Película sorpresa!\nJUEVES 26\n20:30\nOrar Orbil & viceversa\n"
                         ", de\xa0Diego Trerotola (*)\nComprar entradas"}]
    d = directores_de_programaciones(eventos)
    assert d == {"la prisionera": {"director": "Henri-Georges Clouzot"},
                 "orar orbil y viceversa": {"director": "Diego Trerotola"}}


def test_limpiar_titulo():
    assert limpiar_titulo("nocturna: ¿QUÉ CLASE DE JOVEN?,") == ("¿QUÉ CLASE DE JOVEN?", "Nocturna")
    assert limpiar_titulo("FRIDA, NATURALEZA VIVA") == ("FRIDA, NATURALEZA VIVA", None)


def test_eventos_listados_despues_de_la_grilla():
    html = ('<a href="https://malba.org.ar/evento/viva-frida/">menú</a>'
            '<a href="https://malba.org.ar/wp-content/uploads/2026/11/malba-cine-2026-11-1.pdf">grilla</a>'
            '<a href="https://malba.org.ar/evento/perfume/">x</a><a href="https://malba.org.ar/evento/perfume/">y</a>')
    assert eventos_de_cine(html) == ["https://malba.org.ar/evento/perfume/"]


def test_por_dia(funciones):
    por_dia = Counter(f.fecha_hora.date() for f in funciones)
    assert por_dia[date(2026, 11, 13)] == 3 and por_dia[date(2026, 11, 19)] == 3
