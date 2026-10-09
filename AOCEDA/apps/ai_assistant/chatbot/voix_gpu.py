"""Voix BAOULÉ sur la carte graphique de Cerebrium (06/10/2026) : la même voix OmniVoice que sur le PC (voix modèle RK,
8 étapes), mais ~2 s par réponse au lieu de plusieurs minutes. Code du serveur : serveur_gpu\\cerebrium_voix\\.

Mesuré le 06/10/2026 depuis ce PC : machine allumée -> 1,7 à 2,4 s par phrase (dont 0,3-0,5 s de calcul, le reste est
le trajet Abidjan <-> États-Unis) ; machine éteinte (plus d'1 min sans voix) -> 35 s. D'où le RÉVEIL ANTICIPÉ : dès
qu'une conversation part en baoulé (menu, vocal entendu en baoulé, question baoulé), on réveille la machine ; pendant
que DeepSeek répond et que Google traduit, elle démarre.

Coût (plan Loisir) : ~1 $/heure de machine allumée, rien quand elle dort ; elle s'éteint 60 s après la dernière voix.

Clés (jamais écrites dans le code, jamais renvoyées à la page) :
  - CEREBRIUM_API_KEY : appeler le serveur de voix (clé d'inférence du projet) ;
  - CEREBRIUM_SERVICE_ACCOUNT_TOKEN (facultatif) : lire le crédit ; à défaut, la connexion faite sur ce PC avec
    « cerebrium login » (C:\\Users\\<vous>\\.cerebrium\\config.yaml), renouvelée par l'outil cerebrium quand elle expire.
CHATBOT_VOIX_BAOULE_GPU=0 coupe le GPU (retour à l'atelier du PC).

PLAFOND DU JOUR (audit du 09/10/2026) : la machine payante ne reste pas allumée plus de CHATBOT_GPU_MINUTES_JOUR minutes
par jour (120 par défaut, ~2 $) ; au-delà, la voix baoulé repasse sur l'atelier du PC jusqu'au lendemain. Compte gardé
sur le disque (cache/gpu_budget.json) : un redémarrage du serveur ne le remet pas à zéro.
"""
import base64
import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as DelaiDepasse
from datetime import date
from pathlib import Path

import requests

from .config import CACHE

PROJET = os.environ.get("CEREBRIUM_PROJECT", "p-a50fe161")
APP = "voix-baoule"
URL = f"https://api.cerebrium.ai/v4/{PROJET}/{APP}"
URL_GESTION = f"https://rest.cerebrium.ai/v2/projects/{PROJET}"
CONFIG_CLI = Path.home() / ".cerebrium" / "config.yaml"
OUTIL_CLI = Path.home() / ".cerebrium" / "bin" / "cerebrium.exe"
ETAPES = 8
DELAI_S = 120              # machine éteinte : ~35 s de démarrage ; au-delà de 2 min, on abandonne (repli sur le PC)
REVEIL_ESPACE_S = 45       # un réveil au plus toutes les 45 s (la machine reste allumée 60 s après chaque appel)
CREDIT_CACHE_S = 60
RENOUVELLEMENT_CLI_S = 600     # l'outil cerebrium (renouvellement de la connexion) n'est lancé qu'une fois par 10 min au plus
_etat = {"dernier_appel": 0.0, "reveil": None, "lots": {}, "verrou": threading.Lock(), "credit": None, "credit_t": 0.0,
         "echecs": 0, "derniere_erreur": None, "mesures": [], "cli_t": 0.0}
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="voix-gpu")
FICHIER_BUDGET = CACHE / "gpu_budget.json"
_budget = {"jour": None, "minutes": set(), "verrou": threading.Lock()}


class GpuIndisponible(Exception):
    pass


def _cle():
    return os.environ.get("CEREBRIUM_API_KEY", "").strip()


def minutes_max_jour():
    try:
        return max(0, int(os.environ.get("CHATBOT_GPU_MINUTES_JOUR", "120")))
    except ValueError:
        return 120


def _minutes_du_jour():
    """Minutes de la journée où la machine a été (ou sera) allumée par nos appels ; relues sur le disque au 1er usage."""
    jour = date.today().isoformat()
    if _budget["jour"] != jour:
        _budget["jour"], _budget["minutes"] = jour, set()
        try:
            d = json.loads(FICHIER_BUDGET.read_text(encoding="utf-8"))
            if d.get("jour") == jour:
                _budget["minutes"] = {int(m) for m in d.get("minutes", [])}
        except (OSError, ValueError, TypeError):
            pass
    return _budget["minutes"]


