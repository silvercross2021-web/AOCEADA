"""Relais BAOULÉ <-> FRANÇAIS : DeepSeek ne parle pas le baoulé, on passe par le français à l'aller et au retour.

Service : Google (baoulé « bci ») — le seul traducteur fiable trouvé (MADLAD-400 tourne en boucle, validé le 28/09/2026).
Même mécanique que le dioula (dioula_relais) : mémoire des traductions, coupe-circuit après 3 pannes, connexion gardée
ouverte, traduction « restée en français » refusée.

Pièges de Google en baoulé (mesurés le 29/09/2026 sur 44 phrases AOCEDA) :
  - un « ? » parasite AU DÉBUT des questions (« ?Wafa sɛ yɛ ... ») -> retiré ;
  - « sika » (argent) est retraduit en « dollars » -> signalé à DeepSeek (ce sont des francs CFA) ;
  - « Ɛɛ » (oui) est retraduit « Non » -> les oui/non viennent des formules (baoule_texte), pas de la traduction.
"""
import os
import re
import time
import unicodedata

from . import dioula_relais
from .dioula_relais import RelaisIndisponible

DELAI_TOTAL_RETOUR_S = 7.0

dioula_relais.SERVICES.update({
    ("google", "bci_vers_fr"): (dioula_relais._google, "bci", "fr"),
    ("google", "vers_bci"): (dioula_relais._google, "fr", "bci"),
})


def _nettoyer(texte):
    """Retire le « ? » parasite du début et les espaces en trop."""
    t = re.sub(r"^\s*[?¿]+\s*", "", texte or "").strip()
    return re.sub(r"\s+", " ", t)


# « par oui ou non » traduit « ɛɛ annzɛ ɛɛ » (= oui ou OUI) : vu le 30/09/2026 dans une vraie réponse ; le client ne
# saurait pas comment dire non. Le « non » baoulé est « cɛcɛ ».
_OUI_OU_OUI = re.compile(r"\b([ƐɛEe]{2}n?)(\s+annzɛ\s+)[ƐɛEe]{2}n?\b")


def _corriger_oui_non(francais, baoule):
    if re.search(r"\boui\b.*\bnon\b", francais or "", re.I):
        return _OUI_OU_OUI.sub(lambda m: m.group(1) + m.group(2) + "cɛcɛ", baoule)
    return baoule


def vers_francais(texte_baoule, delai_s=dioula_relais.DELAI_S):
    """Baoulé -> français (Google). Renvoie {"google", "duree_s", "erreurs"} (google = None si indisponible).
    Un 2e essai si le 1er échoue ou revient vide, dans le même délai : vu le 30/09/2026, un vocal (« ne tianyi ») est
    parti chez DeepSeek SANS traduction après un raté ponctuel de Google (4,2 s), alors qu'un nouvel essai marchait."""
    t0, erreurs = time.time(), []
    for _ in range(2):
        reste = delai_s - (time.time() - t0)
        if reste < 0.5:
            break
        tache = dioula_relais._services.submit(dioula_relais.traduire, "google", "bci_vers_fr", texte_baoule)
        try:
            out = _nettoyer(tache.result(timeout=reste))
            if out:
                return {"google": out, "duree_s": round(time.time() - t0, 2), "erreurs": erreurs}
            erreurs.append("google : traduction vide")
        except Exception as e:
            erreurs.append(str(e)[:160])
    return {"google": None, "duree_s": round(time.time() - t0, 2), "erreurs": erreurs}


def vers_baoule(texte_francais, delai_total_s=None):
    """Traduit une phrase de la réponse en baoulé. Renvoie (texte_baoule, service). Lève RelaisIndisponible."""
    delai = DELAI_TOTAL_RETOUR_S if delai_total_s is None else delai_total_s
    tache = dioula_relais._services.submit(dioula_relais.traduire, "google", "vers_bci", texte_francais)
    try:
        out = _nettoyer(tache.result(timeout=delai))
    except RelaisIndisponible:
        raise
    except Exception as e:
        raise RelaisIndisponible(f"google : {e or 'trop lent'}"[:160])
    if not out or dioula_relais._reste_en_francais(texte_francais, out):
        raise RelaisIndisponible("google : traduction restée en français")
    out = dioula_relais.sans_parentheses_ajoutees(texte_francais, out)
    # Google écrit les milliers à l'anglaise ou à l'allemande (« 47.700 », « 47,700 ») : 47 700, comme en français
    # (audit du 09/10/2026) ; un vrai décimal (« 2,5 ») n'a jamais 3 chiffres après la virgule
    out = re.sub(r"(?<![\d.,])(\d{1,3})(?:[.,](\d{3}))+(?![\d.,])", lambda m: m.group(0).replace(".", " ").replace(",", " "), out)
    return _corriger_oui_non(texte_francais, out), "google"


def lancer_vers_baoule(texte_francais):
    """Même chose, en arrière-plan (renvoie un Future) : chaque phrase est traduite dès qu'elle est écrite."""
    return dioula_relais._pool.submit(vers_baoule, texte_francais)


