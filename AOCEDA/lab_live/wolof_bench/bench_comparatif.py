import os
import sys
import json
import time
import requests
from pathlib import Path

# Setup paths
base_dir = Path(r"C:\Users\silve\Documents\PlatformIO\Projects\Test_ZMCT\AOCEDA")
bench_dir = base_dir / "lab_live" / "wolof_bench"
audios_dir = bench_dir / "audios_references"
stt_dir = bench_dir / "modeles" / "stt" / "whisper_small_wolof_onnx"
tts_dir = bench_dir / "modeles" / "tts" / "speecht5_tts_wolof"
results_dir = bench_dir / "resultats"
results_dir.mkdir(parents=True, exist_ok=True)

# 1. Calcul du WER (Word Error Rate)
def calcul_wer(reference, hypothese):
    r = reference.lower().split()
    h = hypothese.lower().split()
    # Levenshtein distance sur mots
    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            if r[i - 1] == h[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                d[i][j] = 1 + min(d[i - 1][j], d[i][j - 1], d[i - 1][j - 1])
    return d[len(r)][len(h)] / max(1, len(r))

# 2. Traduction Wolof -> Français via Relais Google
def traduire_wo_vers_fr(texte_wolof):
    url = "https://clients5.google.com/translate_a/t"
    params = {
        "client": "dict-chrome-ex",
        "sl": "wo",
        "tl": "fr",
        "q": texte_wolof
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            res = r.json()
            if isinstance(res, list) and len(res) > 0:
                if isinstance(res[0], list):
                    return "".join([part[0] for part in res if isinstance(part, list) and len(part) > 0])
                elif isinstance(res[0], str):
                    return res[0]
            return str(res)
    except Exception as e:
        return f"Erreur traduction: {e}"
    return texte_wolof

# 3. Synthèse Vocale Oolel-Voices via Space ZeroGPU
def synthese_oolel(texte_wolof, nom_sortie="synthese_oolel.wav", ref_wav_url=None):
    url_call = "https://soynade-research-oolel-voices-demo.hf.space/gradio_api/call/generate_tts_audio"
    payload = {
        "data": [
            texte_wolof[:400],
            None, # ref audio default
            0.3,  # exaggeration
            0.2,  # temperature
            0,    # seed
            0.5   # cfg
        ]
    }
    try:
        t0 = time.time()
        r = requests.post(url_call, json=payload, timeout=20)
        if r.status_code == 200:
            event_id = r.json().get("event_id")
            if event_id:
                res_url = f"{url_call}/{event_id}"
                for _ in range(15):
                    time.sleep(2)
                    r_res = requests.get(res_url, timeout=20)
                    if "data:" in r_res.text:
                        # Extract audio url
                        for line in r_res.text.splitlines():
                            if line.startswith("data:"):
                                data_json = json.loads(line[5:].strip())
                                if isinstance(data_json, list) and len(data_json) > 0:
                                    audio_info = data_json[0]
                                    file_url = audio_info.get("url")
                                    if file_url:
                                        r_wav = requests.get(file_url, timeout=20)
                                        out_path = results_dir / nom_sortie
                                        out_path.write_bytes(r_wav.content)
                                        dt = time.time() - t0
                                        return str(out_path), len(r_wav.content), dt
    except Exception as e:
        print(f"Erreur Oolel: {e}")
    return None, 0, 0
