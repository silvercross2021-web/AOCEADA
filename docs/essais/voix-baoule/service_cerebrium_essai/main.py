"""SERVICE D'ESSAI de la voix baoulé (Cerebrium), SÉPARÉ du service du chatbot (voix-baoule).

Même modèle (OmniVoice, k2-fsa), même machine et mêmes versions que le service du chatbot ; seule différence : il
contient DEUX voix modèles pour comparer les réglages dans les mêmes conditions :
  - « ancienne » : la voix modèle actuelle du chatbot (RK, 2,4 s de parole) ;
  - « nouvelle » : RK, 9,9 s de parole (phrase 2 du passage WAXAL bau_RK_RK_BCI_4_228).
Appel : POST .../voix-baoule-essai/fabriquer  {"texte": "...", "voix": "ancienne" | "nouvelle", "etapes": 8 | 16 | 32}
"""
import base64
import io
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
MODELE = OmniVoice.from_pretrained(str(POIDS), device_map="cuda", dtype=torch.float16)
VOIX = {
    "ancienne": MODELE.create_voice_clone_prompt(
        ref_audio=str(ICI / "voix" / "ancienne.wav"), ref_text="Mi kpangɔ i dja be ti kukluku."),
    "nouvelle": MODELE.create_voice_clone_prompt(
        ref_audio=str(ICI / "voix" / "nouvelle.wav"),
        ref_text="Kanada ti famiɛn diwlɛ kun mɔ be fa mmla'n be sie i lɔ'n, mɔ famiɛn'n yɛ ɔ ti nvle'n i su kpɛn'n niɔn."),
    # Common Voice (Mozilla), locuteur 566016a2, clip common_voice_bci_41505820 : 7,7 s de parole
    "commonvoice": MODELE.create_voice_clone_prompt(
        ref_audio=str(ICI / "voix" / "commonvoice.wav"), ref_text="Nzue mʼɔ la nglo lɔ plaiiʼn ti kɛ kplo ufue sa."),
}
CHARGEMENT_S = round(time.time() - _t, 1)


def fabriquer(texte: str, voix: str = "nouvelle", etapes: int = 32):
    if voix not in VOIX:
        return {"erreur": f"voix inconnue : {voix}"}
    t = time.time()
    audio = MODELE.generate(text=texte[:600], language="Baoulé", voice_clone_prompt=VOIX[voix], num_step=int(etapes))[0]
    torch.cuda.synchronize()
    calcul = time.time() - t
    tampon = io.BytesIO()
    sf.write(tampon, audio, 24000, format="WAV")
    return {"wav_b64": base64.b64encode(tampon.getvalue()).decode(), "calcul_s": round(calcul, 2),
            "audio_s": round(len(audio) / 24000, 1), "voix": voix, "etapes": int(etapes), "chargement_s": CHARGEMENT_S}


def reveil():
    return {"pret": True, "chargement_s": CHARGEMENT_S}
