"""Pauses à l'intérieur de la phrase 3 du passage RK (36 s) : à chaque virgule, durée du silence et point de coupe."""
import json, re, sys, unicodedata
from pathlib import Path
import numpy as np, soundfile as sf, torch, torchaudio.functional as F

sys.stdout.reconfigure(encoding="utf-8")
ICI = Path(sys.argv[1])
jetons = json.loads((ICI / "emissions/jetons.json").read_text(encoding="utf-8"))
index = {t: i for i, t in enumerate(jetons) if len(t) == 1}
seg = [s for s in json.loads((ICI / "segments.json").read_text(encoding="utf-8")) if s["source"].endswith("4_228")]
p3 = seg[2]
lp = np.load(ICI / "emissions/bau_RK_RK_BCI_4_228.npy")
audio, _ = sf.read(ICI / "waxal/bau_RK_RK_BCI_4_228.wav", dtype="float32")
w = 320; n = len(audio) // w
e = 10 * np.log10(np.mean(audio[: n * w].reshape(n, w) ** 2, axis=1) + 1e-12)


def cibles(t):
    ids = []
    for c in unicodedata.normalize("NFC", t.lower()):
        if c in index:
            ids.append(index[c])
        elif c.isspace() and ids and ids[-1] != index[" "]:
            ids.append(index[" "])
    return ids


a0, b0 = int(p3["coupe_avant_s"] / 0.02), int(p3["coupe_apres_s"] / 0.02)
morceaux = [m.strip() for m in re.split(r"(?<=,)\s+", p3["texte"])]
toks, bornes = [], []
for m in morceaux:
    ids = cibles(m)
    if toks:
        toks.append(index[" "])
    bornes.append((len(toks), len(toks) + len(ids))); toks += ids
ali, _ = F.forced_align(torch.from_numpy(lp[a0:b0])[None], torch.tensor([toks], dtype=torch.int32), blank=0)
ali = ali[0].numpy()
pos, k = [], 0
prec = -1
for t, x in enumerate(ali):
    if x != 0 and x != prec and k < len(toks) and x == toks[k]:
        pos.append(t); k += 1
    prec = x
choix = []
for i in range(len(morceaux) - 1):
    fin, deb = a0 + pos[bornes[i][1] - 1] + 1, a0 + pos[bornes[i + 1][0]]
    coupe = fin + int(np.argmin(e[fin:deb + 1])) if deb > fin else fin
    texte_avant = " ".join(morceaux[: i + 1])
    print(f"après la virgule {i + 1} ({fin * 0.02:5.2f} s) : silence {(deb - fin) * 0.02:4.2f} s, niveau {e[coupe]:5.0f} dB, "
          f"1re partie {(fin - a0) * 0.02:4.1f} s / 2e {(b0 - deb) * 0.02:4.1f} s  …{texte_avant[-40:]}")
    choix.append({"i": i, "coupe_s": round(coupe * 0.02, 2), "silence_s": round((deb - fin) * 0.02, 2), "niveau_db": float(e[coupe]),
                  "partie1": texte_avant, "partie2": " ".join(morceaux[i + 1:]), "duree1": (fin - a0) * 0.02, "duree2": (b0 - deb) * 0.02})
(ICI / "pauses_phrase3.json").write_text(json.dumps(choix, ensure_ascii=False, indent=1), encoding="utf-8")
