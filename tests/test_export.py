import json
from datetime import datetime

from cartelera import db
from cartelera.export import exportar, titulo_a_mostrar
from cartelera.ingest import ingestar
from cartelera.schema import Cine, FuncionCruda
from cartelera.tiempo import TZ

MOMENTO = datetime(2026, 11, 13, 12, 0, tzinfo=TZ)


def test_titulo_a_mostrar():
    assert titulo_a_mostrar("4 HISTORIAS INCREIBLES", "4 historias increíbles") == "4 historias increíbles"
    assert titulo_a_mostrar("Huracán de pasiones", "Cayo Largo") == "Huracán de pasiones"  # el del cine
    assert titulo_a_mostrar("CLIENTE MUERTO NO PAGA", "El Cliente Muerto No Paga") == "CLIENTE MUERTO NO PAGA"
    assert titulo_a_mostrar("LS83", "LS83") == "LS83"
    assert titulo_a_mostrar("LA CASA", None) == "LA CASA"


def test_export_ventana_y_campos(tmp_path):
    class Fijo:
        def fetch(self, cliente, hoy, dias):
            return None

        def parse(self, crudo, hoy):
            return [
                FuncionCruda(fecha_hora=datetime(2026, 11, 13, 10, 0, tzinfo=TZ), titulo="Pasada",
                             modo_venta="online", fuente_url="x"),
                FuncionCruda(fecha_hora=datetime(2026, 11, 14, 0, 30, tzinfo=TZ), titulo="Trasnoche",
                             modo_venta="boleteria", fuente_url="x"),
                FuncionCruda(fecha_hora=datetime(2026, 11, 22, 23, 0, tzinfo=TZ), titulo="Último día",
                             modo_venta="gratis", fuente_url="x"),
                FuncionCruda(fecha_hora=datetime(2026, 11, 23, 15, 0, tzinfo=TZ), titulo="Fuera de la ventana",
                             modo_venta="online", fuente_url="x"),
            ]

    con = db.conectar(":memory:")
    cines = [Cine(id="a", nombre="Cine A", direccion="Calle 1", verificada=True, tanda=1, es_comercial=False, adaptador="a"),
             Cine(id="b", nombre="Cine B", direccion=None, verificada=False, tanda=4, es_comercial=True, adaptador=None)]
    ingestar(con, cines, momento=MOMENTO - __import__("datetime").timedelta(hours=3), cliente=object(),
             cargar=lambda n: Fijo())
    ruta = tmp_path / "c.json"
    datos = exportar(con, cines, momento=MOMENTO, ruta=ruta)
    assert json.loads(ruta.read_text(encoding="utf-8")) == datos
    assert [f["titulo"] for f in datos["funciones"]] == ["Trasnoche", "Último día"]
    t = datos["funciones"][0]
    assert (t["fecha"], t["hora"], t["dia_semana"]) == ("2026-11-14", "00:30", 5)  # sábado
    assert t["inicio"] == "2026-11-14T00:30:00-03:00" and t["modo_venta"] == "boleteria"
    assert datos["desde"] == "2026-11-13" and datos["dias"] == 10
    estados = {c["id"]: c for c in datos["cines"]}
    assert estados["a"]["activo"] and estados["a"]["ultima_actualizacion"]
    assert not estados["b"]["activo"] and estados["b"]["es_comercial"]
