# AGENTS.md : guide pour les agents IA qui travaillent sur ce dépôt

Ce fichier s'adresse aux agents de code (Claude Code, Codex, Cursor, Copilot, Gemini…) qui aident un collaborateur
d'AOCEDA. **Lis-le en entier avant toute action**, en particulier avant de changer de branche ou de modifier
l'assistant IA (le chatbot). Le guide d'installation pour les humains est
[AOCEDA/INSTALLATION.md](AOCEDA/INSTALLATION.md).

Tu le lis depuis une autre branche (par exemple avec `git show origin/feature/chatbot-ia-update:AGENTS.md`) ?
Applique la section 1, cas B, **avant** de changer de branche.

## L'essentiel en 8 règles

1. La branche de travail est **`feature/chatbot-ia-update`** (section 1).
2. Après chaque arrivée ou mise à jour sur la branche : `cd AOCEDA` puis `installer.bat` (Windows) ou
   `python3 installer.py` (Linux / Mac). On peut le relancer sans risque.
3. Le Python du projet est **`AOCEDA/.venv_local`**, jamais `venv`.
4. Ne jamais committer `.env`, `db.sqlite3`, `donnees_ia/` ni un modèle ; jamais `git add -A` ni `git add .`.
5. Jamais `git switch -f`, `git checkout -f`, `git reset --hard`, `git clean`, `git push --force`, ni réécriture de
   l'historique : ce sont des pertes de données. En cas de blocage, applique la section 1 ou demande à l'humain.
6. Ne modifie pas les **zones protégées** (section 4) sans demande explicite de l'humain.
7. Après toute modification de l'assistant : les deux suites de tests (section 7) doivent rester toutes vertes.
8. Ne pousse que si l'humain le demande ; ne télécharge pas les modèles (2,1 Go) sans son accord ; n'affiche jamais
   une clé d'API.

En cas de doute : **arrête-toi et demande à l'humain.** Une question coûte moins cher qu'une base effacée.

## 0. Le dépôt en bref

| Dossier | Contenu |
|---|---|
| racine (`platformio.ini`, `src/`, `include/`, `lib/`, `test/`) | micrologiciel ESP32 + capteurs ZMCT103C (PlatformIO) |
| `AOCEDA/` | serveur Django 6 : espace client, technicien, administration, API, **assistant IA** |
| `AOCEDA/apps/ai_assistant/` | l'assistant IA (ce fichier en parle surtout) |
| `AOCEDA/mobile_app/` | application Android (Capacitor) qui affiche le site |

