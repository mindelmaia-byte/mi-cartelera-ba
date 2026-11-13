"""Cruce de películas con TMDB.

Regla de aceptación (nunca inventar datos):
  1. El título normalizado tiene que coincidir con el título original de TMDB o con alguna de
     sus traducciones o títulos alternativos.
  2. Si la fuente trae año: el año de TMDB tiene que estar a ±1.
     Si no trae año: tiene que coincidir el director.
     Sin año y sin director no hay forma de confirmar -> sin_match.
  3. Si las dos duraciones se conocen y difieren en más de 20 minutos, se descarta.
  4. Si sobrevive más de un candidato y el director no desempata -> ambiguo.
Si no hay match confiable los campos quedan vacíos y el motivo queda registrado.
"""

import time as reloj
from dataclasses import dataclass, field
from typing import Any

import httpx

from cartelera.texto import algun_director_coincide, normalizar

BASE = "https://api.themoviedb.org/3"
IDIOMA = "es-MX"
MAX_CANDIDATOS = 8
TOLERANCIA_ANIO = 1
TOLERANCIA_DURACION = 20
PREFERENCIA_TITULO = [("es", "AR"), ("es", "MX"), ("es", "ES")]


def clave_grabacion(path: str, params: dict[str, Any]) -> str:
    pares = sorted((k, str(v)) for k, v in params.items() if k != "api_key")
    return path + "?" + "&".join(f"{k}={v}" for k, v in pares)


class ClienteTMDB:
    def __init__(self, api_key: str, cliente: httpx.Client, grabacion: dict | None = None, pausa: float = 0.05):
        if not api_key:
            raise ValueError("falta TMDB_API_KEY (ver .env.example)")
        self.api_key = api_key
        self.cliente = cliente
        self.grabacion = grabacion
        self.pausa = pausa

    def _get(self, path: str, **params: Any) -> dict:
        r = self.cliente.get(BASE + path, params={**params, "api_key": self.api_key})
        r.raise_for_status()
        datos = r.json()
        if self.grabacion is not None:
            self.grabacion[clave_grabacion(path, params)] = datos
        if self.pausa:
            reloj.sleep(self.pausa)
        return datos

    def buscar(self, titulo: str, anio: int | None = None) -> list[dict]:
        params = {"query": titulo, "language": IDIOMA, "include_adult": "false"}
        if anio is not None:
            params["year"] = anio
        return self._get("/search/movie", **params)["results"]

    def detalle(self, tmdb_id: int) -> dict:
        return self._get(f"/movie/{tmdb_id}", language=IDIOMA,
                         append_to_response="credits,translations,alternative_titles")


@dataclass
class Pistas:
    titulo: str
    titulo_original: str | None = None
    anio: int | None = None
    director: str | None = None
    duracion: int | None = None


@dataclass
class Match:
    estado: str  # ok | sin_match | ambiguo
    motivo: str
    tmdb_id: int | None = None
    titulo: str | None = None
    titulo_original: str | None = None
    anio: int | None = None
    director: str | None = None
    duracion: int | None = None
    candidatos: list[int] = field(default_factory=list)

    @property
    def letterboxd_url(self) -> str | None:
        return f"https://letterboxd.com/tmdb/{self.tmdb_id}/" if self.tmdb_id else None


def resolver(tmdb: ClienteTMDB, p: Pistas) -> Match:
    consultas = list(dict.fromkeys(t for t in (p.titulo_original, p.titulo) if t))
    buscados = {normalizar(t) for t in consultas}

    descartes: list[str] = []
    revisados: set[int] = set()
    aprobados, hubo = _ronda(tmdb, p, consultas, buscados, None, revisados, descartes)
    if not aprobados and p.anio is not None:
        # Títulos muy comunes ("Freud") dejan la película buscada fuera de los primeros
        # resultados: segunda ronda filtrando la búsqueda por año.
        aprobados, hubo2 = _ronda(tmdb, p, consultas, buscados, p.anio, revisados, descartes)
        hubo = hubo or hubo2
    if not hubo:
        return Match("sin_match", "TMDB no devolvió resultados")

    if len(aprobados) > 1 and p.director:
        con_director = [a for a in aprobados if algun_director_coincide(p.director, a[1])]
        if con_director:
            aprobados = con_director
    if len(aprobados) == 1:
        det, directores = aprobados[0]
        return Match(
            "ok",
            "año" if p.anio is not None else "director",
            tmdb_id=det["id"],
            titulo=_titulo_preferido(det),
            titulo_original=det.get("original_title"),
            anio=_anio(det),
            director=", ".join(directores) or None,
            duracion=det.get("runtime") or None,
        )
    if aprobados:
        ids = [a[0]["id"] for a in aprobados]
        return Match("ambiguo", f"{len(ids)} candidatos posibles", candidatos=ids)
    motivo = "; ".join(descartes) if descartes else "ningún resultado coincide en título"
    return Match("sin_match", motivo)


