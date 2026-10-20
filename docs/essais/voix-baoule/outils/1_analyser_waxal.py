"""Extrait les enregistrements WAXAL baoulé présents sur le PC et mesure leur qualité.
Sortie : un dossier de WAV 16 kHz mono + un tableau (locuteur, durée, bruit de fond, niveau de voix, saturation)."""
import io, json, sys
from pathlib import Path
import numpy as np, soundfile as sf, pyarrow.parquet as pq

sys.stdout.reconfigure(encoding="utf-8")
SORTIE = Path(sys.argv[1]); SORTIE.mkdir(parents=True, exist_ok=True)
SOURCES = {"train": "D:/AOCEDA_IA_LAB/cache/waxal_bau_train_00000.parquet",
           "test": "D:/AOCEDA_IA_LAB/donnees/google__WaxalNLP/data/TTS/bau/bau-test-00003.parquet"}


def reechantillonner(x, sr, cible=16000):
    if sr == cible:
        return x
    n = int(len(x) * cible / sr)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


fiches = []
for jeu, f in SOURCES.items():
    for r in pq.read_table(f).to_pylist():
        x, sr = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        sat = float(np.mean(np.abs(x) > 0.99))
        # bruit / voix : énergie par fenêtres de 20 ms ; bruit = 10e centile, voix = 90e centile
        w = int(0.02 * sr); n = len(x) // w
        e = 10 * np.log10(np.mean(x[: n * w].reshape(n, w) ** 2, axis=1) + 1e-12)
        bruit, voix = np.percentile(e, 10), np.percentile(e, 90)
        y = reechantillonner(x, sr)
        nom = f"{r['id']}.wav"
        sf.write(SORTIE / nom, y, 16000)
        fiches.append({"id": r["id"], "jeu": jeu, "locuteur": r["speaker_id"], "fichier": nom, "sr_origine": sr,
                       "duree_s": round(len(x) / sr, 2), "bruit_db": round(float(bruit), 1), "voix_db": round(float(voix), 1),
                       "ecart_db": round(float(voix - bruit), 1), "saturation": round(sat * 100, 3), "texte": r["text"]})
(SORTIE / "fiches.json").write_text(json.dumps(fiches, ensure_ascii=False, indent=1), encoding="utf-8")
for f in sorted(fiches, key=lambda f: (f["locuteur"], f["duree_s"])):
    print(f"{f['locuteur']} {f['id']:24s} {f['jeu']:5s} {f['duree_s']:6.1f} s  écart voix/bruit {f['ecart_db']:5.1f} dB  "
          f"saturation {f['saturation']:.3f} %  {len(f['texte'])} car.  sr={f['sr_origine']}")
