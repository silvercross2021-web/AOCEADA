# 01 · Inventaire du dépôt (lecture seule)

Date : 2026-10-19 · Branche : `refactor/architecture-propre` (tag `avant-refonte`) · 749 fichiers suivis par Git.

**Méthode et limites.** Cet inventaire vient de commandes (`git ls-files`, `wc`, `git grep`, extraction des `import`).
Les 82 fichiers Python de `ai_assistant` (zone protégée) et les gros fichiers JS/CSS n'ont pas été relus ligne par
ligne : ils sont cartographiés par leur structure, leur taille et leurs références. Toute affirmation « inutilisé »
du document 02 s'appuie sur une recherche de références, pas sur la lecture intégrale.

## 1. Vue d'ensemble

| Ensemble | Chemin | Fichiers suivis | Rôle |
|---|---|---|---|
| Micrologiciel ESP32 | `src/`, `include/`, `lib/`, `test/`, `platformio.ini` | 4 + 3 READMEs vides | Lecture ZMCT103C, envoi à `/api/sensors/zmct/` |
| Serveur Django | `AOCEDA/aoceda/` + `AOCEDA/apps/` | 6 + 467 | Configuration + 6 applications |
| Front servi par Django | `AOCEDA/static/`, `AOCEDA/templates/` | 74 + 17 | CSS/JS/images/vidéos + gabarits |
| Application Android | `AOCEDA/mobile_app/` | 85 | Capacitor qui affiche le site |
| Assistant IA | `AOCEDA/apps/ai_assistant/` | ~330 | Moteur, rapports, personnage, tests |
| Outillage | `AOCEDA/scripts/`, `installer.*`, `lancer_aoceda.bat`, `lancer_ngrok.bat` | 15 + 4 | Installation, lancement, essais |
| Documentation | racine, `AOCEDA/*.md`, mémoire | voir §6 | |
| Déchets probables | `AOCEDA/_backup_presync`, `brain`, `maquette`, `rapport`, `detect_dashes.py`… | ~45 | voir doc 02 |

