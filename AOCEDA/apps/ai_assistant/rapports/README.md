# Tests et rapports de l'assistant IA : catalogue

Ce dossier contient les résultats des essais faits pendant la construction de l'assistant (chat, dioula, baoulé, voix, appel Live).
Ils s'affichent dans l'application : **Assistant IA > Options > Tests et rapports** (le sommaire est en haut de la page).
Ce fichier est **généré** par `AOCEDA/outils/construire_catalogue_rapports.py` : ne le modifiez pas à la main, modifiez la liste dans ce programme.

Organisation du dossier :

| Dossier | Contenu |
|---|---|
| `resultats/` | les mesures (JSON et texte), et `captures/` (images des essais dans le navigateur) |
| `documentation/` | les bilans par étape, les plans, l'audit |
| `audios/` | les sons à écouter : vocaux de test, réponses, voix comparées, `voix_baoule/` (clonage de voix) |

Les chemins de ces dossiers sont lus par le serveur et par les fichiers JSON eux-mêmes : on n'y déplace rien, on ajoute et on référence ici.

## Chat écrit et vocal en français et en anglais (étape 1)

Le chatbot de base : on lui pose des questions écrites ou parlées et on vérifie qu'il répond juste, dans la bonne langue, avec la bonne voix.

### Évaluation complète du chatbot

- **Ce qu'on vérifie** : 23 questions (14 écrites, 9 parlées) posées au vrai serveur avec les vraies API, puis relues par un juge. On mesure si la réponse est juste, la vitesse du 1er mot et la qualité de la compréhension d'un vocal.
- **Date** : 29/09/2026
- **Résultat** : 23/23 réponses correctes
- **Fichiers** : `resultats/evaluation.json`
- **Dans la page** : section « Résumé de l'évaluation… »
- **Refaire l'essai** : tests\mesures\evaluation.py (laboratoire où l'assistant a été construit (hors dépôt))

### La même évaluation avant chaque réglage

- **Ce qu'on vérifie** : Quatre copies de l'évaluation prises juste avant un réglage (langue stricte, longueur des réponses, retouches, vitesse), pour voir l'effet de chaque réglage.
- **Date** : 29/09/2026
- **Résultat** : 22/23 réponses correctes ; 22/23 réponses correctes ; 20/23 réponses correctes ; 23/23 réponses correctes
- **Fichiers** : `resultats/evaluation_avant_langue_stricte.json`, `resultats/evaluation_avant_longueur.json`, `resultats/evaluation_avant_retouches.json`, `resultats/evaluation_avant_vitesse.json`

### Bilan et revue critique de l'étape 1

- **Ce qu'on vérifie** : Ce qui a été fait, corrigé, les limites connues et la relecture complète du code de l'étape 1.
- **Date** : 29/09/2026
- **Fichiers** : `documentation/ETAPE_1_CHATBOT.txt`, `documentation/REVUE_CRITIQUE_ETAPE_1.txt`

### Choix du cerveau, des voix « Écouter » et de la dictée

- **Ce qu'on vérifie** : Pourquoi DeepSeek pour le texte, quelle voix gratuite lit les réponses (12 voix comparées, à écouter), comment dicter à la voix.
- **Date** : 29/09/2026
- **Fichiers** : `documentation/CHOIX_CERVEAU_VOIX_LIVE.txt`, `resultats/comparaison_voix.json`, `audios/voix_gratuites/`
- **Dans la page** : section « Comparer les voix… »

### Whisper : reconnaître la langue et transcrire

- **Ce qu'on vérifie** : Vingt-deux vocaux de test : Whisper trouve-t-il la langue, combien de mots faux, en combien de temps ? Plus quatre réglages de vitesse comparés et un vocal long de 22 secondes.
- **Date** : 29/09/2026
- **Fichiers** : `resultats/essai_whisper_langue.json`, `resultats/banc_whisper_vitesse.json`, `resultats/essai_long_vocal.json`, `audios/questions/`, `audios/reponses/`

### La vraie page testée dans un navigateur

- **Ce qu'on vérifie** : Un robot ouvre la vraie page dans Microsoft Edge et vérifie chaque bouton (envoyer, écouter, enregistrer, langues, thème).
- **Date** : étape 1, puis refonte
- **Résultat** : 13/13 cas réussis
- **Fichiers** : `resultats/essai_navigateur.json`, `resultats/_verif_navigateur_maquette.txt`, `resultats/_verif_navigateur_refonte.txt`
- **Dans la page** : section « Essai de la vraie page… »

### Essais fonction par fonction et cas difficiles

