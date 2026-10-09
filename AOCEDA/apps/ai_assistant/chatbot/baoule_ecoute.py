"""Écoute du BAOULÉ : Tree-AI-lab/omniASR-CTC-300M-baoule (Omnilingual 300M de Meta réentraîné UNIQUEMENT sur le
baoulé, enregistrements WAXAL ; Apache 2.0), compressé en int8 par tests/bancs/convertir_ecoute_baoule.py, sur le serveur,
hors ligne. Validé par le client le 29/09/2026 : plus léger et plus rapide que la version 1B, précision annoncée
presque égale (11,0 % de lettres fausses contre 10,6 %).

Même moteur que l'écoute dioula (dioula_ecoute.Moteur) : silences retirés, vocaux longs coupés aux pauses, lecture
limitée à l'alphabet latin, certitude de chaque mot, « preuve sonore ».
"""
from . import dioula_ecoute
from .config import MODELES

DOSSIER = MODELES / "omniasr-300m-baoule-int8"
MOTEUR = dioula_ecoute.Moteur(DOSSIER, "omniasr-300m-baoule")


def charger(fils=None):
    return MOTEUR.charger(fils)


def pret():
    return MOTEUR.pret()


def disponible():
    """Le modèle est-il sur le disque ? (sinon le chatbot marche sans l'écoute baoulé)"""
    return MOTEUR.disponible()


def transcrire_audio(audio, garder_probas=True, annulation=None):
    """Écoute BAOULÉ. audio : numpy float32 16 kHz mono. Renvoie un objet dioula_ecoute.Ecoute (annulation : voir
    dioula_ecoute.Annulation)."""
    return MOTEUR.transcrire_audio(audio, garder_probas, annulation)
