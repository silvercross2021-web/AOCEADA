"""VOIX BAOULÉ sur GPU Cerebrium. OmniVoice (k2-fsa, licence CC-BY-NC, projet d'étude) imite une vraie voix baoulé.

18/10/2026 : DEUX voix au choix (Options > Voix du chatbot), réglage validé par l'essai ESSAI_VOIX_BAOULE (réglage C) :
  - « femme » : RK (WAXAL, studio), voix modèle de 9,9 s ;
  - « homme » : locuteur Common Voice 566016a2, voix modèle de 7,7 s ;
  32 étapes de fabrication. Compréhension mesurée par l'oreille baoulé : 10,5 % (femme) et 11,8 % (homme) de lettres
  fausses, comme la vraie voix (10,6 %) ; l'ancien réglage (voix modèle de 2,4 s, 8 étapes) en faisait 38,3 % et
  « déraillait » sur les phrases longues. Calcul : ~1 à 3 s par phrase sur la L4. Débit non modifié (demande du client).

Le chargement du modèle (ci-dessous, hors fonction) a lieu une fois par démarrage de la machine ; les poids sont gardés
dans /persistent-storage (téléchargés au tout premier démarrage seulement). Copie en fichiers RÉELS (local_dir) : le
stockage persistant de Cerebrium perd les liens symboliques du cache Hugging Face (constaté au 1er déploiement).
Appel : POST https://api.cerebrium.ai/v4/p-a50fe161/voix-baoule/fabriquer  {"texte": "...", "voix": "femme" | "homme"}
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
ETAPES = int(REF["etapes"])
MODELE = OmniVoice.from_pretrained(str(POIDS), device_map="cuda", dtype=torch.float16)
VOIX = {nom: MODELE.create_voice_clone_prompt(ref_audio=str(ICI / "voix" / v["fichier"]), ref_text=v["texte"])
        for nom, v in REF["voix"].items()}
CHARGEMENT_S = round(time.time() - _t, 1)


def fabriquer(texte: str, voix: str = "femme", etapes: int = ETAPES):
    if voix not in VOIX:
        return {"erreur": f"voix inconnue : {voix}"}
    t = time.time()
    audio = MODELE.generate(text=texte[:400], language="Baoulé", voice_clone_prompt=VOIX[voix], num_step=int(etapes))[0]
    torch.cuda.synchronize()
    calcul = time.time() - t
    tampon = io.BytesIO()
    sf.write(tampon, audio, 24000, format="WAV")
    return {"wav_b64": base64.b64encode(tampon.getvalue()).decode(), "calcul_s": round(calcul, 2),
            "audio_s": round(len(audio) / 24000, 1), "voix": voix, "etapes": int(etapes), "chargement_s": CHARGEMENT_S}


def fabriquer_lot(textes: list, voix: str = "femme", etapes: int = ETAPES):
    """Toutes les phrases d'une réponse en UN appel : un seul aller-retour réseau (~1,5 s depuis Abidjan) au lieu d'un
    par phrase. Une phrase en échec n'empêche pas les autres (sa place contient l'erreur)."""
    sortie = []
    for texte in textes[:12]:
        try:
            sortie.append(fabriquer(texte, voix, etapes))
        except Exception as e:
            sortie.append({"erreur": f"{type(e).__name__} : {e}"[:200]})
    return {"voix": sortie, "chargement_s": CHARGEMENT_S}


def reveil():
    """Appel vide : démarre la machine (et charge le modèle) AVANT la vraie demande de voix."""
    return {"pret": True, "chargement_s": CHARGEMENT_S, "voix": sorted(VOIX), "etapes": ETAPES}
