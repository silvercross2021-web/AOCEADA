"""Construit le catalogue des tests et rapports de l'assistant IA.

Source unique : la liste THEMES ci-dessous (à tenir à jour quand on ajoute un rapport). Le programme produit :
  - apps/ai_assistant/rapports/resultats/catalogue.json : lu par la page Options > Tests et rapports (sommaire en haut de la page) ;
  - apps/ai_assistant/rapports/README.md : le même catalogue en texte, pour qui ouvre le dossier ;
et VÉRIFIE que chaque fichier du dossier rapports/ (résultats, documentation, audios) est cité au moins une fois : sinon il s'arrête
en listant les oublis. `--verifier` : ne fait que cette vérification.

Usage, depuis AOCEDA, avec le Python du projet :
    .venv_local\\Scripts\\python.exe outils\\construire_catalogue_rapports.py [--verifier]
Ne fait rien à l'import.
"""
import json
import sys
from pathlib import Path

RAPPORTS = Path(__file__).resolve().parent.parent / "apps" / "ai_assistant" / "rapports"
LAB = "laboratoire où l'assistant a été construit (hors dépôt)"

# Chaque rapport : id, titre, ce qu'on vérifie (simple), date ou étape, fichiers (relatifs à rapports/), section de la page (début du titre).
THEMES = [
    {"id": "chat", "titre": "Chat écrit et vocal en français et en anglais (étape 1)",
     "intro": "Le chatbot de base : on lui pose des questions écrites ou parlées et on vérifie qu'il répond juste, dans la bonne langue, avec la bonne voix.",
     "rapports": [
         {"id": "evaluation", "titre": "Évaluation complète du chatbot", "date": "29/09/2026", "section": "Résumé de l'évaluation",
          "explication": "23 questions (14 écrites, 9 parlées) posées au vrai serveur avec les vraies API, puis relues par un juge. On mesure si la réponse est juste, la vitesse du 1er mot et la qualité de la compréhension d'un vocal.",
          "fichiers": ["resultats/evaluation.json"], "relancer": f"tests\\mesures\\evaluation.py ({LAB})"},
         {"id": "evaluation_historique", "titre": "La même évaluation avant chaque réglage", "date": "29/09/2026",
          "explication": "Quatre copies de l'évaluation prises juste avant un réglage (langue stricte, longueur des réponses, retouches, vitesse), pour voir l'effet de chaque réglage.",
          "fichiers": ["resultats/evaluation_avant_langue_stricte.json", "resultats/evaluation_avant_longueur.json",
                       "resultats/evaluation_avant_retouches.json", "resultats/evaluation_avant_vitesse.json"]},
         {"id": "bilan_etape1", "titre": "Bilan et revue critique de l'étape 1", "date": "29/09/2026",
          "explication": "Ce qui a été fait, corrigé, les limites connues et la relecture complète du code de l'étape 1.",
          "fichiers": ["documentation/ETAPE_1_CHATBOT.txt", "documentation/REVUE_CRITIQUE_ETAPE_1.txt"]},
         {"id": "cerveau_voix", "titre": "Choix du cerveau, des voix « Écouter » et de la dictée", "date": "29/09/2026", "section": "Comparer les voix",
          "explication": "Pourquoi DeepSeek pour le texte, quelle voix gratuite lit les réponses (12 voix comparées, à écouter), comment dicter à la voix.",
          "fichiers": ["documentation/CHOIX_CERVEAU_VOIX_LIVE.txt", "resultats/comparaison_voix.json", "audios/voix_gratuites/"]},
         {"id": "whisper", "titre": "Whisper : reconnaître la langue et transcrire", "date": "29/09/2026",
          "explication": "Vingt-deux vocaux de test : Whisper trouve-t-il la langue, combien de mots faux, en combien de temps ? Plus quatre réglages de vitesse comparés et un vocal long de 22 secondes.",
          "fichiers": ["resultats/essai_whisper_langue.json", "resultats/banc_whisper_vitesse.json", "resultats/essai_long_vocal.json", "audios/questions/", "audios/reponses/"]},
         {"id": "navigateur", "titre": "La vraie page testée dans un navigateur", "date": "étape 1, puis refonte",
          "explication": "Un robot ouvre la vraie page dans Microsoft Edge et vérifie chaque bouton (envoyer, écouter, enregistrer, langues, thème).",
          "fichiers": ["resultats/essai_navigateur.json", "resultats/_verif_navigateur_maquette.txt", "resultats/_verif_navigateur_refonte.txt"],
          "section": "Essai de la vraie page"},
         {"id": "par_fonction", "titre": "Essais fonction par fonction et cas difficiles", "date": "étape 1",
          "explication": "25 cas, un par fonction du chatbot, et 29 cas difficiles : mémoire d'une conversation, ordre caché dans un message (détournement), dioula tapé sans lettres spéciales…",
          "fichiers": ["resultats/essai_final.json", "resultats/essai_pousse.json"]},
         {"id": "tests_unitaires", "titre": "Tests automatiques du code", "date": "09/10/2026", "section": "Tests automatiques du code",
          "explication": "La liste des tests du moteur, sans Internet. Photo du 09/10 : aujourd'hui `pytest` en passe bien davantage (voir docs/developpement/tests.md).",
          "fichiers": ["resultats/tests_unitaires.txt"], "relancer": "cd AOCEDA puis .venv_local\\Scripts\\python.exe -m pytest"}]},
    {"id": "dioula", "titre": "Dioula (étape 2)",
     "intro": "Le chatbot comprend et répond en dioula : écoute des vocaux, compréhension de ce qui est demandé, réponse.",
     "rapports": [
         {"id": "dioula_evaluation", "titre": "Évaluation du dioula", "date": "29/09/2026", "section": "Dioula (étape 2)",
          "explication": "Vocaux dioula reconnus comme dioula, demandes comprises sur 100 phrases AOCEDA, fiabilité quand le chatbot se dit « sûr », vitesse.",
          "fichiers": ["resultats/dioula_evaluation.json", "documentation/ETAPE_2_DIOULA.txt", "audios/dioula/"]},
         {"id": "dioula_navigateur", "titre": "Le dioula dans la vraie page", "date": "29/09/2026",
          "explication": "Le robot choisit le dioula dans le menu, parle, appuie sur Stop en pleine réponse : tout se passe proprement.",
          "fichiers": ["resultats/essai_navigateur_dioula.json", "resultats/essai_navigateur_dioula2.json"]},
         {"id": "comparatif_intention", "titre": "Quel cerveau comprend le mieux le dioula et le baoulé ?", "date": "04/10/2026",
          "explication": "DeepSeek, Gemini et Claude comparés sur les mêmes phrases en dioula et en baoulé, juge indépendant, trois jeux de test.",
          "fichiers": ["resultats/COMPARATIF_INTENTION.txt", "resultats/comparatif_intention.json", "resultats/comparatif_intention_openrouter.json"]},
         {"id": "traduction", "titre": "Traduire : Gemini contre Google", "date": "30/09/2026",
          "explication": "Baoulé et dioula vers l'anglais, et l'inverse, avec Gemini et avec Google Traduction.",
          "fichiers": ["resultats/comparaison_traduction_gemini_google.json"]}]},
    {"id": "baoule", "titre": "Baoulé : écouter et comprendre (étape 3 et chaîne robuste)",
     "intro": "Le chatbot comprend le baoulé parlé ou écrit : on mesure l'écoute, la réparation du texte entendu et la compréhension de la demande.",
     "rapports": [
         {"id": "baoule_evaluation", "titre": "Évaluation du baoulé", "date": "30/09/2026", "section": "Baoulé (étape 3)",
          "explication": "Lettres fausses à l'écoute de vraies voix de téléphone, langue reconnue, sens compris sur 44 phrases AOCEDA, vitesse de la 1re phrase.",
          "fichiers": ["resultats/baoule_evaluation.json", "documentation/ETAPE_3_BAOULE.txt"]},
         {"id": "chaine_baoule", "titre": "La chaîne robuste du baoulé", "date": "06/10/2026", "section": "Baoulé : la chaîne robuste",
          "explication": "Un message baoulé passe par quatre blocs (réparer ce qui a été entendu, deviner la demande dans une liste fermée, décider, répondre). Essai réel sur 58 cas et mesure de la réparation sur 170 vrais vocaux.",
          "fichiers": ["resultats/essai_chaine_baoule.json", "resultats/essai_reparation_baoule.json"]},
         {"id": "baoule_navigateur", "titre": "Le baoulé dans la vraie page", "date": "30/09/2026",
          "explication": "Le robot choisit le baoulé, envoie un vocal et vérifie l'affichage et la voix.",
          "fichiers": ["resultats/essai_navigateur_baoule.json"]},
         {"id": "non_regression", "titre": "Non-régression du dioula", "date": "30/09/2026",
          "explication": "Après avoir ajouté le baoulé, le dioula marche-t-il toujours comme avant ? (vocaux rejoués, temps comparés)",
          "fichiers": ["resultats/_verif_non_regression.txt"]}]},
    {"id": "voix_baoule", "titre": "Baoulé : la voix (clonage de voix)",
     "intro": "La voix du chatbot en baoulé est une voix clonée : un modèle écoute un extrait d'une vraie voix puis dit un texte nouveau en l'imitant, sans rien réapprendre. On vérifie qu'elle ressemble à la vraie voix et qu'elle reste compréhensible.",
     "rapports": [
         {"id": "voix_baoule", "titre": "Essai du clonage de voix baoulé : ancien réglage, nouveau réglage, autre voix", "date": "18/10/2026",
          "section": "Voix baoulé : le clonage de voix",
          "explication": "8 phrases : la vraie voix, trois voix fabriquées, ce que l'oreille baoulé comprend de chacune, vitesse de parole, hauteur et mélodie de la voix, temps de fabrication. À écouter phrase par phrase.",
          "fichiers": ["resultats/voix_baoule.json", "audios/voix_baoule/", "documentation/ESSAI_VOIX_BAOULE.txt"],
          "relancer": "outils\\construire_rapport_voix_baoule.py ; essai d'origine et ses programmes : docs/essais/voix-baoule/"},
         {"id": "voix_gpu", "titre": "La voix baoulé sur la carte graphique (Cerebrium)", "date": "06/10/2026", "section": "Voix baoulé sur carte graphique",
          "explication": "La voix est fabriquée sur une carte graphique louée : vitesse machine allumée ou endormie, détection de la langue des vocaux, crédit consommé.",
          "fichiers": ["resultats/essai_voix_gpu.json", "audios/voix_gpu/"]},
         {"id": "plan_omnivoice", "titre": "Plan d'amélioration de la voix (affinage)", "date": "29/09/2026",
          "explication": "Les pistes notées pour améliorer la voix baoulé (rien lancé à l'époque).",
          "fichiers": ["documentation/PLAN_AMELIORATION_OMNIVOICE.txt"]},
         {"id": "premieres_voix", "titre": "Premières réponses baoulé avec la voix OmniVoice", "date": "fin septembre 2026",
          "explication": "Deux réponses à écouter, fabriquées sur le PC avant l'arrivée de la carte graphique.",
          "fichiers": ["audios/reponse_baoule_omnivoice.wav", "audios/reponse_baoule_continue.wav"]}]},
    {"id": "live", "titre": "Appel Live (conversation vocale en direct)",
     "intro": "On parle, l'agent répond tout de suite à voix haute, peut lire les données AOCEDA, agir sur la page et voir l'écran ou la caméra.",
     "rapports": [
         {"id": "live_bilan", "titre": "Bilan de l'étape 4 et plan de l'agent", "date": "01/10/2026", "section": "Appel Live avec l'agent",
          "explication": "Ce qui marche, comment c'est fait, les mesures, les limites et ce qu'il fallait valider.",
          "fichiers": ["documentation/ETAPE_4_LIVE.txt", "documentation/PLAN_AGENT_LIVE.txt"]},
         {"id": "live_essais", "titre": "Un appel réel de bout en bout", "date": "01/10/2026", "section": "Un appel réel",
          "explication": "Une vraie conversation avec le vrai Gemini : question sur les données, ouvrir les options, regarder l'écran, au revoir.",
          "fichiers": ["resultats/essai_live_agent.json", "resultats/essai_gemini_live.json", "audios/live/"]},
         {"id": "live_reserves", "titre": "Passage d'un compte ou d'un modèle à l'autre", "date": "01/10/2026", "section": "Passage d'une réserve",
          "explication": "Quand une limite de Google est atteinte, l'appel continue tout seul sur un autre compte ou modèle.",
          "fichiers": ["resultats/essai_live_reserves.json"]},
         {"id": "live_periodes", "titre": "Les périodes (« la semaine dernière »)", "date": "01/10/2026", "section": "Les périodes",
          "explication": "La même question posée trois fois donne les mêmes dates et le même chiffre.",
          "fichiers": ["resultats/essai_live_periodes.json"]},
         {"id": "live_langue", "titre": "Langue des réponses", "date": "05/10/2026", "section": "Langue des réponses",
          "explication": "« Réponds en anglais » est respecté pour toutes les réponses ; baoulé et dioula : il dit honnêtement qu'il ne les parle pas, sans rien inventer.",
          "fichiers": ["resultats/essai_live_langue.json", "resultats/essai_chat_langue.json"]},
         {"id": "live_endurance", "titre": "Endurance : 18 minutes d'appel", "date": "01/10/2026",
          "explication": "Un long appel (58 échanges) pour voir si ça tient et si le délai monte.",
          "fichiers": ["resultats/endurance_live.json"]},
         {"id": "live_navigateur", "titre": "L'appel Live dans la vraie page", "date": "01/10/2026", "section": "Appel Live dans Microsoft Edge",
          "explication": "Le robot lance un appel, coupe la parole, partage l'écran, raccroche.",
          "fichiers": ["resultats/essai_navigateur_live.json", "resultats/_verif_navigateur_live.txt"]},
         {"id": "live_sondes", "titre": "Quels modèles Google conviennent ?", "date": "01/10/2026",
          "explication": "Sondes sur 5 modèles Live : lesquels appellent les outils, voient les images, gèrent la planification.",
          "fichiers": ["resultats/sonde_modeles_live.json", "resultats/sonde_capacites_live.json", "resultats/sonde_images_live.json",
                       "resultats/sonde_images_live_outil.json"]},
         {"id": "live_cout", "titre": "Coût et alternative OpenRouter", "date": "01/10/2026",
          "explication": "Jetons consommés par tour sur Gemini Live, et essai d'un modèle audio d'OpenRouter pour comparer.",
          "fichiers": ["resultats/mesure_cout_live.json", "resultats/essai_live_openrouter.json"]}]},
    {"id": "agent", "titre": "Agent qui agit sur la page et personnage animé",
     "intro": "L'agent clique, choisit, écrit sur la page comme une personne ; le lapin animé réagit.",
     "rapports": [
         {"id": "agent_plan", "titre": "L'agent qui planifie une demande entière", "date": "05/10/2026", "section": "L'agent qui planifie",
          "explication": "« Ouvre les options, mets la voix d'homme et le thème clair » : un seul plan, exécuté d'un coup, vérifié, appris. Durée et coût.",
          "fichiers": ["resultats/essai_agent_plan.json", "resultats/essai_agent_live.json"]},
         {"id": "agent_page", "titre": "L'agent agit sur la page", "date": "05/10/2026", "section": "L'agent agit sur la page",
          "explication": "Le robot vérifie dans le navigateur que le curseur doré va au bon bouton et appuie.",
          "fichiers": ["resultats/essai_agent_page.json"]},
         {"id": "agent_modeles", "titre": "Quel modèle planifie le mieux ?", "date": "05/10/2026",
          "explication": "Plusieurs modèles comparés sur les mêmes demandes : réussite, durée, coût par demande.",
          "fichiers": ["resultats/comparatif_agent_actions.json"]},
         {"id": "personnage", "titre": "Le personnage animé", "date": "03/10/2026", "section": "Personnage animé",
          "explication": "Le lapin réagit à ce qui se passe (écoute, réfléchit, parle, erreur) ; vérifié dans le navigateur, avec captures.",
          "fichiers": ["resultats/essai_personnage.json", "documentation/ETAPE_5_PERSONNAGE.txt"]}]},
    {"id": "partage", "titre": "Partage par Internet",
     "intro": "Rendre le chatbot joignable depuis un autre appareil ou un autre réseau.",
     "rapports": [
         {"id": "partage", "titre": "Tunnel de partage public", "date": "01/10/2026",
          "explication": "Essai du lien public (étapes, vitesse de la page, du 1er mot, de la transcription et du Live à travers le tunnel), et reprise après 3 minutes de repos.",
          "fichiers": ["resultats/essai_partage_public.json", "resultats/mesure_partage.json", "resultats/essai_tunnel_au_repos_2252.json"]}]},
    {"id": "audits", "titre": "Audits, outils et traces",
     "intro": "Vérifications d'ensemble, documents de référence et fichiers de travail.",
     "rapports": [
         {"id": "audit", "titre": "Audit indépendant et corrections", "date": "08-09/10/2026",
          "explication": "Un relecteur indépendant a lu tout le code : ce qu'il a trouvé et ce qui a été corrigé, avec les tests.",
          "fichiers": ["documentation/AUDIT_09_10_2026.txt"]},
         {"id": "outils_chatbot", "titre": "Les outils du chatbot", "date": "octobre 2026",
          "explication": "Page de référence : la liste des outils (consommation, appareils, crédit…) que l'assistant peut appeler pour lire vos données.",
          "fichiers": ["documentation/OUTILS_DU_CHATBOT.html"]},
         {"id": "captures", "titre": "Captures d'écran des essais", "date": "septembre-octobre 2026",
          "explication": "89 images prises pendant les essais dans le navigateur (accueil, réponse, lecture, téléphone, Live, personnage…).",
          "fichiers": ["resultats/captures/"]},
         {"id": "journal_technique", "titre": "Journal technique d'une traduction", "date": "septembre 2026",
          "explication": "Trace brute d'un essai de traduction (messages techniques de la bibliothèque Gemini). Sans intérêt pour la lecture ; gardé pour mémoire.",
          "fichiers": ["resultats/_traduction_progression.txt"]}]},
]


