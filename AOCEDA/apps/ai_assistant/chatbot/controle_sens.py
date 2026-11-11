"""Contrôle du SENS d'une phrase d'état ou d'ordre de coupure traduite (arbitrage du 10/11/2026, défaut D6).

Le problème : le contrôle des traductions ne regardait que les nombres. Mesuré le 10/11/2026 : en baoulé, « le courant de la lampe
est rétabli » revenait « le pouvoir de la lumière a disparu » (sens inverse) ; en wolof, « le fer à repasser est éteint » revenait
« le fer est sorti ». Pour une phrase qui dit si un appareil est allumé, éteint, coupé ou rétabli, se tromper de sens est
l'erreur la plus grave : la personne croirait son appareil dans l'autre état.

La solution : la traduction est retraduite en français (par l'autre traducteur quand il y en a un) et on compare, dans la phrase
d'origine et dans la retraduction :
  - la POLARITÉ : allumé / rétabli (« on ») ou éteint / coupé / arrêté (« off »), avec la négation (« n'est PAS coupé » vaut « on ») ;
  - le LIEU ou l'APPAREIL (salon, chambre, climatiseur, lampe…) : un autre lieu, sans aucun lieu commun, est un écart.
Une phrase en écart reste en FRANÇAIS (« non traduit ») : le français est toujours juste, une traduction au sens inversé non.
Tout ceci n'est PAS un jugement de langue (aucun locuteur n'a relu) : c'est un garde-fou sur les deux erreurs qui comptent.
"""
import re
import unicodedata

INVERSE = "sens inversé (allumé / éteint)"
NON_RETROUVE = "sens de l'état non retrouvé"
LIEU = "lieu ou appareil différent"

_OFF = re.compile(r"\b(?:coup\w*|eteint\w*|eteign\w*|eteindr\w*|arret\w*|debranch\w*|deconnect\w*|deconnex\w*|retir\w*|desactiv\w*|interromp\w*|"
                  r"interrupt\w*|disparu\w*|perdu\w*|hors\s+tension|sans\s+courant|plus\s+de\s+courant|plus\s+d['’]electricite)")
_ON = re.compile(r"\b(?:retabli\w*|rallum\w*|remis\w*|remet\w*|revient\w*|revenu\w*|reprend\w*|repris\w*|allum\w*|activ\w*|en\s+marche|"
                 r"sous\s+tension|fonctionn\w*|demarr\w*|redemarr\w*|de\s+retour|retour\s+du\s+courant|reconnect\w*|rebranch\w*|branch\w*|renvoy\w*|"
                 r"ininterrompu\w*|reinser\w*|operationnel\w*|en\s+service)")
_NEGATION = re.compile(r"\bpas\b|\bnon\b|\baucun\w*|\bjamais\b|\bne\s+\w+\s+plus\b|\bn['’]\w+\s+plus\b")

# lieux et appareils : nom canonique -> racines (sur le texte sans accents), synonymes courants des traducteurs compris
_LIEUX = {"salon": r"\bsalon|\bsejour", "chambre": r"\bchambre", "cuisine": r"\bcuisine", "bureau": r"\bbureau",
          "climatiseur": r"\bclim", "lampe": r"\blamp|\blumi|\bampoul|\beclair", "prise": r"\bprise", "ventilateur": r"\bventil",
          "refrigerateur": r"\brefrig|\bfrigo|\bfrigid|\bcongel", "television": r"\btele|\btv\b", "fer": r"\bfer\b|\brepass",
          "pompe": r"\bpompe", "chargeur": r"\bcharg", "chauffe-eau": r"\bchauffe"}


def _sans_accents(texte):
    return "".join(c for c in unicodedata.normalize("NFD", (texte or "").lower()) if unicodedata.category(c) != "Mn")


def polarite(texte):
    """« on » (allumé, rétabli), « off » (éteint, coupé) ou None (aucun des deux, ou les deux : on ne tranche pas).
    La négation inverse : « n'est pas coupé » -> « on »."""
    t = _sans_accents(texte)
    off, on = bool(_OFF.search(t)), bool(_ON.search(t))
    if off == on:
        return None
    base = "off" if off else "on"
    if _NEGATION.search(t):
        return "on" if base == "off" else "off"
    return base


def lieux(texte):
    """Les lieux et appareils nommés dans le texte (noms canoniques)."""
    t = _sans_accents(texte)
    return {nom for nom, motif in _LIEUX.items() if re.search(motif, t)}


def a_controler(source_fr):
    """Seules les phrases qui disent un état ou un ordre de coupure sont retraduites : les autres n'ont rien d'inversible."""
    return polarite(source_fr) is not None


def ecarts(source_fr, retour_fr):
    """Écarts de sens entre la phrase française et sa retraduction ([] si tout concorde, ou si rien n'est à contrôler).
    `retour_fr` None (aucune retraduction à temps) : rien à comparer, aucun écart."""
    if retour_fr is None:
        return []
    ps = polarite(source_fr)
    if ps is None:
        return []
    out = []
    pr = polarite(retour_fr)
    if pr is None:
        out.append(NON_RETROUVE)
    elif pr != ps:
        out.append(INVERSE)
    a, b = lieux(source_fr), lieux(retour_fr)
    if a and b and not (a & b):                    # un lieu nommé de chaque côté, aucun en commun : « salon » est devenu « chambre »
        out.append(LIEU)
    return out


def inverse(ecart_liste):
    """Y a-t-il un écart GRAVE (sens inversé, autre lieu) ? Un état seulement « non retrouvé » est un doute, pas une erreur."""
    return any(e in (INVERSE, LIEU) for e in ecart_liste)
