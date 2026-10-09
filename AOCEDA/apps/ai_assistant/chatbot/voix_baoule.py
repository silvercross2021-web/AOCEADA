"""Voix BAOULÉ du chatbot.

06/10/2026 : d'abord la CARTE GRAPHIQUE Cerebrium (voix_gpu : même voix, ~2 s) ; l'atelier du PC ci-dessous ne sert plus
que de SECOURS (Cerebrium injoignable, crédit épuisé, GPU coupé par CHATBOT_VOIX_BAOULE_GPU=0).

Atelier du PC : pilote OmniVoice (omnivoice_atelier.py, programme à part avec le Python du labo).
- L'atelier est démarré À LA DEMANDE (1re voix baoulé) et s'arrête seul après 15 min sans travail (~3,5 Go rendus).
- Une seule phrase fabriquée à la fois, dans une file À PART : une voix baoulé de plusieurs minutes ne bloque jamais les
  voix des autres langues (quelques secondes).
- Les voix finies sont gardées sur le disque (cache\\tts) : une phrase déjà dite est instantanée.
- Lenteur connue et assumée : ~3 à 4 min par phrase sur ce PC. La page affiche le texte tout de suite et la voix
  arrive ensuite (« voix en préparation »).
"""
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from django.conf import settings

from . import voix_gpu
from .config import CACHE, DONNEES, MODELES, PAQUET

# Python qui a OmniVoice et PyTorch (réglage CHATBOT_PYTHON_OMNIVOICE du .env) ; vide = pas d'atelier sur ce serveur,
# la voix baoulé passe par le GPU Cerebrium seulement
PYTHON_LABO = Path(os.environ.get("CHATBOT_PYTHON_OMNIVOICE") or settings.CHATBOT_PYTHON_OMNIVOICE or "-introuvable-")
ATELIER = PAQUET / "omnivoice_atelier.py"
POIDS_OMNIVOICE = MODELES / "omnivoice_hf"     # cache Hugging Face d'OmniVoice pour l'atelier (~3,1 Go, facultatif)
PORT = int(os.environ.get("CHATBOT_PORT_OMNIVOICE", "8771"))
URL = f"http://127.0.0.1:{PORT}"
DEMARRAGE_MAX_S = 180            # chargement d'OmniVoice (3,3 Go) : ~10-60 s selon le disque
FABRICATION_MAX_S = 1200         # une phrase : ~3-4 min mesurées ; au-delà, abandon
ESTIMATION_S = 40                # durée d'une phrase avant la 1re mesure (30/09/2026, réglage rapide : 13 à 42 s)
_etat = {"process": None, "verrou": threading.Lock(), "file": 0, "durees": []}
_file = ThreadPoolExecutor(max_workers=1, thread_name_prefix="voix-baoule")    # une phrase à la fois


class AtelierIndisponible(Exception):
    pass


def disponible():
    """Une voix baoulé est-elle possible (GPU configuré, ou atelier du PC installé) ? CHATBOT_VOIX_BAOULE=0 coupe tout."""
    if os.environ.get("CHATBOT_VOIX_BAOULE", "1") == "0":
        return False
    return voix_gpu.disponible() or atelier_installe()


def atelier_installe():
    """OmniVoice est-il installé sur ce PC (Python du labo + voix de référence) ?"""
    return PYTHON_LABO.exists() and ATELIER.exists() and (DONNEES / "voix_baoule" / "reference.json").exists()


def moteur():
    """Où la prochaine voix sera fabriquée (affiché dans la page et le journal)."""
    return "gpu" if voix_gpu.disponible() else "pc"


def _vivant():
    try:
        return requests.get(URL + "/etat", timeout=2).json()
    except Exception:
        return None


