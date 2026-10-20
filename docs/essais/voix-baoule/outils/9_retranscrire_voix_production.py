"""Retranscription des voix du chatbot « en service » (dossier 6_VOIX_EN_PRODUCTION_A_ECOUTER, 18/10/2026).

Même méthode que 7_mesurer_comprehension.py : l'oreille baoulé du chatbot (omniASR 300M) réécoute chaque voix, on garde ce qu'elle a
compris (« lu ») et le pourcentage de lettres différentes du texte exact. Écrit 4_RESULTATS/mesures_production.json.
Ajouté le 19/10/2026 : les pourcentages de l'essai (12,1 / 5,4 / 9,1 / 14,2 / 14,0 pour la voix de femme ; 10,3 / 6,9 / 9,8 / 13,0 / 10,1
pour celle d'homme) étaient notés dans le LISEZ-MOI sans le texte compris.

Lancé depuis AOCEDA, avec le Python du projet (variable ESSAI = dossier ESSAI_VOIX_BAOULE) :
    set ESSAI=C:\\chemin\\ESSAI_VOIX_BAOULE
    .venv_local\\Scripts\\python.exe manage.py shell -c "exec(open(r'docs\\essais\\voix-baoule\\outils\\9_retranscrire_voix_production.py', encoding='utf-8').read())"
"""
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from apps.ai_assistant.chatbot import baoule_ecoute

sys.stdout.reconfigure(encoding="utf-8")
E = Path(os.environ["ESSAI"]).resolve()


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


baoule_ecoute.charger()
resultats = []
for f in sorted((E / "6_VOIX_EN_PRODUCTION_A_ECOUTER").glob("*.wav")):
    num = f.name.split("_")[1]
    dossier = next(d for d in (E / "3_COMPARAISONS_A_ECOUTER").iterdir() if d.name.startswith(f"phrase_{num}_"))
    ref = norme((dossier / "texte.txt").read_text(encoding="utf-8"))
    lu = baoule_ecoute.transcrire_audio(en16k(f)).texte
    cer = round(100 * dist(norme(lu), ref) / max(1, len(ref)), 1)
    resultats.append({"fichier": f.name, "phrase": int(num), "genre": "femme" if "FEMME" in f.name else "homme", "cer": cer, "lu": lu})
    print(f"{f.name:34s} {cer:5.1f} %")
(E / "4_RESULTATS" / "mesures_production.json").write_text(json.dumps(resultats, ensure_ascii=False, indent=1), encoding="utf-8")
