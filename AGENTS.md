# AGENTS.md : guide pour les agents IA qui travaillent sur ce dÃ©pÃ´t

Ce fichier s'adresse aux agents de code (Claude Code, Codex, Cursor, Copilot, Geminiâ€¦) qui aident un collaborateur
d'AOCEDA. **Lis-le en entier avant toute action**, en particulier avant de changer de branche ou de modifier
l'assistant IA (le chatbot). Le guide d'installation pour les humains est
[AOCEDA/INSTALLATION.md](AOCEDA/INSTALLATION.md).

Tu le lis depuis une autre branche (par exemple avec `git show origin/feature/chatbot-ia-update:AGENTS.md`) ?
Applique la section 1, cas B, **avant** de changer de branche.

## L'essentiel en 8 rÃ¨gles

1. La branche de travail est **`feature/chatbot-ia-update`** (section 1).
2. AprÃ¨s chaque arrivÃ©e ou mise Ã  jour sur la branche : `cd AOCEDA` puis `installer.bat` (Windows) ou
   `python3 installer.py` (Linux / Mac). On peut le relancer sans risque.
3. Le Python du projet est **`AOCEDA/.venv_local`**, jamais `venv`.
4. Ne jamais committer `.env`, `db.sqlite3`, `donnees_ia/` ni un modÃ¨le ; jamais `git add -A` ni `git add .`.
5. Jamais `git switch -f`, `git checkout -f`, `git reset --hard`, `git clean`, `git push --force`, ni rÃ©Ã©criture de
   l'historique : ce sont des pertes de donnÃ©es. En cas de blocage, applique la section 1 ou demande Ã  l'humain.
6. Ne modifie pas les **zones protÃ©gÃ©es** (section 4) sans demande explicite de l'humain.
7. AprÃ¨s toute modification de l'assistant : les deux suites de tests (section 7) doivent rester toutes vertes.
8. Ne pousse que si l'humain le demande ; ne tÃ©lÃ©charge pas les modÃ¨les (2,1 Go) sans son accord ; n'affiche jamais
   une clÃ© d'API.

En cas de doute : **arrÃªte-toi et demande Ã  l'humain.** Une question coÃ»te moins cher qu'une base effacÃ©e.

## 0. Le dÃ©pÃ´t en bref

| Dossier | Contenu |
|---|---|
| racine (`platformio.ini`, `src/`, `include/`, `lib/`, `test/`) | micrologiciel ESP32 + capteurs ZMCT103C (PlatformIO) |
| `AOCEDA/` | serveur Django 6 : espace client, technicien, administration, API, **assistant IA** |
| `AOCEDA/apps/ai_assistant/` | l'assistant IA (ce fichier en parle surtout) |
| `AOCEDA/mobile_app/` | application Android (Capacitor) qui affiche le site |