# ── Deuxième interprète : NiuTrans (06/10/2026) ──────────────────────────────────
# Le seul autre service qui propose le baoulé (machinetranslate.org/baule). Gratuit : 200 000 caractères par jour, avec
# une clé personnelle (NIUTRANS_API_KEY dans le fichier de clés). Sans clé, il est simplement absent : Google seul.
URL_NIUTRANS = "https://api.niutrans.com/NiuTransServer/translation"
dioula_relais._etat.setdefault("niutrans", {"pannes": 0, "coupe_jusqu_a": 0.0})


def niutrans_disponible():
    return bool(os.environ.get("NIUTRANS_API_KEY", "").strip())


def _niutrans(texte, source, cible):
    if not niutrans_disponible():
        raise RelaisIndisponible("niutrans : pas de clé (NIUTRANS_API_KEY)")
    r = dioula_relais._http.post(URL_NIUTRANS, data={"from": source, "to": cible, "src_text": texte,
                                                     "apikey": os.environ["NIUTRANS_API_KEY"].strip()},
                                 timeout=(3.0, dioula_relais.DELAI_S))
    r.raise_for_status()
    d = r.json()
    if d.get("error_code") or "tgt_text" not in d:
        raise RelaisIndisponible(f"niutrans : {d.get('error_msg') or d.get('error_code') or 'réponse vide'}"[:160])
    return d["tgt_text"].strip()


dioula_relais.SERVICES.update({
    ("niutrans", "bci_vers_fr"): (_niutrans, "bci", "fr"),
    ("niutrans", "vers_bci"): (_niutrans, "fr", "bci"),
    ("google", "fr_vers_en"): (dioula_relais._google, "fr", "en"),
})

_MOTS_VIDES = set("le la les l un une des de du d et à a au aux en dans pour par sur ce cet cette ces se sa son ses mon ma mes "
                  "ton ta tes votre vos notre nos leur leurs il elle ils elles je tu nous vous on qui que quoi ne pas est sont "
                  "être avoir y c qu s n m t".split())


def _mots_pleins(texte):
    t = "".join(c for c in unicodedata.normalize("NFD", (texte or "").lower()) if unicodedata.category(c) != "Mn")
    return {re.sub(r"(?<=\w{3})s$", "", m) for m in re.findall(r"[a-z0-9]+", t) if m not in _MOTS_VIDES}


def accord(a, b):
    """Accord entre deux traductions (0 à 1) : part des mots pleins en commun. None si l'une manque."""
    if not a or not b:
        return None
    x, y = _mots_pleins(a), _mots_pleins(b)
    if not x or not y:
        return None
    return round(len(x & y) / len(x | y), 2)


def deux_interpretes(texte_baoule, delai_s=dioula_relais.DELAI_S):
    """Baoulé -> français par Google ET NiuTrans EN MÊME TEMPS (environ 1 s). Renvoie {"google", "niutrans", "accord",
    "duree_s", "erreurs"} ; un interprète absent ou en panne vaut None (le système continue avec l'autre)."""
    t0 = time.time()
    taches = {"google": dioula_relais._services.submit(vers_francais, texte_baoule, delai_s)}
    if niutrans_disponible():
        taches["niutrans"] = dioula_relais._services.submit(dioula_relais.traduire, "niutrans", "bci_vers_fr", texte_baoule)
    out, erreurs = {"google": None, "niutrans": None}, []
    for nom, t in taches.items():
        try:
            r = t.result(timeout=delai_s + 1)
            out[nom] = r["google"] if nom == "google" else (_nettoyer(r) or None)
            if nom == "google":
                erreurs += r["erreurs"]
        except Exception as e:
            erreurs.append(f"{nom} : {e}"[:160])
    return {**out, "accord": accord(out["google"], out["niutrans"]), "duree_s": round(time.time() - t0, 2), "erreurs": erreurs}


def retour_en_francais(texte_baoule):
    """Contre-vérification : la réponse baoulé retraduite en français, par l'AUTRE interprète si possible (NiuTrans),
    sinon Google. Renvoie (texte, service) ; (None, None) si aucun ne répond."""
    for service in (("niutrans", "google") if niutrans_disponible() else ("google",)):
        try:
            out = _nettoyer(dioula_relais.traduire(service, "bci_vers_fr", texte_baoule))
            if out:
                return out, service
        except Exception:
            continue
    return None, None


def vers_anglais(texte_francais):
    """Un mot français en anglais (Google), pour chercher dans GATITOS (anglais-baoulé)."""
    return _nettoyer(dioula_relais.traduire("google", "fr_vers_en", texte_francais)) or None


def prechauffer():
    try:
        dioula_relais.traduire("google", "bci_vers_fr", "Aɲiho")
    except RelaisIndisponible:
        pass


def etat():
    return {"google": {"disponible": dioula_relais._disponible("google"), "pannes": dioula_relais._etat["google"]["pannes"]},
            "niutrans": {"cle": niutrans_disponible(), "disponible": niutrans_disponible() and dioula_relais._disponible("niutrans"),
                         "pannes": dioula_relais._etat["niutrans"]["pannes"]}}
