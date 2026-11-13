import shutil
import time
import wave
from pathlib import Path
from gradio_client import Client, handle_file

base_dir = Path(r"C:\Users\silve\Documents\PlatformIO\Projects\Test_ZMCT\AOCEDA")
bench_dir = base_dir / "lab_live" / "wolof_bench"
audios_dir = bench_dir / "audios_references"

# Assurer la présence de 8_1_c_officiel.wav
src_81c = audios_dir / "audio_03_studio_pro_femme.wav"
dst_81c = audios_dir / "8_1_c_officiel.wav"
if src_81c.exists() and not dst_81c.exists():
    shutil.copy(src_81c, dst_81c)
    print(f"Copié {src_81c.name} vers {dst_81c.name}")

print("Connexion au client Gradio Space...")
client = Client("soynade-research/Oolel-Voices-Demo")

texte_test = "Nanga diisoo, ak sa jëkkër, bala ngay def dara."
print(f"Texte à synthétiser: {texte_test}")

t0 = time.time()
result = client.predict(
    text_input=texte_test,
    audio_prompt_path_input=handle_file(str(dst_81c)),
    exaggeration_input=0.35,
    temperature_input=0.30,
    seed_num_input=0,
    cfgw_input=0.35,
    api_name="/generate_tts_audio"
)
dt = time.time() - t0
print(f"Génération terminée en {dt:.2f}s !")
print(f"Fichier résultat retourné: {result}")

# Analyser le fichier généré
with wave.open(result, "rb") as w:
    frames = w.getnframes()
    rate = w.getframerate()
    duration = frames / float(rate)
    print(f"Durée de l'audio généré avec référence officielle: {duration:.2f}s (Fréquence: {rate} Hz)")
