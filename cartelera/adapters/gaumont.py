"""Gaumont (Espacio INCAA, Av. Rivadavia 1635).

Fuente: https://www.cinegaumont.ar (plataforma de venta Cinexo, Next.js). La página pide la
grilla de cada día a un JSON interno:

  GET https://apifront.cinexo.com.ar/mobile/consultas/peliculas/PeliculasConFuncionesYHorarios
      ?idComplejo=372001&fecha=DD/MM/YYYY

  -> {"success": true, "data": {"datos": [película...], "funciones": [{codPelicula, hora, ...}]}}

`datos` lista todas las películas del complejo; `funciones` son las de ese día y apuntan a la
película por `codPelicula` = `peliculas_codigo`. La venta es online desde la página de cada
película. Ver docs/fuentes.md.
"""

import logging
import re
import time as reloj
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from cartelera.schema import FuncionCruda
from cartelera.tiempo import combinar

log = logging.getLogger(__name__)

ID_COMPLEJO = "372001"
URL_API = "https://apifront.cinexo.com.ar/mobile/consultas/peliculas/PeliculasConFuncionesYHorarios"
URL_PELICULA = "https://www.cinegaumont.ar/es-AR/programacion/{codigo}"
PAUSA_SEGUNDOS = 0.5


class Gaumont:
    def fetch(self, cliente: httpx.Client, hoy: date, dias: int) -> dict[str, Any]:
        crudo: dict[str, Any] = {"id_complejo": ID_COMPLEJO, "dias": []}
        for i in range(dias):
            dia = hoy + timedelta(days=i)
            params = {"idComplejo": ID_COMPLEJO, "fecha": dia.strftime("%d/%m/%Y")}
            r = cliente.get(URL_API, params=params)
            r.raise_for_status()
            crudo["dias"].append({"fecha": dia.isoformat(), "url": str(r.url), "respuesta": r.json()})
            reloj.sleep(PAUSA_SEGUNDOS)
        return crudo

    def parse(self, crudo: dict[str, Any], hoy: date) -> list[FuncionCruda]:
        funciones: list[FuncionCruda] = []
        for dia in crudo["dias"]:
            resp = dia["respuesta"]
            if not resp.get("success"):
                raise ValueError(f"la API respondió success=false para {dia['fecha']}: {resp.get('message')}")
            data = resp.get("data") or {}
            peliculas = {p["peliculas_codigo"]: p for p in data.get("datos") or []}
            fecha = date.fromisoformat(dia["fecha"])
            for f in data.get("funciones") or []:
                peli = peliculas.get(f["codPelicula"])
                if peli is None:
                    log.warning("gaumont %s: función %s sin película %s en 'datos'", fecha, f.get("_id"), f["codPelicula"])
                    continue
                hora = datetime.strptime(f["hora"].strip(), "%H:%M").time()
                funciones.append(
                    FuncionCruda(
                        fecha_hora=combinar(fecha, hora),
                        titulo=_limpiar_titulo(peli["peliculas_nombre"]),
                        url_entradas=URL_PELICULA.format(codigo=peli["peliculas_codigo"]),
                        modo_venta="online",
                        fuente_url=dia["url"],
                        director_fuente=_texto(peli.get("director")),
                        duracion_fuente=_entero(peli.get("peliculas_duracion")),
                    )
                )
        return funciones


def _limpiar_titulo(t: str) -> str:
    # La API publica "DESENTIERROS,LOS LIBROS..." sin espacio después de la coma.
    return re.sub(r",(?=[^\s\d])", ", ", " ".join(t.split()))


def _texto(v: Any) -> str | None:
    if v is None:
        return None
    v = " ".join(str(v).split())
    return v or None


def _entero(v: Any) -> int | None:
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


ADAPTADOR = Gaumont()