def _ronda(tmdb: ClienteTMDB, p: Pistas, consultas: list[str], buscados: set[str], anio: int | None,
           revisados: set[int], descartes: list[str]) -> tuple[list[tuple[dict, list[str]]], bool]:
    """Una búsqueda + revisión de candidatos. Devuelve (aprobados, hubo_resultados)."""
    resultados: dict[int, dict] = {}
    for q in consultas:
        for r in tmdb.buscar(q, anio)[:MAX_CANDIDATOS]:
            resultados.setdefault(r["id"], r)
    nuevos = [i for i in resultados if i not in revisados]

    # Primero los que ya coinciden por título en la búsqueda; si ninguno aprueba, mirar las
    # traducciones de los demás (una película puede figurar solo con su título original).
    directos = [i for i in nuevos if buscados & {normalizar(resultados[i].get("title")),
                                                  normalizar(resultados[i].get("original_title"))}]
    resto = [i for i in nuevos if i not in directos][:5]
    aprobados = _revisar(tmdb, p, directos, buscados, revisados, descartes)
    if not aprobados:
        aprobados = _revisar(tmdb, p, resto, buscados, revisados, descartes)
    return aprobados, bool(resultados)


def _revisar(tmdb: ClienteTMDB, p: Pistas, ids: list[int], buscados: set[str], revisados: set[int],
             descartes: list[str]) -> list[tuple[dict, list[str]]]:
    aprobados: list[tuple[dict, list[str]]] = []
    for tmdb_id in ids:
        revisados.add(tmdb_id)
        det = tmdb.detalle(tmdb_id)
        if not buscados & _titulos(det):
            continue
        directores = _directores(det)
        anio = _anio(det)
        if p.anio is not None:
            if anio is None or abs(anio - p.anio) > TOLERANCIA_ANIO:
                descartes.append(f"{tmdb_id}: año {anio} vs {p.anio}")
                continue
        elif p.director:
            if not algun_director_coincide(p.director, directores):
                descartes.append(f"{tmdb_id}: director {directores} vs {p.director!r}")
                continue
        else:
            descartes.append(f"{tmdb_id}: sin año ni director para confirmar")
            continue
        dur = det.get("runtime") or None
        if p.duracion and dur and abs(dur - p.duracion) > TOLERANCIA_DURACION:
            descartes.append(f"{tmdb_id}: duración {dur} vs {p.duracion}")
            continue
        aprobados.append((det, directores))
    return aprobados


def _titulos(det: dict) -> set[str]:
    t = {normalizar(det.get("title")), normalizar(det.get("original_title"))}
    for tr in (det.get("translations") or {}).get("translations", []):
        t.add(normalizar((tr.get("data") or {}).get("title")))
    for alt in (det.get("alternative_titles") or {}).get("titles", []):
        t.add(normalizar(alt.get("title")))
    t.discard("")
    return t


def _directores(det: dict) -> list[str]:
    crew = (det.get("credits") or {}).get("crew", [])
    return list(dict.fromkeys(c["name"] for c in crew if c.get("job") == "Director"))


def _anio(det: dict) -> int | None:
    fecha = det.get("release_date") or ""
    return int(fecha[:4]) if fecha[:4].isdigit() else None


def _titulo_preferido(det: dict) -> str:
    traducciones = (det.get("translations") or {}).get("translations", [])
    for idioma, pais in PREFERENCIA_TITULO:
        for tr in traducciones:
            titulo = (tr.get("data") or {}).get("title")
            if tr.get("iso_639_1") == idioma and tr.get("iso_3166_1") == pais and titulo:
                return titulo
    return det.get("title") or det.get("original_title")
