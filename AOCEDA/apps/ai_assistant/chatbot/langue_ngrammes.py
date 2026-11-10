"""Langue d'un message ÉCRIT d'après ses suites de lettres (n-grammes de 1 à 4 caractères, Bayes naïf).

Pourquoi (audit du 10/11/2026, 1 329 messages) : les règles par mots (dioula_texte, baoule_texte, wolof_texte) reconnaissent
bien le dioula et le baoulé, mais le wolof seulement à 61 %, et elles n'ont pas de sortie « autre langue » : l'agni, le
twi, le yoruba partaient en baoulé ou en dioula (agni : 0 sur 93). Un mot isolé y pèse trop (« AOCEDA », « seen »).
Les suites de lettres, elles, regardent TOUT le message. Mesuré en validation croisée (5 plis, messages rédigés jamais
appris) : règles seules 81,9 %, règles + ce module 98,7 % ; wolof 218 sur 220 ; langues inconnues 105 sur 119.

Ce module ne remplace pas les règles : `service_chat.choisir_langue` s'en sert pour ARBITRER quand le message a au
moins 3 mots et que le français / l'anglais ne sont pas déjà sûrs. Message plus court : les règles et la conversation.

Le modèle (`donnees/langue_ngrammes.json`, comptes de n-grammes par langue) est CONSTRUIT par
`outils/construire_detecteur_langue.py` : ne pas l'éditer à la main.
"""
import json
import math
import re
import unicodedata
from pathlib import Path

FICHIER = Path(__file__).resolve().parent / "donnees" / "langue_ngrammes.json"
N_MAX = 4
MOTS_MIN = 3                 # en dessous, trop peu de lettres pour décider : pas d'avis
SEUIL_LOCALE = 0.90          # dioula / baoulé / wolof retenu à partir de cette probabilité
SEUIL_AUTRE = 0.97           # « autre langue » : seulement si c'est très net (on ne refuse pas une langue à la légère)
SEUIL_DIRECTE = 0.98         # français / anglais
LOCALES = ("dyu", "bci", "wo")
_modele = {}


def normaliser(texte):
    t = unicodedata.normalize("NFC", (texte or "").lower()).replace("’", "'").replace("ʼ", "'")
    return re.sub(r"\s+", " ", re.sub(r"[0-9]+", "0", t)).strip()


def ngrammes(texte):
    t = f" {normaliser(texte)} "
    return [t[i:i + n] for n in range(1, N_MAX + 1) for i in range(len(t) - n + 1)]


def modele():
    """Le modèle, lu une fois (None s'il manque : le module ne donne alors aucun avis, les règles décident seules)."""
    if "m" not in _modele:
        try:
            m = json.loads(FICHIER.read_text(encoding="utf-8"))
            m["log_den"] = [math.log(t + m["alpha"] * m["vocabulaire"]) for t in m["totaux"]]
            _modele["m"] = m
        except (OSError, ValueError, KeyError):
            _modele["m"] = None
    return _modele["m"]


def probabilites(texte):
    """{langue: probabilité} pour fr, en, dyu, bci, wo, autre ; {} sans modèle ou sans lettres."""
    m = modele()
    if m is None or not re.search(r"[^\W\d_]", texte or ""):
        return {}
    grammes = ngrammes(texte)
    comptes, alpha, n = m["ngrammes"], m["alpha"], len(grammes)
    connus = [comptes[g] for g in grammes if g in comptes]
    lp = []
    for i in range(len(m["langues"])):
        s = sum(math.log(c[i] + alpha) for c in connus) - len(connus) * m["log_den"][i]
        lp.append(s / max(1, n) * min(n, 40))            # longueur plafonnée : un long message ne donne pas 1,000000
    haut = max(lp)
    z = sum(math.exp(v - haut) for v in lp)
    return {lg: math.exp(v - haut) / z for lg, v in zip(m["langues"], lp)}


def avis(texte):
    """(langue, probabilité) si le message est assez long et le modèle assez sûr, sinon (None, probabilité).
    langue : « dyu », « bci », « wo », « autre » (langue que l'assistant ne gère pas), « fr » ou « en »."""
    if len(re.findall(r"[^\W\d_]+", texte or "")) < MOTS_MIN:
        return None, 0.0
    p = probabilites(texte)
    if not p:
        return None, 0.0
    lg = max(p, key=p.get)
    seuil = SEUIL_AUTRE if lg == "autre" else SEUIL_LOCALE if lg in LOCALES else SEUIL_DIRECTE
    return (lg, round(p[lg], 3)) if p[lg] >= seuil else (None, round(p[lg], 3))
