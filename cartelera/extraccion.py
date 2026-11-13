"""Extracción estructurada de programaciones en texto libre (Sala Lugones, Museo del Cine).

Flujo:
  1. El adaptador consigue el texto (PDF o nota web).
  2. `cargar(cine, texto)` busca una extracción ya hecha para ESE texto (clave = hash del texto).
     Si el texto no cambió, no se vuelve a extraer.
  3. Si no hay, `guardar_pendiente` deja el texto en data/extracciones/<cine>/pendientes/ y el
     cine conserva sus funciones anteriores. Mientras no haya crédito de API, la extracción la
     hace Claude en una sesión de Claude Code siguiendo INSTRUCCIONES, y se guarda con
     `python -m cartelera extracciones guardar ...`. Con ANTHROPIC_API_KEY se automatizará
     (pendiente para la entrega).
  4. `validar` descarta toda función cuyo día de la semana no coincida con la fecha resuelta
     o que caiga fuera del período declarado. No corrige nada.

Cada extracción se guarda junto con el texto original: <hash>.txt + <hash>.json.
"""

import hashlib
import json
from datetime import date, datetime, time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from cartelera.registro import RAIZ
from cartelera.texto import normalizar
from cartelera.tiempo import ahora, combinar, iso

DIR_EXTRACCIONES = RAIZ / "data" / "extracciones"

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

INSTRUCCIONES = """\
Extraé las funciones de cine de este texto (programa de un ciclo o nota de programación).
- Una entrada por película; cada función con el día de la semana TAL COMO APARECE en el texto,
  la fecha completa resuelta (YYYY-MM-DD) y la hora (HH:MM, 24 h).
- El texto suele dar solo "Jueves 18 / A las 15 horas": el mes y el año salen del texto
  introductorio ("Del jueves 20 de febrero al ...") o del contexto. Si una línea da varias horas
  ("A las 15 y 21 horas") son dos funciones.
- La fecha es la del día bajo el que aparece la función, aunque la hora sea de madrugada.
- titulo: el título en castellano como lo publica el texto. titulo_original: el que aparece
  entre paréntesis si es distinto. pais, anio, director (después de "Dirección:"),
  duracion_min (p. ej. "(84’; DCP)" -> 84). ciclo: solo si el texto lo indica por película
  (p. ej. lo que sigue a la barra en "Sábado 5 de septiembre a las 16 h | Cine argentino").
- No inventes: si un dato no está en el texto, null. No incluyas actividades que no sean
  proyecciones (charlas, talleres) salvo que se proyecte una película.
- periodo_desde / periodo_hasta: el rango que declara el texto, si lo declara.
"""


class FuncionExtraida(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dia_semana_texto: str = Field(description="Día de la semana como aparece en el texto, p. ej. 'Jueves'")
    fecha: date
    hora: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    def fecha_hora(self) -> datetime:
        return combinar(self.fecha, time.fromisoformat(self.hora))


class PeliculaExtraida(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str
    titulo_original: str | None = None
    pais: str | None = None
    anio: int | None = None
    director: str | None = None
    duracion_min: int | None = None
    ciclo: str | None = None
    funciones: list[FuncionExtraida]


class ResultadoExtraccion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    periodo_desde: date | None = None
    periodo_hasta: date | None = None
    peliculas: list[PeliculaExtraida]


class Registro(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cine: str
    hash: str
    fuente_url: str | None
    titulo_fuente: str | None
    extraido_por: str
    extraido_en: str
    resultado: ResultadoExtraccion


def hash_texto(texto: str) -> str:
    return hashlib.sha256(texto.strip().encode("utf-8")).hexdigest()[:16]


def _dir(cine: str) -> Path:
    return DIR_EXTRACCIONES / cine


def cargar(cine: str, texto: str) -> Registro | None:
    ruta = _dir(cine) / f"{hash_texto(texto)}.json"
    if not ruta.exists():
        return None
    return Registro.model_validate_json(ruta.read_text(encoding="utf-8"))


def guardar_pendiente(cine: str, texto: str, fuente_url: str | None, titulo: str | None) -> Path:
    h = hash_texto(texto)
    d = _dir(cine) / "pendientes"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{h}.txt").write_text(texto, encoding="utf-8")
    (d / f"{h}.meta.json").write_text(
        json.dumps({"cine": cine, "hash": h, "fuente_url": fuente_url, "titulo_fuente": titulo},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return (d / f"{h}.txt").relative_to(RAIZ)


def guardar(cine: str, texto: str, resultado: ResultadoExtraccion, *, fuente_url: str | None,
            titulo_fuente: str | None, extraido_por: str) -> Path:
    """Guarda texto original + extracción y borra el pendiente, si había."""
    h = hash_texto(texto)
    d = _dir(cine)
    d.mkdir(parents=True, exist_ok=True)
    registro = Registro(cine=cine, hash=h, fuente_url=fuente_url, titulo_fuente=titulo_fuente,
                        extraido_por=extraido_por, extraido_en=iso(ahora()), resultado=resultado)
    (d / f"{h}.txt").write_text(texto, encoding="utf-8")
    ruta = d / f"{h}.json"
    ruta.write_text(registro.model_dump_json(indent=1), encoding="utf-8")
    for p in (d / "pendientes").glob(f"{h}.*"):
        p.unlink()
    return ruta


def pendientes(cine: str | None = None) -> list[Path]:
    base = _dir(cine) if cine else DIR_EXTRACCIONES
    return sorted(base.glob("**/pendientes/*.txt"))


def validar(r: ResultadoExtraccion) -> tuple[list[tuple[PeliculaExtraida, FuncionExtraida]], list[str]]:
    """Devuelve las funciones válidas y la lista de errores de las descartadas."""
    validas, errores = [], []
    for peli in r.peliculas:
        for f in peli.funciones:
            dia_texto = normalizar(f.dia_semana_texto)
            esperado = DIAS[f.fecha.weekday()]
            if dia_texto != esperado:
                errores.append(f"{peli.titulo} {f.fecha} {f.hora}: dice «{f.dia_semana_texto}» pero esa fecha es {esperado}")
                continue
            if r.periodo_desde and f.fecha < r.periodo_desde or r.periodo_hasta and f.fecha > r.periodo_hasta:
                errores.append(f"{peli.titulo} {f.fecha} {f.hora}: fuera del período {r.periodo_desde}..{r.periodo_hasta}")
                continue
            validas.append((peli, f))
    return validas, errores
