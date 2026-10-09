# AGENTS.md : guide pour les agents IA qui travaillent sur ce dépôt

Ce fichier s'adresse aux agents de code (Claude Code, Codex, Cursor, Copilot, Gemini…) qui aident un collaborateur
d'AOCEDA. Lis-le en entier avant toute modification de l'**assistant IA** (le chatbot). Le guide d'installation pour
les humains est [AOCEDA/INSTALLATION.md](AOCEDA/INSTALLATION.md).

## 0. Le dépôt en bref

| Dossier | Contenu |
|---|---|
| racine (`platformio.ini`, `src/`, `include/`, `lib/`, `test/`) | micrologiciel ESP32 + capteurs ZMCT103C (PlatformIO) |
| `AOCEDA/` | serveur Django 6 : espace client, technicien, administration, API, **assistant IA** |
| `AOCEDA/apps/ai_assistant/` | l'assistant IA (ce fichier en parle surtout) |
| `AOCEDA/mobile_app/` | application Android (Capacitor) qui affiche le site |

Le projet est **en français** : commentaires, textes affichés, messages d'erreur, commits. Pour les noms dans le
code, suis le fichier que tu modifies (le moteur de l'assistant est entièrement en français).

## 1. Quelle branche

L'assistant IA actuel vit sur la branche **`feature/chatbot-ia-update`**. `main` est très ancienne : ne pars jamais
de `main` pour travailler sur l'assistant.

```bash
git clone -b feature/chatbot-ia-update https://github.com/silvercross2021-web/AOCEADA.git
```

Si le dépôt est déjà cloné : `git fetch origin` puis `git switch feature/chatbot-ia-update`.

## 2. Installer après un clone (dans cet ordre)

Prérequis : **Python 3.12 ou 3.13** (pas 3.11 : Django 6 le refuse ; pas 3.14 : `kokoro-onnx` n'existe pas encore pour
lui) et environ 4 Go libres.

```bat
cd AOCEDA
installer.bat              :: Windows
python3 installer.py       :: Linux / Mac
```

L'installateur fait tout, et on peut le relancer sans risque (ce qui est déjà fait est sauté) :

1. crée le Python du projet dans `AOCEDA/.venv_local` (c'est LE Python du projet ; l'ancien dossier `venv` n'existe plus) ;
2. installe `requirements.txt` ;
3. crée `AOCEDA/.env` depuis `.env.example` (clé secrète générée, base SQLite) ;
4. applique les migrations ;
5. télécharge les modèles de l'assistant (**~2,1 Go**) depuis leurs sources officielles et vérifie leur SHA-256 ;
6. liste les clés d'API qui manquent dans `.env`.

Règles pour toi, agent :

- **Demande à l'humain avant de lancer l'étape 5** (2,1 Go à télécharger). Pour la sauter : `--sans-modeles`, puis
  plus tard `manage.py installer_modeles_ia`. État des modèles sans rien télécharger :
  `manage.py installer_modeles_ia --verifier`. Modèles sur un autre disque : `installer.py --dossier-ia <dossier>`.
- Le message « Pas encore téléchargeable : omniasr-300m-baoule-int8 » est **normal** : l'archive d'écoute baoulé
  n'est pas encore publiée (réglage `CHATBOT_SOURCE_ECOUTE_BAOULE` vide). Ce n'est pas un bug à corriger. Sans ce
  modèle, l'assistant marche ; seul un message vocal en baoulé n'est pas reconnu.
- Les **clés d'API** sont mises dans `AOCEDA/.env` par l'humain lui-même. Ne demande jamais qu'on te colle une clé dans
  la conversation, n'en affiche jamais, n'en écris jamais dans un autre fichier. Sans `DEEPSEEK_API_KEY`, l'assistant
  le dit honnêtement : ce n'est pas un bug.
- **Comptes** (pas d'inscription publique) : `manage.py createsuperuser`, puis `/admin/` pour créer les clients ; ou,
  pour essayer, `manage.py setup_demo` (comptes de démonstration, mot de passe `Password123!`, mesures simulées).

Lancer : `lancer_aoceda.bat` (Windows), ou `.venv_local/bin/python manage.py runserver 0.0.0.0:8003`, puis
http://127.0.0.1:8003 ; l'assistant est sur http://127.0.0.1:8003/ia/.

Toutes les commandes Python passent par le Python du projet : `.venv_local\Scripts\python.exe` (Windows) ou
`.venv_local/bin/python` (Linux / Mac), lancé depuis le dossier `AOCEDA/`.

## 3. Interdits

- **Ne jamais committer** : `.env`, `donnees_ia/` (modèles, conversations, journaux), `.venv_local/`, `venv/`,
  `staticfiles/`, `.playwright-mcp/`, un fichier de modèle (`.onnx`, `.bin`…). Le `.gitignore` les exclut : ne le
  contourne pas.
- **Pas de `git add -A` ni de `git add .`** : ajoute les fichiers un par un. `AOCEDA/db.sqlite3` est encore suivi par
  Git mais contient des données réelles : ne committe jamais ses modifications locales.
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
- **Ne pas pousser** sans que l'humain le demande.

## 4. Architecture de l'assistant IA

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
- `static/js/personnage.js` est **généré** : modifie les sources de `apps/ai_assistant/personnage/`, puis
  `node construire_personnage.js` dans ce dossier.

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
| Omnilingual 1B int8 | micro : écoute du dioula | modèle local |
| omniASR 300M baoulé int8 | micro : écoute du baoulé | modèle local (archive pas encore publiée) |
| Kokoro | voix de secours fr / en | modèle local |

Les modèles locaux vont dans `donnees_ia/modeles/`. Leur liste, leurs sources et leurs empreintes sont dans
`apps/ai_assistant/management/commands/installer_modeles_ia.py` (`CATALOGUE`).

### Ajouter un réglage

1. `aoceda/settings.py` : `NOM = config('NOM', default=…)` dans le bloc de l'assistant ;
2. `.env.example` : la ligne `NOM=` (vide si c'est un secret) avec un commentaire qui l'explique ;
3. `chatbot/config.py` : le lire depuis `settings`, jamais directement dans le `.env`.

## 5. Tests (à lancer après toute modification de l'assistant)

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
- Essai réel de la clé DeepSeek : `manage.py test_deepseek`. Il consomme un peu de crédit : demande d'abord à l'humain.

## 6. Git

- Travaille sur `feature/chatbot-ia-update` ou sur une branche partie d'elle.
- Messages de commit en français, au format `type(portée): résumé` (`feat`, `fix`, `chore`, `docs`, `test`), avec
  une explication du pourquoi dans le corps.
- Ajoute les fichiers un par un, relis `git status` avant chaque commit, et ne pousse que sur demande de l'humain.
