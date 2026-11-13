from datetime import date, datetime, timedelta

import pytest

from cartelera import db
from cartelera.ingest import ingestar
from cartelera.schema import Cine, FuncionCruda
from cartelera.tiempo import TZ

MOMENTO = datetime(2026, 11, 13, 12, 0, tzinfo=TZ)


def _cine(id_, adaptador):
    return Cine(id=id_, nombre=id_.title(), direccion="Calle 1", verificada=True, tanda=1,
                es_comercial=False, adaptador=adaptador)


def _funcion(dia: int, hora: int, titulo: str = "Peli") -> FuncionCruda:
    return FuncionCruda(fecha_hora=datetime(2026, 11, dia, hora, 0, tzinfo=TZ), titulo=titulo,
                        modo_venta="online", fuente_url="https://ejemplo")


class Fijo:
    def __init__(self, funciones):
        self.funciones = funciones

    def fetch(self, cliente, hoy, dias):
        return None

    def parse(self, crudo, hoy):
        return list(self.funciones)


class Roto:
    def fetch(self, cliente, hoy, dias):
        raise ConnectionError("sitio caído")

    def parse(self, crudo, hoy):
        raise AssertionError("no debería llegar")


@pytest.fixture
def con():
    c = db.conectar(":memory:")
    yield c
    c.close()


def _correr(con, adaptadores: dict, momento=MOMENTO):
    cines = [_cine(i, i) for i in adaptadores]
    return ingestar(con, cines, momento=momento, cliente=object(), cargar=lambda n: adaptadores[n])


def _filas(con, cine_id):
    return [tuple(r) for r in con.execute(
        "SELECT fecha_hora, titulo FROM funciones WHERE cine_id = ? ORDER BY fecha_hora", (cine_id,))]


def test_idempotente(con):
    a = Fijo([_funcion(13, 20), _funcion(14, 18), _funcion(14, 18)])  # duplicado exacto
    _correr(con, {"a": a})
    primera = _filas(con, "a")
    _correr(con, {"a": a})
    assert _filas(con, "a") == primera
    assert len(primera) == 2


def test_reemplaza_solo_futuras(con):
    _correr(con, {"a": Fijo([_funcion(13, 10), _funcion(13, 20), _funcion(14, 18)])},
            momento=MOMENTO - timedelta(hours=3))  # a las 9, la de las 10 todavía era futura
    _correr(con, {"a": Fijo([_funcion(15, 21, "Nueva")])})
    assert _filas(con, "a") == [
        ("2026-11-13T10:00:00-03:00", "Peli"),   # pasada: se conserva
        ("2026-11-15T21:00:00-03:00", "Nueva"),  # futuras: reemplazadas
    ]


def test_un_cine_roto_no_corta_el_resto(con):
    _correr(con, {"roto": Fijo([_funcion(14, 18)]), "b": Fijo([])})
    res = _correr(con, {"roto": Roto(), "b": Fijo([_funcion(14, 20)])})
    estados = {r.cine_id: r.estado for r in res}
    assert estados == {"roto": "error", "b": "ok"}
    assert len(_filas(con, "roto")) == 1  # conserva lo anterior
    assert len(_filas(con, "b")) == 1
    cine = con.execute("SELECT * FROM cines WHERE id = 'roto'").fetchone()
    assert cine["ultimo_estado"] == "error" and "sitio caído" in cine["ultimo_error"]
    assert cine["ultima_actualizacion"] is not None  # la del ingest exitoso anterior


def test_cero_funciones_no_borra(con):
    _correr(con, {"a": Fijo([_funcion(14, 18)])})
    [r] = _correr(con, {"a": Fijo([])})
    assert r.estado == "sin_funciones"
    assert len(_filas(con, "a")) == 1


def test_guarda_fecha_de_actualizacion(con):
    _correr(con, {"a": Fijo([_funcion(14, 18)])})
    cine = con.execute("SELECT * FROM cines WHERE id = 'a'").fetchone()
    assert cine["ultima_actualizacion"] == "2026-11-13T12:00:00-03:00"
    assert cine["ultimo_estado"] == "ok"


def test_cines_sin_adaptador_se_saltean(con):
    res = ingestar(con, [_cine("x", None)], momento=MOMENTO, cliente=object())
    assert res == []
