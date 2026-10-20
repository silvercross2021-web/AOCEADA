"""Débit et intonation de A (vraie voix), B et C (voix générées).
- durée de parole : temps où la voix est présente (silences retirés) ;
- débit : lettres du texte par seconde de parole (comparé à la vraie voix) ;
- intonation : étendue de la mélodie de la voix, en demi-tons (écart-type de la hauteur sur les moments voisés) :
  une voix « plate » a une petite étendue, une voix vivante une plus grande.
Lancé avec un Python qui a torchaudio (ex. D:\\AOCEDA_IA_LAB\\env_omnivoice\\Scripts\\python.exe)."""
import json, sys
from pathlib import Path
import numpy as np, soundfile as sf, torch, torchaudio.functional as F

sys.stdout.reconfigure(encoding="utf-8")
E = Path(__file__).resolve().parents[1]


def mesurer(f):
    x, sr = sf.read(f, dtype="float32")
    x = x.mean(axis=1) if x.ndim > 1 else x
    w = int(0.02 * sr); n = len(x) // w
    e = 10 * np.log10(np.mean(x[: n * w].reshape(n, w) ** 2, axis=1) + 1e-12)
    parole = e > (np.percentile(e, 95) - 35)                       # trames de 20 ms où la voix est présente
    f0 = F.detect_pitch_frequency(torch.from_numpy(x)[None], sr, frame_time=0.02, freq_low=70, freq_high=400)[0].numpy()
    m = min(len(f0), len(parole))
    f0, actif = f0[:m], parole[:m] & (f0[:m] > 70) & (f0[:m] < 400)
    demi_tons = 12 * np.log2(f0[actif] / np.median(f0[actif])) if actif.sum() > 10 else np.array([0.0])
    return {"duree_parole_s": round(parole.sum() * 0.02, 2), "hauteur_mediane_hz": round(float(np.median(f0[actif])), 0) if actif.sum() else 0,
            "etendue_demi_tons": round(float(np.std(demi_tons)), 2)}


res = []
for d in sorted((E / "3_COMPARAISONS_A_ECOUTER").iterdir()):
    lettres = len([c for c in (d / "texte.txt").read_text(encoding="utf-8") if c.isalpha()])
    for f in sorted(d.glob("*.wav")):
        m = mesurer(f); m["debit_lettres_s"] = round(lettres / max(0.1, m["duree_parole_s"]), 1)
        res.append({"dossier": d.name, "fichier": f.name, **m})
        print(f"{d.name:36s} {f.name[:1]}  parole {m['duree_parole_s']:5.1f} s  débit {m['debit_lettres_s']:4.1f} lettres/s  "
              f"hauteur {m['hauteur_mediane_hz']:4.0f} Hz  étendue {m['etendue_demi_tons']:.2f} demi-tons")
(E / "4_RESULTATS" / "mesures_debit_intonation.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
