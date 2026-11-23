"""Multiplex (cadena comercial). En la cartelera: Multiplex Lavalle y Multiplex Belgrano.

Fuente: https://multiplex.com.ar (WordPress). La home trae la programación de todos los
complejos y de todo el mes ya embebida en el HTML: cada película es un
`<div class='funcion-item' data-funciones='[...]'>` con un JSON de funciones

  {"complejo": "184", "dia": "11.23.2026", "dia_real": "11.24.2026", "hora": "00:10",
   "formato": "2D", "idioma": "Subtitulada", "tech_code": "1", "pelicula_id": "240", "id": "228416"}

Las fechas van como MM.DD.AAAA. `dia` es el día de la grilla y `dia_real` la fecha calendario
real (en la trasnoche difieren), así que se usa `dia_real` con datetime.combine, sin correr la
fecha. La venta es online: el link se arma igual que en el JS de la home
(ventas.cinemultiplex.com.ar/funcion?df=complejo-pelicula-funcion-AAAAMMDD-tech).

La página de cada película (/peliculas/<slug>/) da la duración en minutos y la fecha de estreno,
que se usan como pistas para TMDB. Ver docs/fuentes.md.
"""

import html
import json
import re
import time as reloj
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from cartelera.schema import FuncionCruda
from cartelera.tiempo import TZ

URL_HOME = "https://multiplex.com.ar/"
URL_COMPRA = "https://ventas.cinemultiplex.com.ar/funcion?df={complejo}-{pelicula}-{funcion}-{fecha}{tech}"
PAUSA_SEGUNDOS = 1.0

RE_ITEM = re.compile(r"<div class='funcion-item[^']*'[^>]*?data-funciones='(\[.*?\])'>(.*?)</h4>", re.S)
RE_LINK = re.compile(r"href='(https://multiplex\.com\.ar/peliculas/[^']+)'")
RE_TITULO = re.compile(r"<h4[^>]*>([^<]*)$", re.S)


def items_de_home(texto: str) -> list[dict[str, str]]:
    """Cada película de la home: link a su ficha, título y el JSON de funciones tal como viene."""
    items = []
    for crudo, cabecera in RE_ITEM.findall(texto):
        link = RE_LINK.search(cabecera)
        titulo = RE_TITULO.search(cabecera)
        items.append({
            "url": link.group(1) if link else None,
            "titulo": html.unescape(titulo.group(1)).strip() if titulo else None,
            "funciones": html.unescape(crudo),
        })
    return items


def ficha(texto: str) -> dict[str, str | None]:
    """Duración y estreno de la página de una película (los rótulos van seguidos de su valor)."""
    sin_codigo = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", texto, flags=re.S)
    lineas = [html.unescape(x).strip() for x in re.split(r"<[^>]+>", sin_codigo)]
    lineas = [x for x in lineas if x]
    datos: dict[str, str | None] = {"duracion": None, "estreno": None}
    for i, x in enumerate(lineas[:-1]):
        if x == "Duración" and datos["duracion"] is None:
            datos["duracion"] = lineas[i + 1]
        elif x == "Estreno" and datos["estreno"] is None:
            datos["estreno"] = lineas[i + 1]
    return datos


class Multiplex:
    def __init__(self, complejo: str):
        self.complejo = complejo
        self.avisos: list[str] = []

    def fetch(self, cliente: httpx.Client, hoy: date, dias: int) -> dict[str, Any]:
        r = cliente.get(URL_HOME)
        r.raise_for_status()
        items = items_de_home(r.text)
        if not items:
            raise ValueError("la home de Multiplex no trae películas con data-funciones (¿cambió el HTML?)")
        desde, hasta = hoy, hoy + timedelta(days=dias)
        propios = []
        for item in items:
            funciones = [
                f for f in json.loads(item["funciones"])
                if f.get("complejo") == self.complejo and desde <= _fecha(f["dia_real"]) < hasta
            ]
            if not funciones:
                continue
            propios.append({**item, "funciones": funciones, "ficha": None})
        for item in propios:
            if item["url"]:
                reloj.sleep(PAUSA_SEGUNDOS)
                rf = cliente.get(item["url"])
                if rf.status_code == 200:
                    item["ficha"] = ficha(rf.text)
        return {"complejo": self.complejo, "url": URL_HOME, "desde": desde.isoformat(),
                "hasta": hasta.isoformat(), "peliculas": propios}

    def parse(self, crudo: dict[str, Any], hoy: date) -> list[FuncionCruda]:
        self.avisos = []
        desde, hasta = date.fromisoformat(crudo["desde"]), date.fromisoformat(crudo["hasta"])
        funciones: list[FuncionCruda] = []
        for peli in crudo["peliculas"]:
            if not peli.get("titulo"):
                self.avisos.append(f"película sin título en la home ({peli.get('url')})")
                continue
            datos = peli.get("ficha") or {}
            duracion = _entero(datos.get("duracion"))
            anio = _anio(datos.get("estreno"))
            for f in peli["funciones"]:
                if f.get("complejo") != self.complejo:
                    continue
                dia = _fecha(f["dia_real"])
                if not (desde <= dia < hasta):
                    continue
                hora = datetime.strptime(f["hora"].strip(), "%H:%M").time()
                tech = str(f.get("tech_code") or "").strip()
                funciones.append(FuncionCruda(
                    fecha_hora=datetime.combine(dia, hora, tzinfo=TZ),
                    titulo=" ".join(peli["titulo"].split()),
                    url_entradas=URL_COMPRA.format(
                        complejo=f["complejo"], pelicula=f["pelicula_id"], funcion=f["id"],
                        fecha=dia.strftime("%Y%m%d"), tech=f"-{tech}" if tech else ""),
                    modo_venta="online",
                    fuente_url=peli.get("url") or crudo["url"],
                    anio_fuente=anio,
                    duracion_fuente=duracion,
                ))
        return funciones


def _fecha(mm_dd_aaaa: str) -> date:
    return datetime.strptime(mm_dd_aaaa.strip(), "%m.%d.%Y").date()


def _entero(v: Any) -> int | None:
    m = re.fullmatch(r"\s*(\d{1,3})\s*", str(v or ""))
    n = int(m.group(1)) if m else 0
    return n if n > 0 else None


def _anio(estreno: Any) -> int | None:
    # "15/01/2026" -> 2026: es el estreno en la Argentina, sirve como pista de año para TMDB.
    m = re.fullmatch(r"\s*\d{1,2}/\d{1,2}/(\d{4})\s*", str(estreno or ""))
    return int(m.group(1)) if m else None