Le projet est **en français** : commentaires, textes affichés, messages d'erreur, commits. Pour les noms dans le
code, suis le fichier que tu modifies (le moteur de l'assistant est entièrement en français).

## 1. Commencer ici : arriver sur la branche

D'abord, regarde où tu en es : `git branch --show-current` et `git status`.

### Cas A : pas encore de copie du projet

```bash
git clone -b feature/chatbot-ia-update https://github.com/silvercross2021-web/AOCEADA.git
```

Puis installe (section 2). Sans `-b feature/chatbot-ia-update`, le clone arrive sur `main`, très ancienne (sans ce
fichier, et sous Windows souvent avec l'erreur « Filename too long » : section 6) : passe alors sur la branche avec le
cas B.

### Cas B : une copie existe déjà, sur une autre branche

Ces étapes ont été déroulées pour de vrai (09/10/2026) depuis une ancienne copie de la branche `next-programs` :

1. **Changements en cours ?** `git status`. Si d'autres fichiers que `AOCEDA/db.sqlite3` sont modifiés, **ne jette
   rien** : montre la liste à l'humain et, avec son accord, commit sur sa branche actuelle ou
   `git stash push -m "avant feature/chatbot-ia-update"`.
2. **Sauvegarder sa base** (`db.sqlite3` contient ses comptes et ses mesures ; Git refuse de changer de branche
   tant qu'elle est modifiée) :
   ```bash
   cp AOCEDA/db.sqlite3 AOCEDA/db.sqlite3.sauvegarde      # PowerShell, Git Bash, Linux, Mac (invite cmd : copy)
   git restore AOCEDA/db.sqlite3
   ```
3. **Changer de branche :**
   ```bash
   git fetch origin
   git switch feature/chatbot-ia-update
   ```
   - « untracked working tree files would be overwritten » : déplace les fichiers cités **hors du dépôt** (ne les
     supprime pas), puis relance `git switch`.
   - « Filename too long » (Windows) : `git config core.longpaths true`, puis relance.
4. **Ce qui change tout seul, et c'est normal :** les anciens dossiers `AOCEDA/venv`, `AOCEDA/staticfiles`, `logs/`
   et `.claude/` disparaissent (ils ne sont plus suivis) ; le `.env` et `db.sqlite3.sauvegarde` restent.
5. **Quelle base garder ?** Par défaut, la branche fournit sa propre `db.sqlite3`. Si l'humain veut retrouver ses
   comptes et ses mesures : `cp AOCEDA/db.sqlite3.sauvegarde AOCEDA/db.sqlite3`. L'installateur la met à jour
   (migrations) sans perdre ses données.
6. **Installer** (section 2) : l'installateur garde l'ancien `.env` et y ajoute, **vides**, les réglages qui lui
   manquent (clés de l'assistant…). Il ne touche jamais aux réglages déjà présents (`DB_ENGINE`, `SECRET_KEY`…).
7. Dans VS Code, choisis l'interpréteur Python `AOCEDA/.venv_local`.

### Cas C : déjà sur la branche (mettre à jour)

```bash
git pull --ff-only
```

Si Git refuse à cause de `AOCEDA/db.sqlite3`, fais les étapes 2 et 5 du cas B. Ensuite, relance l'installateur
(nouvelles bibliothèques, migrations, modèles) : ce qui est déjà fait est sauté.

## 2. Installer

Prérequis : **Python 3.12 ou 3.13** (pas 3.11 : Django 6 le refuse ; pas 3.14 : `kokoro-onnx` n'existe pas encore pour
lui) et environ 4 Go libres.

```bat
cd AOCEDA
installer.bat              :: Windows
python3 installer.py       :: Linux / Mac
```

L'installateur fait tout, et on peut le relancer sans risque (ce qui est déjà fait est sauté) :

1. crée le Python du projet dans `AOCEDA/.venv_local` ;
2. installe `requirements.txt` ;
3. crée `AOCEDA/.env` depuis `.env.example` (clé secrète générée, base SQLite), ou complète un `.env` existant ;
4. applique les migrations ;
5. télécharge les modèles de l'assistant (**~2,1 Go**) depuis leurs sources et vérifie leur SHA-256 ;
6. liste les clés d'API qui manquent dans `.env`.

Règles pour toi, agent :

- **Demande à l'humain avant de lancer l'étape 5** (2,1 Go à télécharger). Pour la sauter : `--sans-modeles`, puis
  plus tard `manage.py installer_modeles_ia`. État des modèles sans rien télécharger :
  `manage.py installer_modeles_ia --verifier`. Modèles sur un autre disque : `installer.py --dossier-ia <dossier>`.
- Les écoutes du dioula (`omnilingual-1b-ctc-v2-int8`) et du baoulé (`omniasr-300m-baoule-int8`) viennent de la
  Release `modeles-ia-v1` de **ce** dépôt : ce sont les fichiers mesurés et validés, introuvables ailleurs (l'archive
  officielle du dioula contient une autre fabrication du modèle ; l'original du baoulé n'est plus sur Hugging Face).
  Ne les remplace pas par un modèle trouvé en ligne, même de même nom. Si une installation échoue, l'assistant
  marche quand même ; seul un message vocal dans cette langue n'est pas reconnu.
- **Une vérification d'empreinte qui échoue deux fois de suite** : arrête-toi et préviens l'humain, qui préviendra
  le propriétaire du dépôt. Ne change ni l'empreinte ni l'adresse (c'est ce qui a permis de trouver et corriger le
  défaut du modèle dioula le 10/10/2026).
- Les **clés d'API** vont dans `AOCEDA/.env`, de l'une de ces deux façons, au choix de l'humain :
  - il les y écrit lui-même ;
  - il te donne le **chemin d'un fichier de clés** reçu d'un membre de l'équipe (lignes `NOM=valeur`), et tu lances,
    depuis `AOCEDA/` : `.venv_local\Scripts\python.exe installer.py --cles "<chemin du fichier>"` (Linux / Mac :
    `.venv_local/bin/python installer.py --cles "<chemin>"`). La commande met les clés dans `.env` **sans les
    afficher** (seuls leurs noms apparaissent) et ne touche pas aux réglages propres au PC. Redémarre ensuite le
    serveur et rappelle à l'humain de supprimer le fichier de clés.

  Dans tous les cas : n'ouvre pas et ne lis pas un fichier de clés ni le `.env` pour en afficher le contenu, n'affiche
  jamais une clé, ne demande jamais qu'on t'en colle une dans la conversation, n'en écris jamais ailleurs que dans
  `.env`. Sans `DEEPSEEK_API_KEY`, l'assistant le dit honnêtement : ce n'est pas un bug.
- **Comptes** (pas d'inscription publique) : `manage.py createsuperuser`, puis `/admin/` pour créer les clients ; ou,
  pour essayer, `manage.py setup_demo` (comptes de démonstration, mot de passe `Password123!`, mesures simulées).

Lancer : `lancer_aoceda.bat` (Windows), ou `.venv_local/bin/python manage.py runserver 0.0.0.0:8003`, puis
http://127.0.0.1:8003 ; l'assistant est sur http://127.0.0.1:8003/ia/.

Toutes les commandes Python passent par le Python du projet : `.venv_local\Scripts\python.exe` (Windows) ou
`.venv_local/bin/python` (Linux / Mac), lancé depuis le dossier `AOCEDA/`.

## 3. Interdits

- **Ne jamais committer** : `.env`, `AOCEDA/db.sqlite3` (encore suivi par Git, mais ses modifications locales sont
  les données de la machine), `*.sauvegarde`, `donnees_ia/` (modèles, conversations, journaux), `.venv_local/`,
  `venv/`, `staticfiles/`, `.playwright-mcp/`, un fichier de modèle (`.onnx`, `.bin`…). Ajoute les fichiers un par un
  et relis `git status` avant chaque commit.
- **Aucune commande Git destructrice** (règle 5) ; jamais de commit sur `main` ni sur une branche d'un autre
  collaborateur ; jamais de fusion sans demande.
- **Aucun chemin absolu dans le code** (`D:\…`, `C:\Users\…`, `/home/…`). Tout passe par `settings.BASE_DIR` et
  `settings.CHATBOT_DOSSIER_IA` (vide = `AOCEDA/donnees_ia`). L'assistant a été construit dans un laboratoire séparé
  (`D:\AOCEDA_CHATBOT`) qui n'existe que sur le PC du propriétaire : les mentions de `D:` ou de `tests/bancs/` dans
  `apps/ai_assistant/rapports/` et dans certains commentaires sont de l'**historique**, pas des dépendances.
- **Jamais de fausses données affichées** comme si elles étaient réelles : quand une donnée manque, un état vide
  honnête (« aucune donnée »), jamais un chiffre inventé.
- **Ne pas affaiblir les protections** : jeton JWT obligatoire sur `/api/assistant/*` (sauf les fichiers de
  rapports), conversation vérifiée comme appartenant au client, quota quotidien (`AI_DAILY_LIMIT`), validation de la
  banque baoulé et relecture forcée des crédits réservées à l'administrateur (`is_staff`), en-têtes de sécurité de
  la page (`chatbot/securite.py`).
- **Pas de fichier de réglages d'agent dans le dépôt** (`.claude/`, `.cursor/`…) : chacun garde les siens. Un ancien
  `.claude/settings.json` qui autorisait tout sans demander existe sur d'autres branches : ne le recrée pas ici.

## 4. Zones protégées : ne pas modifier sans demande explicite de l'humain

| Fichier ou dossier | Pourquoi | À faire à la place |
|---|---|---|
| `AOCEDA/apps/ai_assistant/chatbot/` (moteur) | seuils, listes et règles **mesurés** sur de vrais vocaux, validés au laboratoire | ne pas « simplifier » ni « nettoyer » ; modification seulement sur demande, tests verts |
| `AOCEDA/apps/ai_assistant/chatbot/donnees/*.json` | carnets de mots et exemples construits par programme puis validés | jamais à la main |
| `AOCEDA/apps/ai_assistant/rapports/` | résultats historiques des essais (menu « Tests et rapports ») | lecture seule |
| `AOCEDA/apps/ai_assistant/tests_chatbot/`, `apps/*/tests.py` | garde-fous | ne jamais supprimer, désactiver ou affaiblir un test pour le faire passer : corriger le code |
| `AOCEDA/static/js/personnage.js` | fichier **généré** | modifier `apps/ai_assistant/personnage/`, puis `node construire_personnage.js` |
| `installer_modeles_ia.py` (`CATALOGUE` : tailles, SHA-256, adresses) | une empreinte différente = fichier corrompu ou différent de celui validé | ne jamais changer une empreinte pour « faire passer » ; demander |
| `AOCEDA/apps/*/migrations/` (fichiers existants) | déjà appliquées sur des bases réelles | ne jamais modifier ni supprimer : `manage.py makemigrations` pour une nouvelle |
| `AOCEDA/aoceda/settings.py` : authentification, bloc « Tests d'AOCEDA », contrôle de `CHATBOT_DOSSIER_IA` | sécurité, isolement des tests, démarrage sur un autre PC | ne pas retirer |
| `AOCEDA/.env.example` | modèle public du `.env` | jamais une vraie valeur de clé |
| `AOCEDA/deploiement/cerebrium_voix/` | service déployé sur un GPU payant du propriétaire | ne pas toucher (sans redéploiement, une modification ne sert à rien) |
| Release `modeles-ia-v1` (GitHub) | archives (dioula, baoulé) dont l'empreinte est vérifiée par l'installateur | ne jamais remplacer ni supprimer |
| `installer.py`, `installer.bat`, `lancer_aoceda.bat` | parcours de tous les collaborateurs | si modifiés : refaire une installation complète pour vérifier |

## 5. Architecture de l'assistant IA

### La page

```
/ia/            templates/aoceda-ia.html     gabarit AOCEDA (menu, barre du bas) + boutons Nouvelle / Historique / Options
 └─ cadre       /ia/assistant/               templates/assistant.html + static/js/assistant.js + static/css/assistant.css
                                             + static/js/personnage.js (personnage animé)
```

- Dans le cadre, l'en-tête propre au chatbot est caché (`.dans-aoceda .entete`). Les boutons de l'en-tête AOCEDA
  (`data-assistant="<id du bouton>"`) cliquent le bouton correspondant dans le cadre (`static/js/assistant-page.js`).
- Connexion : les jetons d'AOCEDA (`localStorage` : `aoceda_access_token`, `aoceda_refresh_token`). Dans
  `assistant.js`, `api()` ajoute `Authorization: Bearer …` et renouvelle le jeton une fois si besoin.
- Thème : le même réglage que tout AOCEDA (`aoceda-theme-choice` : `light` / `dark` / `auto`).
- Cache des fichiers statiques : la page de l'assistant calcule toute seule ses `?v=` (empreintes dans
  `apps/dashboard/views.py`, `assistant_view`). Pour les autres pages d'AOCEDA, **augmente à la main le `?v=`** d'un
  fichier CSS/JS que tu modifies (ex. `assistant-page.js?v=2` dans `aoceda-ia.html`).

### Le serveur

- `runserver` est servi par **Daphne** (ASGI, `daphne` en tête de `INSTALLED_APPS`) : HTTP et WebSocket sur le même
  port. Ne le remplace pas par un serveur WSGI seul, sinon l'appel Live (WebSocket) ne marche plus.
- `apps/ai_assistant/urls.py` : routes `/api/assistant/…` (vues dans `views.py`).
  - `message` : réponse en flux (SSE) : vue asynchrone, calcul dans des fils.
  - `transcrire`, `transcrire/morceau`, `voix`, `voix/morceaux` : micro et lecture à voix haute.
  - `config`, `nouvelle`, `conversations/` (historique affiché, sur le compte du client), `credits`, `gpu/credit`,
    `live/etat`, `tests`, `baoule/…`, `rapports/…`.
- `live.py` + `routing.py` : appel Live, WebSocket `/api/assistant/live?token=<JWT>` (Django Channels).
- `apps.py` : préchargement (Whisper, oreilles dioula et baoulé, voix) au démarrage du serveur seulement.
- Modèles Django (`models.py`) : `Conversation` (historique affiché), `QuotaIA` (quota du jour). La mémoire de
  dialogue du moteur est dans `donnees_ia/cache/conversations.sqlite3` (`chatbot/conversation.py`).

### Le moteur : `apps/ai_assistant/chatbot/`

Repris du laboratoire **presque à l'identique**. Les adaptations à AOCEDA sont signalées « AOCEDA » dans les
commentaires. Garde cette proximité : ne réécris pas un module qui marche.

| Rôle | Modules |
|---|---|
| Réglages (lit `settings`, qui lit `.env`) | `config.py` |
| Une question, de bout en bout | `service_chat.py` (orchestrateur), `consignes.py` (consigne système), `fournisseurs.py` (DeepSeek en flux + appel des outils) |
| Données réelles du client | `donnees_client.py` + `apps/ai_assistant/outils.py` (9 outils : consommation, appareils, historique, heures de pointe, prévision, crédit, alertes, interventions, capteurs) |
| Langues | `langues.py`, `detection.py`, `garde_langue.py`, `salutations.py`, `nombres_fr.py` |
| Dioula | `service_dioula.py`, `dioula_ecoute.py`, `dioula_routage.py`, `dioula_texte.py`, `dioula_relais.py` |
| Baoulé | `service_baoule.py`, `baoule_chaine.py` + `baoule_comprendre/decider/demandes/repondre/reparation/memoire/lexique/texte/ecoute/relais.py` |
| Voix | `voix.py` (Whisper, voix Microsoft, Kokoro), `voix_baoule.py`, `voix_gpu.py` (Cerebrium), `omnivoice_atelier.py` |
| Appel Live | `live_agent.py`, `cles_gemini.py`, `agent_actions.py` |
| Fonctionnement | `demarrage.py`, `securite.py`, `credits.py`, `journal.py`, `erreurs.py` |
| Données fixes | `chatbot/donnees/*.json` (carnets de mots, exemples baoulé, voix de référence) |

### Services extérieurs et modèles

| Service / modèle | Sert à | Réglage `.env` |
|---|---|---|
| DeepSeek (`deepseek-chat`) | chat écrit et vocal, appel des outils | `DEEPSEEK_API_KEY` (indispensable) |
| Gemini Live (`google-genai`) | appel vocal en direct | `GEMINI_API_KEY`, `_2`, `_3`, `_4` |
| OpenRouter | secours de l'agent Live, lecture du crédit | `OPENROUTER_KEY_AGENT`, `OPENROUTER_MANAGEMENT_KEY` |
| Cerebrium (OmniVoice sur GPU) | voix baoulé | `CEREBRIUM_PROJECT`, `CEREBRIUM_API_KEY` ; service dans `deploiement/cerebrium_voix/` |
| Djelia, Google Traduction | relais dioula / baoulé ↔ français | aucun |
| NiuTrans | second traducteur du baoulé (facultatif) | `NIUTRANS_API_KEY` |
| Voix Microsoft (`edge-tts`) | lecture à voix haute | aucun |
| Whisper tiny + small (`faster-whisper`) | micro : langue parlée et transcription | modèle local |
| Omnilingual 1B int8 | micro : écoute du dioula | modèle local (Release `modeles-ia-v1` du dépôt) |
| omniASR 300M baoulé int8 | micro : écoute du baoulé | modèle local (Release `modeles-ia-v1` du dépôt) |
| Kokoro | voix de secours fr / en | modèle local |

Les modèles locaux vont dans `donnees_ia/modeles/`. Leur liste, leurs sources et leurs empreintes sont dans
`apps/ai_assistant/management/commands/installer_modeles_ia.py` (`CATALOGUE`).

### Ajouter un réglage

1. `aoceda/settings.py` : `NOM = config('NOM', default=…)` dans le bloc de l'assistant ;
2. `.env.example` : la ligne `NOM=` (vide si c'est un secret) avec un commentaire qui l'explique ;
3. `chatbot/config.py` : le lire depuis `settings`, jamais directement dans le `.env`.

## 6. Problèmes connus (et leur vraie solution)

| Ce que tu vois | Cause | Solution |
|---|---|---|
| `git switch` refuse : « local changes to AOCEDA/db.sqlite3 » | la base a été modifiée en utilisant AOCEDA | section 1, cas B, étape 2 (jamais `-f`) |
| « Filename too long » au clone ou au changement de branche (Windows) | ancien dossier `venv` encore suivi sur les anciennes branches | `git config core.longpaths true`, puis : juste après un clone raté (rien à perdre), `git restore --source=HEAD --staged --worktree :/` ; pour un changement de branche, relancer `git switch` |
| `ImproperlyConfigured : CHATBOT_DOSSIER_IA=D:\… le disque D: n'existe pas` | `.env` recopié d'un autre PC | relancer `installer.py` (il remet ce réglage par défaut) |
| l'installateur refuse la version de Python | Python 3.11 ou 3.14 | installer Python 3.12 ou 3.13 |
| l'écoute du dioula échoue à la vérification de l'empreinte (`model.int8.onnx`) | copie du dépôt d'avant le 10/10/2026, qui téléchargeait l'archive officielle (autre fabrication du modèle) | `git pull --ff-only`, puis relancer l'installateur : il télécharge le bon fichier et remplace les restes de l'essai raté |
| l'assistant répond qu'il manque `DEEPSEEK_API_KEY`, ou « Aucune clé Gemini n'est configurée » | pas de clé dans `.env` | ce n'est pas un bug : l'humain met ses clés, ou te donne un fichier de clés pour `installer.py --cles` (section 2) ; puis redémarrer le serveur |
| Options > Crédits : Cerebrium « illisible » | ce PC n'est pas connecté au compte Cerebrium | normal ; la voix baoulé marche quand même |
| `git status` montre `AOCEDA/db.sqlite3` modifié | utilisation normale d'AOCEDA | ne pas committer ce fichier |

## 7. Tests (à lancer après toute modification de l'assistant)

Depuis `AOCEDA/` :

```bat
.venv_local\Scripts\python.exe -m pytest              :: 619 tests du moteur (apps/ai_assistant/tests_chatbot)
.venv_local\Scripts\python.exe manage.py test         :: 189 tests du reste d'AOCEDA (dont apps/ai_assistant/tests.py)
```

- Les tests ne vont pas sur Internet et n'appellent aucun service payant (tout est simulé). Ils écrivent dans un
  dossier temporaire, jamais dans `donnees_ia/` : pour pytest, c'est `tests_chatbot/conftest.py` qui s'en charge ; pour
  `manage.py test`, c'est le bloc « Tests d'AOCEDA » de `aoceda/settings.py`. Garde cet isolement si tu ajoutes des
  tests qui passent par le moteur.
- Sans les modèles locaux, 3 tests se mettent de côté (« modèle absent ») : c'est normal.
- Ils passent **sans aucune clé d'API** dans `.env` (vérifié dans un clone neuf le 09/10/2026) : un test qui échoue
  seulement sans clé est un défaut du test ou du code, à corriger, jamais à contourner en mettant une clé.
- Durée : environ 1 min 30 pour pytest et 2 min pour `manage.py test` sur un PC libre. Les tests créent des comptes,
  et chaque mot de passe est chiffré volontairement lentement : sur un PC très chargé, comptez jusqu'à 10 fois plus.
  Ce n'est pas un blocage, ne les interromps pas. Sur un PC aussi chargé, un test qui mesure des délais peut échouer
  une fois : relance la suite avant de conclure (vu le 09/10/2026 : 1 échec sous forte charge, puis 619/619).
- Essai réel de la clé DeepSeek : `manage.py test_deepseek`. Il consomme un peu de crédit : demande d'abord à l'humain.

## 8. Git

- Travaille sur `feature/chatbot-ia-update` ou sur une branche partie d'elle.
- Messages de commit en français, au format `type(portée): résumé` (`feat`, `fix`, `chore`, `docs`, `test`), avec
  une explication du pourquoi dans le corps.
- Ajoute les fichiers un par un, relis `git status` avant chaque commit, et ne pousse que sur demande de l'humain.
