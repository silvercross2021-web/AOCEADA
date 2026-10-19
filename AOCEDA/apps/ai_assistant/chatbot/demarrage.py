"""Préchargement de l'assistant : Whisper, les oreilles dioula et baoulé (Omnilingual), le carnet de mots baoulé, la liste
des voix et les connexions des traducteurs, en arrière-plan, pour que la 1re question n'attende pas (~10 s).

Lancé UNE fois, à la 1re ouverture de la page de l'assistant (/api/assistant/config), et pas au démarrage de Django :
les commandes (migrate, test, createsuperuser...) ne chargent jamais 1,5 Go de modèles pour rien.
"""
import threading
import time

from . import baoule_ecoute, baoule_lexique, baoule_relais, dioula_ecoute, dioula_relais, voix
from .journal import journaliser

PRET = {"whisper": False, "voix": False, "dioula": False, "baoule": False}
ESSAIS_WHISPER = 3
ATTENTE_NOUVEL_ESSAI_S = 20
_lance = threading.Event()
_verrou = threading.Lock()


def prechauffer():
    with _verrou:
        if _lance.is_set():
            return
        _lance.set()

    def travail():
        try:
            baoule_lexique.donnees()                       # carnet de mots baoulé (1 Mo) : chargé une fois
        except Exception as e:
            journaliser({"type": "demarrage", "erreur": f"carnet baoulé : {e}"[:200]})
        # AOCEDA, 19/10/2026 : mémoire du PC pleine au démarrage (« mkl_malloc: failed to allocate memory ») -> Whisper
        # n'était chargé qu'au 1er vocal, plusieurs secondes de plus pour la personne. On réessaie un peu plus tard.
        for essai in range(ESSAIS_WHISPER):
            try:
                voix.whisper(); PRET["whisper"] = True
                break
            except Exception as e:
                journaliser({"type": "demarrage", "erreur": f"Whisper (essai {essai + 1}) : {e}"[:200]})
                if essai + 1 < ESSAIS_WHISPER:
                    time.sleep(ATTENTE_NOUVEL_ESSAI_S)
        if dioula_ecoute.disponible():
            try:
                dioula_ecoute.charger(); PRET["dioula"] = True
            except Exception as e:
                journaliser({"type": "demarrage", "erreur": f"Omnilingual : {e}"[:200]})
        if baoule_ecoute.disponible():
            try:
                baoule_ecoute.charger(); PRET["baoule"] = True
            except Exception as e:
                journaliser({"type": "demarrage", "erreur": f"écoute baoulé : {e}"[:200]})
        dioula_relais.prechauffer()
        baoule_relais.prechauffer()
        try:
            voix.catalogue_voix(); PRET["voix"] = True
        except Exception as e:
            journaliser({"type": "demarrage", "erreur": f"voix : {e}"[:200]})
    threading.Thread(target=travail, daemon=True, name="assistant-prechauffage").start()
