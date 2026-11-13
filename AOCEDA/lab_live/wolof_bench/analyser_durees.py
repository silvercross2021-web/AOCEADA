import wave
from pathlib import Path

bench_dir = Path(r"C:\Users\silve\Documents\PlatformIO\Projects\Test_ZMCT\AOCEDA\lab_live\wolof_bench")
files = [
    bench_dir / "audios_references" / "audio_04_conseil_famille.wav",
    bench_dir / "comparaisons_audio" / "01_TEST_CONSEIL_SAGESSE" / "1_VOIX_HUMAINE_ORIGINALE.wav",
    bench_dir / "comparaisons_audio" / "01_TEST_CONSEIL_SAGESSE" / "2_SYNTHESE_IA_OOLEL_VOICES.wav",
    bench_dir / "comparaisons_audio" / "01_TEST_CONSEIL_SAGESSE" / "3_SYNTHESE_IA_SPEECHT5.wav",
    bench_dir / "resultats" / "tests_reglages" / "1_brut_sans_ref.wav",
    bench_dir / "resultats" / "tests_reglages" / "2_ponctue_sans_ref.wav"
]

print("=== ANALYSE COMPARATIVE DES DURÉES ET DU DÉBIT ===")
for f in files:
    if f.exists():
        with wave.open(str(f), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            channels = w.getnchannels()
            sampwidth = w.getsampwidth()
            duration = frames / float(rate)
            print(f"{f.name:32} | Durée: {duration:5.2f}s | Freq: {rate:5}Hz | Canaux: {channels} | Poids: {f.stat().st_size} o")
    else:
        print(f"{f.name:32} | INTROUVABLE")
