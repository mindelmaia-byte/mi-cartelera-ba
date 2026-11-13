"""MALBA (Av. Figueroa Alcorta 3415).

Fuentes, ambas oficiales y leídas con un parser determinístico (sin IA, ver docs/fuentes.md:
el robots.txt de malba.org.ar bloquea a los bots de IA y la usuaria eligió no usar Claude acá):

  1. Funciones: el catálogo JSON de la boletería oficial, https://ticketsmalba.liit.ar/api/catalog
     -> items con vertical == "cine", cada uno con sessions [{date, time, sourceId, sourceRoom}].
     El link de compra es https://ticketsmalba.liit.ar/?cine=1&m=<película>&e=<función>.
  2. Pistas para TMDB: la "Ficha técnica" de cada evento listado en https://malba.org.ar/cine/
     ("Dirección: ...", "Argentina–Uruguay, 2026. 97′."). El evento se cruza con el catálogo por
     el id de película (m=...) de su botón "Comprar entradas". Eventos con varias películas
     (festivales, cineclub) no aportan ficha.
"""

import logging
import re
import time as reloj
from datetime import date, datetime
from html import unescape
from typing import Any

import httpx
from selectolax.lexbor import LexborHTMLParser

from cartelera.schema import FuncionCruda
from cartelera.texto import normalizar
from cartelera.tiempo import TZ

log = logging.getLogger(__name__)

URL_CATALOGO = "https://ticketsmalba.liit.ar/api/catalog"
URL_CINE = "https://malba.org.ar/cine/"
URL_COMPRA = "https://ticketsmalba.liit.ar/?cine=1&m={pelicula}&e={funcion}"
PAUSA_SEGUNDOS = 1.5

RE_EVENTO = re.compile(r"https://malba\.org\.ar/evento/[a-z0-9\-]+/")
# Boletería nueva (ticketsmalba.liit.ar/?...m=) y vieja (malba.liit.com.ar/decidir/index.php?...m=).
RE_TICKET = re.compile(r"(?:ticketsmalba\.liit\.ar|malba\.liit\.com\.ar/decidir)/[^\"'\s<>]*?[?&]m=(\d+)")
# "Dirección: X." / "Dirección y guion: X." / "Dirección y guión\n X" (no "Dirección de fotografía")
RE_DIRECCION = re.compile(r"^\s*Direcci[oó]n(?:\s+y\s+gui[oó]n)?\s*(?::[ \t]*|\n\s*)([^\n]+?)\.?\s*$", re.MULTILINE)
RE_ANIO_DURACION = re.compile(r"\b(1[89]\d\d|20\d\d)\.\s*(\d{2,3})\s*[′'’]")
RE_PREFIJO_CICLO = re.compile(r"^([a-záéíóúñ]+):\s*(.+)$")  # "nocturna: PELÍCULA SORPRESA"


class Malba:
    def fetch(self, cliente: httpx.Client, hoy: date, dias: int) -> dict[str, Any]:
        r = cliente.get(URL_CATALOGO)
        r.raise_for_status()
        catalogo = r.json()
        cine = [i for i in catalogo.get("items", []) if i.get("vertical") == "cine"]
        if not cine:
            raise ValueError("el catálogo de la boletería no tiene funciones de cine (¿cambió la API?)")
        for item in cine:  # los tipos de entrada y precios no hacen falta
            for s in item.get("sessions", []):
                s.pop("ticketTypes", None)

        reloj.sleep(PAUSA_SEGUNDOS)
        pagina = cliente.get(URL_CINE)
        pagina.raise_for_status()
        eventos = []
        for url in eventos_de_cine(pagina.text):
            reloj.sleep(PAUSA_SEGUNDOS)
            ev = cliente.get(url)
            if ev.status_code != 200:
                log.warning("malba: %s respondió %s", url, ev.status_code)
                continue
            eventos.append(resumir_evento(url, ev.text))
        return {"url_catalogo": URL_CATALOGO, "catalogo_cine": cine, "eventos": eventos}

    def parse(self, crudo: dict[str, Any], hoy: date) -> list[FuncionCruda]:
        fichas = fichas_por_pelicula(crudo["eventos"])
        por_titulo = directores_de_programaciones(crudo["eventos"])
        funciones: list[FuncionCruda] = []
        for item in crudo["catalogo_cine"]:
            titulo, ciclo = limpiar_titulo(item["title"])
            ficha = fichas.get(str(item["sourceId"])) or por_titulo.get(normalizar(titulo), {})
            # El título de la página del evento está bien escrito ("El tren fluvial" vs "TREN FLUVIAL").
            titulo = ficha.get("titulo") or titulo
            for s in item.get("sessions", []):
                # El catálogo usa la fecha calendario real: "Viernes 13 a las 24:00" figura como
                # 2026-11-14 00:00. No se aplica la regla de trasnoche.
                fecha_hora = datetime.combine(date.fromisoformat(s["date"]),
                                              datetime.strptime(s["time"], "%H:%M").time(), tzinfo=TZ)
                funciones.append(FuncionCruda(
                    fecha_hora=fecha_hora,
                    titulo=titulo,
                    ciclo=ciclo,
                    url_entradas=URL_COMPRA.format(pelicula=item["sourceId"], funcion=s["sourceId"]),
                    modo_venta="online",
                    fuente_url=crudo["url_catalogo"],
                    director_fuente=ficha.get("director"),
                    anio_fuente=ficha.get("anio"),
                    duracion_fuente=ficha.get("duracion"),
                ))
        return funciones


