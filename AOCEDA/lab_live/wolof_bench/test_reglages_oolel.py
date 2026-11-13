import os
import sys
import json
import time
import requests
from pathlib import Path

bench_dir = Path(r"C:\Users\silve\Documents\PlatformIO\Projects\Test_ZMCT\AOCEDA\lab_live\wolof_bench")
out_dir = bench_dir / "resultats" / "tests_reglages"
out_dir.mkdir(parents=True, exist_ok=True)

url_call = "https://soynade-research-oolel-voices-demo.hf.space/gradio_api/call/generate_tts_audio"

def tester_appel(nom, texte, ref_audio, exag, temp, seed, cfg):
    print(f"\n--- Test: {nom} ---")
    payload = {
        "data": [
            texte,
            ref_audio,
            exag,
            temp,
            seed,
            cfg
        ]
    }
    t0 = time.time()
    try:
        r = requests.post(url_call, json=payload, timeout=25)
        print(f"POST status: {r.status_code}")
        if r.status_code != 200:
            print(f"POST error: {r.text[:200]}")
            return None
        event_id = r.json().get("event_id")
        if not event_id:
            print("Pas de event_id")
            return None
        res_url = f"{url_call}/{event_id}"
        for i in range(25):
            time.sleep(2)
            r_res = requests.get(res_url, timeout=25)
            if "data:" in r_res.text:
                for line in r_res.text.splitlines():
                    if line.startswith("data:"):
                        data_json = json.loads(line[5:].strip())
                        if isinstance(data_json, list) and len(data_json) > 0:
                            audio_info = data_json[0]
                            file_url = audio_info.get("url")
                            if file_url:
                                r_wav = requests.get(file_url, timeout=25)
                                out_file = out_dir / f"{nom}.wav"
                                out_file.write_bytes(r_wav.content)
                                dt = time.time() - t0
                                print(f"Succès {nom}: taille={len(r_wav.content)} octets, temps={dt:.2f}s, url={file_url}")
                                return out_file
        print(f"Timeout pour {nom}")
    except Exception as e:
        print(f"Exception {nom}: {e}")
    return None

if __name__ == "__main__":
    # Test 1: Brut sans ponctuation, ref=None (notre ancien appel)
    tester_appel("1_brut_sans_ref", "nanga diisoo ak sa jëkkër bala ngay def dara", None, 0.3, 0.2, 0, 0.5)
    
    # Test 2: Ponctué avec virgules, ref=None
    tester_appel("2_ponctue_sans_ref", "Nanga diisoo, ak sa jëkkër, bala ngay def dara.", None, 0.3, 0.2, 0, 0.5)
    
    # Test 3: Ponctué avec ref audio par défaut 8_1_c.wav
    tester_appel("3_ponctue_avec_ref_default", "Nanga diisoo, ak sa jëkkër, bala ngay def dara.", "8_1_c.wav", 0.3, 0.2, 0, 0.5)
    
    # Test 4: Ponctué avec ref et température plus naturelle (0.6) et cfg plus bas (0.35)
    tester_appel("4_calibre_naturel", "Nanga diisoo, ak sa jëkkër, bala ngay def dara.", "8_1_c.wav", 0.35, 0.6, 0, 0.35)
