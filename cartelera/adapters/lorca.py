"""Lorca (Av. Corrientes 1428).

Fuente: https://cinelorca.wixsite.com/cine-lorca/current-production (sitio Wix del cine,
sección "HORARIOS"). La programación semanal se publica como UNA IMAGEN ("Programación válida
desde el 12/11 al 18/11 2026"), con los mismos horarios todos los días, sala, duración,
calificación e idioma. No hay texto ni JSON: la imagen se estructura con Claude
(cartelera/extraccion.py, igual que los PDF de la Lugones) y se guarda junto al resultado.
No hay venta online: entradas en boletería. Ver docs/fuentes.md.
"""

import base64
import logging
import re
import time as reloj
from datetime import date
from typing import Any

import httpx

from cartelera import extraccion
from cartelera.schema import FuncionCruda

log = logging.getLogger(__name__)

CINE_ID = "lorca"
URL_HORARIOS = "https://cinelorca.wixsite.com/cine-lorca/current-production"
# Imágenes subidas por el sitio (los íconos de redes de Wix no tienen el prefijo "<6 hex>_").
PATRON_IMAGEN = re.compile(r"https://static\.wixstatic\.com/media/[0-9a-f]{6}_[0-9a-f]{32}~mv2\.(?:jpe?g|png)")
EXTENSIONES = {"image/jpeg": ".jpg", "image/png": ".png"}
PAUSA_SEGUNDOS = 1.0


class Lorca:
    def __init__(self) -> None:
        self.avisos: list[str] = []

    def fetch(self, cliente: httpx.Client, hoy: date, dias: int) -> dict[str, Any]:
        r = cliente.get(URL_HORARIOS)
        r.raise_for_status()
        urls = buscar_imagenes(r.text)
        if not urls:
            raise ValueError("la página de horarios no tiene la imagen de la grilla (¿cambió el sitio?)")
        imagenes = []
        for url in urls:
            reloj.sleep(PAUSA_SEGUNDOS)
            img = cliente.get(url)
            img.raise_for_status()
            tipo = img.headers.get("content-type", "").split(";")[0]
            if tipo not in EXTENSIONES:
                raise ValueError(f"{url} no es una imagen ({tipo})")
            imagenes.append({"url": url, "tipo": tipo, "b64": base64.b64encode(img.content).decode()})
        return {"url_pagina": URL_HORARIOS, "imagenes": imagenes}

    def parse(self, crudo: dict[str, Any], hoy: date) -> list[FuncionCruda]:
        self.avisos = []
        funciones: list[FuncionCruda] = []
        for img in crudo["imagenes"]:
            datos = base64.b64decode(img["b64"])
            registro = extraccion.cargar(CINE_ID, datos)
            if registro is None:
                ruta = extraccion.guardar_pendiente(CINE_ID, datos, img["url"], "Grilla semanal",
                                                    ext=EXTENSIONES[img["tipo"]])
                self.avisos.append(f"imagen de grilla nueva sin extraer -> {ruta}")
                continue
            validas, errores = extraccion.validar(registro.resultado)
            self.avisos.extend(errores)
            for peli, f in validas:
                funciones.append(FuncionCruda(
                    fecha_hora=f.fecha_hora(),
                    titulo=peli.titulo,
                    titulo_original=peli.titulo_original,
                    ciclo=peli.ciclo,
                    url_entradas=None,
                    modo_venta="boleteria",
                    fuente_url=crudo["url_pagina"],
                    director_fuente=peli.director,
                    anio_fuente=peli.anio,
                    duracion_fuente=peli.duracion_min,
                    idioma_fuente=peli.idioma,
                ))
        return funciones


def buscar_imagenes(html: str) -> list[str]:
    return list(dict.fromkeys(PATRON_IMAGEN.findall(html)))


ADAPTADOR = Lorca()