- **Ce qu'on vérifie** : 25 cas, un par fonction du chatbot, et 29 cas difficiles : mémoire d'une conversation, ordre caché dans un message (détournement), dioula tapé sans lettres spéciales…
- **Date** : étape 1
- **Résultat** : 25/25 cas réussis ; 29/29 cas réussis
- **Fichiers** : `resultats/essai_final.json`, `resultats/essai_pousse.json`

### Tests automatiques du code

- **Ce qu'on vérifie** : La liste des tests du moteur, sans Internet. Photo du 09/10 : aujourd'hui `pytest` en passe bien davantage (voir docs/developpement/tests.md).
- **Date** : 09/10/2026
- **Fichiers** : `resultats/tests_unitaires.txt`
- **Dans la page** : section « Tests automatiques du code… »
- **Refaire l'essai** : cd AOCEDA puis .venv_local\Scripts\python.exe -m pytest

## Dioula (étape 2)

Le chatbot comprend et répond en dioula : écoute des vocaux, compréhension de ce qui est demandé, réponse.

### Évaluation du dioula

- **Ce qu'on vérifie** : Vocaux dioula reconnus comme dioula, demandes comprises sur 100 phrases AOCEDA, fiabilité quand le chatbot se dit « sûr », vitesse.
- **Date** : 29/09/2026
- **Fichiers** : `resultats/dioula_evaluation.json`, `documentation/ETAPE_2_DIOULA.txt`, `audios/dioula/`
- **Dans la page** : section « Dioula (étape 2)… »

### Le dioula dans la vraie page

- **Ce qu'on vérifie** : Le robot choisit le dioula dans le menu, parle, appuie sur Stop en pleine réponse : tout se passe proprement.
- **Date** : 29/09/2026
- **Résultat** : 11/11 cas réussis ; 8/8 cas réussis
- **Fichiers** : `resultats/essai_navigateur_dioula.json`, `resultats/essai_navigateur_dioula2.json`

### Quel cerveau comprend le mieux le dioula et le baoulé ?

- **Ce qu'on vérifie** : DeepSeek, Gemini et Claude comparés sur les mêmes phrases en dioula et en baoulé, juge indépendant, trois jeux de test.
- **Date** : 04/10/2026
- **Fichiers** : `resultats/COMPARATIF_INTENTION.txt`, `resultats/comparatif_intention.json`, `resultats/comparatif_intention_openrouter.json`

### Traduire : Gemini contre Google

- **Ce qu'on vérifie** : Baoulé et dioula vers l'anglais, et l'inverse, avec Gemini et avec Google Traduction.
- **Date** : 30/09/2026
- **Fichiers** : `resultats/comparaison_traduction_gemini_google.json`

## Baoulé : écouter et comprendre (étape 3 et chaîne robuste)

Le chatbot comprend le baoulé parlé ou écrit : on mesure l'écoute, la réparation du texte entendu et la compréhension de la demande.

### Évaluation du baoulé

- **Ce qu'on vérifie** : Lettres fausses à l'écoute de vraies voix de téléphone, langue reconnue, sens compris sur 44 phrases AOCEDA, vitesse de la 1re phrase.
- **Date** : 30/09/2026
- **Fichiers** : `resultats/baoule_evaluation.json`, `documentation/ETAPE_3_BAOULE.txt`
- **Dans la page** : section « Baoulé (étape 3)… »

### La chaîne robuste du baoulé

- **Ce qu'on vérifie** : Un message baoulé passe par quatre blocs (réparer ce qui a été entendu, deviner la demande dans une liste fermée, décider, répondre). Essai réel sur 58 cas et mesure de la réparation sur 170 vrais vocaux.
- **Date** : 06/10/2026
- **Résultat** : 52/58 bonnes réponses du premier coup
- **Fichiers** : `resultats/essai_chaine_baoule.json`, `resultats/essai_reparation_baoule.json`
- **Dans la page** : section « Baoulé : la chaîne robuste… »

### Le baoulé dans la vraie page

- **Ce qu'on vérifie** : Le robot choisit le baoulé, envoie un vocal et vérifie l'affichage et la voix.
- **Date** : 30/09/2026
- **Résultat** : 12/12 cas réussis
- **Fichiers** : `resultats/essai_navigateur_baoule.json`

### Non-régression du dioula

- **Ce qu'on vérifie** : Après avoir ajouté le baoulé, le dioula marche-t-il toujours comme avant ? (vocaux rejoués, temps comparés)
- **Date** : 30/09/2026
- **Fichiers** : `resultats/_verif_non_regression.txt`

## Baoulé : la voix (clonage de voix)

