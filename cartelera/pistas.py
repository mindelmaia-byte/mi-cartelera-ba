"""Pistas manuales para TMDB: datos que el cine publica, pero no en un formato que lee el adaptador.

Ejemplo: Cacodelphia pone el director de las películas del ciclo SOY solo en el póster (una imagen),
no en su API. Las pistas viven en config/pistas.yaml, una por cine + título, con la fuente anotada:

  - cine: cacodelphia
    titulo: PLATA QUEMADA           # como lo devuelve el adaptador (se compara normalizado)
    director: Marcelo Piñeyro
    fuente: póster del cine (ciclo SOY), confirmado el 2026-11-23

Reglas:
  - Solo completan campos vacíos (`director_fuente`, `anio_fuente`); nunca pisan lo que trae la web.
  - Son pistas, igual que las de la web: TMDB tiene que confirmar el match con sus reglas de siempre.
  - Cada pista dice de dónde salió. Nunca se cargan datos que el cine no publica.
"""

from pathlib import Path
from typing import Any

import yaml

from cartelera.registro import RAIZ
from cartelera.schema import FuncionCruda
from cartelera.texto import normalizar

RUTA_PISTAS = RAIZ / "config" / "pistas.yaml"
CAMPOS = {"director": "director_fuente", "anio": "anio_fuente"}


def cargar(ruta: Path = RUTA_PISTAS) -> dict[tuple[str, str], dict[str, Any]]:
    if not ruta.exists():
        return {}
    filas = yaml.safe_load(ruta.read_text(encoding="utf-8")) or []
    pistas: dict[tuple[str, str], dict[str, Any]] = {}
    for p in filas:
        if not p.get("fuente"):
            raise ValueError(f"config/pistas.yaml: la pista de {p.get('titulo')!r} no dice de dónde salió (fuente)")
        pistas[(p["cine"], normalizar(p["titulo"]))] = {k: p[k] for k in CAMPOS if p.get(k)}
    return pistas


def aplicar(cine_id: str, funciones: list[FuncionCruda],
            pistas: dict[tuple[str, str], dict[str, Any]]) -> list[FuncionCruda]:
    salida = []
    for f in funciones:
        p = pistas.get((cine_id, normalizar(f.titulo)))
        if p:
            cambios = {CAMPOS[k]: v for k, v in p.items() if getattr(f, CAMPOS[k]) in (None, "")}
            if cambios:
                f = f.model_copy(update=cambios)
        salida.append(f)
    return salida
