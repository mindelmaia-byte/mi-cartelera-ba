"""Arma export.zip (inventado) a partir de la carpeta export/, con la misma estructura que el zip
real de Letterboxd: CSV en la raíz y subcarpetas deleted/, etc. Correr si cambian los CSV:
    uv run python tests/fixtures/letterboxd/armar_zip.py
"""
import zipfile
from pathlib import Path

aca = Path(__file__).parent
with zipfile.ZipFile(aca / "export.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted((aca / "export").rglob("*.csv")):
        z.write(f, f.relative_to(aca / "export").as_posix())
print("ok")
