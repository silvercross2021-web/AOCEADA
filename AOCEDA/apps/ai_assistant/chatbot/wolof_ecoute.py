"""Écoute du WOLOF : Whisper Small Wolof ONNX (quantifié INT8, sherpa-onnx), sur le serveur (aucun GPU payant).

Modèle : malinali-app/whisper-small-wolof-onnx (licence MIT), installé par `manage.py installer_modeles_ia` dans
`modeles/whisper_small_wolof_onnx` (empreintes SHA-256 vérifiées). Sans lui, l'écoute wolof est simplement indisponible
et la page le dit (`disponible()`).

Mesures du 10/11/2026 (audit, 67 extraits ALFFA, 2 locuteurs) : 22 % de mots faux, 9 % de lettres fausses. Trois défauts
trouvés ce jour-là et corrigés ici :
  - le modèle « entendait » du texte dans du bruit (7 bruits sur 8 transcrits) : la parole est maintenant cherchée AVANT
    le modèle (`parole_presente`), et un texte en boucle est écarté (`_en_boucle`) ;
  - un vocal de plus de 30 s dépassait la fenêtre de Whisper (313 % de mots faux) : il est coupé aux pauses
    (`MORCEAU_MAX_S`) ;
  - la « certitude » était inventée (0,95 / 0,80 selon la longueur du mot) : ce modèle ne donne aucune probabilité,
    la certitude vaut donc None (« non mesurée ») et aucun mot n'est dit « douteux ».
"""
import os
import re
import threading
import time
from pathlib import Path

import numpy as np
from django.conf import settings

from .config import MODELES
from .dioula_ecoute import Annulee, Ecoute, _energie_db, decouper_aux_silences, remonter_volume, retirer_silences

# Dossier des modèles du projet (installateur). L'ancien dossier du laboratoire reste lu s'il existe (PC du propriétaire).
DOSSIER_PROJET = MODELES / "whisper_small_wolof_onnx"
DOSSIER_LAB = Path(settings.BASE_DIR) / "lab_live" / "wolof_bench" / "modeles" / "stt" / "whisper_small_wolof_onnx"
FICHIERS = ("encoder.int8.onnx", "decoder.int8.onnx", "tokens.txt")

TAUX = 16000
MORCEAU_MAX_S, MORCEAU_MIN_S = 25, 8     # Whisper lit 30 s au plus : on coupe aux pauses avant
# Parole ou bruit ? Écart entre les trames fortes et faibles (p90 - p10, en dB) et part des trames à plus de 8 dB au-dessus
# du fond. Mesuré le 10/11/2026 : bruits purs (silence, souffle, bruit blanc ou rose, 50 Hz, clic, ventilateur) ≤ 5,7 dB et
# part ≤ 0,02 ; parole propre (40 wolof, 40 baoulé) ≥ 26,8 dB ; parole avec bruit blanc ajouté à 10 dB ≥ 13 dB et à 5 dB
# ≥ 8,5 dB (part ≥ 0,12) ; à 0 dB (inintelligible) 4,8 à 5,5 dB. Un premier réglage (12 dB / 0,08 à +15 dB) écartait des
# paroles à 10 dB de bruit (3 sur 20) : seuils placés entre les bruits purs et la parole à 5 dB.
DYNAMIQUE_MIN_DB, PART_FORTE_MIN, ECART_FORT_DB = 7.0, 0.06, 8.0

_etat = {"recognizer": None, "verrou": threading.Lock()}


def dossier():
    """Dossier où se trouve le modèle (celui du projet d'abord), ou None s'il n'est installé nulle part."""
    for d in (DOSSIER_PROJET, DOSSIER_LAB):
        if all((d / f).is_file() for f in FICHIERS):
            return d
    return None


def disponible():
    """Le modèle ET la bibliothèque sherpa-onnx sont-ils là ? (sinon : pas d'écoute wolof, et la page le dit)"""
    if dossier() is None:
        return False
    try:
        import sherpa_onnx  # noqa: F401
    except ImportError:
        return False
    return True


def pret():
    """Indique si le modèle est déjà chargé en mémoire."""
    return _etat["recognizer"] is not None


