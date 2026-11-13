"""Sala Lugones (Teatro San Martín, Av. Corrientes 1530).

Fuente: https://complejoteatral.gob.ar (WordPress). La página de la sala lista los ciclos de
cine vigentes y próximos como tarjetas, cada una con:
  - categoría "cine" y el nombre del ciclo (h2),
  - "Comprar localidades" -> entradasba.buenosaires.gob.ar (venta online),
  - "Descargar programa"  -> /programa/<slug>/, que redirige al PDF del ciclo.
El PDF lista cada película con sus funciones como "Jueves 18 / A las 15 horas", sin mes; el
mes sale del texto introductorio. Ese texto se estructura con Claude (cartelera/extraccion.py)
y se valida el día de la semana contra la fecha. Ver docs/fuentes.md.
"""

import io
import logging
import time as reloj
from datetime import date
from typing import Any

import httpx
from pypdf import PdfReader
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from cartelera import extraccion
from cartelera.schema import FuncionCruda
from cartelera.texto import normalizar

log = logging.getLogger(__name__)
# pypdf avisa que le falta fontTools para unas tipografías de los títulos; el texto sale bien igual.
logging.getLogger("pypdf").setLevel(logging.ERROR)

CINE_ID = "lugones"
URL_SALA = "https://complejoteatral.gob.ar/sala/sala-leopoldo-lugones/"
PAUSA_SEGUNDOS = 1.0


class Lugones:
    def __init__(self) -> None:
        self.avisos: list[str] = []

    # ---------- red ----------
    def fetch(self, cliente: httpx.Client, hoy: date, dias: int) -> dict[str, Any]:
        r = cliente.get(URL_SALA)
        r.raise_for_status()
        html = r.text
        tarjetas = leer_tarjetas(html)
        if not tarjetas:
            raise ValueError("la página de la sala no tiene tarjetas de cine (¿cambió el HTML?)")
        ciclos = []
        for t in tarjetas:
            if not t["url_programa"]:
                ciclos.append({**t, "url_pdf": None, "texto": None})
                continue
            reloj.sleep(PAUSA_SEGUNDOS)
            pdf = cliente.get(t["url_programa"])
            pdf.raise_for_status()
            if "pdf" not in pdf.headers.get("content-type", ""):
                raise ValueError(f"{t['url_programa']} no devolvió un PDF")
            ciclos.append({**t, "url_pdf": str(pdf.url), "texto": texto_de_pdf(pdf.content)})
        # El HTML de la sala va en el crudo para poder testear el descubrimiento contra el fixture.
        return {"url_sala": URL_SALA, "html_sala": html, "ciclos": ciclos}

    # ---------- parseo ----------
    def parse(self, crudo: dict[str, Any], hoy: date) -> list[FuncionCruda]:
        self.avisos = []
        funciones: list[FuncionCruda] = []
        for c in crudo["ciclos"]:
            if not c["texto"]:
                self.avisos.append(f"«{c['ciclo']}» ({c['fechas']}): todavía sin programa PDF")
                continue
            registro = extraccion.cargar(CINE_ID, c["texto"])
            if registro is None:
                ruta = extraccion.guardar_pendiente(CINE_ID, c["texto"], c["url_pdf"], c["ciclo"])
                self.avisos.append(f"«{c['ciclo']}»: PDF nuevo sin extraer -> {ruta}")
                continue
            validas, errores = extraccion.validar(registro.resultado)
            self.avisos.extend(f"«{c['ciclo']}»: {e}" for e in errores)
            una_sola = len(registro.resultado.peliculas) == 1
            for peli, f in validas:
                # Un "ciclo" de una sola película con el mismo nombre (un estreno) no es un ciclo.
                ciclo = None if una_sola and normalizar(peli.titulo) == normalizar(c["ciclo"]) else c["ciclo"]
                funciones.append(FuncionCruda(
                    fecha_hora=f.fecha_hora(),
                    titulo=peli.titulo,
                    titulo_original=peli.titulo_original,
                    ciclo=ciclo,
                    url_entradas=c["url_entradas"],
                    modo_venta="online" if c["url_entradas"] else "boleteria",
                    fuente_url=c["url_pdf"],
                    director_fuente=peli.director,
                    anio_fuente=peli.anio,
                    duracion_fuente=peli.duracion_min,
                ))
        return funciones


def leer_tarjetas(html: str) -> list[dict[str, Any]]:
    """Tarjetas de la página de la sala con categoría 'cine'."""
    tarjetas = []
    for col in HTMLParser(html).css("div.col_50"):
        categoria = col.css_first("span.category")
        titulo = col.css_first("h2")
        if not categoria or not titulo or normalizar(categoria.text()) != "cine":
            continue
        links = {normalizar(a.text()): a.attributes.get("href") for a in col.css("a")}
        texto = " ".join(col.text(separator=" ").split())
        tarjetas.append({
            "ciclo": " ".join(titulo.text().split()),
            "fechas": _fechas_de_tarjeta(texto),
            "url_info": links.get("info"),
            "url_entradas": links.get("comprar localidades"),
            "url_programa": links.get("descargar programa"),
        })
    return tarjetas


def _fechas_de_tarjeta(texto: str) -> str:
    """'... Del 12 al 25 de noviembre Sala Leopoldo Lugones ...' -> 'Del 12 al 25 de noviembre'."""
    for marca in ("Del ", "A partir del ", "El ", "Desde el "):
        i = texto.find(marca)
        if i >= 0:
            fin = texto.find(" Sala ", i)
            return texto[i: fin if fin > 0 else i + 80].strip()
    return ""


def texto_de_pdf(contenido: bytes) -> str:
    lector = PdfReader(io.BytesIO(contenido))
    paginas = [(p.extract_text() or "").strip() for p in lector.pages]
    return "\n\n".join(p for p in paginas if p)


ADAPTADOR = Lugones()
