# ARCHITECTURE : où est quoi dans le dépôt AOCEDA

Carte complète et à jour du dépôt (relue le 2026-10-19 à partir du code réel : arborescence Git, docstrings, routeur Django,
gabarits, JS/CSS, firmware). Pour les règles de travail : [AGENTS.md](AGENTS.md). Pour démarrer : [README.md](README.md).
Pour le détail de chaque sujet : [docs/](docs/README.md).

**Sommaire** : [1. Vue d'ensemble](#1-vue-densemble) · [2. Arborescence](#2-arborescence-complète) · [3. Le serveur Django](#3-le-serveur-django) ·
[4. Les 6 applications](#4-les-6-applications) · [5. L'assistant IA](#5-lassistant-ia) · [6. Le front](#6-le-front-pages-js-css) ·
[7. Le firmware](#7-le-firmware-esp32) · [8. L'application Android](#8-lapplication-android) · [9. Flux de bout en bout](#9-flux-de-bout-en-bout) ·
[10. Tests](#10-les-tests) · [11. Outillage et installation](#11-outillage-installation-lancement) · [12. Fichiers locaux](#12-ce-qui-nest-jamais-dans-git) ·
[13. Contrats et zones protégées](#13-contrats-figés-et-zones-protégées) · [14. Dépendances et dette](#14-dépendances-entre-applications-et-dette-connue) ·
[15. Où mettre quoi](#15-où-mettre-quoi-quand-on-ajoute-quelque-chose)

---

## 1. Vue d'ensemble

```
Capteurs ZMCT103C ─► ESP32 (src/main.cpp) ──Wi-Fi──► Serveur Django (AOCEDA/) ──► base SQLite / PostgreSQL
 + relais (coupure)        ▲  ordres de coupure          │   ▲                         │
                           └──── réponse HTTP ◄──────────┘   │                         ▼
Arduino + pont série (outils/serial_bridge.py) ────────────►│            pages web (templates + static)
                                                             │            application Android (Capacitor)
                         assistant IA (apps/ai_assistant) ◄──┘            tâches Celery (alertes, prévisions, météo)
                         DeepSeek, Gemini Live, Whisper, voix, dioula, baoulé
```

Quatre ensembles indépendants dans un seul dépôt :

| Ensemble | Où | Techno | Dépend de |
|---|---|---|---|
| Micrologiciel | `src/`, `include/`, `lib/`, `test/`, `platformio.ini` | C++ Arduino / PlatformIO, ESP32 | l'URL et le format de `POST /api/sensors/zmct/` |
| Serveur | `AOCEDA/aoceda/`, `AOCEDA/apps/` | Python 3.12-3.13, Django 6, DRF, JWT, Channels (Daphne, ASGI), Celery | rien d'autre |
| Front | `AOCEDA/static/`, `AOCEDA/templates/` | HTML, JS et CSS « à la main » (sans framework de build) | l'API du serveur |
| Mobile | `AOCEDA/mobile_app/` | Capacitor (Android) | le site déployé |

---

## 2. Arborescence complète

```
Test_ZMCT/                              racine du dépôt
├── README.md                           présentation, démarrage en 5 minutes
├── ARCHITECTURE.md                     ce fichier
├── AGENTS.md                           règles pour les agents IA (prime sur tout) ; CLAUDE.md, GEMINI.md, .github/ le citent
├── platformio.ini                      configuration PlatformIO : carte esp32dev, 9 600 bauds, upload_port COM4
├── src/main.cpp                        firmware ESP32 (1 082 lignes) : voir §7
├── include/  lib/  test/               dossiers PlatformIO standard (README seulement)
├── .github/copilot-instructions.md     renvoie vers AGENTS.md (aucun workflow CI)
├── .vscode/                            réglages, extensions et tâches VS Code partagés (tasks.json : Ctrl+Shift+B lance le serveur)
├── docs/                               TOUTE la documentation (voir docs/README.md)
│   ├── architecture/                   vue-ensemble.md, tarification-cie.md, decisions/ (0001 à 0004)
│   ├── developpement/                  conventions, ajouter…, tests, front-statique, gabarit-page-client-reference.html
│   ├── api/endpoints.md                les 90 routes /api/, générées depuis le routeur
│   ├── exploitation/                   déploiement, variables .env, dépannage
│   ├── firmware/                       firmware-esp32.md, guide-test-bout-en-bout.md, detection-onoff-zmct103c.md (historique)
│   ├── memoire/                        mémoire IIT (texte + images + versions et diagrammes)
│   ├── maquettes/                      maquettes HTML de design
│   └── refonte/                        historique de la refonte du dépôt + gardien/ (scripts de contrôle)
└── AOCEDA/                             SERVEUR DJANGO (nom figé : contrat de l'installateur et d'AGENTS.md)
    ├── manage.py  pytest.ini  Procfile  requirements.txt  .env.example
    ├── installer.py  installer.bat  lancer_aoceda.bat   parcours de tous les collaborateurs (figés)
    ├── lancer_ngrok.bat                tunnel public ngrok vers le port 8003
    ├── INSTALLATION.md  README.md      guide humain d'installation ; présentation du dossier
    ├── pyrefly.toml  pyrightconfig.json  réglages d'analyse de types de l'éditeur
    ├── aoceda/                         projet Django : settings, urls, asgi, wsgi, celery (voir §3)
    ├── apps/                           les 6 applications (voir §4 et §5)
    │   ├── accounts/  sensors/  analytics/  alerts/  dashboard/
    │   └── ai_assistant/               l'assistant IA (§5) : chatbot/ (moteur), rapports/, personnage/, tests_chatbot/
    ├── templates/                      11 gabarits de pages + partials/ + admin/ (§6)
    ├── static/                         js/ (15), css/ (19), img/, video/ (§6)
    ├── outils/                         scripts lancés à la main (§11)
    ├── deploiement/cerebrium_voix/     service de voix baoulé sur GPU (Cerebrium) : ne pas toucher
    ├── mobile_app/                     application Android Capacitor (§8)
    ├── db.sqlite3                      base locale, encore suivie par Git (ne jamais la committer)
    └── (locaux, non suivis : voir §12)  .env  .venv_local/  donnees_ia/  staticfiles/  media/
```

---

## 3. Le serveur Django

### 3.1 Le projet `AOCEDA/aoceda/`

| Fichier | Rôle |
|---|---|
| `settings.py` | tous les réglages ; lit `.env` (python-decouple) ; `AUTH_USER_MODEL = accounts.Utilisateur` |
| `urls.py` | routeur racine (tableau §3.2) |
| `asgi.py` | application ASGI : HTTP (Django) + WebSocket (Channels, routes de `apps/ai_assistant/routing.py`) |
| `wsgi.py` | entrée WSGI pour gunicorn (production, **sans** WebSocket) |
| `celery.py` | application Celery + planning `beat_schedule` (4 tâches) |
| `__init__.py` | charge Celery au démarrage si installé |

Points clés de `settings.py` :
- `INSTALLED_APPS` : `daphne` en **premier** (sinon `runserver` n'est pas ASGI), `jazzmin` avant `admin`, DRF, `simplejwt` +
  `token_blacklist`, `channels`, puis les 6 apps `apps.<nom>.apps.<Nom>Config`.
- Middleware Django standard (sécurité, sessions, CSRF, auth, messages, clickjacking). Pas de whitenoise branché (il est dans
  `requirements.txt` mais non utilisé).
- DRF : `IsAuthenticated` par défaut, authentification JWT. Pagination à `page_size` large (piège : les réponses de liste sont
  parfois `{results: [...]}`).
- Base : SQLite si `DB_ENGINE=sqlite3`, sinon PostgreSQL ; Celery via Redis (`CELERY_BROKER_URL`).
- Assistant : bloc de réglages `CHATBOT_*`, `DEEPSEEK_*`, `GEMINI_*`, `AI_DAILY_LIMIT`… et contrôle de `CHATBOT_DOSSIER_IA` (zone protégée).
- Bloc « Tests d'AOCEDA » : isole les tests dans un dossier temporaire (zone protégée).

### 3.2 Table des URL (préfixe → application)

| Préfixe | Application | Contenu |
|---|---|---|
| `/` , `/auth/`, `/dashboard/`, `/historique/`, `/alertes/`, `/interventions/`, `/ia/`, `/ia/assistant/`, `/previsions/`, `/parametres/`, `/technicien/` (+ variantes `aoceda-*.html`) | `dashboard` | pages HTML |
| `/admin/` | Django + Jazzmin | administration |
| `/api/auth/` | `accounts` (`urls.py`) | connexion JWT, 2FA, rafraîchissement, déconnexion, mot de passe oublié |
| `/api/users/` | `accounts` (`urls_users.py`) | profil, photo, mot de passe, 2FA, connexions, export, gestion des utilisateurs |
| `/api/sensors/` | `sensors` | réception ESP32 (`zmct/`), pont série, capteurs, dispositifs, interventions, flux temps réel (`stream/`) |
| `/api/mesures/`, `/api/mesures/serie/` | `sensors` (déclarées dans `aoceda/urls.py`) | mesures et séries pour les graphes |
| `/api/alertes/`, `/api/regles/` | `alerts` | alertes, compteur, règles de détection |
| `/api/analytics/`, `/api/previsions/` | `analytics` | résumé, facture, historique, répartition, heatmap, prévision, tarif, exports |
| `/api/assistant/` | `ai_assistant` | chat en flux, voix, historique, crédits, essais ; WebSocket `live` |

Liste complète avec méthodes et droits : [docs/api/endpoints.md](docs/api/endpoints.md).

### 3.3 Tâches planifiées (Celery beat)

| Tâche | Fréquence | Application |
|---|---|---|
| `apps.alerts.tasks.detecter_anomalies` | 5 min | applique les règles et crée des alertes |
| `apps.analytics.tasks.enregistrer_previsions` | 1 h | enregistre les prévisions |
| `apps.analytics.tasks.rafraichir_meteo` | 6 h | température du jour par ville (Open-Meteo) |
| `apps.alerts.tasks.purger_alertes_lues` | 24 h | nettoyage |

---

## 4. Les 6 applications

Structure type d'une app : `models.py`, `serializers.py`, `views.py`, `urls.py`, `admin.py`, `apps.py`, `migrations/`, `tests*.py`.
Le nom de l'app est son `app_label` (figé, [décision 0001](docs/architecture/decisions/0001-garder-les-noms-d-apps-django.md)).

### 4.1 `accounts` : identité et droits (≈ 3 700 lignes)
- **Modèles** : `Utilisateur` (`AbstractUser`, rôle) ; `Client`, `Technicien`, `Administrateur` (héritage multi-table de `Utilisateur` ;
  `Client` porte l'ampérage, le type de tarif et de compteur, le groupe de facturation, la ville, le seuil de crédit bas…) ;
  `AuditLog` (→ `Utilisateur`, → `Client`) ; `NoteClient` (→ `Client`, → `Technicien`).
- **Fichiers** : `views.py` (≈ 750 l. : connexion JWT, 2FA, profil, photo, mot de passe, export JSON, gestion des utilisateurs),
  `serializers.py`, `authentication.py` (jeton avec révocation), `permissions.py` (rôles), `audit.py` + `signals.py` (journal de
  connexions), `utils.py` (e-mail asynchrone), `villes.py` (villes de Côte d'Ivoire et coordonnées).
- **Commandes** : `creer_client_anzouango`, `test_email` (diagnostic SMTP).
- **URL** : `/api/auth/*` (`urls.py`), `/api/users/*` (`urls_users.py`).

### 4.2 `sensors` : appareils, mesures, interventions (4 841 lignes)
- **Modèles** : `Dispositif` (→ `Client`, porte la clé `Device`) ; `Capteur` (→ `Client`, → `Dispositif`, `coupureDemandee`, calibration) ;
  `PresenceCapteur` (→ `Capteur`) ; `MesureEnergie` (→ `Capteur`) ; `Intervention` (→ `Technicien`, `Client`, `Dispositif`, `Capteur`,
  et → elle-même pour le suivi) ; `RapportIntervention` (→ `Intervention`, texte riche `ckeditor`).
- **Fichiers** : `views.py` (1 430 l. : **réception des mesures de l'ESP32**, réponse avec les ordres `coupe_N`, pont série, flux SSE temps
  réel, capteurs, dispositifs et QR de configuration, interventions, espace technicien), `authentication.py` (en-tête
  `Authorization: Device <clé>` et `X-Bridge-Token`), `serializers.py`.
- **Commandes** : `seed_demo`, `seed_kpi3`, `setup_nguessan`.
- **URL** : `/api/sensors/*`, `/api/mesures/*`.

### 4.3 `analytics` : tarifs, historique, prévisions (≈ 4 900 lignes)
- **Modèles** : `Prevision` (→ `Client`), `RechargeCredit` (→ `Client`, prépayé), `MeteoJour`.
- **Fichiers** : `tarifs_cie.py` (**moteur tarifaire** de l'arrêté 1355, voir [tarification](docs/architecture/tarification-cie.md)),
  `views.py` (1 612 l. : résumé, facture à ce jour, historique, répartition, heatmap, exports CSV/PDF, prévision),
  `prevision_ia.py` (habitudes + température), `meteo.py`, `jours_feries.py`, `conseils.py` (conseils du tableau de bord),
  `pdf.py` (socle PDF des exports), `tasks.py` (Celery).
- **URL** : `/api/analytics/*`, `/api/previsions/`.

### 4.4 `alerts` : détection et notifications (≈ 2 000 lignes)
- **Modèles** : `RegleDetection` (→ `Client`, → `Capteur`), `Alerte` (→ `Client`, `MesureEnergie`, `RegleDetection`, `Intervention`).
- **Fichiers** : `utils.py` (≈ 510 l. : **moteur d'alertes** : règles, crédit bas prépayé, seuil de tranche postpayé, e-mails),
  `tasks.py` (Celery), `signals.py` (suivi d'une demande d'intervention), `views.py`, `serializers.py`.
- **URL** : `/api/alertes/*`, `/api/regles/*`.

### 4.5 `dashboard` : les pages HTML (1 115 lignes)
- **Aucun modèle.** `views.py` associe chaque URL à un gabarit (voir §6) et sert le film de la vitrine (`site_video`, Range 206),
  les données du tableau de bord de l'administration (`admin_stats_data`) et la page de l'assistant avec ses empreintes `?v=`
  (`assistant_view`). `management/commands/setup_demo.py` crée des comptes et des mesures de démonstration.

### 4.6 `ai_assistant` : l'assistant IA → voir [§5](#5-lassistant-ia).

---

## 5. L'assistant IA (`AOCEDA/apps/ai_assistant/`)

### 5.1 Couches

```
navigateur : templates/assistant.html + static/js/assistant.js + css/assistant.css + js/personnage.js (généré)
        │  /api/assistant/…                          WebSocket /api/assistant/live?token=<JWT>
        ▼                                                      ▼
views.py (message en flux SSE, voix, historique…)       live.py + routing.py (appel Live, Channels)
        │                                                      │
        ▼                                                      ▼
chatbot/service_chat.py  ──►  fournisseurs.py (DeepSeek en flux + appel des outils)      chatbot/live_agent.py (Gemini Live)
        │                             │
        ▼                             ▼
service_dioula.py / service_baoule.py (relais)       outils.py (10 outils : données du client connecté UNIQUEMENT)
```

### 5.2 Fichiers hors moteur

| Fichier | Rôle |
|---|---|
| `views.py` | API `/api/assistant/*` : `message` (SSE asynchrone), `transcrire`, `voix`, `config`, `nouvelle`, `conversations/`, `credits`, `tests`, `rapports/` ; JWT obligatoire (sauf fichiers de rapports) |
| `urls.py`, `routing.py` | routes HTTP et WebSocket |
| `live.py` | consommateur WebSocket de l'appel Live |
| `outils.py` | outils « function calling » : consommation, appareils, historique, heures de pointe, prévision, crédit, alertes, interventions, capteurs, `preparer_coupure` (ne coupe rien : carte Oui / Non) |
| `models.py` | `Conversation` (historique affiché, → `Client`), `QuotaIA` (quota du jour, → `Client`) |
| `serializers.py`, `admin.py`, `apps.py` | historique affiché ; admin ; préchargement des modèles au démarrage du serveur (Whisper, écoutes, voix) |
| `management/commands/installer_modeles_ia.py` | télécharge et vérifie les modèles (~2,1 Go ; `CATALOGUE` protégé) ; `test_deepseek.py` : essai réel de la clé |

### 5.3 Le moteur `chatbot/` (53 fichiers, **zone protégée**)

| Rôle | Modules |
|---|---|
| Réglages | `config.py` (lit `settings`) |
| Une question de bout en bout | `service_chat.py` (orchestrateur), `consignes.py` (consigne système), `fournisseurs.py` (cerveau DeepSeek), `conversation.py` (mémoire SQLite) |
| Données du client | `donnees_client.py` (+ `apps/ai_assistant/outils.py`) |
| Langues | `langues.py`, `detection.py`, `garde_langue.py`, `salutations.py`, `nombres_fr.py` |
| Facture jointe | `facture.py` (PDF ou photo → Gemini → comparé à la consommation mesurée) |
| Dioula | `service_dioula.py`, `dioula_ecoute.py`, `dioula_routage.py`, `dioula_texte.py`, `dioula_relais.py` |
| Baoulé | `service_baoule.py`, `baoule_chaine.py`, `baoule_comprendre/decider/demandes/repondre/reparation/memoire/lexique/texte/ecoute/relais.py`, `baoule_direct.py` (question en français, réponse en baoulé) |
| Voix | `voix.py` (Whisper, voix Microsoft, Kokoro), `voix_baoule.py`, `voix_gpu.py` (Cerebrium), `omnivoice_atelier.py` |
| Appel Live | `live_agent.py` (outils de la page, dont `commande_appel` : l'agent appuie sur Micro, Caméra, Écran, Écrire à la demande ; Raccrocher = `terminer_appel` ; le partage d'écran exige un vrai appui de la personne, le navigateur l'impose), `cles_gemini.py` (réserves de clés), `agent_actions.py` |
| Fonctionnement | `demarrage.py`, `securite.py`, `credits.py`, `journal.py`, `erreurs.py` |
| Données fixes | `donnees/*.json` (lexiques et exemples baoulé/dioula), `donnees/voix_baoule/` (voix de référence) |

### 5.4 Autres dossiers de l'assistant

| Dossier | Contenu |
|---|---|
| `tests_chatbot/` | 13 fichiers `test_*.py` + `conftest.py` : **692 tests** pytest (zone protégée) ; `client_test.py` et `serveur_labo.py` sont des outils de laboratoire |
| `rapports/` | résultats historiques des essais (audios, documentation, captures) : **lecture seule**, menu « Tests et rapports » de la page |
| `personnage/` | sources du lapin animé (`moteur/`, `scene_personnage.js`, `personnage_aoceda.js`) ; `construire_personnage.js` génère `static/js/personnage.js` |
| `migrations/` | migrations de `Conversation` et `QuotaIA` (ne jamais modifier) |

### 5.5 Données locales et modèles (hors Git)
`AOCEDA/donnees_ia/` (ou `CHATBOT_DOSSIER_IA`) : `modeles/` (Whisper, Omnilingual dioula, omniASR baoulé, Kokoro), `cache/`
(conversations, voix déjà faites, réserves Live), `journaux/`. Services extérieurs : DeepSeek, Gemini Live, OpenRouter, Cerebrium,
Djelia / Google Traduction, NiuTrans, Microsoft `edge-tts` (tableau complet : [AGENTS.md](AGENTS.md) §5).

---

## 6. Le front : pages, JS, CSS

Les gabarits sont à plat dans `AOCEDA/templates/`, appelés par nom depuis `apps/dashboard/views.py`.

| URL | Vue | Gabarit | JS de la page | CSS de la page | API principales appelées |
|---|---|---|---|---|---|
| `/` | `index` | `index.html` | `index.js` | `index.css` | (vitrine, film scrubbé) |
| `/auth/` | `auth_view` | `aoceda-auth.html` | `auth.js` | `auth.css` | `/api/auth/login/`, `login/2fa/`, `password/reset/` |
| `/dashboard/` | `dashboard_view` | `aoceda-dashboard.html` | `dashboard.js` | `dashboard.css` + `refonte-dashboard.css` | `analytics/summary`, `facture`, `repartition`, `conseils`, `mesures/serie`, `sensors/stream` |
| `/historique/` | `historique_view` | `aoceda-historique.html` | `historique.js` | `historique.css` + `refonte-historique.css` | `analytics/historique`, `heatmap`, `export*`, `mesures/serie` |
| `/alertes/` | `alertes_view` | `aoceda-alertes.html` | `alertes.js` | `alertes.css` + `refonte-alertes.css` | `alertes/*`, `regles/*`, `analytics/summary` |
| `/interventions/` | `interventions_view` | `aoceda-interventions.html` | `interventions.js` | `historique.css` + `refonte-interventions.css` | `sensors/interventions/*` |
| `/previsions/` (page **Facturation**) | `previsions_view` | `aoceda-previsions.html` | `previsions.js` | `previsions.css`, `facturation.css`, `refonte-previsions.css` | `analytics/prevision`, `facture`, `historique-mensuel`, `credit/releve`, `tarif`, `alertes/tranche` |
| `/parametres/` | `parametres_view` | `aoceda-parametres.html` | `parametres.js` | `parametres.css` + `refonte-parametres.css` | `users/me/*`, `regles`, `analytics/tarif`, `sensors/mes-capteurs` |
| `/ia/` | `ia_view` | `aoceda-ia.html` (cadre) | `assistant-page.js` | (socle) | boutons qui pilotent le cadre |
| `/ia/assistant/` | `assistant_view` | `assistant.html` | `assistant.js`, `personnage.js` | `assistant.css` | `/api/assistant/*`, WebSocket Live |
| `/technicien/` | `technicien_view` | `aoceda-technicien.html` | `technicien.js` | `technicien.css`, `parametres.css` | `sensors/capteurs`, `dispositifs`, `interventions` |

- **Socle commun des pages client** : `js/client-shell.js` (session, jeton, thème, compteur d'alertes, déconnexion), `js/refonte-shell.js`,
  `js/i18n.js` ; `css/client-shell.css`, `refonte-shell.css`, `refonte-theme.css` ; gabarits partagés `partials/_sidebar_client.html` et
  `partials/_bottom_nav_client.html`. Modèle à recopier pour une nouvelle page : [docs/developpement/gabarit-page-client-reference.html](docs/developpement/gabarit-page-client-reference.html).
- **Les `refonte-*.css`** sont une surcouche posée sur les CSS de page : à ne pas supprimer sans vérifier la cascade.
- **Contrats** : clés `localStorage` (`aoceda_access_token`, `aoceda_refresh_token`, `aoceda_user_role`, `aoceda-theme-choice`),
  identifiants HTML lus par le JS, numéros `?v=` à augmenter à la main à chaque modification (sauf la page de l'assistant).
- **Autres** : `templates/admin/` (personnalisation Jazzmin), `static/img/` (logos, auth, assistant, `refonte/` pictogrammes),
  `static/video/` (films de la vitrine), `js/personnage.js` (**généré**).

---

## 7. Le firmware ESP32

`src/main.cpp` (1 082 lignes) : deux capteurs ZMCT103C (GPIO 34 et 35), deux relais (GPIO 26 et 27), Wi-Fi multi-réseaux, détection par
fréquences du secteur (50 Hz + harmoniques 150/250 Hz), bruit appris, tampon hors ligne (LittleFS + NVS), ordres de coupure lus dans la
réponse du serveur, journal UDP, mise à jour OTA. **Détail : [docs/firmware/firmware-esp32.md](docs/firmware/firmware-esp32.md).**
Contrat avec le serveur : `POST /api/sensors/zmct/`, en-tête `Authorization: Device <clé>`, corps `{capteur_index, etat, courant, puissance,
timestamp_unix, coupe}`, réponse `{created, coupe_1, coupe_2}`. ⚠️ Les numéros sont **inversés** par rapport aux noms locaux : `Capteur_1`
(GPIO 34, lampe) = capteur **2** côté serveur, `Capteur_2` (GPIO 35, prise) = capteur **1** ; ne jamais les changer. Un tampon hors ligne est
effacé au redémarrage de la carte. Ne pas modifier sans demande explicite.

---

## 8. L'application Android

`AOCEDA/mobile_app/` : projet Capacitor (`ci.aoceda.app`). `www/` ne contient qu'un petit lanceur (`index.html`, deux logos) ; l'application
affiche le **site distant** (`allowNavigation: ["*"]`, `cleartext: true`, agent `AOCEDA-NativeApp`). `android/app/` : projet Gradle
(`node_modules/` ignoré par Git). Les sessions et exports de l'APK dépendent des URL du serveur.

---

## 9. Flux de bout en bout

1. **Mesure** : l'ESP32 envoie une mesure (changement d'état ou toutes les secondes) → `sensors/views.py` crée une `MesureEnergie`
   rattachée au `Capteur` du `Dispositif` identifié par la clé (`capteur_index` côté serveur, inversé par rapport aux noms du firmware, voir §7)
   → la réponse porte `coupe_N` (ordre de coupure).
2. **Coupure à distance** : sur le site (ou par l'assistant : `preparer_coupure` → carte Oui / Non → le clic envoie l'ordre),
   `Capteur.coupureDemandee` passe à vrai ; au prochain envoi, l'ESP32 ouvre son relais et le mémorise.
3. **Affichage** : `dashboard.js` interroge l'API avec le jeton JWT ; `analytics` calcule facture à ce jour, prévision, historique avec
   `tarifs_cie.py` ; `sensors/stream/` pousse l'état en direct.
4. **Alertes** : Celery `detecter_anomalies` (5 min) applique les `RegleDetection` ; `alerts/utils.py` crée les `Alerte` et envoie les e-mails ;
   crédit bas (prépayé) et seuil de tranche (postpayé) sont des alertes de ce moteur.
5. **Assistant** : question → `views.py` → `service_chat.py` → DeepSeek avec les outils bornés au client connecté → réponse en flux ;
   langue dioula/baoulé via relais de traduction ; voix par Whisper, écoutes locales et synthèse ; appel en direct par WebSocket + Gemini Live.

---

## 10. Les tests

| Suite | Où | Commande (depuis `AOCEDA/`) | Tests |
|---|---|---|---|
| Moteur de l'assistant | `apps/ai_assistant/tests_chatbot/test_*.py` | `.venv_local\Scripts\python.exe -m pytest` | 692 (1 min 30 à 2 min 45) |
| Reste d'AOCEDA | `apps/<app>/tests.py` et `tests_<sujet>.py` | `.venv_local\Scripts\python.exe manage.py test` | 458 (21 à 23 min) |

Fichiers de la suite Django : `accounts` (`tests.py`, `tests_parametres.py`), `alerts` (`tests.py`, `tests_alertes_page.py`, `tests_alertes_simples.py`),
`analytics` (`tests.py`, `tests_conseils.py`, `tests_facturation.py`, `tests_historique.py`, `tests_prevision.py`, `tests_tableau_bord.py`),
`dashboard` (`tests.py`), `sensors` (`tests.py`, `tests_interventions_client.py`), `ai_assistant` (`tests.py`). Aucun test n'appelle Internet ni un
service payant. Ils patchent des chemins précis (`mock.patch('apps.alerts.utils…')`) : on ne déplace donc pas le code qu'ils visent
([décision 0003](docs/architecture/decisions/0003-refonte-sans-deplacer-le-code-python.md)). Le firmware n'a aucun test automatisé.
Contrôles de non-régression sans les suites : `docs/refonte/gardien/` (voir [docs/developpement/tests.md](docs/developpement/tests.md)).

---

## 11. Outillage, installation, lancement

| Élément | Rôle |
|---|---|
| `AOCEDA/installer.py` / `installer.bat` | installation en une commande : `.venv_local`, dépendances, `.env`, migrations, modèles de l'assistant (SHA-256 vérifiés), `--cles <fichier>` pour poser les clés d'API sans les afficher |
| `AOCEDA/lancer_aoceda.bat` | `manage.py runserver 0.0.0.0:8003` (Daphne) avec le Python du projet |
| `AOCEDA/lancer_ngrok.bat` | tunnel public ngrok vers le port 8003 |
| `AOCEDA/Procfile` | production : gunicorn (sans WebSocket), worker et beat Celery |
| `AOCEDA/outils/` | `serial_bridge.py` (pont série Arduino), `detect_dashes.py`, `seed_kpi3_ai_conversations.py`, `make_kpi3_pdf.py` ([README](AOCEDA/outils/README.md)) |
| `AOCEDA/deploiement/cerebrium_voix/` | service OmniVoice (voix baoulé) sur GPU : `main.py`, `cerebrium.toml`, `voix/` |
| `docs/refonte/gardien/` | `controle.py` (20 contrôles de non-régression), `smoke_pages.py` (Playwright), `verifier_liens.py` |

---

## 12. Ce qui n'est jamais dans Git

`AOCEDA/.env` (secrets), `AOCEDA/.venv_local/`, `AOCEDA/donnees_ia/` (modèles, conversations, journaux), `AOCEDA/staticfiles/`
(`collectstatic`), `AOCEDA/media/` (photos envoyées), `*.sauvegarde` (copies de la base), `.pio/`, `compile_commands.json`, `.claude/`,
`.playwright-mcp/`, `__pycache__/`. **`AOCEDA/db.sqlite3` est suivi** (base de départ fournie par le dépôt) : ses modifications locales sont
les données de la machine, ne jamais les committer.

---

## 13. Contrats figés et zones protégées

Ce qui ne doit pas changer sans décision explicite : URL publiques et format des réponses (ESP32, application Android, WebSocket, ngrok),
`app_label`, tables et migrations existantes, noms de tâches Celery, variables `.env`, clés `settings`, `installer.*`, `lancer_aoceda.bat`,
`CATALOGUE` des modèles (empreintes SHA-256), Release GitHub `modeles-ia-v1`, clés `localStorage`, Daphne/ASGI.
Zones protégées : `apps/ai_assistant/chatbot/` (+ `donnees/`), `rapports/`, `tests_chatbot/`, `apps/*/tests.py`, `static/js/personnage.js`
(généré), `deploiement/cerebrium_voix/`, parties de `settings.py`. Liste exacte et raisons : [AGENTS.md](AGENTS.md) §4 et
[décision 0002](docs/architecture/decisions/0002-contrats-figes-et-zones-protegees.md).

---

## 14. Dépendances entre applications et dette connue

Imports `apps.X` mesurés entre applications (hors migrations et tests) : `accounts → alerts, analytics, sensors` ; `sensors → accounts, alerts,
analytics` ; `alerts → accounts, analytics, sensors` ; `analytics → accounts, alerts, sensors` ; `dashboard → accounts, ai_assistant, alerts,
analytics, sensors` ; `ai_assistant → accounts, alerts, analytics, sensors`. Il existe des **cycles** (accounts ↔ sensors ↔ alerts ↔ analytics),
masqués par des imports faits à l'intérieur des fonctions.

Dette connue (non traitée, voir [décision 0003](docs/architecture/decisions/0003-refonte-sans-deplacer-le-code-python.md)) :
- vues de plus de 1 400 lignes (`analytics/views.py` 1 612, `sensors/views.py` 1 430) ; moteurs très gros : `live_agent.py` 1 268, `voix.py` 1 259 ;
- tarification répartie sur `analytics/tarifs_cie.py`, `analytics/views.py` et `alerts/utils.py` ;
- accès base dans quelques serializers ; deux fichiers d'URL dans `accounts` (`urls.py` et `urls_users.py`, contrat) ;
- `requirements.txt` : `reportlab`, `gunicorn`, `psycopg2-binary`, `celery`, `redis`, `whitenoise` non épinglés ; `whitenoise` non branché ;
  `uvicorn` et `pytest*` mêlés aux dépendances de production ;
- jeton du pont série codé en dur dans `AOCEDA/outils/serial_bridge.py` (à passer dans `.env`).

---

## 15. Où mettre quoi quand on ajoute quelque chose

| Je veux ajouter… | Je le mets… | Je n'oublie pas |
|---|---|---|
| une page client | gabarit `templates/aoceda-<page>.html`, `static/js/<page>.js`, `static/css/<page>.css`, vue + route dans `apps/dashboard/` | `?v=` ; test dans `apps/dashboard/tests.py` ; [modèle de gabarit](docs/developpement/gabarit-page-client-reference.html) |
| un endpoint | `views.py` + `urls.py` de l'app concernée | mettre à jour `docs/api/endpoints.md` ; test |
| un calcul de facture ou de tarif | `apps/analytics/tarifs_cie.py` (jamais dans une vue ni un gabarit) | tests de `analytics/tests.py` ; [tarification](docs/architecture/tarification-cie.md) |
| une règle d'alerte | `apps/alerts/utils.py` | `tests*.py` d'`alerts` |
| un outil pour l'assistant | `apps/ai_assistant/outils.py` (borné au client connecté) | tests ; zone `chatbot/` protégée |
| un réglage | `aoceda/settings.py` + `.env.example` (+ `chatbot/config.py`) | jamais de vraie clé dans `.env.example` |
| un champ ou un modèle | `models.py` + **nouvelle** migration | ne jamais modifier une migration existante |
| un script manuel | `AOCEDA/outils/` + ligne dans son README | pas de chemin absolu |
| de la documentation | `docs/<sujet>/` | lien depuis `docs/README.md` ; `python docs/refonte/gardien/verifier_liens.py` |
| un changement du firmware | `src/main.cpp` | respecter le contrat `POST /api/sensors/zmct/` ; ne jamais committer de mot de passe Wi-Fi |
