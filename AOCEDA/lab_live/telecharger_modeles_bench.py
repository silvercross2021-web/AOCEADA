import os
import sys
from pathlib import Path
from decouple import Config, RepositoryEnv
from huggingface_hub import hf_hub_download

base_dir = Path(r"C:\Users\silve\Documents\PlatformIO\Projects\Test_ZMCT\AOCEDA")
env_file = base_dir / ".env"
env_config = Config(RepositoryEnv(env_file))
hf_token = env_config('HF_TOKEN', default=None)

bench_dir = base_dir / "lab_live" / "wolof_bench"
stt_dir = bench_dir / "modeles" / "stt" / "whisper_small_wolof_onnx"
tts_dir = bench_dir / "modeles" / "tts" / "speecht5_tts_wolof"

stt_dir.mkdir(parents=True, exist_ok=True)
tts_dir.mkdir(parents=True, exist_ok=True)

print("=== TÉLÉCHARGEMENT DES MODÈLES STT ET TTS DANS LE LAB ===")

# --- 1. STT : whisper-small-wolof-onnx (~375 Mo) ---
print("\n--- 1. TÉLÉCHARGEMENT DU MODÈLE STT : malinali-app/whisper-small-wolof-onnx ---")
stt_repo = "malinali-app/whisper-small-wolof-onnx"
stt_files = [
    "encoder.int8.onnx",
    "decoder.int8.onnx",
    "tokens.txt"
]

for fname in stt_files:
    dest = stt_dir / fname
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  [STT] Déjà présent : {fname} ({dest.stat().st_size / (1024*1024):.2f} Mo)")
    else:
        print(f"  [STT] Téléchargement de {fname} depuis {stt_repo}...")
        hf_hub_download(
            repo_id=stt_repo,
            filename=fname,
            local_dir=str(stt_dir),
            token=hf_token
        )
        print(f"  [STT] Terminé : {fname} ({dest.stat().st_size / (1024*1024):.2f} Mo)")

# --- 2. TTS : speecht5_tts-wolof (~578 Mo) ---
print("\n--- 2. TÉLÉCHARGEMENT DU MODÈLE TTS : bilalfaye/speecht5_tts-wolof ---")
tts_repo = "bilalfaye/speecht5_tts-wolof"
tts_files = [
    "model.safetensors",
    "spm_char.model",
    "config.json",
    "tokenizer_config.json",
    "special_tokens_map.json"
]

for fname in tts_files:
    dest = tts_dir / fname
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  [TTS] Déjà présent : {fname} ({dest.stat().st_size / (1024*1024):.2f} Mo)")
    else:
        print(f"  [TTS] Téléchargement de {fname} depuis {tts_repo}...")
        hf_hub_download(
            repo_id=tts_repo,
            filename=fname,
            local_dir=str(tts_dir),
            token=hf_token
        )
        print(f"  [TTS] Terminé : {fname} ({dest.stat().st_size / (1024*1024):.2f} Mo)")

print("\n=== TOUS LES MODÈLES ONT ÉTÉ TÉLÉCHARGÉS AVEC SUCCÈS DANS LEURS DOSSIERS RESPECTIFS ===")
