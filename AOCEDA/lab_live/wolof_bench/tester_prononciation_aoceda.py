import sys
from pathlib import Path
from decouple import Config, RepositoryEnv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from gradio_client import Client, handle_file

base_dir = Path(r"C:\Users\silve\Documents\PlatformIO\Projects\Test_ZMCT\AOCEDA")
env_file = base_dir / ".env"
env_config = Config(RepositoryEnv(env_file))
hf_token = env_config("HF_TOKEN", default=None)

bench_dir = base_dir / "lab_live" / "wolof_bench"
audios_dir = bench_dir / "audios_references"
ref_officielle = audios_dir / "8_1_c_prompt_6s.wav"
out_dir = bench_dir / "resultats" / "tests_aoceda"
out_dir.mkdir(parents=True, exist_ok=True)

# Différentes variantes d'écriture phonétique d'AOCEDA
variantes = [
    ("1_brut_AOCEDA", "AOCEDA dafay saytu sa kuraŋ, ba noppi, di la xamal sa koppar."),
    ("2_phonetique_Aoseda", "Aoseda dafay saytu sa kuraŋ, ba noppi, di la xamal sa koppar."),
    ("3_phonetique_Aosedaa", "Aoséda dafay saytu sa kuraŋ, ba noppi, di la xamal sa koppar."),
    ("4_epele_A_O_C_E_D_A", "A, O, C, E, D, A, dafay saytu sa kuraŋ, ba noppi, di la xamal sa koppar."),
    ("5_tirets_A_o_se_da", "A-o-sé-da dafay saytu sa kuraŋ, ba noppi, di la xamal sa koppar.")
]

client = Client("soynade-research/Oolel-Voices-Demo", token=hf_token, httpx_kwargs={"timeout": 180.0})

for nom, texte in variantes:
    print(f"\n--- Test de prononciation: {nom} ---")
    print(f"Texte envoyé: {texte}")
    try:
        res = client.predict(
            text_input=texte,
            audio_prompt_path_input=handle_file(str(ref_officielle)),
            exaggeration_input=0.35,
            temperature_input=0.30,
            seed_num_input=0,
            cfgw_input=0.35,
            api_name="/generate_tts_audio"
        )
        dst = out_dir / f"{nom}.wav"
        import shutil
        shutil.copy(res, dst)
        print(f"  -> Généré avec succès: {dst.name} ({dst.stat().st_size} octets)")
    except Exception as e:
        print(f"  -> Erreur: {e}")
