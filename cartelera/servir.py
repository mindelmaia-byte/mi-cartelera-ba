"""Servidor local de desarrollo: sirve public/ e imita la función de Vercel.

  /                    -> public/
  /api/letterboxd      -> mismo JSON que api/letterboxd.mjs (Vercel)
  /pruebas/            -> tests/ (tests de la interfaz en el navegador: /pruebas/js/; no se publican)
  /_api/               -> api/ (para testear el parser JS del proxy contra el fixture)
"""

import json
import logging
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from cartelera.adapters.base import USER_AGENT
from cartelera.letterboxd import leer_rss
from cartelera.registro import RAIZ

log = logging.getLogger(__name__)
PUBLIC = RAIZ / "public"
MONTAJES = {"/pruebas/": RAIZ / "tests", "/_api/": RAIZ / "api"}


class Manejador(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".mjs": "text/javascript"}

    def translate_path(self, path: str) -> str:
        ruta = unquote(urlparse(path).path)
        for prefijo, base in MONTAJES.items():
            if ruta.startswith(prefijo):
                destino = (base / ruta.removeprefix(prefijo)).resolve()
                return str(destino) if destino.is_relative_to(base.resolve()) else str(base / "__no__")
        return super().translate_path(path)

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path == "/api/letterboxd":
            usuario = parse_qs(url.query).get("user", [""])[0]
            try:
                with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True) as c:
                    self._json(200, leer_rss(usuario, c))
            except ValueError as e:
                self._json(400, {"error": str(e)})
            except LookupError as e:
                self._json(404, {"error": str(e)})
            except httpx.HTTPError as e:
                self._json(502, {"error": f"Letterboxd: {e}"})
            return
        super().do_GET()

    def _json(self, status: int, cuerpo: dict) -> None:
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def servir(puerto: int = 8765) -> None:
    servidor = ThreadingHTTPServer(("127.0.0.1", puerto), partial(Manejador, directory=str(PUBLIC)))
    print(f"Sirviendo http://localhost:{puerto} (Ctrl+C para cortar)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
