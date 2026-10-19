"""Jours fériés de Côte d'Ivoire (19/10/2026) : un jour férié se vit comme un dimanche, la prévision le traite donc
comme un jour de repos.

Fêtes à date fixe, fêtes chrétiennes calculées depuis Pâques, et fêtes musulmanes : leurs dates suivent la lune et sont
fixées chaque année par décret ; celles ci-dessous sont les dates attendues, à corriger ici si le décret en donne une
autre (un jour décalé ne change qu'une journée de prévision).
"""
from datetime import date, timedelta
from functools import lru_cache

FIXES = ((1, 1), (5, 1), (8, 7), (8, 15), (11, 1), (11, 15), (12, 25))
# lendemain de la Nuit du Destin, Aïd el-Fitr (fin du ramadan), Tabaski, lendemain du Maouloud
MUSULMANES = {
    2025: (date(2025, 3, 28), date(2025, 3, 31), date(2025, 6, 7), date(2025, 9, 5)),
    2026: (date(2026, 3, 17), date(2026, 3, 20), date(2026, 5, 27), date(2026, 8, 26)),
    2027: (date(2027, 3, 6), date(2027, 3, 10), date(2027, 5, 17), date(2027, 8, 16)),
    2028: (date(2028, 2, 24), date(2028, 2, 27), date(2028, 5, 5), date(2028, 8, 4)),
}


def paques(annee):
    """Dimanche de Pâques (calendrier grégorien, méthode de Meeus)."""
    a, b, c = annee % 19, annee // 100, annee % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois = (h + l - 7 * m + 114) // 31
    jour = (h + l - 7 * m + 114) % 31 + 1
    return date(annee, mois, jour)


@lru_cache(maxsize=16)
def feries(annee):
    p = paques(annee)
    jours = {date(annee, m, j) for m, j in FIXES}
    jours |= {p + timedelta(days=1), p + timedelta(days=39), p + timedelta(days=50)}   # lundi de Pâques, Ascension, Pentecôte
    jours |= set(MUSULMANES.get(annee, ()))
    return frozenset(jours)


def type_jour(d):
    """« repos » (samedi, dimanche, jour férié) ou « semaine » : on ne vit pas pareil le mardi et le dimanche."""
    return "repos" if d.weekday() >= 5 or d in feries(d.year) else "semaine"
