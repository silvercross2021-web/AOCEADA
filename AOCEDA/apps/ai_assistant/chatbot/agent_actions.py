"""AGENT D'ACTIONS (05/10/2026) : l'appel Live confie une demande (« ouvre les options, mets une voix d'homme et le thème
clair ») ; on la fait en UNE question au modèle au lieu d'une par clic (clic par clic, c'était « extrêmement lent »).

  1. la page envoie sa CARTE (tous les écrans et éléments, avec une clé stable) et l'état de l'écran ;
  2. RACCOURCI : une demande déjà réussie avec la même carte est rejouée telle quelle, sans modèle (0 s, 0 coût) ;
  3. sinon PLAN : DeepSeek Flash, réflexion désactivée, réponse JSON (comparatif du 05/10 : 4/4, ~0,05 centime de $ et
     ~1,5 s par plan) ; secours Qwen 3.7 Flash par OpenRouter (clé plafonnée) si DeepSeek ne répond pas ;
  4. le plan est CONTRÔLÉ ici (clés de la carte seulement, rien de réservé à la personne, valeurs des listes existantes) ;
  5. la page l'exécute vite et vérifie chaque étape ; au premier écart elle s'arrête : on fait corriger le plan
     (au plus 2 corrections), avec la raison et le nouvel écran ;
  6. réussi -> gardé comme raccourci.
"""
import json
import os
import re
import threading
import time
import unicodedata
from datetime import datetime, timezone

import requests

from .config import CACHE, CONFIG

MODELE = "deepseek-flash"
SECOURS = ("https://openrouter.ai/api/v1/chat/completions", "qwen/qwen3.7-flash")
ACTIONS = ("cliquer", "choisir", "ecrire", "defiler", "fermer", "attendre")
MAX_ETAPES = 15
CORRECTIONS = 2
DELAI_MODELE_S = 25
FICHIER_RACCOURCIS = CACHE / "raccourcis_actions.json"
MAX_RACCOURCIS = 300

SYSTEME = """Tu es le PLANIFICATEUR d'actions de l'application AOCEDA (suivi de la consommation d'électricité). On te donne la
CARTE de l'application (tous ses écrans et éléments, avec une clé « cle »), l'ÉTAT de l'écran et un OBJECTIF dit par la
personne. Tu renvoies le plan COMPLET qui réalise tout l'objectif, en un seul JSON (sans aucun texte autour) :

{"etapes": [{"action": "...", "cible": "<cle de la carte>", ...}], "dit": "<une phrase>", "impossible": null}

ACTIONS
- {"action": "cliquer", "cible": cle}                          bouton, ligne d'une liste, suggestion, case du thème
- {"action": "choisir", "cible": cle, "valeur": option}         liste déroulante : « valeur » = texte EXACT d'une option
- {"action": "ecrire", "cible": cle, "texte": "...", "envoyer": true|false}
- {"action": "defiler", "cible": cle_de_l_ecran, "sens": "haut"|"bas"}
- {"action": "fermer"}                                          ferme la fenêtre ouverte

RÈGLES
1. N'utilise QUE des « cle » présentes dans la carte, recopiées à l'identique.
2. Le moteur ouvre tout seul l'écran qui contient l'élément visé (et le referme ensuite) : n'ajoute PAS d'étape pour
   ouvrir ou fermer une fenêtre, SAUF si la personne demande de l'OUVRIR, de la VOIR ou de l'AFFICHER : alors clique
   sur son bouton (élément « ouvre ») et elle reste ouverte.
3. Le moins d'étapes possible, dans l'ordre demandé ; rien de plus que l'objectif. Si l'état montre que c'est déjà fait,
   renvoie "etapes": [] et dis-le.
4. Jamais un élément marqué « reserve_a_la_personne » ni une action définitive : si l'objectif l'exige, renvoie
   "etapes": [] et "impossible": "<raison courte>". Pareil si l'application n'a pas ce qu'il faut (dis ce qui manque).
5. « attention » (nouvelle conversation) : seulement si la personne le demande clairement.
6. Thème : clique la case du thème voulu. Langue des réponses écrites : choisis dans la liste « Langue ». Voix : liste
   « Voix ». Envoyer un message dans le chat écrit : ecrire dans le champ du message avec "envoyer": true. Reprendre
   une conversation : clique sa ligne dans l'Historique.
7. « dit » : une phrase courte, au passé, en français, qui dit ce qui sera fait (ou pourquoi c'est impossible).
8. Texte à ÉCRIRE : recopie EXACTEMENT les mots de la personne, dans SA langue, sans les traduire, les corriger ni les
   reformuler (« écris combien consomme un frigo » -> texte « combien consomme un frigo »).
9. Les gens nomment les écrans à leur façon : « paramètres », « réglages », « préférences », « settings », « menu » =
   l'écran Options ; « mes conversations », « conversations d'avant » = Historique ; « rapports », « tests », « mesures »
   = Tests et rapports ; « langues » = Langue des réponses. Ne réponds jamais « impossible » pour un simple autre nom.
10. Demande claire mais sans détail : fais le choix ÉVIDENT au lieu de renvoyer « impossible » : « change le thème » =
   le thème opposé à celui de l'état (clair -> sombre, sombre -> clair, auto -> sombre) ; « change la voix » = l'autre
   voix (femme <-> homme).

CARTE DE L'APPLICATION
{carte}"""


