"""Prépare ESSAI_VOIX_BAOULE : nouvelle voix modèle + 8 vraies voix de test, découpées en qualité d'origine (48 kHz)
dans les silences (fondu de 15 ms), avec leur texte exact. Les points de coupe viennent de l'alignement (segments.json)."""
import io, json, re, shutil, sys
from pathlib import Path
import numpy as np, soundfile as sf, pyarrow.parquet as pq

sys.stdout.reconfigure(encoding="utf-8")
ICI, RACINE, AOCEDA = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
MARGE = 0.35                     # silence gardé avant et après la parole (s)
FONDU = 0.015
SOURCES = ["D:/AOCEDA_IA_LAB/cache/waxal_bau_train_00000.parquet",
           "D:/AOCEDA_IA_LAB/donnees/google__WaxalNLP/data/TTS/bau/bau-test-00003.parquet"]
originaux = {}
for f in SOURCES:
    for r in pq.read_table(f).to_pylist():
        if r["speaker_id"] == "RK":
            x, sr = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="float32")
            originaux[r["id"]] = (x if x.ndim == 1 else x.mean(axis=1), sr)
seg = json.loads((ICI / "segments.json").read_text(encoding="utf-8"))
p3 = next(c for c in json.loads((ICI / "pauses_phrase3.json").read_text(encoding="utf-8")) if c["i"] == 2)


def propre(t):
    t = re.sub(r",(?=\S)", ", ", t)
    t = re.sub(r'"\s*([^"]*?)\s*"', r'"\1"', t)
    return re.sub(r"\s+", " ", t).strip()


def extrait(source, debut, fin):
    x, sr = originaux[source]
    a, b = max(0, int(debut * sr)), min(len(x), int(fin * sr))
    y = x[a:b].copy()
    n = int(FONDU * sr)
    y[:n] *= np.linspace(0, 1, n); y[-n:] *= np.linspace(1, 0, n)
    return y, sr


def borne(s, cle_coupe, parole, sens):
    """Bord de l'extrait : la parole ± MARGE, sans dépasser le point de coupe dans le silence voisin."""
    v = s[parole] + sens * MARGE
    if cle_coupe in s:
        v = min(v, s[cle_coupe]) if sens > 0 else max(v, s[cle_coupe])
    return v


def bords_du_silence(source, coupe, seuil_db=-45):
    """Fin de la parole avant `coupe` et reprise après, lues dans le son (fenêtres de 10 ms au-dessus de seuil_db)."""
    x, sr = originaux[source]; w = int(0.01 * sr)
    e = lambda t: 10 * np.log10(np.mean(x[int(t * sr):int(t * sr) + w] ** 2) + 1e-12)
    fin = coupe
    while fin > 0 and e(fin) < seuil_db:
        fin -= 0.01
    deb = coupe
    while deb < len(x) / sr and e(deb) < seuil_db:
        deb += 0.01
    return round(fin + 0.01, 2), round(deb, 2)


fin_p3a, deb_p3b = bords_du_silence("bau_RK_RK_BCI_4_228", p3["coupe_s"])
print(f"phrase 3 : fin de la 1re partie {fin_p3a} s, reprise {deb_p3b} s")
passage = [s for s in seg if s["source"].endswith("4_228")]
courts = {s["source"]: s for s in seg if not s["source"].endswith("4_228")}
# 1) voix modèle : phrase 2 du passage
ref = passage[1]
# 2) les 8 phrases de test (la phrase « Mi kpangɔ… » est l'ANCIENNE voix modèle : exclue)
tests = [
    ("Bakan kun wa", courts["bau_RK_RK_BCI_1_6b"]), ("Me i le kun su", courts["bau_RK_RK_BCI_2_189"]),
    ("Burkina Faso", courts["bau_RK_RK_BCI_2_133"]), ("Kanada lo politiki", passage[0]),
    ("I yole nun_debut", {**passage[2], "texte": p3["partie1"], "fin_parole_s": fin_p3a, "coupe_apres_s": p3["coupe_s"]}),
    ("I yole nun_suite", {**passage[2], "texte": p3["partie2"], "debut_parole_s": deb_p3b, "coupe_avant_s": p3["coupe_s"]}),
    ("Be waan Kanada", passage[3]), ("Kanada lo politiki nun", passage[4]),
]

E = RACINE / "ESSAI_VOIX_BAOULE"
for d in ["1_VOIX_MODELE", "2_REGLAGES", "3_COMPARAISONS_A_ECOUTER", "4_RESULTATS", "5_OUTILS"]:
    (E / d).mkdir(parents=True, exist_ok=True)
V = E / "1_VOIX_MODELE"
# ancienne voix modèle (celle du chatbot aujourd'hui)
anc = AOCEDA / "apps/ai_assistant/chatbot/donnees/voix_baoule"
shutil.copy(anc / "RK_waxal_court.wav", V / "ANCIENNE_voix_modele_RK_2,4s.wav")
anc_txt = json.loads((anc / "reference.json").read_text(encoding="utf-8"))["texte"]
(V / "ANCIENNE_voix_modele_RK_2,4s_texte.txt").write_text(anc_txt + "\n", encoding="utf-8")
# nouvelle voix modèle
y, sr = extrait(ref["source"], borne(ref, "coupe_avant_s", "debut_parole_s", -1), borne(ref, "coupe_apres_s", "fin_parole_s", +1))
nom_ref = f"NOUVELLE_voix_modele_RK_{len(y) / sr:.1f}s".replace(".", ",")
sf.write(V / f"{nom_ref}.wav", y, sr, subtype="PCM_16")
(V / f"{nom_ref}_texte.txt").write_text(propre(ref["texte"]) + "\n", encoding="utf-8")
print(f"voix modèle : {len(y) / sr:.2f} s ({sr} Hz) : {propre(ref['texte'])}")
# vraies voix de test
fiches = []
C = E / "3_COMPARAISONS_A_ECOUTER"
for n, (titre, s) in enumerate(tests, 1):
    d = C / f"phrase_{n:02d}_{re.sub(r'[^A-Za-z0-9_]+', '_', titre).strip('_')}"
    d.mkdir(exist_ok=True)
    y, sr = extrait(s["source"], borne(s, "coupe_avant_s", "debut_parole_s", -1), borne(s, "coupe_apres_s", "fin_parole_s", +1))
    sf.write(d / "A_VRAIE_VOIX_RK.wav", y, sr, subtype="PCM_16")
    texte = propre(s["texte"])
    (d / "texte.txt").write_text(texte + "\n", encoding="utf-8")
    fiches.append({"dossier": d.name, "texte": texte, "duree_vraie_s": round(len(y) / sr, 2), "source_waxal": s["source"]})
    print(f"{d.name:40s} {len(y) / sr:5.1f} s  {texte[:60]}")
(E / "5_OUTILS" / "phrases.json").write_text(json.dumps({"voix_modele": {"fichier": f"{nom_ref}.wav", "texte": propre(ref["texte"])},
                                                          "ancienne": {"fichier": "ANCIENNE_voix_modele_RK_2,4s.wav", "texte": anc_txt},
                                                          "phrases": fiches}, ensure_ascii=False, indent=1), encoding="utf-8")
