"""Showcase (cadena comercial). En la cartelera: Showcase Belgrano (Monroe 1655).

Fuente: https://www.todoshowcase.com (sitio institucional) y su boletería, entradas.todoshowcase.com
(plataforma Voy al Cine). No hay un listado por complejo:

  1. La home enlaza cada película como entradas.todoshowcase.com/showcase/pelicula?filmid=N.
  2. La ficha pide sus funciones a un JSON:
       GET https://api.voyalcine.net/films/{filmid}/tree/showcase
       -> {"name", "days": {"2026-11-23": [{"id": 14, "name": "Showcase Belgrano", "ewaveId",
            "formats": [{"formatDescription": "2D-Doblada", "performances": [{"showTime": "16:50"}]}]}]}}
  3. La ficha HTML trae título original, director y duración ("<li><strong>Director:</strong> …"),
     que se usan como pistas para TMDB. Solo se pide para las películas que dan en Belgrano.

Trasnoche: el 2026-11-23 no había funciones antes de las 06:00 para confirmar si "days" es el día
de la grilla o la fecha real; se aplica la regla general (tiempo.combinar). Revisarlo cuando aparezca
un caso. Ver docs/fuentes.md.
"""

import html
import re
import time as reloj
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from cartelera.schema import FuncionCruda
from cartelera.texto import normalizar
from cartelera.tiempo import combinar

URL_HOME = "https://www.todoshowcase.com/"
URL_ARBOL = "https://api.voyalcine.net/films/{id}/tree/showcase"
URL_FICHA = "https://entradas.todoshowcase.com/showcase/pelicula?filmid={id}"
PAUSA_SEGUNDOS = 0.5

RE_FILM = re.compile(r"entradas\.todoshowcase\.com/showcase/pelicula\?filmid=(\d+)")
RE_DATO = re.compile(r"<li><strong>\s*([^<:]+?)\s*:?\s*</strong>\s*([^<]*)", re.S)


def ficha(pagina: str) -> dict[str, str]:
    """Los datos de la lista de la ficha: {"Título Original": "...", "Director": "...", ...}."""
    return {html.unescape(k).strip(): " ".join(html.unescape(v).split())
            for k, v in RE_DATO.findall(pagina) if v.strip()}


class Showcase:
    def __init__(self, complejo: int):
        self.complejo = complejo  # "id" del complejo en el árbol (14 = Showcase Belgrano)
        self.avisos: list[str] = []

    def fetch(self, cliente: httpx.Client, hoy: date, dias: int) -> dict[str, Any]:
        r = cliente.get(URL_HOME)
        r.raise_for_status()
        ids = list(dict.fromkeys(RE_FILM.findall(r.text)))
        if not ids:
            raise ValueError("la home de Showcase no enlaza películas (¿cambió el HTML?)")
        desde, hasta = hoy.isoformat(), (hoy + timedelta(days=dias)).isoformat()
        peliculas = []
        for film in ids:
            reloj.sleep(PAUSA_SEGUNDOS)
            ra = cliente.get(URL_ARBOL.format(id=film))
            if ra.status_code != 200:
                continue
            arbol = ra.json()
            dias_propios = {
                dia: [c for c in complejos if c.get("id") == self.complejo]
                for dia, complejos in (arbol.get("days") or {}).items() if desde <= dia < hasta
            }
            dias_propios = {d: c for d, c in dias_propios.items() if c}
            if not dias_propios:
                continue
            reloj.sleep(PAUSA_SEGUNDOS)
            rf = cliente.get(URL_FICHA.format(id=film))
            peliculas.append({"filmid": film, "nombre": arbol.get("name"), "dias": dias_propios,
                              "ficha": ficha(rf.text) if rf.status_code == 200 else {}})
        return {"complejo": self.complejo, "hoy": hoy.isoformat(), "dias": dias, "peliculas": peliculas}

    def parse(self, crudo: dict[str, Any], hoy: date) -> list[FuncionCruda]:
        self.avisos = []
        desde = date.fromisoformat(crudo["hoy"])
        hasta = desde + timedelta(days=crudo["dias"])
        funciones: list[FuncionCruda] = []
        for p in crudo["peliculas"]:
            if not p.get("nombre"):
                self.avisos.append(f"película {p.get('filmid')} sin nombre")
                continue
            datos = p.get("ficha") or {}
            original = datos.get("Título Original")
            for dia_txt, complejos in p["dias"].items():
                dia = date.fromisoformat(dia_txt)
                if not (desde <= dia < hasta):
                    continue
                for c in complejos:
                    if c.get("id") != crudo["complejo"]:
                        continue
                    url = URL_FICHA.format(id=p["filmid"]) + (f"&house_id={c['ewaveId']}" if c.get("ewaveId") else "")
                    for formato in c.get("formats") or []:
                        for f in formato.get("performances") or []:
                            hora = datetime.strptime(f["showTime"].strip(), "%H:%M").time()
                            funciones.append(FuncionCruda(
                                fecha_hora=combinar(dia, hora),
                                titulo=" ".join(p["nombre"].split()),
                                titulo_original=original if original and normalizar(original) != normalizar(p["nombre"]) else None,
                                url_entradas=url,
                                modo_venta="online",
                                fuente_url=URL_ARBOL.format(id=p["filmid"]),
                                director_fuente=datos.get("Director") or None,
                                duracion_fuente=_minutos(datos.get("Duración")),
                            ))
        return funciones


def _minutos(v: str | None) -> int | None:
    m = re.fullmatch(r"\s*(\d{1,3})\s*(?:minutos|min)?\.?\s*", v or "", re.I)
    return int(m.group(1)) if m and int(m.group(1)) > 0 else None
