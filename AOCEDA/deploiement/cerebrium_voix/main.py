"""VOIX BAOULÉ sur GPU Cerebrium (06/10/2026). Même voix que sur le PC : OmniVoice (k2-fsa, licence CC-BY-NC, projet
d'étude), voix modèle RK WAXAL courte clonée, 8 étapes. Mesuré sur Colab T4 : ~1 s de calcul pour 3 à 11 s de voix.

Le chargement du modèle (ci-dessous, hors fonction) a lieu une fois par démarrage de la machine ; les poids sont gardés
dans /persistent-storage (téléchargés au tout premier démarrage seulement). Copie en fichiers RÉELS (local_dir) : le
stockage persistant de Cerebrium perd les liens symboliques du cache Hugging Face (constaté au 1er déploiement).
Appel : POST https://api.cerebrium.ai/v4/p-a50fe161/voix-baoule/fabriquer  {"texte": "...", "etapes": 8}
"""
import base64
import io
import json
import time
from pathlib import Path

import soundfile as sf
import torch
from huggingface_hub import snapshot_download
from omnivoice import OmniVoice

ICI = Path(__file__).resolve().parent
POIDS = Path("/persistent-storage/omnivoice")
_t = time.time()
if not (POIDS / "model.safetensors").exists():
    snapshot_download("k2-fsa/OmniVoice", local_dir=str(POIDS))
REF = json.loads((ICI / "voix" / "reference.json").read_text(encoding="utf-8"))
MODELE = OmniVoice.from_pretrained(str(POIDS), device_map="cuda", dtype=torch.float16)
INVITE = MODELE.create_voice_clone_prompt(ref_audio=str(ICI / "voix" / REF["fichier"]), ref_text=REF["texte"])
CHARGEMENT_S = round(time.time() - _t, 1)


def fabriquer(texte: str, etapes: int = 8):
    t = time.time()
    audio = MODELE.generate(text=texte[:400], language="Baoulé", voice_clone_prompt=INVITE, num_step=etapes)[0]
    torch.cuda.synchronize()
    calcul = time.time() - t
    tampon = io.BytesIO()
    sf.write(tampon, audio, 24000, format="WAV")
    return {"wav_b64": base64.b64encode(tampon.getvalue()).decode(), "calcul_s": round(calcul, 2),
            "audio_s": round(len(audio) / 24000, 1), "chargement_s": CHARGEMENT_S}


def fabriquer_lot(textes: list, etapes: int = 8):
    """Toutes les phrases d'une réponse en UN appel : un seul aller-retour réseau (~1,5 s depuis Abidjan) au lieu d'un
    par phrase. Une phrase en échec n'empêche pas les autres (sa place contient l'erreur)."""
    sortie = []
    for texte in textes[:12]:
        try:
            sortie.append(fabriquer(texte, etapes))
        except Exception as e:
            sortie.append({"erreur": f"{type(e).__name__} : {e}"[:200]})
    return {"voix": sortie, "chargement_s": CHARGEMENT_S}


def reveil():
    """Appel vide : démarre la machine (et charge le modèle) AVANT la vraie demande de voix."""
    return {"pret": True, "chargement_s": CHARGEMENT_S}
