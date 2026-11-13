import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import pytest

from cartelera import extraccion
from cartelera.adapters.lugones import ADAPTADOR, leer_tarjetas
from cartelera.tiempo import TZ

FIXTURE = Path(__file__).parent / "fixtures" / "lugones" / "crudo-2026-11-13.json"
HOY = date(2026, 11, 13)


@pytest.fixture(scope="module")
def crudo():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_descubre_ciclos_de_cine(crudo):
    tarjetas = leer_tarjetas(crudo["html_sala"])
    nombres = [t["ciclo"] for t in tarjetas]
    assert nombres[:4] == ["Museo de la subversión", "Homenaje a John Huston",
                           "Herzog-Kinski: enemigo mío", "El tren fluvial"]
    assert len(tarjetas) == 8
    huston = tarjetas[1]
    assert huston["url_programa"] == "https://complejoteatral.gob.ar/programa/homenaje-a-john-huston/"
    assert huston["url_entradas"].startswith("https://entradasba.buenosaires.gob.ar/evento/")
    assert huston["fechas"] == "Del 6 de noviembre al 4 de diciembre"
    assert sum(1 for t in tarjetas if t["url_programa"] is None) == 4


def test_todas_las_extracciones_estan_guardadas(crudo):
    for c in crudo["ciclos"]:
        if c["texto"]:
            assert extraccion.cargar("lugones", c["texto"]) is not None, c["ciclo"]


def test_parse_con_extracciones_guardadas(crudo):
    funciones = ADAPTADOR.parse(crudo, HOY)
    assert len(funciones) == 60  # 2 + 7 + 12 + 39, todas pasan la validación
    por_ciclo = Counter(f.ciclo for f in funciones)
    assert por_ciclo == {"Homenaje a John Huston": 39, "Herzog-Kinski: enemigo mío": 12, None: 9}
    assert len(ADAPTADOR.avisos) == 4 and all("sin programa" in a for a in ADAPTADOR.avisos)


def test_campos_de_una_funcion(crudo):
    funciones = ADAPTADOR.parse(crudo, HOY)
    freud = [f for f in funciones if f.titulo == "Freud, pasión secreta"]
    assert [f.fecha_hora for f in freud] == [
        datetime(2026, 11, 29, 20, 30, tzinfo=TZ),
        datetime(2026, 12, 3, 14, 30, tzinfo=TZ),
        datetime(2026, 12, 3, 20, 30, tzinfo=TZ),
    ]
    f = freud[0]
    assert f.titulo_original == "Freud" and f.anio_fuente == 1962 and f.director_fuente == "John Huston"
    assert f.duracion_fuente == 140 and f.modo_venta == "online"
    assert f.url_entradas.startswith("https://entradasba.buenosaires.gob.ar/")
    assert f.fuente_url.endswith("Prog-2026Homenaje-a-John-Huston.pdf")


def test_estreno_de_una_pelicula_no_es_ciclo(crudo):
    museo = [f for f in ADAPTADOR.parse(crudo, HOY) if f.titulo == "Museo de la subversión"]
    assert len(museo) == 7 and all(f.ciclo is None for f in museo)


def test_pdf_nuevo_queda_pendiente(tmp_path, monkeypatch, crudo):
    monkeypatch.setattr(extraccion, "DIR_EXTRACCIONES", tmp_path)
    monkeypatch.setattr(extraccion, "RAIZ", tmp_path)
    funciones = ADAPTADOR.parse(crudo, HOY)
    assert funciones == []
    pendientes = extraccion.pendientes("lugones")
    assert len(pendientes) == 4
    assert sum("PDF nuevo sin extraer" in a for a in ADAPTADOR.avisos) == 4


# ---------- validación ----------

def _resultado(*funciones, desde=None, hasta=None):
    return extraccion.ResultadoExtraccion(periodo_desde=desde, periodo_hasta=hasta, peliculas=[
        extraccion.PeliculaExtraida(titulo="X", funciones=[
            extraccion.FuncionExtraida(dia_semana_texto=d, fecha=f, hora=h) for d, f, h in funciones])])


def test_valida_dia_de_la_semana():
    r = _resultado(("Jueves", date(2026, 11, 19), "21:00"),     # ok
                   ("Miércoles", date(2026, 11, 19), "18:00"),  # el 19 es jueves: se descarta
                   ("sábado", date(2026, 11, 21), "15:00"))     # minúscula y tilde: ok
    validas, errores = extraccion.validar(r)
    assert [f.hora for _, f in validas] == ["21:00", "15:00"]
    assert len(errores) == 1 and "esa fecha es jueves" in errores[0]


def test_valida_periodo():
    r = _resultado(("Jueves", date(2026, 11, 12), "21:00"), ("Jueves", date(2026, 11, 26), "21:00"),
                   desde=date(2026, 11, 12), hasta=date(2026, 11, 25))
    validas, errores = extraccion.validar(r)
    assert len(validas) == 1 and "fuera del período" in errores[0]


def test_hora_invalida_no_entra_al_esquema():
    with pytest.raises(ValueError):
        extraccion.FuncionExtraida(dia_semana_texto="Jueves", fecha=date(2026, 11, 19), hora="21 hs")


def test_guardar_y_cargar(tmp_path, monkeypatch):
    monkeypatch.setattr(extraccion, "DIR_EXTRACCIONES", tmp_path)
    r = _resultado(("Jueves", date(2026, 11, 19), "21:00"))
    extraccion.guardar("prueba", "texto original", r, fuente_url="u", titulo_fuente="t", extraido_por="test")
    reg = extraccion.cargar("prueba", "texto original\n")  # mismo texto salvo espacios finales
    assert reg is not None and reg.resultado == r
    assert (tmp_path / "prueba" / f"{reg.hash}.txt").read_text(encoding="utf-8") == "texto original"
    assert extraccion.cargar("prueba", "otro texto") is None
