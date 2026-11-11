"""Heures du soir en français parlé, AVANT la traduction vers une langue locale (arbitrage du 10/11/2026, défaut D7).

Le problème : Djelia et Google convertissent les heures sur 24 h en heures sur 12 h SANS dire « du soir » (« à 18 h » devient « à
6 h », « 20 heures » devient « 8 h », « 14 h 30 » devient « 2:30 p.m. »). Le contrôle des nombres voyait alors « 18 » disparaître et
rejetait la phrase (9 phrases sur 9 avec une heure de 13 h à 23 h restaient en français en dioula, en wolof et en baoulé) ; et
quand le contrôle laissait passer, la traduction disait « 6 heures » sans préciser matin ou soir.

La solution : écrire l'heure comme on la dit dans ces langues, sur 12 h avec le moment de la journée (« à 6 heures du soir »). Les
traducteurs gardent alors le nombre ET le moment ; le contrôle des nombres compare ce même texte (le « 6 » est bien là).

Seuls les INSTANTS sont réécrits (« à 18 h », « vers 20 heures », « avant 19 h 30 », « entre 17 h et 19 h », « de 17 h à 19 h »). Une
DURÉE (« pendant 20 h », « sur 24 h », « toutes les 18 h ») n'est jamais touchée : un instant mal reconnu serait pire que le
français laissé tel quel.
"""
import re

from .nombres_fr import en_lettres

_LETTRES = {"treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "dix-sept": 17, "dix-huit": 18, "dix-neuf": 19, "vingt": 20,
            "vingt et un": 21, "vingt et une": 21, "vingt-et-un": 21, "vingt-et-une": 21, "vingt-deux": 22, "vingt-trois": 23}
_MOTS_LETTRES = "|".join(sorted((re.escape(k) for k in _LETTRES), key=len, reverse=True))
_MINUTES = r"[0-5]\d|trente|quinze|quarante-cinq|et\s+demie|et\s+quart"
# une heure : 18 h, 18h30, 18 heures 30, vingt heures, vingt heures trente
_HEURE = (r"(?P<h>\d{1,2}|" + _MOTS_LETTRES + r")\s?(?P<u>h(?![a-zA-ZÀ-ÿ])|heures?\b)(?:\s?(?P<m>(?:" + _MINUTES + r")\b))?")
_HEURE_RE = re.compile(_HEURE, re.I)
# ce qui rend une heure « instant » quand il la précède juste avant
_MARQUEUR_RE = re.compile(r"(?:^|[\s(,;:])(?:à|vers|avant|après|apres|dès|depuis|jusqu['’]à|jusqu['’]a|jusque|autour\s+de|"
                          r"aux\s+alentours\s+de|il\s+est|il\s+était|il\s+etait|entre|de)\s+$", re.I)
_MARQUEUR_STRICT_RE = re.compile(r"(?:^|[\s(,;:])(?:à|vers|avant|après|apres|dès|depuis|jusqu['’]à|jusqu['’]a|jusque|autour\s+de|"
                                 r"aux\s+alentours\s+de|il\s+est|il\s+était|il\s+etait)\s+$", re.I)
_SUITE_PLAGE_RE = re.compile(r"^\s*(?:à|et|jusqu['’]à)\s+" + _HEURE, re.I)
_ENTRE_RE = re.compile(r"entre\s+" + _HEURE + r"\s+et\s+$", re.I)             # le 2e terme de « entre 17 h et 19 h »


def _valeur(brut):
    brut = brut.lower().replace("-et-", " et ")
    return int(brut) if brut.isdigit() else _LETTRES.get(brut)


def _ecrire(m, h24):
    """L'heure réécrite sur 12 h avec le moment de la journée ; en chiffres ou en lettres comme la source."""
    h12 = h24 - 12
    moment = "de l'après-midi" if h24 <= 17 else ("du soir" if h24 <= 21 else "de la nuit")   # « 11 heures du soir » devenait « 11 h du jour » en wolof
    en_chiffres = m["h"].isdigit()
    nombre = str(h12) if en_chiffres else ("une" if h12 == 1 else en_lettres(h12))
    minutes = f" {m['m']}" if m["m"] else ""
    return f"{nombre} heure{'s' if h12 > 1 else ''}{minutes} {moment}"


def heures_sur_12h(texte):
    """Réécrit les instants de 13 h à 23 h (« à 18 h » -> « à 6 heures du soir »). Le reste du texte est rendu tel quel."""
    if not texte or not re.search(r"\d\s?h|heure", texte, re.I):
        return texte
    morceaux, fin = [], 0
    for m in _HEURE_RE.finditer(texte):
        h24 = _valeur(m["h"])
        if h24 is None or not 13 <= h24 <= 23:
            continue
        avant, apres = texte[:m.start()], texte[m.end():]
        if _MARQUEUR_STRICT_RE.search(avant) or _ENTRE_RE.search(avant):
            instant = True
        elif _MARQUEUR_RE.search(avant):                  # « de 17 h à 19 h » ; « entre 17 h et 19 h » : une plage, pas une durée
            instant = bool(_SUITE_PLAGE_RE.match(apres))
        else:
            instant = False
        if not instant:
            continue
        morceaux.append(texte[fin:m.start()])
        morceaux.append(_ecrire(m, h24))
        fin = m.end()
    if not morceaux:
        return texte
    return "".join(morceaux) + texte[fin:]