def demarrer():
    """Démarre l'atelier s'il ne tourne pas, et attend qu'il soit prêt. Lève AtelierIndisponible."""
    with _etat["verrou"]:
        e = _vivant()
        if e and e.get("pret"):
            return
        if not atelier_installe() or os.environ.get("CHATBOT_VOIX_BAOULE", "1") == "0":
            raise AtelierIndisponible("OmniVoice n'est pas installé sur ce PC")
        p = _etat["process"]
        if p is None or p.poll() is not None:
            if _etat.get("journal"):                     # journal du démarrage précédent : refermé (audit du 09/10/2026)
                _etat["journal"].close()
            (CACHE / "tmp").mkdir(parents=True, exist_ok=True)
            journal = _etat["journal"] = open(CACHE / "tmp" / "omnivoice_atelier.log", "ab")
            # PRIORITÉ LA PLUS BASSE du système : l'atelier n'utilise le processeur que quand le chatbot n'en a pas besoin.
            # Bug vu le 30/09/2026 : à priorité normale, une transcription de 8 s de parole a pris 88 s (au lieu de 2 s)
            # et les traductions ont expiré pendant qu'OmniVoice fabriquait des voix.
            env = {**os.environ, "OMNIVOICE_HF_HOME": str(POIDS_OMNIVOICE), "CHATBOT_VOIX_BAOULE_DIR": str(DONNEES / "voix_baoule"),
                   "TMP": str(CACHE / "tmp"), "TEMP": str(CACHE / "tmp")}
            _etat["process"] = subprocess.Popen([str(PYTHON_LABO), "-u", str(ATELIER), str(PORT)], stdout=journal,
                                                stderr=subprocess.STDOUT, cwd=str(PAQUET), env=env,
                                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                                | getattr(subprocess, "IDLE_PRIORITY_CLASS", 0))
        t0 = time.time()
        while time.time() - t0 < DEMARRAGE_MAX_S:
            if _etat["process"].poll() is not None:
                raise AtelierIndisponible("l'atelier OmniVoice s'est arrêté au démarrage (voir cache\\tmp\\omnivoice_atelier.log)")
            e = _vivant()
            if e and e.get("pret"):
                return
            time.sleep(1)
        raise AtelierIndisponible("OmniVoice trop long à démarrer")


def fabriquer(texte):
    """Fabrique la voix baoulé d'un texte. Renvoie l'audio WAV. GPU Cerebrium d'abord (~2 s), sinon l'atelier du PC
    (plusieurs minutes). Lève AtelierIndisponible si aucun des deux ne marche."""
    erreur_gpu = None
    if voix_gpu.disponible():
        t = time.time()
        try:
            audio = voix_gpu.fabriquer(texte)
            _etat["durees"] = (_etat["durees"] + [time.time() - t])[-10:]
            _etat["dernier_moteur"] = "gpu"
            return audio
        except voix_gpu.GpuIndisponible as e:
            erreur_gpu = str(e)
    if not atelier_installe():
        raise AtelierIndisponible(f"GPU : {erreur_gpu}" if erreur_gpu else "OmniVoice n'est pas installé sur ce PC")
    _etat["dernier_moteur"] = "pc"
    return _fabriquer_pc(texte)


def _fabriquer_pc(texte):
    demarrer()
    t = time.time()
    try:
        r = requests.post(URL + "/voix", json={"texte": texte}, timeout=(5, FABRICATION_MAX_S))
    except requests.RequestException as e:
        raise AtelierIndisponible(f"OmniVoice : {e}"[:160])
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("audio"):
        raise AtelierIndisponible(f"OmniVoice : {r.status_code} {r.text[:120]}")
    _etat["durees"] = (_etat["durees"] + [time.time() - t])[-10:]
    return r.content


def soumettre(fonction, *args):
    """Met une fabrication dans la file baoulé (une à la fois). Renvoie un Future."""
    with _etat["verrou"]:
        _etat["file"] += 1

    def travail():
        try:
            return fonction(*args)
        finally:
            with _etat["verrou"]:
                _etat["file"] -= 1
    return _file.submit(travail)


def attente_estimee_s(rang=1):
    """Temps estimé avant qu'une voix placée au rang `rang` de la file soit prête."""
    if voix_gpu.disponible():                          # GPU : ~2 s machine allumée, ~35 s si elle dormait
        return 3 if voix_gpu.eveille() else 35
    d = _etat["durees"]
    moyenne = sum(d) / len(d) if d else ESTIMATION_S
    return int(moyenne * max(1, rang))


def arreter():
    """Arrête l'atelier (fin du serveur ou tests)."""
    p = _etat["process"]
    if p is not None and p.poll() is None:
        p.terminate()
    if _etat.get("journal"):
        _etat["journal"].close()
        _etat["journal"] = None
