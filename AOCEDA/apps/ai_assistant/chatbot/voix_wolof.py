"""Voix WOLOF du chatbot sur GPU Cerebrium (Oolel-Voices, T3 LLaMA + S3Gen).
Entièrement aligné sur l'architecture Cerebrium du projet AOCEDA.

Caractéristiques techniques :
- Application Cerebrium dédiée : 'voix-wolof' (isolée de 'voix-baoule') ;
- Audio prompt de référence : 8_1_c_prompt_6s.wav (voix studio officielle Soynade) ;
- Pacing / CFG Weight : 0.35, Température : 0.30, Exagération : 0.35 ;
- Règle phonétique stricte : « AOCEDA » -> « A-o-sé-da » avant tout appel ;
- Cache disque automatique dans cache/tts (0 ms de latence sur les phrases connues) ;
- Réveil anticipé du GPU en arrière-plan pendant que DeepSeek rédige la réponse.
"""
import base64
import hashlib
import io
import json
import os
import threading
import time
from datetime import date
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from django.conf import settings

from . import wolof_texte
from .config import CACHE

# Session HTTP Keep-Alive persistante vers api.cerebrium.ai (évite ~250 ms de renégociation TLS à chaque phrase)
_ORIG_POST = requests.post
_http = requests.Session()
_adaptateur_http = HTTPAdapter(pool_connections=2, pool_maxsize=8)
_http.mount("https://", _adaptateur_http)
_http.mount("http://", _adaptateur_http)


def _post_cerebrium(url, **kwargs):
    """Réutilise le pool TLS Keep-Alive en production, tout en respectant un monkeypatch éventuel de requests.post en test."""
    if requests.post is _ORIG_POST:
        return _http.post(url, **kwargs)
    return requests.post(url, **kwargs)

DOSSIER_TTS = CACHE / "tts"
DOSSIER_TTS.mkdir(parents=True, exist_ok=True)

# Configuration Cerebrium
PROJET = os.environ.get("CEREBRIUM_PROJECT", "p-a50fe161")
APP = "voix-wolof"
URL_CEREBRIUM = f"https://api.cerebrium.ai/v4/{PROJET}/{APP}"
DELAI_S = 120
REVEIL_ESPACE_S = 45
MAX_CAR = 380       # le service Cerebrium lit 400 caractères au plus ; au-delà il COUPAIT la phrase sans rien dire
                    # (audit du 10/11/2026 : des réponses de 434 caractères perdaient leur fin)

_etat = {
    "verrou": threading.Lock(),
    "dernier_appel": 0.0,
    "dernier_reveil": 0.0,
    "moteur": "oolel-voices-cerebrium"
}
_taches = {"en_cours": {}, "echecs": {}, "verrou": threading.Lock()}
_pool_wolof = None
ATTENTE_APRES_ECHEC_S = 120


class ErreurVoix(Exception):
    """Erreur levée en cas d'échec de synthèse vocale Wolof."""
    pass


def _cle():
    """Récupère la clé d'API Cerebrium."""
    return os.environ.get("CEREBRIUM_API_KEY", "").strip()


def configure():
    """Indique si Cerebrium est configuré avec une clé valide."""
    return bool(_cle()) and os.environ.get("CHATBOT_VOIX_WOLOF_GPU", "1") != "0"


def disponible():
    """La voix wolof peut-elle être fabriquée ? (GPU Cerebrium configuré ; avant le 10/11/2026 : toujours « oui », même
    sans clé : la page annonçait une voix qui n'existait pas.) Une phrase déjà en cache reste lisible sans GPU."""
    return configure()


def moteur():
    """Nom du moteur affiché dans les journaux et diagnostics."""
    return _etat["moteur"]


def _pool():
    global _pool_wolof
    if _pool_wolof is None:
        from concurrent.futures import ThreadPoolExecutor
        _pool_wolof = ThreadPoolExecutor(max_workers=6, thread_name_prefix="voix-wolof")
    return _pool_wolof


def reveiller_voix_wolof(raison=""):
    """Réveil ANTICIPÉ du GPU Wolof sur Cerebrium (min_replicas 0 -> 1).
    Déclenché dès qu'un vocal ou une question Wolof est détecté.
    """
    if not configure():
        return False
    maintenant = time.time()
    with _etat["verrou"]:
        if maintenant - _etat["dernier_reveil"] < REVEIL_ESPACE_S:
            return False
        _etat["dernier_reveil"] = maintenant

    def appel_reveil():
        try:
            r = _post_cerebrium(
                f"{URL_CEREBRIUM}/reveil",
                json={},
                timeout=60,
                headers={"Authorization": f"Bearer {_cle()}"}
            )
            if r.status_code == 200:
                with _etat["verrou"]:
                    _etat["dernier_appel"] = time.time()
        except Exception:
            pass

    threading.Thread(target=appel_reveil, daemon=True, name="cerebrium-reveil-wolof").start()
    return True


