"""BLOC D : RÉPONDRE en baoulé, avec CONTRE-VÉRIFICATION (06/10/2026).

Pour chaque phrase française de la réponse (construite par baoule_demandes avec les vraies données) :
  1. phrase-type RELUE par un locuteur (chatbot/donnees/phrases_types_baoule.json) : utilisée telle quelle, sûre ;
  2. sinon traduction automatique (Google), PUIS contre-vérification : l'autre interprète (NiuTrans, sinon Google)
     retraduit le baoulé en français, et le code vérifie que les NOMBRES et les NOMS D'APPAREILS sont toujours là
     (5 000 doit rester 5 000) ;
  3. si un élément manque : 2e essai (nombres écrits en chiffres, phrase simplifiée) ; s'il manque encore, la phrase
     est gardée mais marquée « douteuse » (la page montre alors le français dessous, « traduction automatique »).
Toutes les phrases sont traduites EN MÊME TEMPS (environ 1 à 2 s pour une réponse entière).
"""
import json
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from . import baoule_relais
from .config import DONNEES
from .nombres_fr import nombres_dans

PHRASES_TYPES = DONNEES / "phrases_types_baoule.json"
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="baoule-reponse")
_verrou = threading.Lock()
_types = {"t": None, "d": {}}


def phrases_types():
    """{phrase française exacte: baoulé relu par un locuteur}. Fichier relu s'il a changé."""
    with _verrou:
        try:
            t = PHRASES_TYPES.stat().st_mtime
        except OSError:
            return {}
        if _types["t"] != t:
            try:
                d = json.loads(PHRASES_TYPES.read_text(encoding="utf-8"))
                _types["d"] = {x["fr"].strip(): x["bci"].strip() for x in d.get("phrases", []) if x.get("relue")}
            except (ValueError, KeyError):
                _types["d"] = {}
            _types["t"] = t
        return _types["d"]


def _sans_accents(t):
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")


RETOUR_MAX_S = 3.0      # retraduction de contrôle : au-delà, la phrase part quand même, marquée « non vérifiée »


def manques(phrase, retour):
    """Éléments de la phrase française absents de la retraduction : [« 5000 », « climatiseur », « credit »].
    Trois sortes : les NOMBRES, les NOMS D'APPAREILS (cles) et les mots de SENS (sens : au moins un des synonymes ;
    mesuré le 06/10/2026 : « il vous reste 48 200 francs de crédit » retraduit « la société possède 48 200 actions »
    gardait le nombre mais pas le sens)."""
    if retour is None:
        return ["aucune retraduction"]
    vus = nombres_dans(retour)
    r = _sans_accents(retour)
    out = [str(n) for n in phrase.nombres if n is not None and n not in vus]
    for c in phrase.cles:
        if c and _sans_accents(c)[:5] not in r:
            out.append(c)
    for groupe in getattr(phrase, "sens", ()):
        if groupe and not any(_sans_accents(x) in r for x in groupe):
            out.append(groupe[0])
    return out


def _retour_borne(bci):
    """Retraduction de contrôle, bornée dans le temps : (texte, service) ou (None, None) si trop lente ou en panne."""
    from . import dioula_relais
    t = dioula_relais._services.submit(baoule_relais.retour_en_francais, bci)
    try:
        return t.result(timeout=RETOUR_MAX_S)
    except Exception:
        return None, None


def _version_chiffres(fr):
    """2e essai : nombres en chiffres (« quarante-sept mille sept cents » -> « 47 700 »), parfois mieux gardés."""
    from .nombres_fr import en_lettres
    out = fr
    for n in sorted(nombres_dans(fr), reverse=True):
        lettres = en_lettres(n)
        if lettres in out:
            out = out.replace(lettres, f"{n:,}".replace(",", " "))
    return out