def budget_epuise():
    """Le plafond de minutes de machine allumée est-il atteint pour aujourd'hui ?"""
    with _budget["verrou"]:
        minutes = _minutes_du_jour()
        return len(minutes) >= minutes_max_jour() and int(time.time() // 60) not in minutes


def _compter_minutes():
    """Un appel allume la machine pour cette minute et la suivante (elle s'éteint 60 s après la dernière voix)."""
    with _budget["verrou"]:
        minutes = _minutes_du_jour()
        m = int(time.time() // 60)
        minutes.update((m, m + 1))
        try:
            FICHIER_BUDGET.parent.mkdir(parents=True, exist_ok=True)
            FICHIER_BUDGET.write_text(json.dumps({"jour": _budget["jour"], "minutes": sorted(minutes)}), encoding="utf-8")
        except OSError:
            pass


def configure():
    """Le GPU est-il configuré (clé présente et pas coupé par CHATBOT_VOIX_BAOULE_GPU=0) ?"""
    return bool(_cle()) and os.environ.get("CHATBOT_VOIX_BAOULE_GPU", "1") != "0"


def disponible():
    """Le GPU peut-il servir maintenant (configuré, plafond du jour non atteint) ? Ne dit pas s'il répond : voir fabriquer()."""
    return configure() and not budget_epuise()


def _appeler(fonction, donnees, delai=DELAI_S):
    if not configure():
        raise GpuIndisponible("GPU non configuré")
    if budget_epuise():
        raise GpuIndisponible(f"plafond du jour atteint ({minutes_max_jour()} min de machine allumée)")
    _compter_minutes()
    try:
        r = requests.post(f"{URL}/{fonction}", json=donnees, timeout=(10, delai),
                          headers={"Authorization": f"Bearer {_cle()}"})
    except requests.RequestException as e:
        _etat["echecs"] += 1
        _etat["derniere_erreur"] = f"réseau : {type(e).__name__}"
        raise GpuIndisponible(f"Cerebrium injoignable ({type(e).__name__})")
    if r.status_code != 200:
        _etat["echecs"] += 1
        _etat["derniere_erreur"] = f"HTTP {r.status_code}"
        raise GpuIndisponible(f"Cerebrium : HTTP {r.status_code} {r.text[:120]}")
    _etat["dernier_appel"] = time.time()
    _etat["echecs"], _etat["derniere_erreur"] = 0, None
    try:
        return r.json()["result"]
    except (ValueError, KeyError):
        raise GpuIndisponible("Cerebrium : réponse illisible")


def _wav(res):
    if not isinstance(res, dict) or res.get("erreur") or not res.get("wav_b64"):
        raise GpuIndisponible(f"Cerebrium : {(res or {}).get('erreur', 'voix vide')}"[:160])
    return base64.b64decode(res["wav_b64"])


def _noter(duree, phrases):
    _etat["mesures"] = (_etat["mesures"] + [{"duree_s": round(duree, 2), "phrases": phrases, "t": time.time()}])[-20:]


def fabriquer(texte):
    """Voix baoulé d'une phrase (WAV). Si un lot en cours contient déjà cette phrase, on attend ce lot (pas de 2e appel)."""
    with _etat["verrou"]:
        lot = _etat["lots"].get(texte)
    if lot is not None:
        try:
            return lot.result(timeout=DELAI_S + 15)
        except DelaiDepasse:                   # audit du 09/10/2026 : non rattrapé, il empêchait le secours sur le PC
            raise GpuIndisponible("Cerebrium : la voix du lot n'est pas venue à temps")
        except GpuIndisponible:
            pass                               # le lot a échoué : on retente cette phrase seule
    t = time.time()
    audio = _wav(_appeler("fabriquer", {"texte": texte, "etapes": ETAPES}))
    _noter(time.time() - t, 1)
    return audio


def annoncer(phrases):
    """Toutes les phrases d'une réponse partent en UN appel (un seul trajet réseau) ; fabriquer() les retrouve ensuite.
    Les phrases déjà demandées ne sont pas renvoyées. Renvoie le Future du lot (None si rien à faire)."""
    if not disponible():
        return None
    with _etat["verrou"]:
        nouvelles = [p for p in dict.fromkeys(phrases) if p and p not in _etat["lots"]]
        if not nouvelles:
            return None
        futurs = {p: Future() for p in nouvelles}
        _etat["lots"].update(futurs)

    def travail():
        t = time.time()
        try:
            res = _appeler("fabriquer_lot", {"textes": nouvelles, "etapes": ETAPES})
            sorties = res.get("voix") or []
            for i, p in enumerate(nouvelles):
                try:
                    futurs[p].set_result(_wav(sorties[i] if i < len(sorties) else None))
                except GpuIndisponible as e:
                    futurs[p].set_exception(e)
            _noter(time.time() - t, len(nouvelles))
        except Exception as e:
            for f in futurs.values():
                if not f.done():
                    f.set_exception(e if isinstance(e, GpuIndisponible) else GpuIndisponible(str(e)[:160]))
        finally:
            def oublier():                    # les voix sont sur le disque entre-temps (voix.py) : le lot peut partir
                time.sleep(300)
                with _etat["verrou"]:
                    for p, f in futurs.items():
                        if _etat["lots"].get(p) is f:
                            _etat["lots"].pop(p, None)
            threading.Thread(target=oublier, daemon=True).start()
    return _pool.submit(travail)


def reveiller(raison=""):
    """Réveille la machine en arrière-plan, sans attendre (au plus une fois toutes les 45 s ; inutile si elle vient de
    servir). Renvoie True si un réveil part."""
    if not disponible():
        return False
    with _etat["verrou"]:
        maintenant = time.time()
        en_cours = _etat["reveil"] is not None and not _etat["reveil"].done()
        if en_cours or maintenant - _etat["dernier_appel"] < REVEIL_ESPACE_S:
            return False
        _etat["dernier_appel"] = maintenant          # bloque les réveils en double pendant le démarrage

        def travail():
            try:
                _appeler("reveil", {}, delai=DELAI_S)
            except GpuIndisponible:
                pass
        _etat["reveil"] = _pool.submit(travail)
    return True


def eveille():
    """La machine a-t-elle servi il y a moins d'une minute (donc probablement encore allumée) ?"""
    return time.time() - _etat["dernier_appel"] < 55


# ── Crédit restant (bouton « Voix baoulé (GPU) » des Options) ──

def _jeton_gestion():
    """Jeton pour lire la facturation : compte de service s'il y en a un, sinon la connexion « cerebrium login » du PC."""
    jeton = os.environ.get("CEREBRIUM_SERVICE_ACCOUNT_TOKEN", "").strip()
    if jeton:
        return jeton
    for essai in range(2):
        if not CONFIG_CLI.exists():
            return None
        m = re.search(r"^accesstoken:\s*(\S+)", CONFIG_CLI.read_text(encoding="utf-8"), re.M)
        jeton = m.group(1) if m else None
        if jeton and _expire_dans(jeton) > 60:
            return jeton
        if essai == 0 and OUTIL_CLI.exists() and time.time() - _etat["cli_t"] > RENOUVELLEMENT_CLI_S:
            _etat["cli_t"] = time.time()             # expirée : l'outil cerebrium la renouvelle (une fois par 10 min au plus)
            try:
                subprocess.run([str(OUTIL_CLI), "projects", "list", "--no-color"], capture_output=True, timeout=40,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception:
                return None
    return None


def _expire_dans(jeton):
    try:
        charge = jeton.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(charge + "=" * (-len(charge) % 4))).get("exp", 0) - time.time()
    except Exception:
        return 0


def credit(forcer=False):
    """{"ok", "offert_usd", "depense_mois_usd", "restant_usd", "conversations_restantes", "heures_restantes", ...}.
    Gardé 60 s (Cerebrium met lui-même quelques minutes à compter)."""
    if not forcer and _etat["credit"] and time.time() - _etat["credit_t"] < CREDIT_CACHE_S:
        return _etat["credit"]
    jeton = _jeton_gestion()
    with _budget["verrou"]:
        minutes_jour = len(_minutes_du_jour())
    base = {"configure": configure(), "eveille": eveille(), "derniere_erreur": _etat["derniere_erreur"],
            "dernieres_mesures": [m["duree_s"] for m in _etat["mesures"][-5:]],
            "minutes_jour": minutes_jour, "minutes_max_jour": minutes_max_jour(), "plafond_atteint": budget_epuise()}
    if not jeton:
        return {**base, "ok": False, "raison": "Connexion à Cerebrium absente sur ce PC (cerebrium login) : crédit illisible."}
    try:
        r = requests.get(f"{URL_GESTION}/cost", headers={"Authorization": f"Bearer {jeton}"}, timeout=20)
        r.raise_for_status()
        d = r.json()
    except Exception as e:
        return {**base, "ok": False, "raison": f"Facturation Cerebrium illisible ({type(e).__name__})."}
    s = d.get("summary") or {}
    coupons = d.get("coupons") or []
    offert = sum(c.get("amount_cents", 0) for c in coupons) / 100
    reste_coupons = sum(c.get("amount_cents_remaining", 0) for c in coupons) / 100
    depense = (s.get("combined_cost_before_discounts_cents") or 0) / 100
    restant = max(0.0, round(reste_coupons - depense, 2))
    res = {**base, "ok": True, "offert_usd": round(offert, 2), "depense_mois_usd": round(depense, 2), "restant_usd": restant,
           "gpu_minutes_mois": round((s.get("total_gpu_seconds") or 0) / 60, 1),
           "constructions_mois": s.get("total_build_count") or 0,
           # ~1,02 $/h machine allumée (L4 + 4 vCPU + 16 Go) ; ~0,02 $ par conversation (réveil + voix + 60 s d'attente)
           "heures_restantes": round(restant / 1.02, 1), "conversations_restantes": int(restant / 0.02),
           "lu_a": time.strftime("%H:%M")}
    _etat["credit"], _etat["credit_t"] = res, time.time()
    return res
