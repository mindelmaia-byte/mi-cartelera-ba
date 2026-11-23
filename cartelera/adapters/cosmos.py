"""Cine Cosmos (UBA, Av. Corrientes 2046).

Fuente: https://cosmos.uba.ar (HTML del servidor, sin JSON). La home lista la cartelera de la
semana en tarjetas:

  <h4 class="card-title">Los colores del tiempo</h4>
  <p class="direccion">Dirección: Cédric Klapisch</p>
  <p class="lightText">Francia / 126m</p>
  <p class="textoPeliFooter"><span>Ju Vi Sá Do Lu Ma Mi | </span>14:50 - 19:00</p>

No hay fechas: los días son los de la semana de estrenos, de jueves a miércoles, y la grilla
nueva sale cada jueves. Por eso la cartelera cubre desde hoy hasta el miércoles de esa semana y
no se extiende más allá. "14:50 - 19:00" son dos funciones (la página /hoy las muestra como
"14:50, 19:00"). Como la fuente publica el día de la grilla, se usa tiempo.combinar
(trasnoche). La ficha /pelicula?idPelicula=N trae el año, que se usa como pista para TMDB.
La entrada se compra en boletería. Ver docs/fuentes.md.
"""

import html
import re
import time as reloj
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from cartelera.schema import FuncionCruda
from cartelera.tiempo import combinar

URL_HOME = "https://cosmos.uba.ar/"
URL_FICHA = "https://cosmos.uba.ar/pelicula?idPelicula={id}"
PAUSA_SEGUNDOS = 1.0

# Abreviaturas en el orden de la semana de estrenos; el valor es date.weekday().
DIAS = {"ju": 3, "vi": 4, "sa": 5, "do": 6, "lu": 0, "ma": 1, "mi": 2}

RE_TARJETA = re.compile(r'<div class="card">(.*?)<div class="card-footer">(.*?)</div>', re.S)
RE_ID = re.compile(r'href="/pelicula\?idPelicula=(\d+)"')
RE_TITULO = re.compile(r'<h4 class="card-title">(.*?)</h4>', re.S)
RE_DIRECTOR = re.compile(r'<p class="direccion">\s*Dirección:\s*(.*?)</p>', re.S)
RE_DURACION = re.compile(r'<p class="lightText">.*?/\s*(\d{1,3})m', re.S)
RE_ANIO = re.compile(r"Año:\s*(?:<[^>]+>\s*)*(\d{4})")


def _texto(fragmento: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragmento)).split())


def tarjetas(pagina: str) -> list[dict[str, Any]]:
    """Las tarjetas de la sección Cartelera (la home también tiene un carrusel, que se ignora)."""
    inicio = pagina.find('id="CarteleraTit"')
    pagina = pagina[inicio:] if inicio >= 0 else pagina
    salida = []
    for cuerpo, pie in RE_TARJETA.findall(pagina):
        ident, titulo = RE_ID.search(cuerpo), RE_TITULO.search(cuerpo)
        director, duracion = RE_DIRECTOR.search(cuerpo), RE_DURACION.search(cuerpo)
        salida.append({
            "id": ident.group(1) if ident else None,
            "titulo": _texto(titulo.group(1)) if titulo else None,
            "director": _texto(director.group(1)) if director else None,
            "duracion": int(duracion.group(1)) if duracion else None,
            "horarios": _texto(pie),
        })
    return salida


def leer_horarios(texto: str) -> tuple[list[int], list[str]] | None:
    """"Ju Vi Sá Do Lu Ma Mi | 14:50 - 19:00" -> ([3, 4, 5, 6, 0, 1, 2], ["14:50", "19:00"])."""
    if texto.count("|") != 1:
        return None
    izq, der = texto.split("|")
    sin_tildes = izq.lower().replace("á", "a")
    tokens = re.findall(r"[a-z]+", sin_tildes)
    if not tokens or any(t not in DIAS for t in tokens):
        return None
    horas = re.findall(r"\b(\d{1,2}:\d{2})\b", der)
    if not horas or re.sub(r"[\d:\s,\-]", "", der):
        return None  # algo más que horas: formato nuevo, mejor avisar que adivinar
    return [DIAS[t] for t in tokens], [h.zfill(5) for h in horas]


def fin_de_semana(hoy: date) -> date:
    """El miércoles que cierra la semana de estrenos (jueves a miércoles) que contiene a hoy."""
    return hoy + timedelta(days=(2 - hoy.weekday()) % 7)


class Cosmos:
    def __init__(self):
        self.avisos: list[str] = []

    def fetch(self, cliente: httpx.Client, hoy: date, dias: int) -> dict[str, Any]:
        r = cliente.get(URL_HOME)
        r.raise_for_status()
        pelis = tarjetas(r.text)
        if not pelis:
            raise ValueError("la home de Cosmos no trae tarjetas de cartelera (¿cambió el HTML?)")
        for p in pelis:
            p["anio"] = None
            if p["id"]:
                reloj.sleep(PAUSA_SEGUNDOS)
                rf = cliente.get(URL_FICHA.format(id=p["id"]))
                if rf.status_code == 200:
                    m = RE_ANIO.search(rf.text)
                    p["anio"] = int(m.group(1)) if m else None
        return {"url": URL_HOME, "hoy": hoy.isoformat(), "dias": dias, "peliculas": pelis}

    def parse(self, crudo: dict[str, Any], hoy: date) -> list[FuncionCruda]:
        self.avisos = []
        desde = date.fromisoformat(crudo["hoy"])
        if desde.weekday() == 3:
            # Jueves: la grilla no tiene fechas y puede seguir siendo la de la semana que terminó.
            # Antes que atribuirla a la semana nueva, se espera al viernes.
            self.avisos.append("jueves: no se sabe si la grilla publicada ya es la de la semana nueva; se lee mañana")
            return []
        hasta = min(fin_de_semana(desde), desde + timedelta(days=crudo["dias"] - 1))
        funciones: list[FuncionCruda] = []
        for p in crudo["peliculas"]:
            leido = leer_horarios(p.get("horarios") or "")
            if not p.get("titulo") or leido is None:
                self.avisos.append(f"no entendí los horarios de {p.get('titulo')!r}: {p.get('horarios')!r}")
                continue
            dias_semana, horas = leido
            dia = desde
            while dia <= hasta:
                if dia.weekday() in dias_semana:
                    for h in horas:
                        funciones.append(FuncionCruda(
                            fecha_hora=combinar(dia, datetime.strptime(h, "%H:%M").time()),
                            titulo=p["titulo"],
                            modo_venta="boleteria",
                            fuente_url=URL_FICHA.format(id=p["id"]) if p.get("id") else crudo["url"],
                            director_fuente=p.get("director"),
                            anio_fuente=p.get("anio"),
                            duracion_fuente=p.get("duracion"),
                        ))
                dia += timedelta(days=1)
        return funciones


ADAPTADOR = Cosmos()
