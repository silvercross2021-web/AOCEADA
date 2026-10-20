"""Aligne le texte exact de chaque enregistrement RK sur le son (alignement CTC forcé, torchaudio) et repère les
phrases du long passage. Vérifie aussi que chaque texte correspond bien à son audio (lecture de l'oreille vs texte).
Sortie : segments.json (début / fin de chaque phrase, en secondes, silences autour)."""
import json, re, sys, unicodedata
from pathlib import Path
import numpy as np, soundfile as sf, torch, torchaudio.functional as F

sys.stdout.reconfigure(encoding="utf-8")
ICI = Path(sys.argv[1]); EM = ICI / "emissions"; WAV = ICI / "waxal"
jetons = json.loads((EM / "jetons.json").read_text(encoding="utf-8"))
index = {t: i for i, t in enumerate(jetons) if len(t) == 1}
fiches = {f["id"]: f for f in json.loads((WAV / "fiches.json").read_text(encoding="utf-8"))}
TRAME = 0.02


def nettoyer(t):
    t = re.sub(r"\[\d+\]", "", t)                       # renvois de notes Wikipédia, non lus
    t = t.replace("’", "'").replace("ʼ", "'").replace("\n", " ")
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r'\s*"\s*', ' "', t)
    return re.sub(r"\s+", " ", t).strip()


def cibles(t):
    ids = []
    for c in unicodedata.normalize("NFC", t.lower()):
        if c in index:
            ids.append(index[c])
        elif c.isspace():
            if ids and ids[-1] != index[" "]:
                ids.append(index[" "])
    return ids


def lecture(lp):
    ids, prec, out = lp.argmax(axis=1), -1, []
    for i in ids:
        if i != prec and i != 0:
            out.append(jetons[i])
        prec = i
    return "".join(out)


def cer(a, b):
    a, b = re.sub(r"[^\w' ]", "", a.lower()).split(), re.sub(r"[^\w' ]", "", b.lower()).split()
    a, b = " ".join(a), " ".join(b)
    d = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        p, d[0] = d[0], i
        for j, y in enumerate(b, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (x != y))
    return d[-1] / max(1, len(a))


def energie(audio, sr=16000):
    w = int(TRAME * sr); n = len(audio) // w
    return 10 * np.log10(np.mean(audio[: n * w].reshape(n, w) ** 2, axis=1) + 1e-12)


segments = []
for id_ in sorted(i for i in fiches if i.startswith("bau_RK")):
    lp = np.load(EM / f"{id_}.npy")
    audio, _ = sf.read(WAV / fiches[id_]["fichier"], dtype="float32")
    e = energie(audio)
    texte = nettoyer(fiches[id_]["texte"])
    # phrases : le long passage est coupé aux fins de phrase ; un enregistrement court = une phrase
    phrases = [p.strip() for p in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý\"ƐƆ])", texte) if p.strip()] if len(texte) > 150 else [texte]
    toks, bornes = [], []
    for p in phrases:
        ids = cibles(p)
        if toks:
            toks.append(index[" "])
        bornes.append((len(toks), len(toks) + len(ids))); toks += ids
    ali, sc = F.forced_align(torch.from_numpy(lp)[None], torch.tensor([toks], dtype=torch.int32), blank=0)
    ali, sc = ali[0].numpy(), sc[0].exp().numpy()
    # trame où chaque jeton cible est émis (premier passage non blanc sur ce jeton)
    pos, k, prec = [], 0, -1
    for t, a in enumerate(ali):
        if a != 0 and (a != prec or (k < len(toks) and pos and False)) and k < len(toks) and a == toks[k]:
            pos.append(t); k += 1
        prec = a
    pos = np.array(pos + [len(ali) - 1] * (len(toks) - len(pos)))
    print(f"\n{id_} : {len(phrases)} phrase(s) ; lecture de l'oreille vs texte : {100 * cer(texte, lecture(lp)):.0f} % de lettres différentes ; "
          f"confiance moyenne de l'alignement {sc[ali != 0].mean():.2f}")
    for n, ((a, b), p) in enumerate(zip(bornes, phrases), 1):
        debut, fin = pos[a] * TRAME, (pos[b - 1] + 1) * TRAME
        segments.append({"source": id_, "rang": n, "texte": p, "debut_parole_s": round(debut, 2), "fin_parole_s": round(fin, 2),
                         "duree_parole_s": round(fin - debut, 2)})
        print(f"   phrase {n} : {debut:6.2f} → {fin:6.2f} s ({fin - debut:4.1f} s)  {p[:70]}")
# silences entre phrases consécutives d'un même enregistrement : point de coupe = énergie minimale du silence
for s1, s2 in zip(segments, segments[1:]):
    if s1["source"] == s2["source"]:
        audio, _ = sf.read(WAV / fiches[s1["source"]]["fichier"], dtype="float32"); e = energie(audio)
        a, b = int(s1["fin_parole_s"] / TRAME), int(s2["debut_parole_s"] / TRAME)
        coupe = (a + int(np.argmin(e[a:b + 1]))) * TRAME if b > a else s1["fin_parole_s"]
        s1["coupe_apres_s"] = s2["coupe_avant_s"] = round(coupe, 2)
        s1["silence_apres_s"] = round(s2["debut_parole_s"] - s1["fin_parole_s"], 2)
        print(f"silence entre {s1['source'][-5:]} p{s1['rang']} et p{s2['rang']} : {s1['silence_apres_s']:.2f} s, coupe à {coupe:.2f} s "
              f"(niveau {e[int(coupe / TRAME)]:.0f} dB)")
(ICI / "segments.json").write_text(json.dumps(segments, ensure_ascii=False, indent=1), encoding="utf-8")