def eventos_de_cine(html: str) -> list[str]:
    """Eventos listados en /cine/ después del link a la grilla mensual (antes están los menús)."""
    corte = html.find("malba-cine-")
    return list(dict.fromkeys(RE_EVENTO.findall(html[corte if corte >= 0 else 0:])))


def resumir_evento(url: str, html: str) -> dict[str, Any]:
    """Texto visible del evento + ids de película de sus links de compra (para no guardar 200 KB de HTML)."""
    doc = LexborHTMLParser(html)
    for nodo in doc.css("script, style, noscript, header, footer, nav"):
        nodo.decompose()
    main = doc.css_first("main") or doc.body
    texto = re.sub(r"\n\s*\n+", "\n", main.text(separator="\n")) if main else ""
    compra = [a.attributes.get("href") or "" for a in (main.css("a") if main else [])
              if "comprar" in a.text().lower()]
    h1 = main.css_first("h1") if main else None
    peliculas = sorted(set(RE_TICKET.findall(unescape(html))))
    return {"url": url, "titulo": " ".join(h1.text().split()) if h1 else None, "texto": texto,
            "peliculas": peliculas, "links_compra": compra}


def fichas_por_pelicula(eventos: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    fichas: dict[str, dict[str, Any]] = {}
    for ev in eventos:
        ids = set(ev["peliculas"]) | {i for link in ev.get("links_compra", []) for i in RE_TICKET.findall(link)}
        if len(ids) != 1:  # festival, cineclub o sin venta: no se puede atribuir la ficha
            continue
        [pelicula] = ids
        texto = ev["texto"]
        i = texto.find("Ficha técnica")
        bloque = texto[i:] if i >= 0 else ""
        ficha: dict[str, Any] = {"url_evento": ev["url"], "titulo": ev.get("titulo")}
        if m := RE_DIRECCION.search(bloque):
            ficha["director"] = " ".join(m.group(1).split())
        if m := RE_ANIO_DURACION.search(bloque):
            ficha["anio"], ficha["duracion"] = int(m.group(1)), int(m.group(2))
        fichas[pelicula] = ficha
    return fichas


RE_HORA = re.compile(r"^\d{1,2}:\d{2}$")


def directores_de_programaciones(eventos: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Festivales y cineclubes listan "19:00 / La prisionera / , de Henri-Georges Clouzot".
    Devuelve {título normalizado: {"director": ...}} para cruzar con el catálogo por título."""
    resultado: dict[str, dict[str, Any]] = {}
    for ev in eventos:
        texto = ev["texto"]
        i = texto.find("Programación")
        if i < 0:
            continue
        # " ".join(split()) también normaliza espacios duros (", de\xa0Boom Boom Kid").
        lineas = [" ".join(l.split()) for l in texto[i:].splitlines() if l.strip()]
        for k, linea in enumerate(lineas[:-2]):
            if not RE_HORA.match(linea):
                continue
            titulo, siguiente = lineas[k + 1], lineas[k + 2]
            if siguiente.startswith(", de "):
                director = siguiente.removeprefix(", de ").replace("(*)", "").strip()
                resultado.setdefault(normalizar(titulo), {"director": director})
    return resultado


def limpiar_titulo(titulo: str) -> tuple[str, str | None]:
    """'nocturna: ¿QUÉ CLASE DE JOVEN...?,' -> ('¿QUÉ CLASE DE JOVEN...?', 'Nocturna')."""
    t = " ".join(titulo.split()).rstrip(" ,;")
    if m := RE_PREFIJO_CICLO.match(t):
        return m.group(2).rstrip(" ,;"), m.group(1).capitalize()
    return t, None


ADAPTADOR = Malba()
