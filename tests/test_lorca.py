import base64
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import pytest

from cartelera import extraccion
from cartelera.adapters.lorca import ADAPTADOR, buscar_imagenes
from cartelera.tiempo import TZ

FIXTURE = Path(__file__).parent / "fixtures" / "lorca" / "crudo-2026-11-13.json"
HOY = date(2026, 11, 13)


@pytest.fixture(scope="module")
def crudo():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_encuentra_solo_la_imagen_de_la_grilla():
    html = ('<img src="https://static.wixstatic.com/media/6cc776af25744f77ab9c420b98d1abe6.png/v1/fill/w_33">'
            '<img src="https://static.wixstatic.com/media/29f330_7820c046a42f4eae90cbce815da99cb2~mv2.jpg/v1/crop/x_0">'
            '"https://static.wixstatic.com/media/29f330_7820c046a42f4eae90cbce815da99cb2~mv2.jpg"')
    assert buscar_imagenes(html) == ["https://static.wixstatic.com/media/29f330_7820c046a42f4eae90cbce815da99cb2~mv2.jpg"]


def test_imagen_del_fixture_tiene_extraccion_guardada(crudo):
    [img] = crudo["imagenes"]
    assert extraccion.cargar("lorca", base64.b64decode(img["b64"])) is not None


def test_parse_grilla_semanal(crudo):
    funciones = ADAPTADOR.parse(crudo, HOY)
    assert ADAPTADOR.avisos == []
    assert len(funciones) == 77  # 11 horarios x 7 días (jue 12 a mié 18)
    por_dia = Counter(f.fecha_hora.date() for f in funciones)
    assert set(por_dia) == {date(2026, 11, d) for d in range(12, 19)}
    assert set(por_dia.values()) == {11}


def test_campos(crudo):
    funciones = ADAPTADOR.parse(crudo, HOY)
    caballo = [f for f in funciones if f.titulo == "CABALLO SALVAJE NUEVE" and f.fecha_hora.date() == date(2026, 11, 14)]
    assert [f.fecha_hora for f in caballo] == [datetime(2026, 11, 14, h, m, tzinfo=TZ) for h, m in ((14, 5), (18, 15), (22, 15))]
    f = caballo[0]
    assert f.modo_venta == "boleteria" and f.url_entradas is None
    assert f.duracion_fuente == 118 and f.anio_fuente is None and f.director_fuente is None
    assert f.fuente_url == "https://cinelorca.wixsite.com/cine-lorca/current-production"


def test_imagen_nueva_queda_pendiente(tmp_path, monkeypatch, crudo):
    monkeypatch.setattr(extraccion, "DIR_EXTRACCIONES", tmp_path)
    monkeypatch.setattr(extraccion, "RAIZ", tmp_path)
    assert ADAPTADOR.parse(crudo, HOY) == []
    [p] = extraccion.pendientes("lorca")
    assert p.suffix == ".jpg" and p.read_bytes()[:2] == b"\xff\xd8"  # JPEG
    assert "imagen de grilla nueva" in ADAPTADOR.avisos[0]