def normal(s):
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in unicodedata.normalize("NFD", str(s or "").lower())
                                               if unicodedata.category(c) != "Mn")).strip()


def _carte_compacte(carte):
    """La carte telle que le modèle la lit : les champs utiles seulement (moins de jetons, même sens)."""
    garder = ("cle", "role", "nom", "valeur", "options", "ouvre", "etat", "reserve_a_la_personne", "attention")
    return json.dumps([{"ecran": e.get("ecran"), "cle": e.get("cle"), "ouvert_par": e.get("ouvert_par"),
                        "elements": [{k: x[k] for k in garder if x.get(k) not in (None, "", [])} for x in e.get("elements", [])]}
                       for e in carte.get("ecrans", [])], ensure_ascii=False, separators=(",", ":"))


def elements(carte):
    return {x["cle"]: x for e in carte.get("ecrans", []) for x in e.get("elements", []) if x.get("cle")}


def controler(plan, carte):
    """Erreurs du plan (liste vide = plan acceptable). Ne laisse passer que des clés de la carte, rien de réservé à la
    personne, des valeurs de listes qui existent : le modèle ne peut rien faire que la carte ne permette."""
    if not isinstance(plan, dict):
        return ["la réponse n'est pas un objet JSON"]
    etapes = plan.get("etapes")
    if not isinstance(etapes, list):
        return ["« etapes » doit être une liste"]
    if len(etapes) > MAX_ETAPES:
        return [f"plan trop long ({len(etapes)} étapes, maximum {MAX_ETAPES})"]
    connus, erreurs = elements(carte), []
    for i, e in enumerate(etapes, 1):
        if not isinstance(e, dict) or e.get("action") not in ACTIONS:
            erreurs.append(f"étape {i} : action inconnue ({e.get('action') if isinstance(e, dict) else e})")
            continue
        if e["action"] in ("fermer", "attendre"):
            continue
        x = connus.get(e.get("cible"))
        if x is None and not (e["action"] == "defiler" and any(c.get("cle") == e.get("cible") for c in carte.get("ecrans", []))):
            erreurs.append(f"étape {i} : « {e.get('cible')} » n'est pas une clé de la carte")
            continue
        if x and x.get("reserve_a_la_personne"):
            erreurs.append(f"étape {i} : « {x.get('nom')} » est réservé à la personne ({x['reserve_a_la_personne']})")
        if e["action"] == "choisir":
            opts = (x or {}).get("options") or []
            v = normal(e.get("valeur"))
            if not opts:
                erreurs.append(f"étape {i} : « {e.get('cible')} » n'est pas une liste déroulante")
            elif not any(normal(o) == v for o in opts) and not any(v and v in normal(o) for o in opts):
                erreurs.append(f"étape {i} : « {e.get('valeur')} » n'est pas une option de « {(x or {}).get('nom')} »")
        if e["action"] == "ecrire" and (x or {}).get("role") != "champ":
            erreurs.append(f"étape {i} : « {e.get('cible')} » n'est pas un champ où écrire")
    return erreurs


