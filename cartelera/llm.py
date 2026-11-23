"""Extracción estructurada con la API de Claude (PDF de la Lugones, grilla en imagen del Lorca).

- Modelo: claude-opus-5-5, con structured outputs: `client.messages.parse(output_format=...)` y
  `response.parsed_output`, que ya viene validado contra el esquema.
- Si el modelo se niega (`stop_reason == "refusal"`), se reintenta una vez con claude-opus-4-8.
  Si también se niega, el texto queda pendiente: nunca se inventa una respuesta.
- La validación de negocio (día de la semana vs. fecha, período) sigue en `extraccion.validar`.
- Tope de gasto: solo se procesan MAX_POR_CORRIDA originales nuevos por corrida. Como cada texto
  se extrae una sola vez (caché por hash), en régimen son 1 o 2 llamadas por semana.
"""

import base64
import json
import logging
import os
from datetime import date
from pathlib import Path

import anthropic
from pydantic import BaseModel

from cartelera import extraccion
from cartelera.extraccion import INSTRUCCIONES, ResultadoExtraccion

log = logging.getLogger(__name__)

MODELO = "claude-opus-5-5"
MODELO_RESPALDO = "claude-opus-4-8"
MAX_POR_CORRIDA = int(os.environ.get("CARTELERA_MAX_EXTRACCIONES", "6"))
TIPOS_IMAGEN = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


# Esquema que ve el modelo: tipos simples (strings para fechas y horas). Después se convierte a
# ResultadoExtraccion, que valida formatos de fecha, hora e idioma con Pydantic.
class _Funcion(BaseModel):
    dia_semana_texto: str
    fecha: str
    hora: str


class _Pelicula(BaseModel):
    titulo: str
    titulo_original: str | None
    pais: str | None
    anio: int | None
    director: str | None
    duracion_min: int | None
    idioma: str | None
    ciclo: str | None
    funciones: list[_Funcion]


class _Resultado(BaseModel):
    periodo_desde: str | None
    periodo_hasta: str | None
    peliculas: list[_Pelicula]


class ErrorExtraccion(Exception):
    pass


def hay_api() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def _contenido(original: extraccion.Original, ext: str, contexto: str) -> list[dict]:
    pedido = {"type": "text", "text": f"{contexto}\n\nDevolvé solo el JSON con el esquema pedido."}
    if isinstance(original, bytes):
        tipo = TIPOS_IMAGEN.get(ext.lower())
        if not tipo:
            raise ErrorExtraccion(f"formato de imagen no soportado: {ext}")
        imagen = {"type": "image", "source": {"type": "base64", "media_type": tipo,
                                               "data": base64.standard_b64encode(original).decode("ascii")}}
        return [imagen, pedido]
    return [{"type": "text", "text": f"<texto>\n{original}\n</texto>"}, pedido]


def extraer(original: extraccion.Original, ext: str, contexto: str,
            cliente: anthropic.Anthropic | None = None) -> tuple[ResultadoExtraccion, str]:
    """Devuelve (resultado, modelo que respondió). Levanta ErrorExtraccion si no se pudo."""
    cliente = cliente or anthropic.Anthropic()
    mensajes = [{"role": "user", "content": _contenido(original, ext, contexto)}]
    for modelo in (MODELO, MODELO_RESPALDO):
        try:
            r = cliente.messages.parse(
                model=modelo,
                max_tokens=16000,
                system=INSTRUCCIONES,
                output_config={"effort": "high"},
                output_format=_Resultado,
                messages=mensajes,
            )
        except anthropic.APIConnectionError as e:
            raise ErrorExtraccion(f"sin conexión con la API: {e}") from e
        except anthropic.RateLimitError as e:
            raise ErrorExtraccion("límite de uso de la API (se reintenta en la próxima corrida)") from e
        except anthropic.APIStatusError as e:
            raise ErrorExtraccion(f"la API respondió {e.status_code}: {e.message}") from e
        if r.stop_reason == "refusal":
            log.warning("%s no quiso extraer este texto; pruebo con %s", modelo, MODELO_RESPALDO)
            continue
        if r.stop_reason == "max_tokens" or r.parsed_output is None:
            raise ErrorExtraccion("la respuesta quedó cortada o vacía")
        try:
            return ResultadoExtraccion.model_validate(r.parsed_output.model_dump()), modelo
        except ValueError as e:
            raise ErrorExtraccion(f"la respuesta no cumple el esquema: {e}") from e
    raise ErrorExtraccion("los dos modelos se negaron a extraer este texto")


def procesar_pendientes(cine: str | None = None, hoy: date | None = None,
                        cliente: anthropic.Anthropic | None = None, limite: int = MAX_POR_CORRIDA) -> list[str]:
    """Extrae con la API los originales pendientes (de un cine o de todos). Devuelve un informe por archivo."""
    informe = []
    hoy = hoy or date.today()
    for ruta in extraccion.pendientes(cine)[:limite]:
        meta = json.loads(ruta.with_suffix(".meta.json").read_text(encoding="utf-8"))
        original = extraccion.leer_original(ruta)
        contexto = (f"Cine: {meta['cine']}. Fuente: {meta.get('titulo_fuente') or 'programación'} "
                    f"({meta.get('fuente_url')}). Hoy es {hoy.isoformat()}: si el texto no dice el año, "
                    f"es el de las fechas más cercanas a hoy. Si la imagen o el texto no es una grilla o "
                    f"programación de funciones, devolvé peliculas vacío.")
        try:
            resultado, modelo = extraer(original, ruta.suffix, contexto, cliente)
        except ErrorExtraccion as e:
            informe.append(f"{Path(ruta).name}: sigue pendiente ({e})")
            continue
        validas, errores = extraccion.validar(resultado)
        extraccion.guardar(meta["cine"], original, resultado, fuente_url=meta.get("fuente_url"),
                           titulo_fuente=meta.get("titulo_fuente"), extraido_por=f"{modelo} (API)", ext=ruta.suffix)
        informe.append(f"{Path(ruta).name}: {len(resultado.peliculas)} películas, {len(validas)} funciones válidas"
                       + (f", {len(errores)} descartadas" if errores else ""))
    return informe
