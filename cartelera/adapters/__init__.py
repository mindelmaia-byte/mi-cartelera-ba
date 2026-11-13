"""Adaptadores, uno por cine. El nombre del módulo es el campo `adaptador` de config/cines.yaml."""

import importlib

from cartelera.adapters.base import Adaptador


def cargar_adaptador(nombre: str) -> Adaptador:
    modulo = importlib.import_module(f"cartelera.adapters.{nombre}")
    return modulo.ADAPTADOR
