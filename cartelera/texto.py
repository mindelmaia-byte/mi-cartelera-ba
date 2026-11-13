"""Normalización de textos para comparar títulos y nombres."""

import re
import unicodedata


def normalizar(s: str | None) -> str:
    """'¿Querés ser mi hijo?' -> 'queres ser mi hijo'. Sin tildes, minúsculas, sin puntuación."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", " y ")
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def separar_nombres(s: str | None) -> list[str]:
    """'Enrique Fernández y César Charlone' -> ['enrique fernandez', 'cesar charlone']."""
    if not s:
        return []
    partes = re.split(r",|;|/|&|\s+y\s+|\s+e\s+", s, flags=re.IGNORECASE)
    return [n for n in (normalizar(p) for p in partes) if n]


def mismo_nombre(a: str, b: str) -> bool:
    """Coincidencia de personas tolerante a segundos nombres (los tokens de uno incluidos en el otro)
    y a una errata por palabra larga ('goldfrind' ~ 'goldfrid'). Con un solo token no alcanza
    (evita que 'juan' coincida con cualquiera)."""
    ta, tb = a.split(), b.split()
    if set(ta) == set(tb):
        return True
    menor, mayor = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return len(menor) >= 2 and all(any(_casi_igual(t, u) for u in mayor) for t in menor)


def _casi_igual(a: str, b: str) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) < 5 or abs(len(a) - len(b)) > 1:
        return False
    return _distancia(a, b) <= 1


def _distancia(a: str, b: str) -> int:
    """Distancia de Levenshtein."""
    previa = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        actual = [i]
        for j, cb in enumerate(b, 1):
            actual.append(min(previa[j] + 1, actual[j - 1] + 1, previa[j - 1] + (ca != cb)))
        previa = actual
    return previa[-1]


def algun_director_coincide(fuente: str | None, directores_tmdb: list[str]) -> bool:
    nombres_tmdb = [normalizar(d) for d in directores_tmdb]
    return any(mismo_nombre(f, t) for f in separar_nombres(fuente) for t in nombres_tmdb)
