"""Extracción con la API de Claude, con un cliente falso: sin red y sin gastar."""

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from cartelera import db, extraccion, llm
from cartelera.ingest import ingestar
from cartelera.schema import Cine, FuncionCruda
from cartelera.tiempo import TZ


def _resultado(n=1):
    return llm._Resultado(periodo_desde="2026-11-19", periodo_hasta="2026-11-25", peliculas=[
        llm._Pelicula(titulo="Minotauro", titulo_original=None, pais=None, anio=None, director=None,
                      duracion_min=141, idioma="ru", ciclo=None,
                      funciones=[llm._Funcion(dia_semana_texto="Jueves", fecha="2026-11-19", hora="18:00")] * n)])


class ClienteFalso:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)  # stop_reason por llamada
        self.llamadas = []
        self.messages = self

    def parse(self, **kwargs):
        self.llamadas.append(kwargs)
        stop = self.respuestas.pop(0)
        return SimpleNamespace(stop_reason=stop, parsed_output=_resultado() if stop == "end_turn" else None)


def test_texto_con_esquema_estricto():
    c = ClienteFalso(["end_turn"])
    r, modelo = llm.extraer("Jueves 19 / A las 18 horas", ".txt", "contexto", c)
    [k] = c.llamadas
    assert modelo == "claude-opus-5-5" and k["model"] == "claude-opus-5-5"
    assert k["output_format"] is llm._Resultado and k["system"] == extraccion.INSTRUCCIONES
    assert k["output_config"] == {"effort": "high"}
    assert k["messages"][0]["content"][0]["text"].startswith("<texto>")
    assert isinstance(r, extraccion.ResultadoExtraccion) and r.peliculas[0].funciones[0].fecha == date(2026, 11, 19)


def test_imagen_webp():
    c = ClienteFalso(["end_turn"])
    llm.extraer(b"RIFF....WEBP", ".webp", "contexto", c)
    bloque = c.llamadas[0]["messages"][0]["content"][0]
    assert bloque["type"] == "image" and bloque["source"]["media_type"] == "image/webp"


def test_si_se_niega_prueba_el_respaldo():
    c = ClienteFalso(["refusal", "end_turn"])
    _, modelo = llm.extraer("texto", ".txt", "contexto", c)
    assert modelo == "claude-opus-4-8" and [k["model"] for k in c.llamadas] == ["claude-opus-5-5", "claude-opus-4-8"]


def test_si_los_dos_se_niegan_no_inventa():
    with pytest.raises(llm.ErrorExtraccion):
        llm.extraer("texto", ".txt", "contexto", ClienteFalso(["refusal", "refusal"]))


def test_respuesta_cortada_es_error():
    with pytest.raises(llm.ErrorExtraccion):
        llm.extraer("texto", ".txt", "contexto", ClienteFalso(["max_tokens"]))


def test_formato_invalido_no_pasa(monkeypatch):
    malo = llm._Resultado(periodo_desde=None, periodo_hasta=None, peliculas=[
        llm._Pelicula(titulo="X", titulo_original=None, pais=None, anio=None, director=None, duracion_min=None,
                      idioma=None, ciclo=None, funciones=[llm._Funcion(dia_semana_texto="Jueves", fecha="19/11", hora="18 hs")])])
    c = ClienteFalso(["end_turn"])
    c.parse = lambda **kw: SimpleNamespace(stop_reason="end_turn", parsed_output=malo)
    with pytest.raises(llm.ErrorExtraccion):
        llm.extraer("texto", ".txt", "contexto", c)


def test_procesar_pendientes_guarda_y_respeta_el_tope(tmp_path, monkeypatch):
    monkeypatch.setattr(extraccion, "DIR_EXTRACCIONES", tmp_path)
    monkeypatch.setattr(extraccion, "RAIZ", tmp_path)
    for i in range(3):
        extraccion.guardar_pendiente("lugones", f"texto {i}", f"https://x/{i}.pdf", f"Ciclo {i}")
    c = ClienteFalso(["end_turn", "end_turn"])
    informe = llm.procesar_pendientes("lugones", date(2026, 11, 23), c, limite=2)
    assert len(informe) == 2 and all("1 funciones válidas" in linea for linea in informe)
    assert len(extraccion.pendientes("lugones")) == 1  # el tercero espera a la próxima corrida
    registros = [extraccion.cargar("lugones", f"texto {i}") for i in range(3)]
    guardados = [r for r in registros if r is not None]
    assert len(guardados) == 2 and all(r.extraido_por == "claude-opus-5-5 (API)" for r in guardados)


def test_ingest_extrae_y_vuelve_a_parsear():
    class ConPendiente:
        def __init__(self):
            self.extraido = False
            self.avisos = []

        def fetch(self, cliente, hoy, dias):
            return None

        def parse(self, crudo, hoy):
            if not self.extraido:
                self.avisos = ["«Ciclo»: PDF nuevo sin extraer -> x.txt"]
                return []
            self.avisos = []
            return [FuncionCruda(fecha_hora=datetime(2026, 11, 24, 21, tzinfo=TZ), titulo="Una",
                                 modo_venta="online", fuente_url="x")]

    adaptador = ConPendiente()

    def extraer(cine_id):
        adaptador.extraido = True
        return ["x.txt: 1 películas, 1 funciones válidas"]

    con = db.conectar(":memory:")
    cine = Cine(id="a", nombre="A", direccion=None, verificada=False, tanda=1, es_comercial=False, adaptador="a")
    [r] = ingestar(con, [cine], momento=datetime(2026, 11, 23, 12, tzinfo=TZ), cliente=object(),
                   cargar=lambda n: adaptador, extraer_pendientes=extraer)
    assert r.estado == "ok" and r.n_funciones == 1
    assert r.avisos == ["API: x.txt: 1 películas, 1 funciones válidas"]
