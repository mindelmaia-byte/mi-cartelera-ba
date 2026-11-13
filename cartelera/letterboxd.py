"""RSS público de Letterboxd -> JSON simple.

Campos verificados el 2026-11-13: cada entrada de diario trae letterboxd:filmTitle, filmYear,
watchedDate, memberRating (opcional), rewatch, memberLike y tmdb:movieId. El feed tiene solo las
~50 entradas más recientes (más algunas listas, que se ignoran). Letterboxd no habilita CORS, por
eso el navegador lo pide a través de un proxy (api/letterboxd.mjs en Vercel; esta
misma lógica en `cartelera servir` para desarrollo).
"""

import re
import xml.etree.ElementTree as ET

import httpx

NS = {"letterboxd": "https://letterboxd.com", "tmdb": "https://themoviedb.org"}
RE_USUARIO = re.compile(r"^[A-Za-z0-9_]{1,40}$")


def usuario_valido(u: str) -> bool:
    return bool(RE_USUARIO.match(u or ""))


def parsear_rss(contenido: bytes) -> list[dict]:
    raiz = ET.fromstring(contenido)
    entradas = []
    for it in raiz.findall("./channel/item"):
        titulo = it.findtext("letterboxd:filmTitle", namespaces=NS)
        if not titulo:  # listas y otros ítems que no son una película vista
            continue
        anio = it.findtext("letterboxd:filmYear", namespaces=NS)
        tmdb = it.findtext("tmdb:movieId", namespaces=NS)
        puntaje = it.findtext("letterboxd:memberRating", namespaces=NS)
        entradas.append({
            "titulo": titulo.strip(),
            "anio": int(anio) if anio and anio.isdigit() else None,
            "tmdb_id": int(tmdb) if tmdb and tmdb.isdigit() else None,
            "fecha_vista": (it.findtext("letterboxd:watchedDate", namespaces=NS) or "").strip() or None,
            "puntaje": float(puntaje) if puntaje else None,
            "rewatch": (it.findtext("letterboxd:rewatch", namespaces=NS) or "").strip() == "Yes",
        })
    return entradas


def leer_rss(usuario: str, cliente: httpx.Client) -> dict:
    if not usuario_valido(usuario):
        raise ValueError("usuario inválido")
    r = cliente.get(f"https://letterboxd.com/{usuario}/rss/")
    if r.status_code == 404:
        raise LookupError("no existe ese usuario de Letterboxd (o su perfil no es público)")
    r.raise_for_status()
    return {"usuario": usuario, "entradas": parsear_rss(r.content)}