La voix du chatbot en baoulé est une voix clonée : un modèle écoute un extrait d'une vraie voix puis dit un texte nouveau en l'imitant, sans rien réapprendre. On vérifie qu'elle ressemble à la vraie voix et qu'elle reste compréhensible.

### Essai du clonage de voix baoulé : ancien réglage, nouveau réglage, autre voix

- **Ce qu'on vérifie** : 8 phrases : la vraie voix, trois voix fabriquées, ce que l'oreille baoulé comprend de chacune, vitesse de parole, hauteur et mélodie de la voix, temps de fabrication. À écouter phrase par phrase.
- **Date** : 18/10/2026
- **Résultat** : lettres fausses : vraie voix 10.6 %, ancien réglage 38.3 %, nouveau 10.5 %
- **Fichiers** : `resultats/voix_baoule.json`, `audios/voix_baoule/`, `documentation/ESSAI_VOIX_BAOULE.txt`
- **Dans la page** : section « Voix baoulé : le clonage de voix… »
- **Refaire l'essai** : outils\construire_rapport_voix_baoule.py ; essai d'origine et ses programmes : docs/essais/voix-baoule/

### La voix baoulé sur la carte graphique (Cerebrium)

- **Ce qu'on vérifie** : La voix est fabriquée sur une carte graphique louée : vitesse machine allumée ou endormie, détection de la langue des vocaux, crédit consommé.
- **Date** : 06/10/2026
- **Fichiers** : `resultats/essai_voix_gpu.json`, `audios/voix_gpu/`
- **Dans la page** : section « Voix baoulé sur carte graphique… »

### Plan d'amélioration de la voix (affinage)

- **Ce qu'on vérifie** : Les pistes notées pour améliorer la voix baoulé (rien lancé à l'époque).
- **Date** : 29/09/2026
- **Fichiers** : `documentation/PLAN_AMELIORATION_OMNIVOICE.txt`

### Premières réponses baoulé avec la voix OmniVoice

- **Ce qu'on vérifie** : Deux réponses à écouter, fabriquées sur le PC avant l'arrivée de la carte graphique.
- **Date** : fin septembre 2026
- **Fichiers** : `audios/reponse_baoule_omnivoice.wav`, `audios/reponse_baoule_continue.wav`

## Appel Live (conversation vocale en direct)

On parle, l'agent répond tout de suite à voix haute, peut lire les données AOCEDA, agir sur la page et voir l'écran ou la caméra.

### Bilan de l'étape 4 et plan de l'agent

- **Ce qu'on vérifie** : Ce qui marche, comment c'est fait, les mesures, les limites et ce qu'il fallait valider.
- **Date** : 01/10/2026
- **Fichiers** : `documentation/ETAPE_4_LIVE.txt`, `documentation/PLAN_AGENT_LIVE.txt`
- **Dans la page** : section « Appel Live avec l'agent… »

### Un appel réel de bout en bout

- **Ce qu'on vérifie** : Une vraie conversation avec le vrai Gemini : question sur les données, ouvrir les options, regarder l'écran, au revoir.
- **Date** : 01/10/2026
- **Fichiers** : `resultats/essai_live_agent.json`, `resultats/essai_gemini_live.json`, `audios/live/`
- **Dans la page** : section « Un appel réel… »

### Passage d'un compte ou d'un modèle à l'autre

- **Ce qu'on vérifie** : Quand une limite de Google est atteinte, l'appel continue tout seul sur un autre compte ou modèle.
- **Date** : 01/10/2026
- **Résultat** : 3/3 cas réussis
- **Fichiers** : `resultats/essai_live_reserves.json`
- **Dans la page** : section « Passage d'une réserve… »

### Les périodes (« la semaine dernière »)

- **Ce qu'on vérifie** : La même question posée trois fois donne les mêmes dates et le même chiffre.
- **Date** : 01/10/2026
- **Fichiers** : `resultats/essai_live_periodes.json`
- **Dans la page** : section « Les périodes… »

### Langue des réponses

- **Ce qu'on vérifie** : « Réponds en anglais » est respecté pour toutes les réponses ; baoulé et dioula : il dit honnêtement qu'il ne les parle pas, sans rien inventer.
- **Date** : 05/10/2026
- **Résultat** : 18/18 cas réussis ; 6/6 cas réussis
- **Fichiers** : `resultats/essai_live_langue.json`, `resultats/essai_chat_langue.json`
- **Dans la page** : section « Langue des réponses… »

### Endurance : 18 minutes d'appel

- **Ce qu'on vérifie** : Un long appel (58 échanges) pour voir si ça tient et si le délai monte.
- **Date** : 01/10/2026
- **Fichiers** : `resultats/endurance_live.json`