def traduire_une(phrase):
    """{"fr", "bci", "controle", "retour", "manques", "service"} ; controle = relue | verifiee | corrigee | douteuse |
    non_verifiee (retraduction trop lente ou en panne : envoyée sans contrôle) | non_traduite."""
    relue = phrases_types().get(phrase.fr.strip())
    if relue:
        return {"fr": phrase.fr, "bci": relue, "controle": "relue", "retour": None, "manques": [], "service": "relue"}
    essais = [phrase.fr]
    chiffres = _version_chiffres(phrase.fr)
    if chiffres != phrase.fr:
        essais.append(chiffres)
    meilleur = None
    for i, fr in enumerate(essais):
        try:
            bci, service = baoule_relais.vers_baoule(fr)
        except Exception as e:
            if meilleur is None:
                meilleur = {"fr": phrase.fr, "bci": phrase.fr, "controle": "non_traduite", "retour": None,
                            "manques": [str(e)[:80]], "service": "aucun"}
            continue
        if not phrase.nombres and not phrase.cles and not getattr(phrase, "sens", ()):   # rien de précis à garder
            return {"fr": phrase.fr, "bci": bci, "controle": "verifiee", "retour": None, "manques": [], "service": service}
        retour, _ = _retour_borne(bci)
        if retour is None:                                      # contrôle impossible à temps : on n'attend pas plus
            return {"fr": phrase.fr, "bci": bci, "controle": "non_verifiee", "retour": None, "manques": [],
                    "service": service}
        m = manques(phrase, retour)
        r = {"fr": phrase.fr, "bci": bci, "controle": ("verifiee" if i == 0 else "corrigee") if not m else "douteuse",
             "retour": retour, "manques": m, "service": service}
        if not m:
            return r
        if meilleur is None or meilleur["controle"] == "non_traduite" or len(m) < len(meilleur["manques"]):
            meilleur = r
    return meilleur


def traduire_flux(phrases):
    """Toutes les phrases traduites EN MÊME TEMPS ; chacune est rendue, dans l'ordre, DÈS qu'elle est prête (la page
    affiche la 1re phrase sans attendre la dernière)."""
    taches = [_pool.submit(traduire_une, p) for p in phrases]
    for t in taches:
        yield t.result()


def traduire(phrases):
    """Même chose, en liste (voir traduire_une)."""
    return list(traduire_flux(phrases))


# ── Réponse libre (« autre question sur l'électricité ») ─────────────────────────
SYSTEME_LIBRE = """Tu es l'assistant AOCEDA (électricité de la maison en Côte d'Ivoire, francs CFA, fournisseur CIE).
Réponds en FRANÇAIS SIMPLE à la question : ta réponse sera traduite automatiquement en baoulé puis lue à voix haute.
- 2 ou 3 phrases courtes, une seule idée par phrase, sans liste, sans tiret, sans parenthèses, sans guillemets.
- Nombres EN LETTRES. Vouvoie. Pas de sigle sauf CIE.
- Tu n'as PAS les données du compte ici : n'invente aucun chiffre sur le foyer ; ne donne aucun tarif précis de la CIE
  dont tu n'es pas sûr (invite à vérifier auprès de la CIE)."""


def reponse_libre(question_fr, liste=None):
    """Réponse générale du cerveau IA (en français), découpée en phrases. Lève RuntimeError si personne ne répond."""
    from . import fournisseurs
    from .baoule_demandes import Phrase
    fin = None
    for ev in fournisseurs.repondre_flux(SYSTEME_LIBRE, [{"role": "user", "texte": question_fr}], liste=liste,
                                         outils=False):    # réponse générale : la chaîne baoulé lit les données elle-même
        if ev["type"] in ("fin", "erreur"):
            fin = ev
    if not fin or fin["type"] == "erreur" or not fin.get("texte", "").strip():
        raise RuntimeError("aucune réponse du cerveau IA")
    morceaux = [p.strip() for p in re.split(r"(?<=[.!?])\s+", fin["texte"].strip()) if p.strip()][:4]
    return [Phrase(p, tuple(sorted(nombres_dans(p)))) for p in morceaux]
