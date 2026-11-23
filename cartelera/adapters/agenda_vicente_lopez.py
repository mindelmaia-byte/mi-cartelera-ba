"""Agenda presencial de Lumiton (Municipio de Vicente López): Cine York, Centro Cultural Munro y Lumiton.

Fuente: https://lumiton.ar/agenda-presencial/ (WordPress). La página lista todos los eventos
próximos de las tres salas, uno por `<article>`:

  <article class="... post-33739 evento ... tipo-proyecciones tipo-cine"
           data-date="2026-11-25" data-locations='["cine-york"]'>
    ... miércoles 25 nov 20:30hs ... Cine York ... <h3>VLADIMIR EN BUENOS AIRES EN 35 MM</h3>
    <a href="https://lumiton.ar/evento/...">Ver más</a>

- Solo se toman los eventos con la clase `tipo-cine`: la agenda también tiene charlas, talleres
  y visitas guiadas, que no llevan ese tipo.
- `data-date` es la fecha del evento (la misma que muestra la ficha) y no hay funciones de
  trasnoche, así que se usa datetime.combine.
- Director, año y duración salen de la API REST del mismo sitio (campos ACF del tipo `evento`):
  /wp-json/wp/v2/evento?include=<ids>. Se usan como pistas para TMDB solo si tienen el formato
  esperado ("87 min", "1969"); "duración total aprox. 110 min" o "2022 - 2026" (programas de
  cortos) quedan vacíos.
- Las funciones son gratis: "Entrada no arancelada. Acceso por orden de llegada."
Ver docs/fuentes.md.
"""

import html
import re
import time as reloj
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from cartelera.schema import FuncionCruda
from cartelera.tiempo import TZ

URL_AGENDA = "https://lumiton.ar/agenda-presencial/"
URL_API = "https://lumiton.ar/wp-json/wp/v2/evento"
PAUSA_SEGUNDOS = 1.0

RE_ARTICULO = re.compile(r"<article\b(.*?)>(.*?)</article>", re.S)


def articulos(pagina: str) -> list[dict[str, Any]]:
    """Los eventos de la agenda, con los datos que trae el propio HTML."""
    salida = []
    for attrs, cuerpo in RE_ARTICULO.findall(pagina):
        clases = re.search(r'class="([^"]*)"', attrs)
        fecha = re.search(r'data-date="(\d{4}-\d{2}-\d{2})"', attrs)
        lugares = re.search(r"data-locations='\[([^\]]*)\]'", attrs)
        hora = re.search(r"\b(\d{1,2}:\d{2})\s*hs", cuerpo)
        titulo = re.search(r"<h\d[^>]*>(.*?)</h\d>", cuerpo, re.S)
        link = re.search(r'href="(https://lumiton\.ar/evento/[^"]+)"', cuerpo)
        lista_clases = clases.group(1).split() if clases else []
        ident = next((c[5:] for c in lista_clases if re.fullmatch(r"post-\d+", c)), None)
        salida.append({
            "id": ident,
            "tipos": [c[5:] for c in lista_clases if c.startswith("tipo-")],
            "fecha": fecha.group(1) if fecha else None,
            "hora": hora.group(1) if hora else None,
            "lugares": re.findall(r'"([^"]+)"', lugares.group(1)) if lugares else [],
            "titulo": " ".join(html.unescape(re.sub(r"<[^>]+>", " ", titulo.group(1))).split()) if titulo else None,
            "url": link.group(1) if link else None,
        })
    return salida


class AgendaVicenteLopez:
    def __init__(self, lugar: str):
        self.lugar = lugar  # slug de data-locations: "cine-york", "centro-cultural-munro", "lumiton"
        self.avisos: list[str] = []

    def fetch(self, cliente: httpx.Client, hoy: date, dias: int) -> dict[str, Any]:
        r = cliente.get(URL_AGENDA)
        r.raise_for_status()
        eventos = articulos(r.text)
        if not eventos:
            raise ValueError("la agenda de Lumiton no trae eventos (¿cambió el HTML?)")
        ids = sorted({e["id"] for e in eventos if e["id"] and "cine" in e["tipos"]})
        fichas: dict[str, Any] = {}
        if ids:
            reloj.sleep(PAUSA_SEGUNDOS)
            ra = cliente.get(URL_API, params={"include": ",".join(ids), "per_page": 100,
                                              "_fields": "id,link,title,acf"})
            ra.raise_for_status()
            fichas = {str(x["id"]): x.get("acf") or {} for x in ra.json()}
        return {"url": URL_AGENDA, "hoy": hoy.isoformat(), "dias": dias, "eventos": eventos, "fichas": fichas}

    def parse(self, crudo: dict[str, Any], hoy: date) -> list[FuncionCruda]:
        self.avisos = []
        desde = date.fromisoformat(crudo["hoy"])
        hasta = desde + timedelta(days=crudo["dias"])
        funciones: list[FuncionCruda] = []
        for e in crudo["eventos"]:
            if self.lugar not in e["lugares"] or "cine" not in e["tipos"]:
                continue
            if not (e["fecha"] and e["hora"] and e["titulo"]):
                self.avisos.append(f"evento sin fecha, hora o título: {e.get('url')}")
                continue
            dia = date.fromisoformat(e["fecha"])
            if not (desde <= dia < hasta):
                continue
            ficha = crudo["fichas"].get(e["id"] or "", {})
            titulo, ciclo = separar_formato(e["titulo"])
            funciones.append(FuncionCruda(
                fecha_hora=datetime.combine(dia, datetime.strptime(e["hora"], "%H:%M").time(), tzinfo=TZ),
                titulo=titulo,
                ciclo=ciclo,
                modo_venta="gratis",
                fuente_url=e["url"] or crudo["url"],
                director_fuente=_texto(ficha.get("director")),
                anio_fuente=_anio(ficha.get("ano")),
                duracion_fuente=_duracion(ficha.get("duracion")),
            ))
        return funciones


def separar_formato(titulo: str) -> tuple[str, str | None]:
    """ "VLADIMIR EN BUENOS AIRES EN 35 MM" -> ("VLADIMIR EN BUENOS AIRES", "En 35 mm"): el formato
    de proyección no es parte del título (y con él, TMDB no lo encuentra)."""
    m = re.fullmatch(r"(.+?)\s+EN\s+(16|35|70)\s*MM", titulo, re.I)
    return (m.group(1), f"En {m.group(2)} mm") if m else (titulo, None)


def _texto(v: Any) -> str | None:
    v = " ".join(str(v or "").split())
    return v or None


def _anio(v: Any) -> int | None:
    m = re.fullmatch(r"\s*(\d{4})\s*", str(v or ""))
    return int(m.group(1)) if m else None


def _duracion(v: Any) -> int | None:
    m = re.fullmatch(r"\s*(\d{1,3})\s*min\.?\s*", str(v or ""), re.I)
    return int(m.group(1)) if m else None
