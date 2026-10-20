"""Probabilités lettre par lettre (toutes les 20 ms) de l'oreille baoulé (omniASR 300M) pour des WAV 16 kHz.
Sortie : <nom>.npy (log-probabilités [trames, jetons]) + jetons.json. Lancé avec le Python d'AOCEDA (onnxruntime)."""
import json, sys
from pathlib import Path
import numpy as np, soundfile as sf, onnxruntime as ort

M = Path("D:/AOCEDA_IA/modeles/omniasr-300m-baoule-int8")
SORTIE = Path(sys.argv[1]); SORTIE.mkdir(parents=True, exist_ok=True)
s = ort.InferenceSession(str(M / "model.int8.onnx"), providers=["CPUExecutionProvider"])
jet = []
for l in (M / "tokens.txt").read_text(encoding="utf-8").splitlines():
    t, _, n = l.rpartition(" "); jet.append((t, int(n)))
(SORTIE / "jetons.json").write_text(json.dumps([t for t, _ in sorted(jet, key=lambda x: x[1])], ensure_ascii=False), encoding="utf-8")
for f in sys.argv[2:]:
    a, sr = sf.read(f, dtype="float32")
    x = (a - a.mean()) / np.sqrt(a.var() + 1e-5)
    lg = s.run(None, {"x": x[None].astype(np.float32)})[0][0]
    lg = lg - lg.max(axis=1, keepdims=True); lp = lg - np.log(np.exp(lg).sum(axis=1, keepdims=True))
    np.save(SORTIE / (Path(f).stem + ".npy"), lp.astype(np.float32))
    print(Path(f).stem, lp.shape)