def resume_auto(chemin):
    """Une phrase de résultat calculée dans le fichier JSON lui-même (rien d'écrit à la main : toujours à jour)."""
    f = RAPPORTS / chemin
    if not f.suffix == ".json" or not f.is_file():
        return None
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if isinstance(d, list) and d and all(isinstance(x, dict) for x in d) and sum("ok" in x for x in d) >= max(1, len(d) // 2):
        return f"{sum(1 for x in d if x.get('ok'))}/{len(d)} cas réussis"
    if isinstance(d, dict):
        if "reussis" in d and "total" in d:
            return f"{d['reussis']}/{d['total']} cas réussis"
        if "reussies" in d and "total" in d:
            return f"{d['reussies']}/{d['total']} demandes réussies"
        if isinstance(d.get("resume"), dict) and "corrects" in d["resume"]:
            return f"{d['resume']['corrects']}/{d['resume']['total']} réponses correctes"
        if "ok" in d and "total" in d:
            return f"{d['ok']}/{d['total']} bonnes réponses du premier coup"
        if isinstance(d.get("moyennes"), dict) and "C" in d["moyennes"]:
            m = d["moyennes"]
            return f"lettres fausses : vraie voix {m['A']['lettres_fausses_pct']} %, ancien réglage {m['B']['lettres_fausses_pct']} %, nouveau {m['C']['lettres_fausses_pct']} %"
    return None


def tous_les_fichiers():
    """Chemins (relatifs à rapports/) à couvrir : résultats, documentation, et les dossiers de premier niveau de audios/."""
    vus = set()
    for sous in ("resultats", "documentation"):
        for f in sorted((RAPPORTS / sous).iterdir()):
            vus.add(f"{sous}/{f.name}" + ("/" if f.is_dir() else ""))
    for f in sorted((RAPPORTS / "audios").iterdir()):
        vus.add(f"audios/{f.name}" + ("/" if f.is_dir() else ""))
    return vus


def citer(chemin):
    return {c for t in THEMES for r in t["rapports"] for c in r["fichiers"] if c == chemin}


def verifier():
    cites = {c for t in THEMES for r in t["rapports"] for c in r["fichiers"]}
    # fichiers produits par ce programme lui-même
    propres = {"resultats/catalogue.json"}
    manquants = sorted(tous_les_fichiers() - cites - propres)
    inconnus = sorted(c for c in cites if not (RAPPORTS / c.rstrip("/")).exists())
    return manquants, inconnus


def markdown(catalogue):
    L = ["# Tests et rapports de l'assistant IA : catalogue", "",
         "Ce dossier contient les résultats des essais faits pendant la construction de l'assistant (chat, dioula, baoulé, voix, appel Live).",
         "Ils s'affichent dans l'application : **Assistant IA > Options > Tests et rapports** (le sommaire est en haut de la page).",
         "Ce fichier est **généré** par `AOCEDA/outils/construire_catalogue_rapports.py` : ne le modifiez pas à la main, modifiez la liste dans ce programme.", "",
         "Organisation du dossier :", "",
         "| Dossier | Contenu |", "|---|---|",
         "| `resultats/` | les mesures (JSON et texte), et `captures/` (images des essais dans le navigateur) |",
         "| `documentation/` | les bilans par étape, les plans, l'audit |",
         "| `audios/` | les sons à écouter : vocaux de test, réponses, voix comparées, `voix_baoule/` (clonage de voix) |", "",
         "Les chemins de ces dossiers sont lus par le serveur et par les fichiers JSON eux-mêmes : on n'y déplace rien, on ajoute et on référence ici.", ""]
    for t in catalogue["themes"]:
        L += [f"## {t['titre']}", "", t["intro"], ""]
        for r in t["rapports"]:
            L += [f"### {r['titre']}", "", f"- **Ce qu'on vérifie** : {r['explication']}", f"- **Date** : {r['date']}"]
            if r.get("resultat"):
                L.append(f"- **Résultat** : {r['resultat']}")
            L.append("- **Fichiers** : " + ", ".join(f"`{c}`" for c in r["fichiers"]))
            if r.get("section"):
                L.append(f"- **Dans la page** : section « {r['section']}… »")
            if r.get("relancer"):
                L.append(f"- **Refaire l'essai** : {r['relancer']}")
            L.append("")
    return "\n".join(L) + "\n"


def main():
    manquants, inconnus = verifier()
    if manquants or inconnus:
        print("MANQUANTS (dans rapports/ mais pas dans le catalogue) :", *manquants, sep="\n  ")
        print("INCONNUS (dans le catalogue mais absents du dossier) :", *inconnus, sep="\n  ")
        return 1
    if "--verifier" in sys.argv:
        print("catalogue complet : chaque fichier de rapports/ est référencé")
        return 0
    themes = []
    for t in THEMES:
        rapports = []
        for r in t["rapports"]:
            r = dict(r)
            trouves = [x for x in (resume_auto(c) for c in r["fichiers"]) if x]        # un résultat par fichier de mesures
            r["resultat"] = trouves[0] if len(trouves) == 1 else " ; ".join(trouves) if trouves else None
            rapports.append(r)
        themes.append({**t, "rapports": rapports})
    catalogue = {"themes": themes, "nombre_rapports": sum(len(t["rapports"]) for t in themes)}
    (RAPPORTS / "resultats" / "catalogue.json").write_text(json.dumps(catalogue, ensure_ascii=False, indent=1), encoding="utf-8")
    (RAPPORTS / "README.md").write_text(markdown(catalogue), encoding="utf-8")
    print(f"{catalogue['nombre_rapports']} rapports rangés en {len(themes)} thèmes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
