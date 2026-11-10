"""VOIX WOLOF sur GPU Cerebrium : Oolel-Voices (Soynade Research).

Modèle : soynade-research/Oolel-Voices (T3 LLaMA + S3Gen).
Audio prompt studio de référence : 8_1_c_prompt_6s.wav (locutrice dakaroise).
Pacing / CFG : 0.35 (débit posé anti-rush).
Température : 0.30, Exagération : 0.35.
Phonétique : « AOCEDA » -> « A-o-sé-da ».

Stockage persistant : /persistent-storage/oolel_voices (téléchargé une seule fois).
Appel : POST https://api.cerebrium.ai/v4/<PROJET>/voix-wolof/fabriquer  {"texte": "..."}
"""
import base64
import io
import os
import re
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from huggingface_hub import snapshot_download
from transformers import AutoModel

ICI = Path(__file__).resolve().parent
PROMPT_AUDIO = ICI / "voix" / "8_1_c_prompt_6s.wav"

POIDS = Path("/persistent-storage/oolel_voices")
_t = time.time()

# 1. Téléchargement unique dans le stockage persistant Cerebrium si nécessaire
try:
    if not POIDS.exists() or not (POIDS / "config.json").exists():
        POIDS.mkdir(parents=True, exist_ok=True)
        snapshot_download(repo_id="soynade-research/Oolel-Voices", local_dir=str(POIDS))
    dossier_source = str(POIDS)
except Exception as e:
    dossier_source = "soynade-research/Oolel-Voices"

# 2. Chargement du modèle sur GPU
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MODELE = AutoModel.from_pretrained(dossier_source, trust_remote_code=True)
if hasattr(MODELE, "to") and DEVICE == "cuda":
    MODELE = MODELE.to(DEVICE)

CHARGEMENT_S = round(time.time() - _t, 1)


def normaliser_phonetique(texte: str) -> str:
    """Remplace strictement AOCEDA par A-o-sé-da pour une prononciation [s] pure."""
    if not texte:
        return ""
    return re.sub(r"\bAOCEDA\b", "A-o-sé-da", texte, flags=re.IGNORECASE)


def fabriquer(texte: str, voix: str = "femme", pacing: float = 0.35, temperature: float = 0.30, exaggeration: float = 0.35):
    """Génère la voix Wolof Oolel-Voices sur GPU Cerebrium.
    Renvoie un dictionnaire avec le fichier WAV encodé en base64.
    """
    texte_corrige = normaliser_phonetique(texte)
    if not texte_corrige.strip():
        return {"erreur": "texte vide"}

    t0 = time.time()
    try:
        prompt_path = str(PROMPT_AUDIO) if PROMPT_AUDIO.exists() else None

        # Génération audio via Oolel-Voices
        wav = MODELE.generate(
            texte_corrige[:400],
            audio_prompt_path=prompt_path,
            cfg_weight=float(pacing),
            exaggeration=float(exaggeration),
            temperature=float(temperature),
        )

        if DEVICE == "cuda":
            torch.cuda.synchronize()

        calcul = round(time.time() - t0, 2)
        sr = getattr(MODELE, "sr", 22050)

        # Conversion tenseur PyTorch / tableau numpy
        if isinstance(wav, torch.Tensor):
            wav_np = wav.detach().cpu().squeeze().numpy()
        else:
            wav_np = np.asarray(wav).squeeze()

        # Écriture WAV en mémoire
        tampon = io.BytesIO()
        sf.write(tampon, wav_np, sr, format="WAV")
        wav_bytes = tampon.getvalue()
        duree = len(wav_np) / float(sr)

        return {
            "wav_b64": base64.b64encode(wav_bytes).decode("utf-8"),
            "calcul_s": calcul,
            "audio_s": round(duree, 2),
            "moteur": "oolel-voices-cerebrium",
            "voix": "femme-dakar-studio",
            "chargement_s": CHARGEMENT_S,
        }
    except Exception as e:
        return {"erreur": f"{type(e).__name__} : {e}"[:300]}


def fabriquer_lot(textes: list, voix: str = "femme"):
    """Synthétise plusieurs phrases en un seul aller-retour réseau."""
    resultats = []
    for t in textes[:12]:
        resultats.append(fabriquer(t, voix))
    return {"voix": resultats, "chargement_s": CHARGEMENT_S}


def reveil():
    """Réveil anticipé : allume la machine Cerebrium avant que DeepSeek ne termine sa réponse."""
    return {"pret": True, "chargement_s": CHARGEMENT_S, "moteur": "oolel-voices-cerebrium"}
