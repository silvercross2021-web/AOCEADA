"""Compréhension : l'oreille baoulé du chatbot (omniASR 300M, même réglage que dans AOCEDA) réécoute A, B et C ;
on compte les lettres différentes du texte exact (CER). Lancé dans le shell Django d'AOCEDA :
  .venv_local\\Scripts\\python.exe manage.py shell -c "exec(open(r'..\\ESSAI_VOIX_BAOULE\\5_OUTILS\\mesurer_comprehension.py', encoding='utf-8').read())" """
import json, re, sys
from pathlib import Path
import numpy as np, soundfile as sf
from apps.ai_assistant.chatbot import baoule_ecoute

sys.stdout.reconfigure(encoding="utf-8")
E = Path(r"..\ESSAI_VOIX_BAOULE").resolve()


def norme(t):
    t = t.replace("’", "'").replace("ʼ", "'").lower()
    t = re.sub(r"[^\w' ]", " ", t)
    return " ".join(t.split())


def dist(a, b):
    d = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        p, d[0] = d[0], i
        for j, y in enumerate(b, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (x != y))
    return d[-1]


def en16k(f):
    x, sr = sf.read(f, dtype="float32")
    x = x.mean(axis=1) if x.ndim > 1 else x
    if sr != 16000:
        x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * 16000 / sr)), np.arange(len(x)), x).astype(np.float32)
    return x


import os
SEULES = os.environ.get("ESSAI_LETTRES", "")          # ex. « D » : ne mesurer que ces versions, garder les autres
f_res = E / "4_RESULTATS" / "mesures_comprehension.json"
baoule_ecoute.charger()
resultats = [r for r in json.loads(f_res.read_text(encoding="utf-8")) if r["fichier"][0] not in SEULES] if SEULES and f_res.exists() else []
for d in sorted((E / "3_COMPARAISONS_A_ECOUTER").iterdir()):
    ref = norme((d / "texte.txt").read_text(encoding="utf-8"))
    for f in sorted(d.glob("*.wav")):
        if SEULES and f.name[0] not in SEULES:
            continue
        lu = baoule_ecoute.transcrire_audio(en16k(f)).texte
        cer = dist(norme(lu), ref) / max(1, len(ref))
        resultats.append({"dossier": d.name, "fichier": f.name, "cer": round(100 * cer, 1), "lu": lu})
        print(f"{d.name:36s} {f.name[:1]}  {100 * cer:5.1f} % de lettres différentes")
f_res.write_text(json.dumps(sorted(resultats, key=lambda r: (r["dossier"], r["fichier"])), ensure_ascii=False, indent=1), encoding="utf-8")
