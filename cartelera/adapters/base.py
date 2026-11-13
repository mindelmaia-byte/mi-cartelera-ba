"""Interfaz común de los adaptadores.

Cada adaptador separa la red del parseo:
  - fetch(cliente, hoy, dias) -> crudo   : baja lo que publica el cine; el resultado tiene que
                                           ser serializable a JSON (se guarda como fixture).
  - parse(crudo, hoy)         -> funciones: función pura, se testea contra el fixture.
"""

from datetime import date
from typing import Any, Protocol

import httpx

from cartelera.schema import FuncionCruda

USER_AGENT = "cartelera-ba/0.1 (proyecto educativo; lectura una vez por dia)"


def nuevo_cliente() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9"},
        timeout=httpx.Timeout(20.0),
        follow_redirects=True,
    )


class Adaptador(Protocol):
    def fetch(self, cliente: httpx.Client, hoy: date, dias: int) -> Any: ...

    def parse(self, crudo: Any, hoy: date) -> list[FuncionCruda]: ...
