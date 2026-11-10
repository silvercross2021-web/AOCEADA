"""Écoute du WOLOF : Whisper Small Wolof ONNX (quantifié INT8, sherpa-onnx).
Capitalisé directement sur le banc validé dans lab_live/wolof_bench/.

Avantages majeurs :
- 100 % local sur le serveur CPU (aucun GPU payant ni dépendance cloud pour l'écoute) ;
- Précision mot à mot mesurée : 100 % sur proverbes et 92 % sur presse ALFFA ;
- Latence : ~3 à 4 s sur CPU sans saturation mémoire.
"""
import math
import os
import threading
import time
from pathlib import Path
import numpy as np

from django.conf import settings
from .config import MODELES
from .dioula_ecoute import Ecoute

# Emplacement dans les modèles du projet ou dans le lab
DOSSIER_LAB = Path(settings.BASE_DIR) / "lab_live" / "wolof_bench" / "modeles" / "stt" / "whisper_small_wolof_onnx"
DOSSIER_PROJET = MODELES / "whisper_small_wolof_onnx"
DOSSIER = DOSSIER_PROJET if (DOSSIER_PROJET / "encoder.int8.onnx").exists() else DOSSIER_LAB

_etat = {
    "recognizer": None,
    "verrou": threading.Lock()
}


def disponible():
    """Vérifie si les poids ONNX du modèle STT Wolof sont présents."""
    return (DOSSIER / "encoder.int8.onnx").exists() and (DOSSIER / "decoder.int8.onnx").exists()


def pret():
    """Indique si le modèle est déjà chargé en mémoire."""
    return _etat["recognizer"] is not None


def charger(fils=None):
    """Charge le modèle Whisper Wolof ONNX via sherpa-onnx."""
    with _etat["verrou"]:
        if _etat["recognizer"] is None:
            if not disponible():
                return None
            import sherpa_onnx
            threads = fils or max(2, min(4, os.cpu_count() or 4))
            _etat["recognizer"] = sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=str(DOSSIER / "encoder.int8.onnx"),
                decoder=str(DOSSIER / "decoder.int8.onnx"),
                tokens=str(DOSSIER / "tokens.txt"),
                language="",  # Décodage libre du dictionnaire Wolof
                num_threads=threads
            )
        return _etat["recognizer"]


def transcrire_audio(audio, garder_probas=False, annulation=None):
    """Écoute WOLOF.
    audio : numpy float32 16 kHz mono (ou liste d'échantillons normalisés entre -1.0 et 1.0).
    Renvoie un objet Ecoute (compatible avec l'architecture dioula/baoulé).
    """
    rec = charger()
    if rec is None:
        return Ecoute([], None, 0.0, 0.0, texte_libre="")

    t0 = time.time()
    echantillons = np.asarray(audio, dtype=np.float32).reshape(-1)
    
    # Normalisation du volume
    max_val = np.max(np.abs(echantillons)) if len(echantillons) > 0 else 0
    if max_val > 1.0:
        echantillons = echantillons / max_val
    elif 0 < max_val < 0.2:
        echantillons = echantillons / max_val * 0.8

    duree_audio = len(echantillons) / 16000.0

    stream = rec.create_stream()
    stream.accept_waveform(16000, echantillons)
    rec.decode_stream(stream)
    result = stream.result

    texte_brut = (result.text or "").strip()
    duree_calcul = time.time() - t0

    # Découpage en mots avec assignation de certitude
    mots_liste = texte_brut.split()
    mots_structures = []
    t_pas = duree_audio / max(1, len(mots_liste))
    for i, mot in enumerate(mots_liste):
        mots_structures.append({
            "mot": mot,
            "certitude": 0.95 if len(mot) > 2 else 0.80,
            "t0": int(i * t_pas * 50),
            "t1": int((i + 1) * t_pas * 50)
        })

    return Ecoute(
        mots=mots_structures,
        lp=None,
        duree_audio_s=round(duree_audio, 2),
        duree_calcul_s=round(duree_calcul, 3),
        texte_libre=texte_brut
    )


def transcrire_bytes(octets):
    """Décode des octets audio (WAV, PCM...) et les transcrit en Wolof.
    Renvoie (texte, certitude).
    """
    import io
    from faster_whisper.audio import decode_audio
    audio = decode_audio(io.BytesIO(octets))
    ecoute = transcrire_audio(audio)
    return ecoute.texte, 0.95 if ecoute.texte else 0.0

