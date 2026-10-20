"""Construit le rapport « Voix baoulé : clonage de voix » de la page Options > Tests et rapports.

À partir du dossier brut de l'essai du 18/10/2026 (ESSAI_VOIX_BAOULE : audios WAV, mesures JSON, textes), ce programme :
  1. convertit les audios en MP3 (96 kbit/s, mono) dans apps/ai_assistant/rapports/audios/voix_baoule/ (30 Mo de WAV -> environ 3 Mo) ;
  2. assemble apps/ai_assistant/rapports/resultats/voix_baoule.json : pour chaque phrase, le texte baoulé, son sens en français, la vraie voix,
     les voix fabriquées, ce que l'oreille baoulé a retranscrit de chacune et les mesures ;
  3. recopie les documents et les outils de l'essai dans docs/essais/voix-baoule/ (traçabilité : les WAV d'origine, eux, restent hors du dépôt).

Usage, depuis le dossier AOCEDA, avec le Python du projet :
    .venv_local\\Scripts\\python.exe outils\\construire_rapport_voix_baoule.py <dossier ESSAI_VOIX_BAOULE> [--sens sens_fr.json]

`--sens` : fichier JSON { "phrase_01_Bakan_kun_wa": "sens", ..., "voix_modele": "...", "ancienne": "..." } (traduction automatique Google
du baoulé, approximative, à faire relire par un locuteur). Sans lui, le sens reste « non renseigné ». Ne fait rien à l'import.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent                  # AOCEDA/
RAPPORTS = RACINE / "apps" / "ai_assistant" / "rapports"
DOCS = RACINE.parent / "docs" / "essais" / "voix-baoule"

VERSIONS = {
    "A": {"nom": "Vraie voix de RK", "genre": "original", "fichier": "A_VRAIE_VOIX_RK.wav", "sortie": "A_vraie_voix.mp3",
          "explication": "La vraie personne (locuteur RK, enregistrement de studio) qui lit la phrase. C'est la référence."},
    "B": {"nom": "Voix clonée, ancien réglage", "genre": "clone", "fichier": "B_VOIX_GENEREE_ancien_reglage.wav", "sortie": "B_ancien_reglage.mp3",
          "explication": "Ce que faisait le chatbot avant : la voix de RK imitée à partir d'un extrait de 2,4 s, en 8 étapes de fabrication."},
    "C": {"nom": "Voix clonée, nouveau réglage", "genre": "clone", "fichier": "C_VOIX_GENEREE_nouveau_reglage.wav", "sortie": "C_nouveau_reglage.mp3",
          "explication": "La voix de RK imitée à partir d'un extrait de 9,9 s, en 32 étapes. C'est le réglage mis en service."},
    "D": {"nom": "Voix clonée, voix Common Voice", "genre": "clone", "fichier": "D_VOIX_GENEREE_voix_CommonVoice.wav", "sortie": "D_voix_commonvoice.mp3",
          "explication": "Même réglage que C, mais en imitant un autre locuteur (voix d'homme, grave, corpus Common Voice). Sert à comparer la clarté et le naturel."},
}
MODELES = [
    ("ancienne", "ANCIENNE_voix_modele_RK_2,4s", "ancienne_RK_2-4s", "Ancien réglage : extrait court de RK (2,4 s)"),
    ("nouvelle", "NOUVELLE_voix_modele_RK_9,9s", "nouvelle_RK_9-9s", "Nouveau réglage : extrait long de RK (9,9 s)"),
    ("commonvoice", "COMMONVOICE_voix_modele_566016a2_7,7s", "commonvoice_566016a2_7-7s", "Voix Common Voice (locuteur 566016a2, 7,7 s)"),
]
# Lettres mal comprises sur les voix du chatbot « en service » (LISEZ-MOI de 6_VOIX_EN_PRODUCTION_A_ECOUTER, 18/10/2026)
PRODUCTION_CER = {"femme": {3: 12.1, 4: 5.4, 5: 9.1, 6: 14.2, 7: 14.0}, "homme": {3: 10.3, 4: 6.9, 5: 9.8, 6: 13.0, 7: 10.1}}


def en_mp3(source, destination, kbps=96):
    """WAV -> MP3 mono. PyAV (déjà installé avec faster-whisper) ; le fichier d'origine n'est pas modifié."""
    import av
    destination.parent.mkdir(parents=True, exist_ok=True)
    entree = av.open(str(source))
    flux = entree.streams.audio[0]
    sortie = av.open(str(destination), "w")
    codec = sortie.add_stream("libmp3lame", rate=flux.rate)
    codec.bit_rate = kbps * 1000
    codec.layout = "mono"
    reechantillonneur = av.AudioResampler(format="s16p", layout="mono", rate=flux.rate)
    for trame in entree.decode(flux):
        for t in reechantillonneur.resample(trame):
            for paquet in codec.encode(t):
                sortie.mux(paquet)
    for paquet in codec.encode(None):
        sortie.mux(paquet)
    sortie.close()
    entree.close()


def lire(chemin):
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


def moyenne(valeurs):
    v = [x for x in valeurs if isinstance(x, (int, float))]
    return round(sum(v) / len(v), 1) if v else None


def construire(source, sens):
    source = Path(source)
    sortie_audio = RAPPORTS / "audios" / "voix_baoule"
    phrases_src = lire(source / "5_OUTILS" / "phrases.json")
    compr = {(m["dossier"], m["fichier"]): m for m in lire(source / "4_RESULTATS" / "mesures_comprehension.json")}
    debit = {(m["dossier"], m["fichier"]): m for m in lire(source / "4_RESULTATS" / "mesures_debit_intonation.json")}
    fab = {(m["dossier"], m["fichier"]): m for m in lire(source / "4_RESULTATS" / "mesures_fabrication.json")}
    sens = sens or {}
    inconnu = "non renseigné"

    modeles = []
    for ident, base, sortie, nom in MODELES:
        wav = source / "1_VOIX_MODELE" / f"{base}.wav"
        texte = (source / "1_VOIX_MODELE" / f"{base}_texte.txt").read_text(encoding="utf-8").strip()
        en_mp3(wav, sortie_audio / "modeles" / f"{sortie}.mp3")
        modeles.append({"id": ident, "nom": nom, "fichier": f"voix_baoule/modeles/{sortie}.mp3", "texte": texte,
                        "sens_fr": sens.get({"ancienne": "ancienne", "nouvelle": "voix_modele", "commonvoice": "commonvoice"}[ident], inconnu)})

    phrases = []
    for n, p in enumerate(phrases_src["phrases"], 1):
        d = p["dossier"]
        versions = []
        for ident, v in VERSIONS.items():
            wav = source / "3_COMPARAISONS_A_ECOUTER" / d / v["fichier"]
            en_mp3(wav, sortie_audio / "phrases" / d / v["sortie"])
            c, de, f = compr.get((d, v["fichier"]), {}), debit.get((d, v["fichier"]), {}), fab.get((d, v["fichier"]), {})
            versions.append({
                "id": ident, "fichier": f"voix_baoule/phrases/{d}/{v['sortie']}",
                "retranscription": c.get("lu"), "lettres_fausses_pct": c.get("cer"),
                "duree_parole_s": de.get("duree_parole_s"), "hauteur_hz": de.get("hauteur_mediane_hz"),
                "melodie_demi_tons": de.get("etendue_demi_tons"), "debit_lettres_s": de.get("debit_lettres_s"),
                "fabrication": ({"etapes": f.get("etapes"), "calcul_gpu_s": f.get("calcul_gpu_s"), "aller_retour_s": f.get("aller_retour_s")} if f else None)})
        phrases.append({"numero": n, "dossier": d, "texte": p["texte"], "sens_fr": sens.get(d, inconnu), "duree_vraie_s": p.get("duree_vraie_s"),
                        "source": p.get("source_waxal"), "versions": versions})

    moyennes = {ident: {"lettres_fausses_pct": moyenne([next(v for v in ph["versions"] if v["id"] == ident)["lettres_fausses_pct"] for ph in phrases]),
                        "debit_lettres_s_min": min(next(v for v in ph["versions"] if v["id"] == ident)["debit_lettres_s"] for ph in phrases),
                        "debit_lettres_s_max": max(next(v for v in ph["versions"] if v["id"] == ident)["debit_lettres_s"] for ph in phrases),
                        "hauteur_hz_min": min(next(v for v in ph["versions"] if v["id"] == ident)["hauteur_hz"] for ph in phrases),
                        "hauteur_hz_max": max(next(v for v in ph["versions"] if v["id"] == ident)["hauteur_hz"] for ph in phrases),
                        "melodie_min": min(next(v for v in ph["versions"] if v["id"] == ident)["melodie_demi_tons"] for ph in phrases),
                        "melodie_max": max(next(v for v in ph["versions"] if v["id"] == ident)["melodie_demi_tons"] for ph in phrases)}
                for ident in VERSIONS}

    production = []
    for num in (3, 4, 5, 6, 7):
        d = next(ph for ph in phrases if ph["numero"] == num)
        ligne = {"numero": num, "texte": d["texte"], "sens_fr": d["sens_fr"]}
        for genre, motif in (("femme", f"phrase_{num:02d}_FEMME_RK.wav"), ("homme", f"phrase_{num:02d}_HOMME_CommonVoice.wav")):
            sortie = f"phrase_{num:02d}_{genre}.mp3"
            en_mp3(source / "6_VOIX_EN_PRODUCTION_A_ECOUTER" / motif, sortie_audio / "production" / sortie)
            ligne[genre] = {"fichier": f"voix_baoule/production/{sortie}", "lettres_fausses_pct": PRODUCTION_CER[genre][num]}
        production.append(ligne)

    remesure = source / "4_RESULTATS" / "mesures_production.json"
    if remesure.is_file():                          # réécoute des voix en service (9_retranscrire_voix_production.py)
        par = {(m["phrase"], m["genre"]): m for m in lire(remesure)}
        for ligne in production:
            for genre in ("femme", "homme"):
                m = par.get((ligne["numero"], genre))
                if m:
                    ligne[genre]["retranscription"] = m["lu"]
                    ligne[genre]["remesure_pct"] = m["cer"]

    rapport = {
        "date": "2026-10-18",
        "titre": "Voix baoulé : peut-on cloner une voix sans réentraîner le modèle ?",
        "modeles": modeles, "versions": {k: {x: v[x] for x in ("nom", "genre", "explication")} for k, v in VERSIONS.items()},
        "reglages": [
            {"id": "B", "nom": "Ancien réglage", "voix_modele": "RK, 2,4 s", "etapes": 8,
             "pourquoi": "Choisi quand la voix se fabriquait sur le PC, sans carte graphique (plusieurs minutes par phrase) : 10 fois plus rapide."},
            {"id": "C", "nom": "Nouveau réglage", "voix_modele": "RK, 9,9 s", "etapes": 32,
             "pourquoi": "Réglage recommandé par les auteurs du modèle (voix modèle de 3 à 10 s, 32 étapes) ; possible depuis que la voix est fabriquée sur la carte graphique Cerebrium."},
            {"id": "D", "nom": "Nouveau réglage, autre voix", "voix_modele": "Common Voice 566016a2, 7,7 s", "etapes": 32,
             "pourquoi": "Même réglage que C avec la voix d'un autre locuteur, pour comparer la clarté et le naturel."}],
        "phrases": phrases, "moyennes": moyennes, "production": production,
        "production_moyennes": {g: moyenne(list(v.values())) for g, v in PRODUCTION_CER.items()},
        "lecture": [
            {"mot": "Retranscription", "sens": "Ce que l'oreille baoulé du chatbot a écrit en réécoutant la voix. Si elle écrit presque le texte exact, la voix est claire."},
            {"mot": "Lettres fausses", "sens": "Pourcentage de lettres différentes entre le texte exact et la retranscription. 0 % = parfait ; plus c'est BAS, mieux c'est. La vraie voix obtient déjà environ 10 % (l'oreille se trompe aussi) : être proche de 10 %, c'est être compris comme la vraie voix."},
            {"mot": "Débit", "sens": "Lettres prononcées par seconde de parole. La vraie voix : 9 à 11. Beaucoup plus = trop vite."},
            {"mot": "Hauteur", "sens": "Voix grave ou aiguë, en hertz. RK : environ 200 à 225 Hz. Si la hauteur change beaucoup, ce n'est plus la même voix."},
            {"mot": "Mélodie", "sens": "Combien la voix monte et descend, en demi-tons. RK : 2 à 4. Plus c'est petit, plus la voix est plate."},
            {"mot": "Étapes", "sens": "Nombre de passes de fabrication du modèle : plus il y en a, plus c'est soigné et plus c'est long."}],
        "conclusion": [
            "Le nouveau réglage (voix modèle de 9,9 s, 32 étapes) est nettement meilleur : compris comme la vraie voix (10,5 % contre 10,6 %), il garde la voix et la mélodie de RK et ne « déraille » plus sur les phrases longues, pour environ 1 seconde de plus.",
            "L'ancien réglage devient presque incompréhensible sur les phrases longues (72 à 75 % de lettres fausses) : il parle deux fois trop vite et sa voix descend.",
            "La voix Common Voice (D) est presque aussi claire (11,8 %) avec un débit naturel, mais plus plate et d'une autre personne : aucune des deux, C ou D, n'est meilleure partout.",
            "Défaut restant de C : il parle environ 15 % trop vite. Piste sans coût : le réglage « speed » (0,87) le ramènerait au débit de RK ; non testé."],
        "limites": [
            "Le sens en français est une traduction automatique (Google), approximative, jamais relue par un locuteur baoulé.",
            "Les chiffres viennent d'une oreille automatique : l'écoute par un locuteur baoulé reste à faire (grille de notation dans docs/essais/voix-baoule/4_RESULTATS/GRILLE_ECOUTE.txt).",
            "Huit phrases d'un même corpus et un seul locuteur de référence : une indication solide, pas une preuve générale.",
            "Audios compressés en MP3 (96 kbit/s) pour alléger le dépôt ; les fichiers d'origine restent sur le PC de l'auteur."],
        "sens_source": "Traduction automatique Google du baoulé vers le français : approximative, non relue par un locuteur baoulé." if sens else None,
    }
    sortie_json = RAPPORTS / "resultats" / "voix_baoule.json"
    sortie_json.write_text(json.dumps(rapport, ensure_ascii=False, indent=1), encoding="utf-8")

    # traçabilité : documents et outils de l'essai (sans les WAV d'origine)
    DOCS.mkdir(parents=True, exist_ok=True)
    for sous, motifs in (("", ["LISEZ-MOI.txt"]), ("4_RESULTATS", ["RESULTATS.txt", "GRILLE_ECOUTE.txt", "*.json"]), ("1_VOIX_MODELE", ["POURQUOI_CETTE_VOIX.txt"]),
                         ("2_REGLAGES", ["REGLAGES.txt"]), ("6_VOIX_EN_PRODUCTION_A_ECOUTER", ["LISEZ-MOI.txt"])):
        for motif in motifs:
            for f in (source / sous).glob(motif):
                cible = DOCS / (sous or ".") / f.name
                cible.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, cible)
    for f in (source / "5_OUTILS").glob("*"):
        if f.is_file():
            (DOCS / "outils").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, DOCS / "outils" / f.name)
    svc = source / "2_REGLAGES" / "service_cerebrium_essai"
    for f in svc.glob("*.*"):
        (DOCS / "service_cerebrium_essai").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, DOCS / "service_cerebrium_essai" / f.name)
    return rapport


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("source", help="dossier ESSAI_VOIX_BAOULE")
    ap.add_argument("--sens", help="JSON des sens en français")
    a = ap.parse_args()
    sens = None
    if a.sens:
        brut = lire(a.sens)
        sens = {k: (v.get("google") if isinstance(v, dict) else v) for k, v in brut.items()}
    r = construire(a.source, sens)
    print(f"{len(r['phrases'])} phrases, moyennes de lettres fausses : " + ", ".join(f"{k} {v['lettres_fausses_pct']} %" for k, v in r["moyennes"].items()))


if __name__ == "__main__":
    sys.exit(main())
