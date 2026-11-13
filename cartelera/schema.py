"""Esquemas de datos.

`Funcion` es el esquema público del proyecto (ver CLAUDE.md). Los adaptadores no lo arman
directamente: devuelven `FuncionCruda` (lo que sale de la web del cine) y el ingest completa
cine / direccion / es_comercial desde el registro (config/cines.yaml).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

ModoVenta = Literal["online", "boleteria", "gratis"]


class Cine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    nombre: str
    direccion: str | None
    verificada: bool
    tanda: int
    es_comercial: bool
    adaptador: str | None


class FuncionCruda(BaseModel):
    """Lo que devuelve un adaptador. Los campos *_fuente son pistas para el cruce con TMDB:
    vienen de la web del cine, no se muestran como dato verificado."""

    model_config = ConfigDict(extra="forbid")

    fecha_hora: datetime
    titulo: str
    titulo_original: str | None = None
    ciclo: str | None = None
    url_entradas: str | None = None
    modo_venta: ModoVenta
    fuente_url: str
    director_fuente: str | None = None
    anio_fuente: int | None = None
    duracion_fuente: int | None = None
    idioma_fuente: str | None = None  # código ISO 639-1 del idioma original ("en", "it"), si la fuente lo da

    @field_validator("fecha_hora")
    @classmethod
    def _con_zona(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("fecha_hora tiene que tener zona horaria")
        return v

    @field_validator("titulo")
    @classmethod
    def _titulo_no_vacio(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("titulo vacío")
        return v


class Funcion(BaseModel):
    """Esquema público de una función."""

    model_config = ConfigDict(extra="forbid")

    cine: str
    direccion: str | None
    fecha_hora: datetime
    titulo: str
    titulo_original: str | None
    ciclo: str | None
    url_entradas: str | None
    modo_venta: ModoVenta
    es_comercial: bool
