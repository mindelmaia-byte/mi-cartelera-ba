"""Línea de comandos: python -m cartelera <comando>."""

import argparse
import json
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from cartelera import db
from cartelera.adapters import cargar_adaptador
from cartelera.adapters.base import nuevo_cliente
from cartelera.enriquecer import enriquecer
from cartelera.ingest import DIAS, ingestar
from cartelera.registro import RAIZ, cargar_cines
from cartelera.tiempo import ahora, iso
from cartelera.tmdb import ClienteTMDB

DIAS_SEMANA = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def main(argv: list[str] | None = None) -> int:
    load_dotenv(RAIZ / ".env")
    p = argparse.ArgumentParser(prog="cartelera")
    p.add_argument("--db", default=str(db.RUTA_DB), help="ruta de la base SQLite")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="comando", required=True)

    pi = sub.add_parser("ingest", help="baja la programación y reemplaza las funciones futuras")
    pi.add_argument("--cine", action="append", help="solo este cine (se puede repetir)")
    pi.add_argument("--dias", type=int, default=DIAS)
    pi.add_argument("--sin-tmdb", action="store_true", help="no cruzar con TMDB al final")

    pe = sub.add_parser("enriquecer", help="cruza las películas con TMDB")
    pe.add_argument("--forzar", action="store_true", help="vuelve a consultar todas, incluso las resueltas")
    pe.add_argument("--grabar", type=Path, help="guarda las respuestas de TMDB en este JSON (para fixtures)")

    px = sub.add_parser("extracciones", help="textos (PDF/notas) que esperan extracción estructurada")
    sx = px.add_subparsers(dest="accion", required=True)
    sx.add_parser("pendientes", help="lista los textos sin extraer")
    sg = sx.add_parser("guardar", help="valida y guarda una extracción hecha a mano o por Claude")
    sg.add_argument("texto", type=Path, help="el pendiente (data/extracciones/<cine>/pendientes/<hash>.txt o .jpg)")
    sg.add_argument("resultado", type=Path, help="JSON con el esquema ResultadoExtraccion")
    sg.add_argument("--por", required=True, help="quién extrajo, p. ej. 'claude-opus-5-5 (sesión de Claude Code)'")

    pl = sub.add_parser("listar", help="muestra la cartelera guardada en consola")
    pl.add_argument("--cine", action="append")
    pl.add_argument("--dias", type=int, default=DIAS)

    pf = sub.add_parser("fixture", help="guarda lo que publica un cine en tests/fixtures/<cine>/")
    pf.add_argument("cine")
    pf.add_argument("--dias", type=int, default=7)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    # La consola de Windows no siempre es UTF-8.
    sys.stdout.reconfigure(encoding="utf-8")

    cines = cargar_cines()
    if getattr(args, "cine", None) and args.comando != "fixture":
        desconocidos = set(args.cine) - {c.id for c in cines}
        if desconocidos:
            p.error(f"cines desconocidos: {sorted(desconocidos)}")
        cines = [c for c in cines if c.id in args.cine]

    if args.comando == "ingest":
        return _ingest(args, cines)
    if args.comando == "listar":
        return _listar(args, cines)
    if args.comando == "enriquecer":
        return _enriquecer(args)
    if args.comando == "extracciones":
        return _extracciones(args)
    return _fixture(args, cines)


def _extracciones(args) -> int:
    from cartelera import extraccion

    if args.accion == "pendientes":
        lista = extraccion.pendientes()
        for p in lista:
            meta = json.loads(p.with_suffix(".meta.json").read_text(encoding="utf-8"))
            print(f"{p.relative_to(RAIZ)}  [{meta['cine']}] {meta['titulo_fuente']}  ({meta['fuente_url']})")
        print(f"{len(lista)} pendientes.")
        return 0

    meta = json.loads(args.texto.with_suffix(".meta.json").read_text(encoding="utf-8"))
    original = extraccion.leer_original(args.texto)
    resultado = extraccion.ResultadoExtraccion.model_validate_json(args.resultado.read_text(encoding="utf-8"))
    validas, errores = extraccion.validar(resultado)
    for e in errores:
        print(f"  descartada: {e}")
    ruta = extraccion.guardar(meta["cine"], original, resultado, fuente_url=meta["fuente_url"],
                              titulo_fuente=meta["titulo_fuente"], extraido_por=args.por,
                              ext=args.texto.suffix)
    print(f"Guardado {ruta.relative_to(RAIZ)}: {len(resultado.peliculas)} películas, "
          f"{len(validas)} funciones válidas, {len(errores)} descartadas.")
    return 0


