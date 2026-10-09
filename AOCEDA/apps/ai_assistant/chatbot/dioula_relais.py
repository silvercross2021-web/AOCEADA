"""Relais DIOULA <-> FRANÇAIS : DeepSeek ne parle pas bien le dioula, on passe par le français à l'aller et au retour.

Services (sans clé, pages de démonstration ; une clé officielle Djelia sera nécessaire pour la mise en service) :
  - Djelia : bambara <-> français (le bambara est très proche du dioula ; c'est le plus rapide : ~1 s) ;
  - Google : dioula <-> français (vrai dioula, ~1,5 s).
Mesuré le 29/09/2026 : 1er appel 2 à 3 s (ouverture de connexion), puis ~1 s (Djelia) et ~1,5 s (Google) quand la
connexion reste ouverte -> connexions ouvertes au démarrage du serveur (prechauffer) et gardées.

Vitesse à l'aller (dioula -> français) : les deux services sont appelés EN MÊME TEMPS ; dès que le premier répond, on
attend le second au plus ATTENTE_SECOND_S, puis on continue avec ce qu'on a (DeepSeek reçoit les deux s'ils sont là :
quand l'un se trompe, l'autre rattrape souvent).
Retour (français -> dioula) : Djelia d'abord (choix validé), Google en secours ; une « traduction » restée en français
(service en panne silencieuse) est refusée.
Sûreté : un service qui échoue 3 fois de suite est écarté 60 s (coupe-circuit) ; traductions gardées en mémoire.
"""
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import requests

from . import detection

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
DELAI_S = 6.0                 # au-delà, un service est considéré comme sans réponse
ATTENTE_SECOND_S = 0.4        # après la 1re traduction, on attend la 2e au plus ce temps
PANNES_AVANT_COUPURE = 3
COUPURE_S = 60
MEMOIRE_MAX = 3000

_http = requests.Session()
_http.headers.update(UA)
_http.mount("https://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=16))
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="relais")          # une tâche par phrase / message
# les appels aux services eux-mêmes : réserve SÉPARÉE (une tâche qui attend un service ne doit jamais bloquer la place
# dont ce service a besoin : 8 phrases en attente dans _pool ne peuvent pas empêcher leurs traductions de démarrer)
_services = ThreadPoolExecutor(max_workers=16, thread_name_prefix="relais-service")
PREFERENCE_S = 2.5            # Djelia seul pendant ce temps ; ensuite Google est lancé aussi, en parallèle
DELAI_TOTAL_RETOUR_S = 7.0    # une phrase de la réponse : traduite en 7 s au plus (service_dioula attend 8 s)
_memoire, _verrou = OrderedDict(), threading.Lock()
_etat = {"google": {"pannes": 0, "coupe_jusqu_a": 0.0}, "djelia": {"pannes": 0, "coupe_jusqu_a": 0.0}}


class RelaisIndisponible(Exception):
    pass


def _disponible(service):
    return time.time() >= _etat[service]["coupe_jusqu_a"]


def _noter(service, ok):
    with _verrou:
        e = _etat[service]
        if ok:
            e["pannes"] = 0
        else:
            e["pannes"] += 1
            if e["pannes"] >= PANNES_AVANT_COUPURE:
                e["coupe_jusqu_a"], e["pannes"] = time.time() + COUPURE_S, 0


def _google(texte, source, cible):
    r = _http.get("https://clients5.google.com/translate_a/t", params={"client": "dict-chrome-ex", "sl": source,
                  "tl": cible, "q": texte}, timeout=(3.0, DELAI_S))
    r.raise_for_status()
    d = r.json()
    return (d[0][0] if isinstance(d[0], list) else d[0]).strip()


def _djelia(texte, source, cible):
    r = _http.post("https://www.djelia.cloud/api/translate", json={"text": texte, "source": source, "target": cible},
                   timeout=(3.0, DELAI_S))
    r.raise_for_status()
    return r.json()["text"].strip()


SERVICES = {  # (service, sens) -> (fonction, langue source, langue cible)
    ("google", "vers_fr"): (_google, "dyu", "fr"), ("djelia", "vers_fr"): (_djelia, "bam_Latn", "fra_Latn"),
    ("google", "vers_dyu"): (_google, "fr", "dyu"), ("djelia", "vers_dyu"): (_djelia, "fra_Latn", "bam_Latn"),
}


def traduire(service, sens, texte):
    """Une traduction par un service (mémoire + coupe-circuit). Lève RelaisIndisponible."""
    texte = (texte or "").strip()
    if not texte:
        return ""
    cle = (service, sens, texte)
    with _verrou:
        if cle in _memoire:
            _memoire.move_to_end(cle)
            return _memoire[cle]
    if not _disponible(service):
        raise RelaisIndisponible(f"{service} écarté quelques secondes après des pannes")
    f, src, dst = SERVICES[(service, sens)]
    try:
        out = f(texte, src, dst)
        if not out:
            raise RelaisIndisponible(f"{service} : réponse vide")
    except Exception as e:
        _noter(service, False)
        raise RelaisIndisponible(f"{service} : {e}"[:160])
    _noter(service, True)
    with _verrou:
        _memoire[cle] = out
        if len(_memoire) > MEMOIRE_MAX:
            _memoire.popitem(last=False)
    return out


