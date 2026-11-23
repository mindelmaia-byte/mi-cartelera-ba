"""Cinemark (cadena comercial). En la cartelera: Cinemark Palermo, Abasto y Dot.

Fuente: https://www.cinemark.com.ar (Next.js). La página de cada complejo pide los datos a un
JSON interno, que necesita el encabezado `country: AR` (sin él responde 500 "Country undefined"):

  GET https://bff.cinemark.com.ar/api/cinema/showtimes?theater=733
    -> {"data": [{"movieName", "corporateId", "language": {"shortName": "SUB"}, "sessionFormat": "2D",
                  "sessionDateTime": "2026-11-23T16:35:00.000Z", "sessionDisplayDate": "2026-11-23",
                  "isLateNightSession": false, "sessionId", ...}]}
  GET https://bff.cinemark.com.ar/api/cinema/movies?theater=733
    -> {"data": [{"corporateId", "slug", "title", "runTime", "openingDate", ...}]}

- `sessionDateTime` trae una "Z", pero es la hora LOCAL de Buenos Aires: la página muestra esa
  misma hora (16:35). Además ya es la fecha calendario real: la trasnoche del 15/12 a las 00:00
  figura como 2026-12-16T00:00 con sessionDisplayDate 2026-12-15. Por eso se toma tal cual, sin
  correr la fecha ni convertir de UTC.
- `movieName` puede venir cortado ("LOS JUEGOS DEL HAMBRE: AMANECER"); el título completo, la
  duración y el estreno salen de /movies, por `corporateId`.
- Los horarios del sitio no son links: se compra desde la página de la película.
Ver docs/fuentes.md.
"""

import time as reloj
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from cartelera.schema import FuncionCruda
from cartelera.tiempo import TZ

URL_API = "https://bff.cinemark.com.ar/api/cinema"
URL_PELICULA = "https://www.cinemark.com.ar/pelicula/{slug}"
ENCABEZADOS = {"country": "AR"}
PAUSA_SEGUNDOS = 1.0


class Cinemark:
    def __init__(self, theater: str):
        self.theater = theater
        self.avisos: list[str] = []

    def fetch(self, cliente: httpx.Client, hoy: date, dias: int) -> dict[str, Any]:
        crudo: dict[str, Any] = {"theater": self.theater, "hoy": hoy.isoformat(), "dias": dias}
        for nombre in ("showtimes", "movies"):
            r = cliente.get(f"{URL_API}/{nombre}", params={"theater": self.theater}, headers=ENCABEZADOS)
            r.raise_for_status()
            datos = r.json().get("data")
            if not isinstance(datos, list):
                raise ValueError(f"Cinemark /{nombre}: respuesta sin 'data'")
            if nombre == "showtimes":
                # El crudo es el fixture: solo la ventana pedida (la API trae preventas de un mes).
                hasta = (hoy + timedelta(days=dias)).isoformat()
                datos = [s for s in datos if hoy.isoformat() <= s.get("sessionDateTime", "")[:10] < hasta]
            crudo[nombre] = datos
            reloj.sleep(PAUSA_SEGUNDOS)
        return crudo

    def parse(self, crudo: dict[str, Any], hoy: date) -> list[FuncionCruda]:
        self.avisos = []
        desde = date.fromisoformat(crudo["hoy"])
        hasta = desde + timedelta(days=crudo["dias"])
        peliculas = {m["corporateId"]: m for m in crudo["movies"]}
        funciones: list[FuncionCruda] = []
        for s in crudo["showtimes"]:
            if str(s.get("theaterId")) != self.theater:
                continue
            # "2026-11-23T16:35:00.000Z": hora local con una Z de más (ver arriba).
            local = datetime.strptime(s["sessionDateTime"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=TZ)
            if not (desde <= local.date() < hasta):
                continue
            peli = peliculas.get(s.get("corporateId"))
            if peli is None:
                self.avisos.append(f"función de {s.get('movieName')!r} sin película en /movies")
            titulo = (peli or {}).get("title") or s["movieName"]
            estreno = (peli or {}).get("openingDate") or ""
            funciones.append(FuncionCruda(
                fecha_hora=local,
                titulo=" ".join(titulo.split()),
                url_entradas=URL_PELICULA.format(slug=peli["slug"]) if peli and peli.get("slug") else None,
                modo_venta="online",
                fuente_url=f"{URL_API}/showtimes?theater={self.theater}",
                anio_fuente=int(estreno[:4]) if estreno[:4].isdigit() else None,
                duracion_fuente=(peli or {}).get("runTime") or None,
            ))
        return funciones
