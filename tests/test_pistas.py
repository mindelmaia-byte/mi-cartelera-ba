from datetime import datetime
from pathlib import Path

import pytest

from cartelera import pistas
from cartelera.schema import FuncionCruda
from cartelera.tiempo import TZ


def _f(titulo, director=None):
    return FuncionCruda(fecha_hora=datetime(2026, 11, 26, 19, 0, tzinfo=TZ), titulo=titulo,
                        modo_venta="online", fuente_url="x", director_fuente=director)


def test_el_archivo_real_carga_y_tiene_fuente():
    p = pistas.cargar()
    assert p[("cacodelphia", "plata quemada")] == {"director": "Marcelo Piñeyro"}


def test_completa_solo_lo_vacio_y_solo_ese_cine():
    p = {("cacodelphia", "plata quemada"): {"director": "Marcelo Piñeyro"}}
    a, b, c = pistas.aplicar("cacodelphia", [_f("PLATA QUEMADA"), _f("Plata quemada", "Otro"), _f("NAZA")], p)
    assert a.director_fuente == "Marcelo Piñeyro"
    assert b.director_fuente == "Otro"  # lo que publica la web no se pisa
    assert c.director_fuente is None
    (d,) = pistas.aplicar("lorca", [_f("PLATA QUEMADA")], p)
    assert d.director_fuente is None


def test_sin_fuente_no_se_acepta(tmp_path: Path):
    ruta = tmp_path / "pistas.yaml"
    ruta.write_text("- {cine: x, titulo: Y, director: Z}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fuente"):
        pistas.cargar(ruta)
