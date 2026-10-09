"""MÉMOIRE qui s'améliore SANS entraînement (06/10/2026) : la banque d'EXEMPLES baoulé dont on connaît la demande.

- banque (chatbot/donnees/exemples_baoule.json) : les exemples sûrs. Au départ, les 19 phrases de référence (sens
  connu ; une donnée par le client, les autres traduites par Google : à confirmer par un locuteur) ;
- liste d'ATTENTE (cache/exemples_baoule_attente.json) : chaque fois qu'une personne confirme (« oui » à une
  reformulation, ou clic sur un bouton de choix), sa phrase et la demande confirmée y sont ajoutées. Elles n'entrent
  dans la banque qu'après validation dans le menu Tests (un exemple faux ajouté par erreur serait sinon réutilisé
  pour toujours) ;
- proches(texte) : les exemples de la banque qui ressemblent le plus au message (indice fort pour le cerveau IA et
  pour la note de confiance).
"""
import json
import threading
import uuid
from datetime import datetime
from difflib import SequenceMatcher

from . import baoule_texte
from .config import CACHE, DONNEES

BANQUE = DONNEES / "exemples_baoule.json"
ATTENTE = CACHE / "exemples_baoule_attente.json"
SEUIL_PROCHE = 0.60
ATTENTE_MAX = 500
_verrou = threading.Lock()

# phrases de référence (chatbot/donnees/phrases_reference_baoule.json) -> demande de la liste fermée (par leur sens)
DEPART = {0: "courant_revenu", 1: "economiser", 2: "credit_restant", 3: "autre_question_energie", 4: "conso_appareil",
          5: "appareil_gourmand", 6: "facture_chere", 7: "recharger_comment", 8: "conso_appareil", 9: "prepaye_postpaye",
          10: "courant_coupe", 11: "facture_chere", 12: "economiser", 13: "autre_question_energie",
          14: "autre_question_energie", 15: "courant_coupe", 16: "conso_appareil", 17: "climatiseur_conseil",
          18: "autre_question_energie"}


def _lire(f, defaut):
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut


def _ecrire(f, d):
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)


def _depart():
    refs = _lire(DONNEES / "phrases_reference_baoule.json", {"phrases": []})["phrases"]
    return [{"id": f"ref{i}", "bci": p["bci"], "demande": DEPART[i], "sens": p["sens"],
             "statut": "locuteur" if p.get("verifiee") else "reference (traduction Google, à confirmer)",
             "date": "2026-10-05"} for i, p in enumerate(refs) if i in DEPART]


def banque():
    with _verrou:
        if not BANQUE.exists():
            _ecrire(BANQUE, {"exemples": _depart()})
        return _lire(BANQUE, {"exemples": []})["exemples"]


def _mots(texte):
    return [baoule_texte.cle(baoule_texte.sans_article(m.strip("'"))) for m in baoule_texte.mots_de(texte)]


def ressemblance(a, b):
    ma, mb = _mots(a), _mots(b)
    if not ma or not mb:
        return 0.0
    mots = SequenceMatcher(None, ma, mb).ratio()
    lettres = SequenceMatcher(None, "".join(ma), "".join(mb)).ratio()
    return round(max(mots, lettres * 0.95), 3)


def proches(texte, k=2, seuil=SEUIL_PROCHE):
    """[(exemple, ressemblance)] : les k exemples de la banque les plus proches du message (au-dessus du seuil)."""
    if len(_mots(texte)) < 2:
        return []
    notes = sorted(((e, ressemblance(texte, e["bci"])) for e in banque()), key=lambda x: -x[1])
    return [(e, s) for e, s in notes[:k] if s >= seuil]


def ajouter_attente(bci, demande, origine, reformulation=""):
    """Une phrase confirmée par la personne attend la validation (pas de doublon)."""
    if not (bci or "").strip() or not demande:
        return None
    with _verrou:
        d = _lire(ATTENTE, {"exemples": []})
        for e in d["exemples"]:
            if e["bci"].strip() == bci.strip() and e["demande"] == demande:
                return e["id"]
        e = {"id": uuid.uuid4().hex[:10], "bci": bci.strip(), "demande": demande, "origine": origine,
             "reformulation": reformulation, "date": datetime.now().isoformat(timespec="seconds")}
        d["exemples"] = (d["exemples"] + [e])[-ATTENTE_MAX:]
        _ecrire(ATTENTE, d)
        return e["id"]


def attente():
    with _verrou:
        return _lire(ATTENTE, {"exemples": []})["exemples"]


def valider(id_, demande=None):
    """La phrase en attente entre dans la banque (demande corrigée si besoin). Renvoie True si trouvée."""
    banque()
    with _verrou:
        d = _lire(ATTENTE, {"exemples": []})
        e = next((x for x in d["exemples"] if x["id"] == id_), None)
        if e is None:
            return False
        d["exemples"] = [x for x in d["exemples"] if x["id"] != id_]
        b = _lire(BANQUE, {"exemples": []})
        b["exemples"].append({"id": e["id"], "bci": e["bci"], "demande": demande or e["demande"],
                              "sens": e.get("reformulation", ""), "statut": f"validé ({e['origine']})",
                              "date": datetime.now().isoformat(timespec="seconds")})
        _ecrire(BANQUE, b)
        _ecrire(ATTENTE, d)
        return True


def rejeter(id_):
    with _verrou:
        d = _lire(ATTENTE, {"exemples": []})
        avant = len(d["exemples"])
        d["exemples"] = [x for x in d["exemples"] if x["id"] != id_]
        _ecrire(ATTENTE, d)
        return len(d["exemples"]) < avant
