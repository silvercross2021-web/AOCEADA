"""Nombres français en LETTRES, dans les deux sens (06/10/2026).

- en_lettres(47700) -> « quarante-sept mille sept cents » : les réponses à traduire en baoulé écrivent les nombres en
  lettres (mesuré le 29/09/2026 : Google traduit mieux « cinq mille » que « 5 000 ») ;
- nombres_dans(texte) -> {47700, ...} : les nombres d'un texte, en chiffres OU en lettres, pour vérifier qu'une
  traduction aller-retour a gardé les bons montants.
"""
import re
import unicodedata

_UNITES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze", "treize",
           "quatorze", "quinze", "seize"]
_DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _moins_de_100(n):
    if n < 17:
        return _UNITES[n]
    if n < 20:
        return "dix-" + _UNITES[n - 10]
    d, u = divmod(n, 10)
    if d in (7, 9):                                    # 70-79 = soixante-dix..., 90-99 = quatre-vingt-dix...
        base = "soixante" if d == 7 else "quatre-vingt"
        reste = 10 + u
        return base + ("-et-" if d == 7 and u == 1 else "-") + _moins_de_100(reste)
    if d == 8:
        return "quatre-vingts" if u == 0 else "quatre-vingt-" + _UNITES[u]
    return _DIZAINES[d] + ("" if u == 0 else "-et-un" if u == 1 else "-" + _UNITES[u])


def _moins_de_1000(n):
    c, r = divmod(n, 100)
    if c == 0:
        return _moins_de_100(r)
    tete = "cent" if c == 1 else _UNITES[c] + " cent" + ("s" if r == 0 else "")
    return tete if r == 0 else f"{tete} {_moins_de_100(r)}"


def en_lettres(n):
    """Entier positif en toutes lettres (orthographe traditionnelle, tirets)."""
    n = int(round(n))
    if n < 0:
        return "moins " + en_lettres(-n)
    if n < 1000:
        return _moins_de_1000(n)
    if n < 1_000_000:
        m, r = divmod(n, 1000)
        tete = "mille" if m == 1 else _moins_de_1000(m).replace("cents", "cent").replace("vingts", "vingt") + " mille"
        return tete if r == 0 else f"{tete} {_moins_de_1000(r)}"
    m, r = divmod(n, 1_000_000)
    tete = ("un million" if m == 1 else en_lettres(m) + " millions")
    return tete if r == 0 else f"{tete} {en_lettres(r)}"


_VALEURS = {"zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
            "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
            "vingt": 20, "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60}


def _sans_accents(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def nombres_dans(texte):
    """Ensemble des nombres d'un texte français (chiffres « 47 700 », « 47.700 », « 26 » ou lettres)."""
    t = _sans_accents(texte or "")
    out = set()
    for m in re.finditer(r"\d{1,3}(?:[   .,]\d{3})+|\d+", t):
        out.add(int(re.sub(r"\D", "", m.group())))
    mots = re.findall(r"[a-z]+", t.replace("-", " "))
    total, courant, vu, prec = 0, 0, False, None
    for m in mots + ["#fin"]:
        if m in _VALEURS:
            v = _VALEURS[m]
            if v == 20 and prec == "quatre" and courant % 100 >= 4:     # quatre-vingt(s)
                courant += 80 - 4
            else:
                courant += v
            vu = True
        elif m in ("cent", "cents"):
            courant = (courant or 1) * 100 if courant < 100 else courant - courant % 100 + (courant % 100 or 1) * 100
            vu = True
        elif m == "mille":
            total += (courant or 1) * 1000
            courant, vu = 0, True
        elif m in ("million", "millions"):
            total += (courant or 1) * 1_000_000
            courant, vu = 0, True
        elif m == "et" and vu:
            pass
        else:
            if vu:
                out.add(total + courant)
            total, courant, vu = 0, 0, False
        prec = m
    return out