Éléments **présents sur le disque mais non suivis** (ou ignorés) : `AOCEDA/venv` ET `AOCEDA/.venv_local` (deux
environnements), `AOCEDA/staticfiles`, `AOCEDA/dioula_models`, `AOCEDA/donnees_ia`, `logs/` à la
racine, `.pio`, trois sauvegardes `db.sqlite3*.sauvegarde`, `ESSAI_VOIX_BAOULE/` (30 Mo, non suivi), 13 captures
`UserssilveDocuments…audit_dashboard…png` à la racine (non suivies, nom issu d'un chemin Windows mal converti),
`compile_commands.json`.

## 2. Racine du dépôt

| Élément | Rôle | Remarque |
|---|---|---|
| `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md` | consignes aux agents IA | AGENTS.md fait foi ; les 3 autres le pointent |
| `README.md` | présentation | à relire (phase 6) |
| `methode_detection_onoff_zmct103c.md` (28 Ko) | méthode de détection ON/OFF du firmware | doc technique égarée à la racine |
| `platformio.ini`, `src/main.cpp`, `include/`, `lib/`, `test/` | firmware | **non touché**. `src/main.cpp` contient en local des mots de passe Wi-Fi non commités |
| `lancer_ngrok.bat` | tunnel ngrok | à documenter |
| `.vscode/` (2 fichiers suivis), `AOCEDA/.vscode/settings.json` | réglages éditeur | AGENTS.md interdit les réglages d'agent, pas ceux de VS Code |
| `.github/` | uniquement `copilot-instructions.md` | **aucun workflow CI** |

## 3. Serveur Django (`AOCEDA/`)

### 3.1 Racine de `AOCEDA/`

`manage.py`, `pytest.ini`, `requirements.txt`, `Procfile`, `.env.example`, `installer.py`, `installer.bat`,
`lancer_aoceda.bat` (contrats figés), puis des fichiers égarés : `detect_dashes.py` (dernier commit 2026-07-05),
`serial_bridge.py` (pont série Arduino, référencé par `settings.py` et `sensors/urls.py` : **vivant**),
`pyrefly.toml`, `pyrightconfig.json`, `skills-lock.json` (verrou de « skills » d'agent, 2026-07-02), `image pour coxio.png`
(espace dans le nom), `db.sqlite3` (suivi malgré tout, voir AGENTS.md §3), `EXPLICATION_TARIFAIRE.md`, `INSTALLATION.md`.

### 3.2 Applications (lignes de Python hors migrations non comptées à part)

| App | Py | Lignes | Couches présentes |
|---|---|---|---|
| `accounts` | 40 | 3 666 | models, serializers, views (746), permissions, authentication, signals, audit, utils, villes, admin, 2 commandes ; `urls.py` + `urls_users.py` |
| `sensors` | 33 | 4 841 | models, serializers, **views (1 430)**, authentication, urls, admin, 3 commandes (`seed_demo`, `seed_kpi3`, `setup_nguessan`) |
| `analytics` | 26 | 4 870 | models, **views (1 612)**, `tarifs_cie` (344), `prevision_ia` (359), `pdf` (365), `conseils`, `meteo`, `jours_feries`, tasks (Celery) |
| `alerts` | 19 | 1 964 | models, serializers, views (169), **utils (508)** (le moteur d'alertes), signals, tasks (Celery) |
| `dashboard` | 9 | 1 115 | views (386, pages HTML), urls, `setup_demo` (575) |
| `ai_assistant` | 82 | 19 767 | `chatbot/` (53 fichiers, moteur), `tests_chatbot/`, `rapports/` (241 fichiers), `personnage/`, views, live, routing, outils, 2 commandes |
| `aoceda/` (projet) | 6 | — | settings, urls, asgi, celery, wsgi… |

**Modules trop gros ou aux responsabilités mélangées** (> 700 lignes, hors tests) : `analytics/views.py` 1 612,
`sensors/views.py` 1 430, `live_agent.py` 1 268 et `voix.py` 1 259 (zone protégée), `accounts/views.py` 746.

### 3.3 Graphe des dépendances entre applications (imports `apps.X`, hors migrations)

```
accounts   -> alerts(1) analytics(1) sensors(5)
sensors    -> accounts(40) alerts(3) analytics(1)
alerts     -> accounts(9) analytics(10) sensors(7)
analytics  -> accounts(10) ai_assistant(1) alerts(15) sensors(11)
dashboard  -> accounts(3) ai_assistant(1) alerts(4) analytics(2) sensors(3)
ai_assistant -> accounts(6) alerts(3) analytics(8) sensors(13)
```

**Cycles bruts** : `accounts <-> sensors`, `accounts <-> alerts`, `accounts <-> analytics`, `sensors <-> alerts`,
`sensors <-> analytics`, `alerts <-> analytics`, `analytics -> ai_assistant -> analytics`. Pas de couche « basse »
claire : tout le monde importe tout le monde. Les imports différés (dans des fonctions) qui masquent ces cycles
seront listés en phase 2 avec le Gardien.

### 3.4 Tests (≈ 14 000 lignes)

| Emplacement | Nommage | Suite |
|---|---|---|
| `apps/ai_assistant/tests_chatbot/` (13 `test_*.py`, `conftest.py`, `client_test.py`, `serveur_labo.py`) | pytest | 688 |
| `apps/<app>/tests.py` + `tests_<sujet>.py` (accounts 2, alerts 3, analytics 6, dashboard 1, sensors 2, ai_assistant 1) | `manage.py test` | 458 |

Incohérences : un seul gros `tests.py` par app mélange plusieurs sujets ; `client_test.py` et `serveur_labo.py`
sont des outils nommés comme des tests ; deux commandes d'essai (`test_email`, `test_deepseek`) portent un nom en
`test_` alors que ce sont des commandes de gestion.

## 4. Front

- `static/js` : 15 fichiers, un par page (`dashboard.js` 1 980, `technicien.js` 2 950, `assistant.js` 3 140,
  `historique.js`, `alertes.js`, `previsions.js`, `parametres.js`, `interventions.js`, `auth.js`, `index.js`) + socle
  (`client-shell.js`, `refonte-shell.js`, `i18n.js`, `assistant-page.js`) + `personnage.js` (**généré**, 3 194 l.).
- `static/css` : 19 fichiers. Deux générations qui coexistent : pages (`dashboard.css`, `alertes.css`…) et
  `refonte-*.css` (7 fichiers) qui les surchargent ; `client-shell.css` en plus. Le préfixe « refonte » dit une
  date de travail, pas un rôle.
- `templates/` : 13 pages `aoceda-*.html` à plat, `assistant.html`, `index.html`, `partials/`, `admin/`,
  `_client_shell_reference.html` (nom de référence/maquette dans les gabarits).
- `static/img` 33 fichiers, `static/video` 6, `favicon.svg`.
- CDN et `?v=` : à relever gabarit par gabarit en phase 2 (le Gardien en dresse la liste automatiquement).
- `mobile_app/` : Capacitor (`capacitor.config.json`, `android/`, `www/`, `assets/`) ; `node_modules/` présent sur
  le disque, ignoré par Git.

## 5. Scripts, archives et dossiers « hors application »

| Chemin | Contenu | Référencé par |
|---|---|---|
| `AOCEDA/scripts/` (15 fichiers) | essais dioula (WAV, TXT), `lamia_dioula_test.py`, `colab_test_mms_dioula.py`, `make_kpi3_pdf.py`, `seed_kpi3_ai_conversations.py`, JSON de questions | rien, hors eux-mêmes |
| `AOCEDA/_backup_presync/` (5) | copies d'anciens `models.py`, `serializers.py`, `technicien.*` (2026-07) | rien |
| `AOCEDA/brain/<uuid>/scratch/` (2) | `patch_templates.py`, `wrap_verbatim.py` (scripts jetables d'une session d'agent) | rien |
| `AOCEDA/maquette/` (13 HTML) | maquettes de design, dont deux doublons `… (1).html` | citées dans le mémoire et un commentaire |
| `AOCEDA/rapport/` (2 HTML) | rapports de tests et d'audit technicien (2026-07) | des commentaires dans `technicien.js`/`urls.py` parlent d'autre chose (rapport d'intervention) |
| `AOCEDA/diagrame+memoire/` (4) | mémoire V30 `.md` + V41 `.docx` (« diagrame » mal orthographié, `+` dans le nom) | rien |
| `AOCEDA/Memoire_MD/` (19) | mémoire `.md` + 18 images | rien |
| `AOCEDA/deploiement/` (5) | `cerebrium_voix/` (zone protégée) | docs |
| `AOCEDA/media/avatars` (1) | upload suivi alors que `media/` est ignoré | — |

## 6. Documentation (Markdown)

| Fichier | Taille | État |
|---|---|---|
| `AGENTS.md` | 23 Ko | à jour, fait foi ; devra suivre les nouveaux chemins |
| `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md` | < 1 Ko | pointeurs vers AGENTS.md |
| `README.md` | 7,5 Ko | à relire |
| `AOCEDA/INSTALLATION.md` | 7,5 Ko | à jour (guide humain) |
| `AOCEDA/EXPLICATION_TARIFAIRE.md` | 10 Ko | à vérifier contre `tarifs_cie.py` |
| `methode_detection_onoff_zmct103c.md` | 28 Ko | doc firmware à ranger |
| Mémoire IIT (`Memoire_MD/…md` 145 Ko, `diagrame+memoire/…V30FB.md` 128 Ko) | 2 versions du même texte | doublon / versions |
| `apps/ai_assistant/rapports/` | historique (lecture seule) | ne pas toucher |

Pas de dossier `docs/` avant cette refonte (créé ici).
