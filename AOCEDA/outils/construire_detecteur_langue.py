"""Construit le modèle de langue par n-grammes de l'assistant : apps/ai_assistant/chatbot/donnees/langue_ngrammes.json
(lu par chatbot/langue_ngrammes.py).

    .venv_local/Scripts/python.exe outils/construire_detecteur_langue.py <corpus.json> [<autre_corpus.json> ...]

Chaque corpus est une liste de {"texte", "langue", "jeu"} ; langue = fr, en, dyu, bci, wo ou autre. Les jeux dont le nom
commence par « redige » (messages écrits à la main pour l'essai) ne sont JAMAIS appris : ils servent à vérifier le
modèle une fois construit (résultat affiché à la fin). Les corpus ne sont pas dans le dépôt (transcriptions Common
Voice dioula et baoulé, ALFFA wolof, MINDS-14 français et anglais, phrases du domaine) : le modèle, lui, ne contient
que des comptes de suites de lettres.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent / "apps" / "ai_assistant" / "chatbot"))
import langue_ngrammes as lng  # noqa: E402  (module sans dépendance : importé seul, sans Django)

LANGUES = ["fr", "en", "dyu", "bci", "wo", "autre"]
ALPHA = 0.1
COMPTE_MIN = 2               # un n-gramme vu une seule fois n'apprend rien : retiré (modèle bien plus petit)


def main(chemins):
    corpus, vus = [], set()
    for c in chemins:
        for x in json.loads(Path(c).read_text(encoding="utf-8")):
            if x.get("langue") in LANGUES and x["texte"].strip() and x["texte"] not in vus:
                vus.add(x["texte"])
                corpus.append(x)
    appris = [x for x in corpus if not x.get("jeu", "").startswith("redige")]
    essai = [x for x in corpus if x.get("jeu", "").startswith("redige")]
    comptes, totaux, sources = defaultdict(lambda: [0] * len(LANGUES)), [0] * len(LANGUES), Counter()
    for x in appris:
        i = LANGUES.index(x["langue"])
        sources[f"{x['langue']} ({x.get('jeu', '?')})"] += 1
        for g in lng.ngrammes(x["texte"]):
            comptes[g][i] += 1
            totaux[i] += 1
    vocabulaire = len(comptes)
    gardes = {g: c for g, c in comptes.items() if sum(c) >= COMPTE_MIN}
    modele = {"construit_par": "outils/construire_detecteur_langue.py", "langues": LANGUES, "alpha": ALPHA,
              "n_max": lng.N_MAX, "vocabulaire": vocabulaire, "totaux": totaux,
              "phrases_apprises": dict(sorted(sources.items())), "ngrammes": dict(sorted(gardes.items()))}
    lng.FICHIER.write_text(json.dumps(modele, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(appris)} phrases apprises, {len(gardes)} n-grammes gardés sur {vocabulaire} "
          f"-> {lng.FICHIER.name} ({lng.FICHIER.stat().st_size / 1024:.0f} Ko)")
    lng._modele.clear()
    if essai:
        longs = [x for x in essai if len(x["texte"].split()) >= lng.MOTS_MIN]
        avis = [(x, lng.avis(x["texte"])[0]) for x in longs]
        faux = [(x["texte"], x["langue"], a) for x, a in avis if a not in (x["langue"], None)]
        print(f"messages jamais appris : {len(essai)}, dont {len(longs)} d'au moins {lng.MOTS_MIN} mots ; "
              f"avis juste : {sum(a == x['langue'] for x, a in avis)} ; sans avis : {sum(a is None for _, a in avis)} ; "
              f"avis FAUX : {len(faux)}")
        for f in faux:
            print("   faux :", f)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
