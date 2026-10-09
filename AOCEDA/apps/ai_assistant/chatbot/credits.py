"""Crédits des services payants de l'assistant (Options > Crédits des services), lus chez chaque service par le serveur :
  - DeepSeek (chat écrit et vocal)   : solde du compte (GET /user/balance, clé DEEPSEEK_API_KEY) ;
  - OpenRouter (secours de l'agent)  : crédit du compte (GET /api/v1/credits, clé de gestion OPENROUTER_MANAGEMENT_KEY)
                                       et plafond restant de la clé de l'agent (GET /api/v1/key, OPENROUTER_KEY_AGENT) ;
  - Cerebrium (voix baoulé sur GPU)  : voix_gpu.credit() (compte de service, sinon la connexion « cerebrium login »).
Jamais une clé dans la réponse. Gardés 60 s (relecture à la demande : bouton Actualiser).
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from django.conf import settings

from . import voix_gpu

GARDE_S = 60
DELAI_S = 15
_cache = {"t": 0.0, "valeur": None}
_verrou = threading.Lock()


def _deepseek():
    cle = settings.DEEPSEEK_API_KEY
    if not cle:
        return {"ok": False, "raison": "Clé DeepSeek absente du fichier .env (DEEPSEEK_API_KEY)."}
    try:
        r = requests.get(settings.DEEPSEEK_API_URL.split("/chat/")[0].rstrip("/") + "/user/balance",
                         headers={"Authorization": f"Bearer {cle}"}, timeout=DELAI_S)
        r.raise_for_status()
        d = r.json()
    except Exception as e:
        return {"ok": False, "raison": f"Solde DeepSeek illisible ({type(e).__name__})."}
    infos = d.get("balance_infos") or [{}]
    i = next((x for x in infos if x.get("currency") == "USD"), infos[0])
    return {"ok": True, "disponible": bool(d.get("is_available")), "devise": i.get("currency") or "USD",
            "solde": float(i.get("total_balance") or 0), "recharge": float(i.get("topped_up_balance") or 0),
            "offert": float(i.get("granted_balance") or 0)}


def _openrouter():
    res = {"ok": False}
    gestion, agent = settings.OPENROUTER_MANAGEMENT_KEY, settings.OPENROUTER_KEY_AGENT
    if gestion:
        try:
            r = requests.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {gestion}"},
                             timeout=DELAI_S)
            r.raise_for_status()
            d = r.json().get("data") or {}
            achete, utilise = float(d.get("total_credits") or 0), float(d.get("total_usage") or 0)
            res.update(ok=True, achete=round(achete, 2), utilise=round(utilise, 2), restant=round(achete - utilise, 2))
        except Exception as e:
            res["raison"] = f"Crédit OpenRouter illisible ({type(e).__name__})."
    else:
        res["raison"] = "Clé de gestion OpenRouter absente du fichier .env (OPENROUTER_MANAGEMENT_KEY)."
    if agent:
        try:
            r = requests.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {agent}"}, timeout=DELAI_S)
            r.raise_for_status()
            d = r.json().get("data") or {}
            res["agent"] = {"plafond": d.get("limit"), "restant": d.get("limit_remaining"),
                            "utilise": round(float(d.get("usage") or 0), 3)}
        except Exception:
            pass
    return res


def tous(forcer=False, forcer_cerebrium=False):
    """{"deepseek", "openrouter", "cerebrium", "lu_a"} ; jamais de clé."""
    with _verrou:
        if not forcer and _cache["valeur"] and time.time() - _cache["t"] < GARDE_S:
            return _cache["valeur"]
    with ThreadPoolExecutor(max_workers=3) as fils:            # les trois services lus en même temps
        ds, orr = fils.submit(_deepseek), fils.submit(_openrouter)
        gpu = fils.submit(voix_gpu.credit, forcer=forcer_cerebrium)
        valeur = {"deepseek": ds.result(), "openrouter": orr.result(), "cerebrium": gpu.result(),
                  "lu_a": time.strftime("%H:%M")}
    with _verrou:
        _cache.update(t=time.time(), valeur=valeur)
    return valeur