def _ingest(args, cines) -> int:
    con = db.conectar(args.db)
    resultados = ingestar(con, cines, dias=args.dias)
    if not resultados:
        print("No hay cines con adaptador para correr.")
        return 0
    print(f"Ingest {iso(ahora())}")
    for r in resultados:
        marca = {"ok": "OK   ", "error": "ERROR", "sin_funciones": "AVISO"}[r.estado]
        detalle = f"  ({r.error})" if r.error else ""
        print(f"  {marca} {r.cine_id:<20} {r.n_funciones:>4} funciones futuras{detalle}")
        for a in r.avisos:
            print(f"        aviso: {a}")
    fallidos = [r for r in resultados if r.estado != "ok"]
    print(f"{len(resultados) - len(fallidos)} ok, {len(fallidos)} con problemas")
    if not args.sin_tmdb:
        if os.environ.get("TMDB_API_KEY"):
            _correr_tmdb(con)
        else:
            print("TMDB: sin TMDB_API_KEY en .env, no se cruzaron películas.")
    return 1 if fallidos else 0


def _correr_tmdb(con, forzar: bool = False, grabacion: dict | None = None) -> None:
    import httpx

    with httpx.Client(timeout=20.0) as cliente:
        tmdb = ClienteTMDB(os.environ.get("TMDB_API_KEY", ""), cliente, grabacion=grabacion)
        r = enriquecer(con, tmdb, forzar=forzar)
    print(f"TMDB: {r.consultadas} consultadas · {r.ok} ok · {r.sin_match} sin match · "
          f"{r.ambiguo} ambiguas · {r.errores} errores")


def _enriquecer(args) -> int:
    con = db.conectar(args.db)
    grabacion: dict | None = None
    if args.grabar:
        grabacion = json.loads(args.grabar.read_text(encoding="utf-8")) if args.grabar.exists() else {}
    _correr_tmdb(con, forzar=args.forzar, grabacion=grabacion)
    if args.grabar:
        args.grabar.parent.mkdir(parents=True, exist_ok=True)
        args.grabar.write_text(json.dumps(grabacion, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        print(f"Grabadas {len(grabacion)} respuestas en {args.grabar}")
    return 0


def _listar(args, cines) -> int:
    con = db.conectar(args.db)
    desde = ahora()
    hasta = (desde.date() + timedelta(days=args.dias)).isoformat()
    ids = [c.id for c in cines]
    marcas = ",".join("?" * len(ids))
    filas = con.execute(
        f"""SELECT f.*, c.nombre AS cine_nombre, p.match_estado, p.titulo AS titulo_tmdb, p.director,
                   p.anio, p.duracion_min, p.tmdb_id
            FROM funciones f JOIN cines c ON c.id = f.cine_id
            LEFT JOIN peliculas p ON p.id = f.pelicula_id
            WHERE f.fecha_hora >= ? AND f.fecha_hora < ? AND f.cine_id IN ({marcas})
            ORDER BY f.fecha_hora, c.nombre, f.titulo""",
        (iso(desde), hasta, *ids),
    ).fetchall()
    dia_actual = None
    for f in filas:
        dia = date.fromisoformat(f["fecha_hora"][:10])
        if dia != dia_actual:
            dia_actual = dia
            print(f"\n{DIAS_SEMANA[dia.weekday()]} {dia:%d/%m}")
        if f["match_estado"] == "ok":
            extra = f"{f['titulo_tmdb']} · {f['director']} · {f['anio']} · {f['duracion_min'] or '?'} min · tmdb {f['tmdb_id']}"
        else:
            extra = f"TMDB: {f['match_estado'] or 'sin cruzar'}"
        print(f"  {f['fecha_hora'][11:16]}  {f['cine_nombre']:<14} {f['titulo']:<32} [{extra}]")
    print(f"\n{len(filas)} funciones.")
    for c in con.execute(f"SELECT * FROM cines WHERE id IN ({marcas}) AND adaptador IS NOT NULL", ids):
        print(f"{c['nombre']}: última actualización {c['ultima_actualizacion'] or 'nunca'}"
              + (f" · último intento {c['ultimo_estado']}: {c['ultimo_error']}" if c["ultimo_estado"] not in (None, "ok") else ""))
    return 0


def _fixture(args, cines) -> int:
    cine = next((c for c in cines if c.id == args.cine), None)
    if cine is None or not cine.adaptador:
        print(f"{args.cine}: no existe o no tiene adaptador")
        return 1
    adaptador = cargar_adaptador(cine.adaptador)
    with nuevo_cliente() as cliente:
        crudo = adaptador.fetch(cliente, ahora().date(), args.dias)
    destino = RAIZ / "tests" / "fixtures" / cine.id / f"crudo-{ahora().date().isoformat()}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(crudo, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Guardado {destino.relative_to(RAIZ)} ({destino.stat().st_size // 1024} KB)")
    return 0
