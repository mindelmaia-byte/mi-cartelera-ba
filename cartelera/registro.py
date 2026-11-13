"""Lee el registro de cines (config/cines.yaml)."""

from pathlib import Path

import yaml

from cartelera.schema import Cine

RAIZ = Path(__file__).resolve().parent.parent
RUTA_CINES = RAIZ / "config" / "cines.yaml"


def cargar_cines(ruta: Path = RUTA_CINES) -> list[Cine]:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    cines = [Cine(**c) for c in datos["cines"]]
    ids = [c.id for c in cines]
    duplicados = {i for i in ids if ids.count(i) > 1}
    if duplicados:
        raise ValueError(f"ids de cine duplicados en {ruta.name}: {sorted(duplicados)}")
    for c in cines:
        if c.es_comercial != (c.tanda == 4):
            raise ValueError(f"{c.id}: es_comercial tiene que ser true solo en la tanda 4")
    return cines