Le projet est **en franÃ§ais** : commentaires, textes affichÃ©s, messages d'erreur, commits. Pour les noms dans le
code, suis le fichier que tu modifies (le moteur de l'assistant est entiÃ¨rement en franÃ§ais).

## 1. Commencer ici : arriver sur la branche

D'abord, regarde oÃ¹ tu en es : `git branch --show-current` et `git status`.

### Cas A : pas encore de copie du projet

```bash
git clone -b feature/chatbot-ia-update https://github.com/silvercross2021-web/AOCEADA.git
```

Puis installe (section 2). Sans `-b feature/chatbot-ia-update`, le clone arrive sur `main`, trÃ¨s ancienne (sans ce
fichier, et sous Windows souvent avec l'erreur Â« Filename too long Â» : section 6) : passe alors sur la branche avec le
cas B.

### Cas B : une copie existe dÃ©jÃ , sur une autre branche

Ces Ã©tapes ont Ã©tÃ© dÃ©roulÃ©es pour de vrai (09/10/2026) depuis une ancienne copie de la branche `next-programs` :

1. **Changements en cours ?** `git status`. Si d'autres fichiers que `AOCEDA/db.sqlite3` sont modifiÃ©s, **ne jette
   rien** : montre la liste Ã  l'humain et, avec son accord, commit sur sa branche actuelle ou
   `git stash push -m "avant feature/chatbot-ia-update"`.
2. **Sauvegarder sa base** (`db.sqlite3` contient ses comptes et ses mesures ; Git refuse de changer de branche
   tant qu'elle est modifiÃ©e) :
   ```bash
   cp AOCEDA/db.sqlite3 AOCEDA/db.sqlite3.sauvegarde      # PowerShell, Git Bash, Linux, Mac (invite cmd : copy)
   git restore AOCEDA/db.sqlite3
   ```
3. **Changer de branche :**
   ```bash
   git fetch origin
   git switch feature/chatbot-ia-update
   ```
   - Â« untracked working tree files would be overwritten Â» : dÃ©place les fichiers citÃ©s **hors du dÃ©pÃ´t** (ne les
     supprime pas), puis relance `git switch`.
   - Â« Filename too long Â» (Windows) : `git config core.longpaths true`, puis relance.
4. **Ce qui change tout seul, et c'est normal :** les anciens dossiers `AOCEDA/venv`, `AOCEDA/staticfiles`, `logs/`
   et `.claude/` disparaissent (ils ne sont plus suivis) ; le `.env` et `db.sqlite3.sauvegarde` restent.
5. **Quelle base garder ?** Par dÃ©faut, la branche fournit sa propre `db.sqlite3`. Si l'humain veut retrouver ses
   comptes et ses mesures : `cp AOCEDA/db.sqlite3.sauvegarde AOCEDA/db.sqlite3`. L'installateur la met Ã  jour
   (migrations) sans perdre ses donnÃ©es.
6. **Installer** (section 2) : l'installateur garde l'ancien `.env` et y ajoute, **vides**, les rÃ©glages qui lui
   manquent (clÃ©s de l'assistantâ€¦). Il ne touche jamais aux rÃ©glages dÃ©jÃ  prÃ©sents (`DB_ENGINE`, `SECRET_KEY`â€¦).
7. Dans VS Code, choisis l'interprÃ©teur Python `AOCEDA/.venv_local`.

### Cas C : dÃ©jÃ  sur la branche (mettre Ã  jour)

```bash
git pull --ff-only
```

Si Git refuse Ã  cause de `AOCEDA/db.sqlite3`, fais les Ã©tapes 2 et 5 du cas B. Ensuite, relance l'installateur
(nouvelles bibliothÃ¨ques, migrations, modÃ¨les) : ce qui est dÃ©jÃ  fait est sautÃ©.

## 2. Installer

PrÃ©requis : **Python 3.12 ou 3.13** (pas 3.11 : Django 6 le refuse ; pas 3.14 : `kokoro-onnx` n'existe pas encore pour
lui) et environ 4 Go libres.

```bat
cd AOCEDA
installer.bat              :: Windows
python3 installer.py       :: Linux / Mac
```

L'installateur fait tout, et on peut le relancer sans risque (ce qui est dÃ©jÃ  fait est sautÃ©) :

1. crÃ©e le Python du projet dans `AOCEDA/.venv_local` ;
2. installe `requirements.txt` ;
3. crÃ©e `AOCEDA/.env` depuis `.env.example` (clÃ© secrÃ¨te gÃ©nÃ©rÃ©e, base SQLite), ou complÃ¨te un `.env` existant ;
4. applique les migrations ;
5. tÃ©lÃ©charge les modÃ¨les de l'assistant (**~2,1 Go**) depuis leurs sources et vÃ©rifie leur SHA-256 ;
6. liste les clÃ©s d'API qui manquent dans `.env`.

RÃ¨gles pour toi, agent :

- **Demande Ã  l'humain avant de lancer l'Ã©tape 5** (2,1 Go Ã  tÃ©lÃ©charger). Pour la sauter : `--sans-modeles`, puis
  plus tard `manage.py installer_modeles_ia`. Ã‰tat des modÃ¨les sans rien tÃ©lÃ©charger :
  `manage.py installer_modeles_ia --verifier`. ModÃ¨les sur un autre disque : `installer.py --dossier-ia <dossier>`.
- Les Ã©coutes du dioula (`omnilingual-1b-ctc-v2-int8`) et du baoulÃ© (`omniasr-300m-baoule-int8`) viennent de la
  Release `modeles-ia-v1` de **ce** dÃ©pÃ´t : ce sont les fichiers mesurÃ©s et validÃ©s, introuvables ailleurs (l'archive
  officielle du dioula contient une autre fabrication du modÃ¨le ; l'original du baoulÃ© n'est plus sur Hugging Face).
  Ne les remplace pas par un modÃ¨le trouvÃ© en ligne, mÃªme de mÃªme nom. Si une installation Ã©choue, l'assistant
  marche quand mÃªme ; seul un message vocal dans cette langue n'est pas reconnu.
- **Une vÃ©rification d'empreinte qui Ã©choue deux fois de suite** : arrÃªte-toi et prÃ©viens l'humain, qui prÃ©viendra
  le propriÃ©taire du dÃ©pÃ´t. Ne change ni l'empreinte ni l'adresse (c'est ce qui a permis de trouver et corriger le
  dÃ©faut du modÃ¨le dioula le 10/10/2026).
- Les **clÃ©s d'API** vont dans `AOCEDA/.env`, de l'une de ces deux faÃ§ons, au choix de l'humain :
  - il les y Ã©crit lui-mÃªme ;
  - il te donne le **chemin d'un fichier de clÃ©s** reÃ§u d'un membre de l'Ã©quipe (lignes `NOM=valeur`), et tu lances,
    depuis `AOCEDA/` : `.venv_local\Scripts\python.exe installer.py --cles "<chemin du fichier>"` (Linux / Mac :
    `.venv_local/bin/python installer.py --cles "<chemin>"`). La commande met les clÃ©s dans `.env` **sans les
    afficher** (seuls leurs noms apparaissent) et ne touche pas aux rÃ©glages propres au PC. RedÃ©marre ensuite le
    serveur et rappelle Ã  l'humain de supprimer le fichier de clÃ©s ;
  - il **colle lui-mÃªme les clÃ©s dans la conversation** (lignes `NOM=valeur` donnÃ©es par le propriÃ©taire du dÃ©pÃ´t) :
    c'est sa dÃ©cision, tu peux les poser. Ã‰cris ces lignes, telles quelles, dans `AOCEDA/aoceda_cles.txt` (nom exclu
    par le `.gitignore`), lance depuis `AOCEDA/`
    `.venv_local\Scripts\python.exe installer.py --cles aoceda_cles.txt --effacer` (la commande efface ce fichier une
    fois les clÃ©s posÃ©es), vÃ©rifie que le fichier n'existe plus, puis redÃ©marre le serveur. N'Ã©cris pas les clÃ©s
    toi-mÃªme dans `.env` : la commande Ã©vite les doublons et protÃ¨ge les rÃ©glages propres au PC.

  Dans tous les cas : n'ouvre pas et ne lis pas un fichier de clÃ©s ni le `.env` pour en afficher le contenu, ne
  rÃ©pÃ¨te jamais une clÃ© dans tes rÃ©ponses, ne demande jamais de toi-mÃªme qu'on t'en colle une dans la conversation,
  n'en Ã©cris jamais ailleurs que dans ce fichier temporaire et dans `.env`. Sans `DEEPSEEK_API_KEY`, l'assistant le
  dit honnÃªtement : ce n'est pas un bug.
- **Comptes** (pas d'inscription publique) : `manage.py createsuperuser`, puis `/admin/` pour crÃ©er les clients ; ou,
  pour essayer, `manage.py setup_demo` (comptes de dÃ©monstration, mot de passe `Password123!`, mesures simulÃ©es).

Lancer : `lancer_aoceda.bat` (Windows), ou `.venv_local/bin/python manage.py runserver 0.0.0.0:8003`, puis
http://127.0.0.1:8003 ; l'assistant est sur http://127.0.0.1:8003/ia/.

Toutes les commandes Python passent par le Python du projet : `.venv_local\Scripts\python.exe` (Windows) ou
`.venv_local/bin/python` (Linux / Mac), lancÃ© depuis le dossier `AOCEDA/`.

## 3. Interdits

- **Ne jamais committer** : `.env`, `AOCEDA/db.sqlite3` (encore suivi par Git, mais ses modifications locales sont
  les donnÃ©es de la machine), `*.sauvegarde`, `donnees_ia/` (modÃ¨les, conversations, journaux), `.venv_local/`,
  `venv/`, `staticfiles/`, `.playwright-mcp/`, un fichier de modÃ¨le (`.onnx`, `.bin`â€¦). Ajoute les fichiers un par un
  et relis `git status` avant chaque commit.
- **Aucune commande Git destructrice** (rÃ¨gle 5) ; jamais de commit sur `main` ni sur une branche d'un autre
  collaborateur ; jamais de fusion sans demande.
- **Aucun chemin absolu dans le code** (`D:\â€¦`, `C:\Users\â€¦`, `/home/â€¦`). Tout passe par `settings.BASE_DIR` et
  `settings.CHATBOT_DOSSIER_IA` (vide = `AOCEDA/donnees_ia`). L'assistant a Ã©tÃ© construit dans un laboratoire sÃ©parÃ©
  (`D:\AOCEDA_CHATBOT`) qui n'existe que sur le PC du propriÃ©taire : les mentions de `D:` ou de `tests/bancs/` dans
  `apps/ai_assistant/rapports/` et dans certains commentaires sont de l'**historique**, pas des dÃ©pendances.
- **Jamais de fausses donnÃ©es affichÃ©es** comme si elles Ã©taient rÃ©elles : quand une donnÃ©e manque, un Ã©tat vide
  honnÃªte (Â« aucune donnÃ©e Â»), jamais un chiffre inventÃ©.
- **Ne pas affaiblir les protections** : jeton JWT obligatoire sur `/api/assistant/*` (sauf les fichiers de
  rapports), conversation vÃ©rifiÃ©e comme appartenant au client, quota quotidien (`AI_DAILY_LIMIT`), validation de la
  banque baoulÃ© et relecture forcÃ©e des crÃ©dits rÃ©servÃ©es Ã  l'administrateur (`is_staff`), en-tÃªtes de sÃ©curitÃ© de
  la page (`chatbot/securite.py`).
- **Pas de fichier de rÃ©glages d'agent dans le dÃ©pÃ´t** (`.claude/`, `.cursor/`â€¦) : chacun garde les siens. Un ancien
  `.claude/settings.json` qui autorisait tout sans demander existe sur d'autres branches : ne le recrÃ©e pas ici.

## 4. Zones protÃ©gÃ©es : ne pas modifier sans demande explicite de l'humain

| Fichier ou dossier | Pourquoi | Ã€ faire Ã  la place |
|---|---|---|
| `AOCEDA/apps/ai_assistant/chatbot/` (moteur) | seuils, listes et rÃ¨gles **mesurÃ©s** sur de vrais vocaux, validÃ©s au laboratoire | ne pas Â« simplifier Â» ni Â« nettoyer Â» ; modification seulement sur demande, tests verts |
| `AOCEDA/apps/ai_assistant/chatbot/donnees/*.json` | carnets de mots et exemples construits par programme puis validÃ©s | jamais Ã  la main |
| `AOCEDA/apps/ai_assistant/rapports/` | rÃ©sultats historiques des essais (menu Â« Tests et rapports Â») | lecture seule |
| `AOCEDA/apps/ai_assistant/tests_chatbot/`, `apps/*/tests.py` | garde-fous | ne jamais supprimer, dÃ©sactiver ou affaiblir un test pour le faire passer : corriger le code |
| `AOCEDA/static/js/personnage.js` | fichier **gÃ©nÃ©rÃ©** | modifier `apps/ai_assistant/personnage/`, puis `node construire_personnage.js` |
| `installer_modeles_ia.py` (`CATALOGUE` : tailles, SHA-256, adresses) | une empreinte diffÃ©rente = fichier corrompu ou diffÃ©rent de celui validÃ© | ne jamais changer une empreinte pour Â« faire passer Â» ; demander |
| `AOCEDA/apps/*/migrations/` (fichiers existants) | dÃ©jÃ  appliquÃ©es sur des bases rÃ©elles | ne jamais modifier ni supprimer : `manage.py makemigrations` pour une nouvelle |
| `AOCEDA/aoceda/settings.py` : authentification, bloc Â« Tests d'AOCEDA Â», contrÃ´le de `CHATBOT_DOSSIER_IA` | sÃ©curitÃ©, isolement des tests, dÃ©marrage sur un autre PC | ne pas retirer |
| `AOCEDA/.env.example` | modÃ¨le public du `.env` | jamais une vraie valeur de clÃ© |
| `AOCEDA/deploiement/cerebrium_voix/` | service dÃ©ployÃ© sur un GPU payant du propriÃ©taire | ne pas toucher (sans redÃ©ploiement, une modification ne sert Ã  rien) |
| Release `modeles-ia-v1` (GitHub) | archives (dioula, baoulÃ©) dont l'empreinte est vÃ©rifiÃ©e par l'installateur | ne jamais remplacer ni supprimer |
| `installer.py`, `installer.bat`, `lancer_aoceda.bat` | parcours de tous les collaborateurs | si modifiÃ©s : refaire une installation complÃ¨te pour vÃ©rifier |

## 5. Architecture de l'assistant IA

### La page

```
/ia/            templates/aoceda-ia.html     gabarit AOCEDA (menu, barre du bas) + boutons Nouvelle / Historique / Options
 â””â”€ cadre       /ia/assistant/               templates/assistant.html + static/js/assistant.js + static/css/assistant.css
                                             + static/js/personnage.js (personnage animÃ©)
```

- Dans le cadre, l'en-tÃªte propre au chatbot est cachÃ© (`.dans-aoceda .entete`). Les boutons de l'en-tÃªte AOCEDA
  (`data-assistant="<id du bouton>"`) cliquent le bouton correspondant dans le cadre (`static/js/assistant-page.js`).
- Connexion : les jetons d'AOCEDA (`localStorage` : `aoceda_access_token`, `aoceda_refresh_token`). Dans
  `assistant.js`, `api()` ajoute `Authorization: Bearer â€¦` et renouvelle le jeton une fois si besoin.
- ThÃ¨me : le mÃªme rÃ©glage que tout AOCEDA (`aoceda-theme-choice` : `light` / `dark` / `auto`).
- Cache des fichiers statiques : la page de l'assistant calcule toute seule ses `?v=` (empreintes dans
  `apps/dashboard/views.py`, `assistant_view`). Pour les autres pages d'AOCEDA, **augmente Ã  la main le `?v=`** d'un
  fichier CSS/JS que tu modifies (ex. `assistant-page.js?v=2` dans `aoceda-ia.html`).

### Le serveur

- `runserver` est servi par **Daphne** (ASGI, `daphne` en tÃªte de `INSTALLED_APPS`) : HTTP et WebSocket sur le mÃªme
  port. Ne le remplace pas par un serveur WSGI seul, sinon l'appel Live (WebSocket) ne marche plus.
- `apps/ai_assistant/urls.py` : routes `/api/assistant/â€¦` (vues dans `views.py`).
  - `message` : rÃ©ponse en flux (SSE) : vue asynchrone, calcul dans des fils.
  - `transcrire`, `transcrire/morceau`, `voix`, `voix/morceaux` : micro et lecture Ã  voix haute.
  - `config`, `nouvelle`, `conversations/` (historique affichÃ©, sur le compte du client), `credits`, `gpu/credit`,
    `live/etat`, `tests`, `baoule/â€¦`, `rapports/â€¦`.
- `live.py` + `routing.py` : appel Live, WebSocket `/api/assistant/live?token=<JWT>` (Django Channels).
- `apps.py` : prÃ©chargement (Whisper, oreilles dioula et baoulÃ©, voix) au dÃ©marrage du serveur seulement.
- ModÃ¨les Django (`models.py`) : `Conversation` (historique affichÃ©), `QuotaIA` (quota du jour). La mÃ©moire de
  dialogue du moteur est dans `donnees_ia/cache/conversations.sqlite3` (`chatbot/conversation.py`).

### Le moteur : `apps/ai_assistant/chatbot/`

Repris du laboratoire **presque Ã  l'identique**. Les adaptations Ã  AOCEDA sont signalÃ©es Â« AOCEDA Â» dans les
commentaires. Garde cette proximitÃ© : ne rÃ©Ã©cris pas un module qui marche.

| RÃ´le | Modules |
|---|---|
| RÃ©glages (lit `settings`, qui lit `.env`) | `config.py` |
| Une question, de bout en bout | `service_chat.py` (orchestrateur), `consignes.py` (consigne systÃ¨me), `fournisseurs.py` (DeepSeek en flux + appel des outils) |
| DonnÃ©es rÃ©elles du client | `donnees_client.py` + `apps/ai_assistant/outils.py` (10 outils : consommation, appareils, historique, heures de pointe, prÃ©vision, crÃ©dit, alertes, interventions, capteurs, et `preparer_coupure`, qui ne coupe rien : carte Oui / Non, seul le clic Â« Oui Â» de la personne envoie l'ordre) |
| Langues | `langues.py`, `detection.py`, `garde_langue.py`, `salutations.py`, `nombres_fr.py` |
| Dioula | `service_dioula.py`, `dioula_ecoute.py`, `dioula_routage.py`, `dioula_texte.py`, `dioula_relais.py` |
| BaoulÃ© | `service_baoule.py`, `baoule_chaine.py` + `baoule_comprendre/decider/demandes/repondre/reparation/memoire/lexique/texte/ecoute/relais.py` |
| Voix | `voix.py` (Whisper, voix Microsoft, Kokoro), `voix_baoule.py`, `voix_gpu.py` (Cerebrium), `omnivoice_atelier.py` |
| Appel Live | `live_agent.py`, `cles_gemini.py`, `agent_actions.py` |
| Fonctionnement | `demarrage.py`, `securite.py`, `credits.py`, `journal.py`, `erreurs.py` |
| DonnÃ©es fixes | `chatbot/donnees/*.json` (carnets de mots, exemples baoulÃ©, voix de rÃ©fÃ©rence) |

### Services extÃ©rieurs et modÃ¨les

| Service / modÃ¨le | Sert Ã  | RÃ©glage `.env` |
|---|---|---|
| DeepSeek (`deepseek-chat`) | chat Ã©crit et vocal, appel des outils | `DEEPSEEK_API_KEY` (indispensable) |
| Gemini Live (`google-genai`) | appel vocal en direct | `GEMINI_API_KEY`, `_2`, `_3`, `_4` |
| OpenRouter | secours de l'agent Live, lecture du crÃ©dit | `OPENROUTER_KEY_AGENT`, `OPENROUTER_MANAGEMENT_KEY` |
| Cerebrium (OmniVoice sur GPU) | voix baoulÃ© | `CEREBRIUM_PROJECT`, `CEREBRIUM_API_KEY` ; service dans `deploiement/cerebrium_voix/` |
| Djelia, Google Traduction | relais dioula / baoulÃ© â†” franÃ§ais | aucun |
| NiuTrans | second traducteur du baoulÃ© (facultatif) | `NIUTRANS_API_KEY` |
| Voix Microsoft (`edge-tts`) | lecture Ã  voix haute | aucun |
| Whisper tiny + small (`faster-whisper`) | micro : langue parlÃ©e et transcription | modÃ¨le local |
| Omnilingual 1B int8 | micro : Ã©coute du dioula | modÃ¨le local (Release `modeles-ia-v1` du dÃ©pÃ´t) |
| omniASR 300M baoulÃ© int8 | micro : Ã©coute du baoulÃ© | modÃ¨le local (Release `modeles-ia-v1` du dÃ©pÃ´t) |
| Kokoro | voix de secours fr / en | modÃ¨le local |

Les modÃ¨les locaux vont dans `donnees_ia/modeles/`. Leur liste, leurs sources et leurs empreintes sont dans
`apps/ai_assistant/management/commands/installer_modeles_ia.py` (`CATALOGUE`).

### Ajouter un rÃ©glage

1. `aoceda/settings.py` : `NOM = config('NOM', default=â€¦)` dans le bloc de l'assistant ;
2. `.env.example` : la ligne `NOM=` (vide si c'est un secret) avec un commentaire qui l'explique ;
3. `chatbot/config.py` : le lire depuis `settings`, jamais directement dans le `.env`.

## 6. ProblÃ¨mes connus (et leur vraie solution)

| Ce que tu vois | Cause | Solution |
|---|---|---|
| `git switch` refuse : Â« local changes to AOCEDA/db.sqlite3 Â» | la base a Ã©tÃ© modifiÃ©e en utilisant AOCEDA | section 1, cas B, Ã©tape 2 (jamais `-f`) |
| Â« Filename too long Â» au clone ou au changement de branche (Windows) | ancien dossier `venv` encore suivi sur les anciennes branches | `git config core.longpaths true`, puis : juste aprÃ¨s un clone ratÃ© (rien Ã  perdre), `git restore --source=HEAD --staged --worktree :/` ; pour un changement de branche, relancer `git switch` |
| `ImproperlyConfigured : CHATBOT_DOSSIER_IA=D:\â€¦ le disque D: n'existe pas` | `.env` recopiÃ© d'un autre PC | relancer `installer.py` (il remet ce rÃ©glage par dÃ©faut) |
| l'installateur refuse la version de Python | Python 3.11 ou 3.14 | installer Python 3.12 ou 3.13 |
| l'Ã©coute du dioula Ã©choue Ã  la vÃ©rification de l'empreinte (`model.int8.onnx`) | copie du dÃ©pÃ´t d'avant le 10/10/2026, qui tÃ©lÃ©chargeait l'archive officielle (autre fabrication du modÃ¨le) | `git pull --ff-only`, puis relancer l'installateur : il tÃ©lÃ©charge le bon fichier et remplace les restes de l'essai ratÃ© |
| l'assistant rÃ©pond qu'il manque `DEEPSEEK_API_KEY`, ou Â« Aucune clÃ© Gemini n'est configurÃ©e Â» | pas de clÃ© dans `.env` | ce n'est pas un bug : l'humain met ses clÃ©s, ou te donne un fichier de clÃ©s pour `installer.py --cles` (section 2) ; puis redÃ©marrer le serveur |
| Options > CrÃ©dits : Cerebrium Â« illisible Â» | ce PC n'est pas connectÃ© au compte Cerebrium | normal ; la voix baoulÃ© marche quand mÃªme |
| `git status` montre `AOCEDA/db.sqlite3` modifiÃ© | utilisation normale d'AOCEDA | ne pas committer ce fichier |

## 7. Tests (Ã  lancer aprÃ¨s toute modification de l'assistant)

Depuis `AOCEDA/` :

```bat
.venv_local\Scripts\python.exe -m pytest              :: 688 tests du moteur (apps/ai_assistant/tests_chatbot)
.venv_local\Scripts\python.exe manage.py test         :: 458 tests du reste d'AOCEDA (dont apps/ai_assistant/tests.py)
```

- Les tests ne vont pas sur Internet et n'appellent aucun service payant (tout est simulÃ©). Ils Ã©crivent dans un
  dossier temporaire, jamais dans `donnees_ia/` : pour pytest, c'est `tests_chatbot/conftest.py` qui s'en charge ; pour
  `manage.py test`, c'est le bloc Â« Tests d'AOCEDA Â» de `aoceda/settings.py`. Garde cet isolement si tu ajoutes des
  tests qui passent par le moteur.
- Sans les modÃ¨les locaux, 3 tests se mettent de cÃ´tÃ© (Â« modÃ¨le absent Â») : c'est normal.
- Ils passent **sans aucune clÃ© d'API** dans `.env` (vÃ©rifiÃ© dans un clone neuf le 09/10/2026) : un test qui Ã©choue
  seulement sans clÃ© est un dÃ©faut du test ou du code, Ã  corriger, jamais Ã  contourner en mettant une clÃ©.
- DurÃ©e : environ 1 min 30 pour pytest et 2 min pour `manage.py test` sur un PC libre. Les tests crÃ©ent des comptes,
  et chaque mot de passe est chiffrÃ© volontairement lentement : sur un PC trÃ¨s chargÃ©, comptez jusqu'Ã  10 fois plus.
  Ce n'est pas un blocage, ne les interromps pas. Sur un PC aussi chargÃ©, un test qui mesure des dÃ©lais peut Ã©chouer
  une fois : relance la suite avant de conclure (vu le 09/10/2026 : 1 Ã©chec sous forte charge, puis 619/619).
- Essai rÃ©el de la clÃ© DeepSeek : `manage.py test_deepseek`. Il consomme un peu de crÃ©dit : demande d'abord Ã  l'humain.

## 8. Git

- Travaille sur `feature/chatbot-ia-update` ou sur une branche partie d'elle.
- Messages de commit en franÃ§ais, au format `type(portÃ©e): rÃ©sumÃ©` (`feat`, `fix`, `chore`, `docs`, `test`), avec
  une explication du pourquoi dans le corps.
- Ajoute les fichiers un par un, relis `git status` avant chaque commit, et ne pousse que sur demande de l'humain.