def cle_cache(texte):
    """Calcule l'empreinte unique d'une phrase pour le cache disque local."""
    h = hashlib.sha256(texte.strip().encode("utf-8")).hexdigest()[:16]
    return DOSSIER_TTS / f"wo_{h}.wav"


def attente_estimee_s():
    """Estimation du temps restant selon l'état de démarrage du GPU."""
    maintenant = time.time()
    with _etat["verrou"]:
        dr = _etat.get("dernier_reveil", 0.0)
    ecoule = maintenant - dr
    if ecoule < 40:
        return max(5, int(40 - ecoule))
    return 35


def decouper_long(texte, maxi=MAX_CAR):
    """Coupe un texte trop long en morceaux d'au plus `maxi` caractères, à la fin d'une phrase, sinon à une virgule,
    sinon à un espace : jamais au milieu d'un mot."""
    texte = (texte or "").strip()
    morceaux = []
    while len(texte) > maxi:
        zone = texte[:maxi]
        i = max((zone.rfind(c) for c in (". ", "! ", "? ", "; ")), default=-1)
        if i < maxi // 3:
            i = max(zone.rfind(", "), zone.rfind(" "))
        i = i + 1 if i >= maxi // 3 else maxi
        morceaux.append(texte[:i].strip())
        texte = texte[i:].strip()
    return morceaux + [texte] if texte else morceaux


def assembler_wav(wavs):
    """Un seul WAV à partir de plusieurs (mêmes réglages, ce que fabrique le service), avec un court silence entre eux."""
    import wave
    sortie, params, silence = io.BytesIO(), None, b""
    with wave.open(sortie, "wb") as out:
        for i, octets in enumerate(wavs):
            with wave.open(io.BytesIO(octets)) as w:
                if params is None:
                    params = w.getparams()
                    out.setparams(params)
                    silence = bytes(1) * (int(params.framerate * 0.25) * params.nchannels * params.sampwidth)
                if i:
                    out.writeframes(silence)
                out.writeframes(w.readframes(w.getnframes()))
    return sortie.getvalue()


def fabriquer(texte, genre="femme"):
    """Génère la voix Wolof Oolel-Voices sur GPU Cerebrium.
    Applique la normalisation phonétique AOCEDA -> A-o-sé-da.
    Renvoie les octets du fichier WAV 22050 Hz. Un texte de plus de MAX_CAR caractères est fabriqué en plusieurs
    morceaux, puis recollé : plus rien n'est coupé.
    """
    if not texte or not texte.strip():
        return b""
    morceaux = decouper_long(wolof_texte.normaliser_phonetique_tts(texte))
    if len(morceaux) > 1:
        return assembler_wav([_fabriquer_un(m, genre) for m in morceaux])
    return _fabriquer_un(texte, genre)


def _fabriquer_un(texte, genre="femme"):
    """Un texte de MAX_CAR caractères au plus (voir fabriquer)."""

    # 1. Règle d'or : normalisation phonétique [s]
    texte_corrige = wolof_texte.normaliser_phonetique_tts(texte)

    # 2. Vérification du cache disque local (0 ms, 0 $)
    fichier_cache = cle_cache(texte_corrige)
    if fichier_cache.exists() and fichier_cache.stat().st_size > 0:
        return fichier_cache.read_bytes()

    t0 = time.time()

    # 3. Appel GPU Cerebrium prioritaire
    if configure():
        try:
            r = _post_cerebrium(
                f"{URL_CEREBRIUM}/fabriquer",
                json={
                    "texte": texte_corrige,
                    "voix": genre,
                    "pacing": 0.35,
                    "temperature": 0.30,
                    "exaggeration": 0.35
                },
                timeout=(10, DELAI_S),
                headers={"Authorization": f"Bearer {_cle()}"}
            )
            if r.status_code == 200:
                data = r.json()
                res = data.get("result", data) if isinstance(data, dict) else {}
                wav_b64 = res.get("wav_b64") if isinstance(res, dict) else None
                if wav_b64:
                    octets = base64.b64decode(wav_b64)
                    if octets:
                        fichier_cache.write_bytes(octets)
                        return octets
                if isinstance(res, dict) and "erreur" in res:
                    raise ErreurVoix(f"Cerebrium Oolel-Voices : {res['erreur']}")
            elif r.status_code in (401, 402, 403, 429) and any(m in r.text.lower() for m in ("credit", "crédit", "quota", "billing", "payment")):
                # crédit épuisé : dit tel quel (avant, une simple « panne » : impossible de savoir qu'il fallait recharger)
                raise ErreurVoix(f"Crédit Cerebrium épuisé ou plafond atteint (HTTP {r.status_code}) : rechargez le compte")
            elif r.status_code != 200:
                raise ErreurVoix(f"Cerebrium HTTP {r.status_code} : {r.text[:120]}")
        except requests.exceptions.RequestException as e:
            raise ErreurVoix(f"Cerebrium injoignable : {e}")

    # 4. Secours local si déjà en cache
    if fichier_cache.exists() and fichier_cache.stat().st_size > 0:
        return fichier_cache.read_bytes()

    raise ErreurVoix("Voix Wolof indisponible (Cerebrium non configuré ou sans réponse)")


