"""CineArte Cacodelphia (Roque Sáenz Peña 1150).

Fuente: https://cineartecacodelphia.com.ar (aplicación Vue de la plataforma de venta adro.studio).
El sitio pide los datos a un JSON:

  GET https://apiv2.gaf.adro.studio/nowPlaying/86
    -> {"data": [{"pref": "9c41…", "nombre": "EL SONIDO AL CAER", "lenguaje": "Subt", ...}]}
  GET https://apiv2.gaf.adro.studio/movie/86/{pref}
    -> {"data": {"movie": {"nombre", "Duracion": "155", "FechaEstreno": {"date": "2026-11-17 …"}},
                 "showtimes": [{"fechaHora": {"date": "2026-11-23 16:10:00.000000", "timezone": "UTC"},
                                "mostrar": "1", ...}]}}

- `fechaHora` dice "UTC" pero es la hora LOCAL: la página muestra 16:10 para "16:10:00 UTC"
  (igual que Cinemark). Es fecha y hora completas, así que se toma tal cual (sin regla de trasnoche).
- "CICLO SOY - PLATA QUEMADA": lo que va antes del guion es el ciclo.
- `FechaEstreno` es cuándo el cine incorporó la película, no su año: los clásicos del ciclo figuran
  como 2026. Se usa como pista de año solo fuera de los ciclos.
- La compra es desde la página de la película (/pelicula/86/{pref}); los horarios no son links.
Ver docs/fuentes.md.
"""

import re
import time as reloj
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from cartelera.schema import FuncionCruda
from cartelera.tiempo import TZ

ID_CINE = "86"
URL_API = "https://apiv2.gaf.adro.studio"
URL_PELICULA = "https://cineartecacodelphia.com.ar/pelicula/86/{pref}"
PAUSA_SEGUNDOS = 0.5

RE_CICLO = re.compile(r"^\s*(CICLO\s+[^-–]+?)\s*[-–]\s*(.+)$", re.I)


def separar_ciclo(nombre: str) -> tuple[str, str | None]:
    """ "CICLO SOY - LA MUJER SIN CABEZA" -> ("LA MUJER SIN CABEZA", "Ciclo SOY")."""
    nombre = " ".join(nombre.split())
    m = RE_CICLO.match(nombre)
    if not m:
        return nombre, None
    ciclo = m.group(1)
    return m.group(2), "Ciclo" + ciclo[5:] if ciclo.upper().startswith("CICLO") else ciclo


class Cacodelphia:
    def __init__(self):
        self.avisos: list[str] = []

    def fetch(self, cliente: httpx.Client, hoy: date, dias: int) -> dict[str, Any]:
        r = cliente.get(f"{URL_API}/nowPlaying/{ID_CINE}")
        r.raise_for_status()
        cartelera = r.json().get("data")
        if not isinstance(cartelera, list):
            raise ValueError("Cacodelphia /nowPlaying: respuesta sin 'data'")
        peliculas = []
        for p in cartelera:
            reloj.sleep(PAUSA_SEGUNDOS)
            rm = cliente.get(f"{URL_API}/movie/{ID_CINE}/{p['pref']}")
            rm.raise_for_status()
            datos = rm.json().get("data") or {}
            movie = datos.get("movie") or {}
            peliculas.append({
                "pref": p["pref"],
                "nombre": movie.get("nombre") or p.get("nombre"),
                "duracion": movie.get("Duracion"),
                "estreno": ((movie.get("FechaEstreno") or {}).get("date") or "")[:10],
                "funciones": [{"fechaHora": (s.get("fechaHora") or {}).get("date"), "mostrar": s.get("mostrar"),
                               "lenguaje": s.get("lenguaje"), "formato": s.get("formato")}
                              for s in datos.get("showtimes") or []],
            })
        return {"hoy": hoy.isoformat(), "dias": dias, "peliculas": peliculas}

    def parse(self, crudo: dict[str, Any], hoy: date) -> list[FuncionCruda]:
        self.avisos = []
        desde = date.fromisoformat(crudo["hoy"])
        hasta = desde + timedelta(days=crudo["dias"])
        funciones: list[FuncionCruda] = []
        for p in crudo["peliculas"]:
            if not p.get("nombre"):
                self.avisos.append(f"película {p.get('pref')} sin nombre")
                continue
            titulo, ciclo = separar_ciclo(p["nombre"])
            estreno = p.get("estreno") or ""
            anio = int(estreno[:4]) if estreno[:4].isdigit() and ciclo is None else None
            duracion = int(p["duracion"]) if str(p.get("duracion") or "").isdigit() and int(p["duracion"]) > 0 else None
            for s in p["funciones"]:
                if s.get("mostrar") != "1" or not s.get("fechaHora"):
                    continue
                # "2026-11-23 16:10:00.000000" con timezone "UTC": es hora local (ver arriba).
                local = datetime.strptime(s["fechaHora"][:16], "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
                if not (desde <= local.date() < hasta):
                    continue
                funciones.append(FuncionCruda(
                    fecha_hora=local,
                    titulo=titulo,
                    ciclo=ciclo,
                    url_entradas=URL_PELICULA.format(pref=p["pref"]),
                    modo_venta="online",
                    fuente_url=f"{URL_API}/movie/{ID_CINE}/{p['pref']}",
                    anio_fuente=anio,
                    duracion_fuente=duracion,
                ))
        return funciones


ADAPTADOR = Cacodelphia()
