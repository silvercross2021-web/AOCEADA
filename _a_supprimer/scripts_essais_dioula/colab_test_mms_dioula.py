# ═══════════════════════════════════════════════════════════════════
# Test Meta MMS (ASR dioula) SANS RIEN TÉLÉCHARGER SUR TON PC
# À exécuter sur https://colab.research.google.com/ (gratuit, sans CB)
#
# Marche à suivre :
#   1. Va sur colab.research.google.com -> "Nouveau notebook"
#   2. Copie-colle chaque bloc "# %% Cellule N" ci-dessous dans une
#      cellule séparée, exécute-les dans l'ordre (Shift+Entrée)
#   3. Tout tourne sur les serveurs Google, gratuit, rien sur ton disque
# ═══════════════════════════════════════════════════════════════════

# %% Cellule 1 — Dépendances (torch est déjà présent sur Colab)
# !pip install -q transformers accelerate librosa requests

# %% Cellule 2 — Génère un audio dioula réel via LAMIA (LAfricaMobile)
# pour avoir un texte ET un son dont on connaît la bonne réponse,
# et vérifier si Meta MMS transcrit correctement ce même son.
import requests

texte_source_fr = "Bonjour, je suis l'assistant AOCEDA. Votre consommation ce mois-ci est de quarante-deux kilowattheures."

resp = requests.post(
    "https://translate.lafricamobile.com/translate",
    data={"inLang": "français", "outLang": "dioula", "text": texte_source_fr},
    headers={"User-Agent": "Mozilla/5.0"},
)
data = resp.json()
texte_dioula_attendu = data["translatedText"]
audio_url = data["vocalizeText"]
print("Texte dioula attendu (vérité de référence) :", texte_dioula_attendu)

audio_bytes = requests.get(audio_url).content
with open("test_dioula.wav", "wb") as f:
    f.write(audio_bytes)
print("Audio dioula sauvegardé :", len(audio_bytes), "octets")

# %% Cellule 3 — Charge Meta MMS (le téléchargement de ~4 Go se fait ICI,
# sur le disque du notebook Colab, PAS sur ton ordinateur)
import torch
from transformers import Wav2Vec2ForCTC, AutoProcessor

MODEL_ID = "facebook/mms-1b-all"  # remplace par "ikone22/mms-1b-dyula" pour tester l'autre piste

processor = AutoProcessor.from_pretrained(MODEL_ID, target_lang="dyu")
model = Wav2Vec2ForCTC.from_pretrained(MODEL_ID, target_lang="dyu",
                                       ignore_mismatched_sizes=True)
model.load_adapter("dyu")

# %% Cellule 4 — Transcrit l'audio dioula généré à la Cellule 2
import librosa

speech, sr = librosa.load("test_dioula.wav", sr=16000)  # MMS exige 16kHz
inputs = processor(speech, sampling_rate=16000, return_tensors="pt")

with torch.no_grad():
    logits = model(**inputs).logits
ids = torch.argmax(logits, dim=-1)[0]
transcription = processor.decode(ids)

print("\n=== RÉSULTAT ===")
print("Texte dioula ATTENDU (LAMIA)  :", texte_dioula_attendu)
print("Texte dioula TRANSCRIT (MMS) :", transcription)