### L'appel Live dans la vraie page

- **Ce qu'on vérifie** : Le robot lance un appel, coupe la parole, partage l'écran, raccroche.
- **Date** : 01/10/2026
- **Résultat** : 18/18 cas réussis
- **Fichiers** : `resultats/essai_navigateur_live.json`, `resultats/_verif_navigateur_live.txt`
- **Dans la page** : section « Appel Live dans Microsoft Edge… »

### Quels modèles Google conviennent ?

- **Ce qu'on vérifie** : Sondes sur 5 modèles Live : lesquels appellent les outils, voient les images, gèrent la planification.
- **Date** : 01/10/2026
- **Fichiers** : `resultats/sonde_modeles_live.json`, `resultats/sonde_capacites_live.json`, `resultats/sonde_images_live.json`, `resultats/sonde_images_live_outil.json`

### Coût et alternative OpenRouter

- **Ce qu'on vérifie** : Jetons consommés par tour sur Gemini Live, et essai d'un modèle audio d'OpenRouter pour comparer.
- **Date** : 01/10/2026
- **Fichiers** : `resultats/mesure_cout_live.json`, `resultats/essai_live_openrouter.json`

## Agent qui agit sur la page et personnage animé

L'agent clique, choisit, écrit sur la page comme une personne ; le lapin animé réagit.

### L'agent qui planifie une demande entière

- **Ce qu'on vérifie** : « Ouvre les options, mets la voix d'homme et le thème clair » : un seul plan, exécuté d'un coup, vérifié, appris. Durée et coût.
- **Date** : 05/10/2026
- **Résultat** : 13/13 demandes réussies ; 6/6 demandes réussies
- **Fichiers** : `resultats/essai_agent_plan.json`, `resultats/essai_agent_live.json`
- **Dans la page** : section « L'agent qui planifie… »

### L'agent agit sur la page

- **Ce qu'on vérifie** : Le robot vérifie dans le navigateur que le curseur doré va au bon bouton et appuie.
- **Date** : 05/10/2026
- **Fichiers** : `resultats/essai_agent_page.json`
- **Dans la page** : section « L'agent agit sur la page… »

### Quel modèle planifie le mieux ?

- **Ce qu'on vérifie** : Plusieurs modèles comparés sur les mêmes demandes : réussite, durée, coût par demande.
- **Date** : 05/10/2026
- **Fichiers** : `resultats/comparatif_agent_actions.json`

### Le personnage animé

- **Ce qu'on vérifie** : Le lapin réagit à ce qui se passe (écoute, réfléchit, parle, erreur) ; vérifié dans le navigateur, avec captures.
- **Date** : 03/10/2026
- **Fichiers** : `resultats/essai_personnage.json`, `documentation/ETAPE_5_PERSONNAGE.txt`
- **Dans la page** : section « Personnage animé… »

## Partage par Internet

Rendre le chatbot joignable depuis un autre appareil ou un autre réseau.

### Tunnel de partage public

- **Ce qu'on vérifie** : Essai du lien public (étapes, vitesse de la page, du 1er mot, de la transcription et du Live à travers le tunnel), et reprise après 3 minutes de repos.
- **Date** : 01/10/2026
- **Fichiers** : `resultats/essai_partage_public.json`, `resultats/mesure_partage.json`, `resultats/essai_tunnel_au_repos_2252.json`

## Audits, outils et traces

Vérifications d'ensemble, documents de référence et fichiers de travail.

### Audit indépendant et corrections

- **Ce qu'on vérifie** : Un relecteur indépendant a lu tout le code : ce qu'il a trouvé et ce qui a été corrigé, avec les tests.
- **Date** : 08-09/10/2026
- **Fichiers** : `documentation/AUDIT_09_10_2026.txt`

### Les outils du chatbot

- **Ce qu'on vérifie** : Page de référence : la liste des outils (consommation, appareils, crédit…) que l'assistant peut appeler pour lire vos données.
- **Date** : octobre 2026
- **Fichiers** : `documentation/OUTILS_DU_CHATBOT.html`

### Captures d'écran des essais

- **Ce qu'on vérifie** : 89 images prises pendant les essais dans le navigateur (accueil, réponse, lecture, téléphone, Live, personnage…).
- **Date** : septembre-octobre 2026
- **Fichiers** : `resultats/captures/`

### Journal technique d'une traduction

- **Ce qu'on vérifie** : Trace brute d'un essai de traduction (messages techniques de la bibliothèque Gemini). Sans intérêt pour la lecture ; gardé pour mémoire.
- **Date** : septembre 2026
- **Fichiers** : `resultats/_traduction_progression.txt`