def obtenir(texte, genre="femme"):
    """Interface standard appelée par views.py et service_dioula.
    Renvoie (octets_audio, infos_dict).
    """
    texte_corrige = wolof_texte.normaliser_phonetique_tts(texte)
    fichier_cache = cle_cache(texte_corrige)
    en_cache = fichier_cache.exists() and fichier_cache.stat().st_size > 0

    t0 = time.time()
    octets = fabriquer(texte, genre)
    duree = round(time.time() - t0, 2)

    infos = {
        "moteur": "cache" if en_cache else "cerebrium-oolel-voices",
        "voix": "femme-dakar-studio",
        "cache": en_cache,
        "duree_s": duree,
        "mime": "audio/wav"
    }
    return octets, infos


def demander_reponse(texte, genre="femme"):
    """Vérifie si la voix wolof est prête ou lance sa fabrication en arrière-plan.
    Renvoie (etat, tache) avec etat in ("prete", "preparation", "echec").
    """
    from concurrent.futures import Future
    texte_corrige = wolof_texte.normaliser_phonetique_tts(texte)
    f_cache = cle_cache(texte_corrige)
    if f_cache.exists() and f_cache.stat().st_size > 0:
        fut = Future()
        infos = {"moteur": "cache", "voix": "femme-dakar-studio", "cache": True, "duree_s": 0.0, "mime": "audio/wav"}
        fut.set_result((f_cache.read_bytes(), infos))
        return "prete", fut

    cle = (genre, texte_corrige)
    with _taches["verrou"]:
        maintenant = time.time()
        if maintenant - _taches["echecs"].get(cle, 0) < ATTENTE_APRES_ECHEC_S:
            fut = Future()
            fut.set_exception(ErreurVoix("Échec récent de la voix wolof (réessayez dans 2 minutes)"))
            return "echec", fut

        tache = _taches["en_cours"].get(cle)
        if tache is None:
            tache = _pool().submit(obtenir, texte, genre)
            _taches["en_cours"][cle] = tache

            def _apres(f, c=cle):
                with _taches["verrou"]:
                    _taches["en_cours"].pop(c, None)
                    if f.exception() is not None:
                        _taches["echecs"][c] = time.time()

            tache.add_done_callback(_apres)

    if tache.done():
        if tache.exception() is not None:
            return "echec", tache
        return "prete", tache

    return "preparation", tache


def annoncer(texte, genre="femme"):
    """Lance la fabrication en arrière-plan dès la fin de rédaction DeepSeek."""
    if not configure() or not texte:
        return None
    return demander_reponse(texte, genre)


def fabriquer_lot(phrases, genre="femme"):
    """Synthétise une liste de phrases en parallèle avec mise en cache disque.
    Renvoie un dictionnaire {phrase: octets_wav}.
    """
    if not phrases:
        return {}
    phrases_uniques = list(dict.fromkeys(phrases))
    resultats = {}
    futures = {}
    pool = _pool()
    for p in phrases_uniques:
        if not p or not p.strip():
            continue
        corrige = wolof_texte.normaliser_phonetique_tts(p)
        cache_f = cle_cache(corrige)
        if cache_f.exists() and cache_f.stat().st_size > 0:
            resultats[p] = cache_f.read_bytes()
        else:
            futures[p] = pool.submit(fabriquer, p, genre)
    for p, f in futures.items():
        try:
            resultats[p] = f.result(timeout=DELAI_S)
        except Exception:
            resultats[p] = b""
    return resultats


def annoncer_lot(phrases, genre="femme"):
    """Pré-génère en arrière-plan toutes les phrases d'une réponse."""
    if not configure() or not phrases:
        return None
    for p in phrases:
        if p and p.strip():
            annoncer(p, genre)