def _lire_json(texte):
    t = (texte or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    debut, fin = t.find("{"), t.rfind("}")
    return json.loads(t[debut:fin + 1]) if debut >= 0 and fin > debut else json.loads(t)


def _prix_deepseek(u):
    """$ d'une réponse DeepSeek Flash (tarif relevé le 05/10/2026 ; heures pleines 01-04 h et 06-10 h UTC en semaine : x2)."""
    t = datetime.now(timezone.utc)
    k = 2 if t.weekday() < 5 and (1 <= t.hour < 4 or 6 <= t.hour < 10) else 1
    return k * (int(u.get("prompt_cache_hit_tokens") or 0) * 0.003 + int(u.get("prompt_cache_miss_tokens") or 0) * 0.15
                + int(u.get("completion_tokens") or 0) * 0.6) / 1e6


def demander_modele(messages, poster=requests.post):
    """Le plan par DeepSeek Flash (clé du chatbot) ; secours Qwen 3.7 Flash (OpenRouter, clé plafonnée). Renvoie
    (texte, infos) ; lève RuntimeError si aucun ne répond."""
    essais = []
    if CONFIG.get("DEEPSEEK_API_KEY"):
        essais.append(("DeepSeek " + MODELE, CONFIG["DEEPSEEK_API_URL"], CONFIG["DEEPSEEK_API_KEY"],
                       {"model": MODELE, "thinking": {"type": "disabled"}}))
    cle_secours = os.environ.get("OPENROUTER_KEY_AGENT", "").strip().strip('"')
    if cle_secours:
        essais.append(("OpenRouter " + SECOURS[1], SECOURS[0], cle_secours, {"model": SECOURS[1], "usage": {"include": True}}))
    erreurs = []
    for nom, url, cle, extra in essais:
        corps = {"messages": messages, "temperature": 0, "max_tokens": 1500, "response_format": {"type": "json_object"}, **extra}
        t0 = time.time()
        try:
            r = poster(url, headers={"Authorization": f"Bearer {cle}"}, json=corps, timeout=DELAI_MODELE_S)
            if r.status_code != 200:
                erreurs.append(f"{nom} : {r.status_code} {r.text[:120]}")
                continue
            d = r.json()
            u = d.get("usage") or {}
            cout = float(u["cost"]) if "cost" in u else _prix_deepseek(u)
            return d["choices"][0]["message"].get("content") or "", {"modele": nom, "duree_s": round(time.time() - t0, 2),
                                                                     "cout_dollars": round(cout, 6)}
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as e:
            erreurs.append(f"{nom} : {e}"[:160])
    raise RuntimeError("; ".join(erreurs) or "aucun modèle configuré pour l'agent d'actions")


def planifier(objectif, carte, etat, retour=None, poster=requests.post):
    """Plan complet (dict) pour l'objectif. retour = ce qui n'a pas marché au tour précédent (le modèle corrige)."""
    messages = [{"role": "system", "content": SYSTEME.replace("{carte}", _carte_compacte(carte))},
                {"role": "user", "content": f"ÉTAT DE L'ÉCRAN : {json.dumps(etat, ensure_ascii=False)}\nOBJECTIF : {objectif}"}]
    if retour:
        messages.append({"role": "user", "content": f"Le plan précédent n'a pas marché : {retour}\nRenvoie un plan CORRIGÉ "
                                                    "pour ce qui reste à faire (même format JSON)."})
    texte, infos = demander_modele(messages, poster)
    try:
        plan = _lire_json(texte)
    except ValueError:
        plan = {"etapes": None, "brut": texte[:200]}
    return plan, infos


class Raccourcis:
    """Plans qui ont réussi, rejoués sans modèle pour la même demande et la même application (version de la carte)."""
    def __init__(self, fichier=FICHIER_RACCOURCIS):
        self.fichier, self.verrou = fichier, threading.Lock()

    def _lire(self):
        try:
            return json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    @staticmethod
    def cle(objectif, version):
        return f"{version}|{normal(objectif)}"

    def trouver(self, objectif, version):
        return self._lire().get(self.cle(objectif, version))

    def noter(self, objectif, version, plan):
        with self.verrou:
            d = self._lire()
            d[self.cle(objectif, version)] = {"etapes": plan.get("etapes", []), "dit": plan.get("dit", ""), "t": time.time()}
            if len(d) > MAX_RACCOURCIS:                       # les plus anciens partent
                for k in sorted(d, key=lambda k: d[k].get("t", 0))[:len(d) - MAX_RACCOURCIS]:
                    del d[k]
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            self.fichier.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    def oublier(self, objectif, version):
        with self.verrou:
            d = self._lire()
            if d.pop(self.cle(objectif, version), None) is not None:
                self.fichier.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


RACCOURCIS = Raccourcis()


async def faire(objectif, demander_page, planificateur=None, raccourcis=None):
    """Fait l'objectif dans la page. demander_page(dict) -> réponse de la page (async). planificateur(objectif, carte,
    etat, retour) -> (plan, infos) (sync, lancé à part). Renvoie le compte rendu pour l'agent vocal."""
    import asyncio
    objectif = str(objectif or "").strip()[:500]
    if not objectif:
        return {"ok": False, "erreur": "objectif vide : dis ce qu'il faut faire"}
    planificateur, raccourcis = planificateur or planifier, raccourcis or RACCOURCIS   # lus à l'appel (tests)
    t0, infos_modele, source = time.time(), [], "plan"
    r = await demander_page({"type": "page", "nom": "carte", "args": {}})
    temps = {"carte_s": round(time.time() - t0, 2), "page_s": 0.0}   # où passe le temps (journal)
    carte, etat = (r or {}).get("carte"), (r or {}).get("etat")
    if not isinstance(carte, dict) or not carte.get("ecrans"):
        e = str((r or {}).get("erreur") or "")
        if "inconnue" in e:                          # page d'avant la mise à jour : elle ne connaît pas encore « carte »
            return {"ok": False, "erreur": "la page n'est pas à jour : dis à la personne de recharger la page (F5) puis de relancer l'appel"}
        return {"ok": False, "erreur": f"la page n'a pas donné sa carte ({e or 'réponse vide'})"}
    version = carte.get("version", "")
    plan = raccourcis.trouver(objectif, version)
    if plan:
        source = "raccourci"
    retour = None
    for tour in range(CORRECTIONS + 1):
        if plan is None:
            try:
                plan, infos = await asyncio.to_thread(planificateur, objectif, carte, etat, retour)
            except RuntimeError as e:
                return {"ok": False, "erreur": f"le planificateur ne répond pas : {e}"[:240]}
            infos_modele.append(infos)
            source = "plan"
        if plan.get("impossible") and not plan.get("etapes"):
            return {"ok": False, "impossible": str(plan["impossible"])[:200], "dit": plan.get("dit"),
                    "duree_s": round(time.time() - t0, 1), "modeles": infos_modele}
        erreurs = controler(plan, carte)
        if erreurs:
            retour, plan = "plan refusé avant exécution : " + " ; ".join(erreurs[:5]), None
            continue
        if not plan["etapes"]:
            return {"ok": True, "fait": plan.get("dit") or "rien à faire : c'est déjà le cas", "etapes": 0, "source": source,
                    "duree_s": round(time.time() - t0, 1), "modeles": infos_modele}
        t_page = time.time()
        res = await demander_page({"type": "page", "nom": "executer_plan", "args": {"etapes": plan["etapes"]}})
        temps["page_s"] = round(temps["page_s"] + time.time() - t_page, 2)
        if (res or {}).get("ok"):
            if source == "plan":
                raccourcis.noter(objectif, version, plan)
            return {"ok": True, "fait": plan.get("dit") or "c'est fait", "etapes": len(plan["etapes"]), "source": source,
                    "faites": res.get("faites"), "duree_s": round(time.time() - t0, 1), "modeles": infos_modele, "temps": temps}
        if source == "raccourci":
            raccourcis.oublier(objectif, version)            # l'application a changé : on refait un plan
        retour = (f"arrêt à l'étape {(res or {}).get('etape')} ({(res or {}).get('action')} {(res or {}).get('cible')}) : "
                  f"{(res or {}).get('raison') or (res or {}).get('erreur') or 'la page ne répond pas'} ; déjà fait : "
                  f"{(res or {}).get('faites')}")
        etat = (res or {}).get("ecran") or etat
        plan = None
    return {"ok": False, "erreur": f"pas réussi après {CORRECTIONS} corrections : {retour}"[:300],
            "duree_s": round(time.time() - t0, 1), "modeles": infos_modele}