def charger(fils=None):
    """Charge le modèle Whisper Wolof ONNX via sherpa-onnx (None s'il n'est pas installé)."""
    with _etat["verrou"]:
        if _etat["recognizer"] is None:
            if not disponible():
                return None
            import sherpa_onnx
            d = dossier()
            _etat["recognizer"] = sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=str(d / "encoder.int8.onnx"), decoder=str(d / "decoder.int8.onnx"), tokens=str(d / "tokens.txt"),
                language="",  # décodage libre : le modèle a été ajusté sur le wolof
                num_threads=fils or max(2, min(4, os.cpu_count() or 4)))
        return _etat["recognizer"]


class EcouteWolof(Ecoute):
    """Écoute sans probabilités : la certitude n'est PAS mesurée (None), jamais inventée."""

    @property
    def certitude(self):
        return None


def parole_presente(audio):
    """Y a-t-il de la parole dans ce son ? (bruit régulier, souffle, bourdonnement, silence : non)"""
    if len(audio) < int(0.25 * TAUX):
        return False
    db = _energie_db(audio)
    p10, p90 = np.percentile(db, 10), np.percentile(db, 90)
    return bool(p90 - p10 >= DYNAMIQUE_MIN_DB and float((db > p10 + ECART_FORT_DB).mean()) >= PART_FORTE_MIN)


def _en_boucle(texte):
    """Whisper qui tourne en rond (« masin di sini masin di sini… ») : un groupe de 1 à 4 mots répété 4 fois d'affilée."""
    mots = texte.lower().split()
    for n in (1, 2, 3, 4):
        for i in range(len(mots) - 4 * n + 1):
            if mots[i:i + n] * 4 == mots[i:i + 4 * n]:
                return True
    return False


def transcrire_audio(audio, garder_probas=False, annulation=None):
    """Écoute WOLOF. audio : numpy float32 16 kHz mono. Renvoie une Ecoute (comme le dioula et le baoulé), vide s'il
    n'y a pas de parole. `annulation` : l'écoute s'arrête entre deux morceaux (elle lève alors Annulee)."""
    t0 = time.time()
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    duree = round(len(audio) / TAUX, 2)

    def vide():
        return EcouteWolof([], None, duree, round(time.time() - t0, 3), texte_libre="")

    rec = charger()
    if rec is None:
        return vide()
    crete = float(np.abs(audio).max()) if len(audio) else 0.0
    if crete > 1.0:
        audio = audio / crete
    audio = remonter_volume(audio)                       # micro lointain : volume remonté (jamais un vrai silence)
    if not parole_presente(audio):
        return vide()
    utile = retirer_silences(audio)
    if len(utile) < int(0.25 * TAUX):
        return vide()
    textes = []
    for morceau in decouper_aux_silences(utile, maxi_s=MORCEAU_MAX_S, mini_s=MORCEAU_MIN_S):
        if annulation is not None and annulation.annulee:
            raise Annulee()
        stream = rec.create_stream()
        stream.accept_waveform(TAUX, morceau)
        rec.decode_stream(stream)
        t = re.sub(r"\s+", " ", stream.result.text or "").strip()
        if t and not _en_boucle(t):
            textes.append(t)
    texte = " ".join(textes)
    mots, pas = texte.split(), (len(utile) / TAUX) / max(1, len(texte.split()))
    # t0 / t1 : positions RÉPARTIES également (le modèle ne date pas les mots) ; certitude None = non mesurée
    structures = [{"mot": m, "certitude": None, "t0": int(i * pas * 50), "t1": int((i + 1) * pas * 50)}
                  for i, m in enumerate(mots)]
    return EcouteWolof(structures, None, duree, round(time.time() - t0, 3), texte_libre=texte)


def transcrire_bytes(octets):
    """Décode des octets audio et les transcrit en wolof. Renvoie (texte, certitude) ; la certitude est None (non mesurée)."""
    import io
    from faster_whisper.audio import decode_audio
    ecoute = transcrire_audio(decode_audio(io.BytesIO(octets)))
    return ecoute.texte, None