def vers_francais(texte_dioula, delai_s=DELAI_S, attente_second_s=ATTENTE_SECOND_S):
    """Les deux traductions en parallèle. Renvoie {"google", "djelia", "duree_s", "erreurs"} (None si absente)."""
    t0 = time.time()
    taches = {_services.submit(traduire, s, "vers_fr", texte_dioula): s for s in ("djelia", "google")}
    sortie, erreurs, restant = {"google": None, "djelia": None}, [], set(taches)
    fin = t0 + delai_s
    while restant and time.time() < fin:
        faits, restant = wait(restant, timeout=max(0.0, fin - time.time()), return_when=FIRST_COMPLETED)
        for t in faits:
            try:
                sortie[taches[t]] = t.result()
            except Exception as e:
                erreurs.append(str(e))
        if any(sortie.values()):                        # une traduction est là : on n'attend l'autre qu'un instant
            fin = min(fin, time.time() + attente_second_s)
    for t in restant:
        erreurs.append(f"{taches[t]} : trop lent, ignoré pour ce message")
    return {**sortie, "duree_s": round(time.time() - t0, 2), "erreurs": erreurs}


def _reste_en_francais(entree, sortie):
    code, conf = detection.detecter(sortie)
    return sortie.strip().lower() == entree.strip().lower() or (code == "fr" and conf >= 0.9 and len(sortie.split()) >= 4)


def sans_parentheses_ajoutees(source, traduction):
    """Le traducteur ajoute parfois une variante entre parenthèses (« ... (sara) ») : lue à voix haute, elle embrouille.
    Retirée si la phrase d'origine n'avait pas de parenthèses (audit du 09/10/2026)."""
    if "(" in (source or "") or "(" not in (traduction or ""):
        return traduction
    propre = re.sub(r"\s*\([^()]*\)", "", traduction)
    return re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"\s{2,}", " ", propre)).strip() or traduction


def _vers_dioula_par(service, texte_francais):
    out = traduire(service, "vers_dyu", texte_francais)
    if _reste_en_francais(texte_francais, out):
        raise RelaisIndisponible(f"{service} : traduction restée en français")
    return sans_parentheses_ajoutees(texte_francais, out)


def vers_dioula(texte_francais, ordre=("djelia", "google"), delai_total_s=None, preference_s=None):
    """Traduit une phrase de la réponse. Renvoie (texte_dioula, service). Lève RelaisIndisponible si tout échoue.
    Djelia d'abord ; s'il n'a pas répondu après PREFERENCE_S (ou s'il échoue), Google est lancé EN PARALLÈLE et la
    1re bonne traduction gagne. Le tout est borné à DELAI_TOTAL_RETOUR_S.
    (Bug corrigé le 29/09/2026 : les secours passaient l'un APRÈS l'autre ; un Djelia lent à échouer (~8 s) épuisait
    tout le temps et la phrase restait en français alors que Google répondait en 1 s.)"""
    delai_total_s = DELAI_TOTAL_RETOUR_S if delai_total_s is None else delai_total_s
    preference_s = PREFERENCE_S if preference_s is None else preference_s
    t0, erreurs, taches, suivants = time.time(), [], {}, list(ordre)
    taches[_services.submit(_vers_dioula_par, suivants.pop(0), texte_francais)] = ordre[0]
    while taches or suivants:
        ecoule = time.time() - t0
        if ecoule >= delai_total_s:
            break
        attente = delai_total_s - ecoule if not suivants else max(0.0, min(delai_total_s, preference_s) - ecoule)
        faits, _ = wait(list(taches), timeout=attente, return_when=FIRST_COMPLETED)
        for t in sorted(faits, key=lambda t: ordre.index(taches[t])):
            service = taches.pop(t)
            try:
                return t.result(), service
            except Exception as e:
                erreurs.append(str(e))
        if suivants and (not taches or time.time() - t0 >= preference_s):
            s = suivants.pop(0)
            taches[_services.submit(_vers_dioula_par, s, texte_francais)] = s
        elif not taches and not suivants:
            break
    for t, s in taches.items():
        erreurs.append(f"{s} : trop lent")
    raise RelaisIndisponible(" ; ".join(erreurs) or "traducteurs trop lents")


def lancer_vers_dioula(texte_francais):
    """Même chose, en arrière-plan (renvoie un Future) : chaque phrase est traduite dès qu'elle est écrite."""
    return _pool.submit(vers_dioula, texte_francais)


def prechauffer():
    """Ouvre les connexions (TLS) dès le démarrage : le 1er client ne paie pas les 1 à 2 s d'ouverture."""
    for service, sens, texte in (("djelia", "vers_fr", "i ni ce"), ("google", "vers_fr", "i ni ce")):
        try:
            traduire(service, sens, texte)
        except RelaisIndisponible:
            pass


def etat():
    return {s: {"disponible": _disponible(s), "pannes": e["pannes"]} for s, e in _etat.items()}
