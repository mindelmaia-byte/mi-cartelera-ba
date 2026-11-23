"""Ingest: corre cada adaptador por separado y reemplaza las funciones futuras de su cine.

Reglas:
  - Un adaptador que falla no corta el resto: se registra el error y se conservan sus funciones.
  - Si un adaptador devuelve 0 funciones pero el cine tenía funciones futuras, se trata como
    sospechoso (estado `sin_funciones`): no se borra nada. Probablemente cambió la web.
  - Correrlo dos veces seguidas deja la base igual (idempotente).
"""

import logging
import sqlite3
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import httpx

from cartelera import db
from cartelera import pistas as pistas_manuales
from cartelera.adapters import cargar_adaptador
from cartelera.adapters.base import Adaptador, nuevo_cliente
from cartelera.schema import Cine
from cartelera.tiempo import ahora

log = logging.getLogger(__name__)

DIAS = 10


@dataclass
class Resultado:
    cine_id: str
    estado: str  # ok | error | sin_funciones
    n_funciones: int
    error: str | None = None
    avisos: list[str] = field(default_factory=list)  # problemas parciales (no cortan el cine)


def ingestar(
    con: sqlite3.Connection,
    cines: list[Cine],
    *,
    dias: int = DIAS,
    momento: datetime | None = None,
    cliente: httpx.Client | None = None,
    cargar: Callable[[str], Adaptador] = cargar_adaptador,
    extraer_pendientes: Callable[[str], list[str]] | None = None,
    pistas: dict | None = None,
) -> list[Resultado]:
    """`extraer_pendientes(cine_id)`: si se pasa (hay clave de API), se llama cuando un cine deja
    textos o imágenes sin extraer, y después se vuelve a parsear ese cine con lo ya extraído."""
    momento = momento or ahora()
    hoy: date = momento.date()
    pistas = pistas_manuales.cargar() if pistas is None else pistas
    db.sincronizar_cines(con, cines)
    propio = cliente is None
    cliente = cliente or nuevo_cliente()
    resultados: list[Resultado] = []
    try:
        for cine in cines:
            if not cine.adaptador:
                continue
            resultados.append(_ingestar_cine(con, cine, cliente, hoy, dias, momento, cargar, extraer_pendientes, pistas))
    finally:
        if propio:
            cliente.close()
    return resultados


def _ingestar_cine(
    con: sqlite3.Connection,
    cine: Cine,
    cliente: httpx.Client,
    hoy: date,
    dias: int,
    momento: datetime,
    cargar: Callable[[str], Adaptador],
    extraer_pendientes: Callable[[str], list[str]] | None = None,
    pistas: dict | None = None,
) -> Resultado:
    informe_api: list[str] = []
    try:
        adaptador = cargar(cine.adaptador)
        crudo: Any = adaptador.fetch(cliente, hoy, dias)
        funciones = adaptador.parse(crudo, hoy)
        sin_extraer = any("sin extraer" in a for a in getattr(adaptador, "avisos", []) or [])
        if sin_extraer and extraer_pendientes is not None:
            informe_api = [f"API: {linea}" for linea in extraer_pendientes(cine.id)]
            funciones = adaptador.parse(crudo, hoy)  # ahora con lo recién extraído
        funciones = pistas_manuales.aplicar(cine.id, funciones, pistas or {})
    except Exception as e:  # noqa: BLE001 - un cine roto no puede cortar el ingest
        log.debug("detalle del error en %s:\n%s", cine.id, traceback.format_exc())
        error = f"{type(e).__name__}: {e}"
        n = db.contar_futuras(con, cine.id, momento)
        db.registrar_resultado(con, cine.id, momento, "error", n, error)
        return Resultado(cine.id, "error", n, error)

    avisos = informe_api + list(getattr(adaptador, "avisos", []) or [])
    previas = db.contar_futuras(con, cine.id, momento)
    if not [f for f in funciones if f.fecha_hora >= momento] and previas > 0:
        error = f"el adaptador no devolvió funciones y había {previas}; no se borró nada"
        db.registrar_resultado(con, cine.id, momento, "sin_funciones", previas, error, avisos)
        return Resultado(cine.id, "sin_funciones", previas, error, avisos)

    n = db.reemplazar_futuras(con, cine, funciones, momento)
    db.registrar_resultado(con, cine.id, momento, "ok", n, None, avisos)
    return Resultado(cine.id, "ok", n, None, avisos)
