# 02 · Diagnostic (lecture seule)

> **Document historique** : photo du dépôt au 2026-10-19, **avant** la refonte. Les chemins cités sont ceux d'avant ; pour les
> retrouver, voir le [CHANGELOG](CHANGELOG.md). La carte à jour du dépôt est [ARCHITECTURE.md](../../ARCHITECTURE.md).

Date : 2026-10-19. Chaque constat donne sa preuve. Légende : **G** gravité, **E** effort, **R** risque de régression
si on le traite, **Lot** = lot de la phase 4 (doc 03).

**Limite importante.** `ruff`, `vulture` et `coverage` ne sont pas installés dans `.venv_local` (vérifié :
`No module named …`). Aucun outil n'a donc servi d'indice ; seules les recherches de références (`git grep`) ont été
faites. Tout « code mort » ci-dessous est un **candidat**. Le code mort *dans* les fichiers Python (fonctions,
classes, routes, tâches, CSS/JS) n'est PAS encore analysé : il demande un outil et sera traité à la phase 5 avec
l'accord de l'humain d'abord sur l'installation de `vulture`/`coverage` dans un environnement jetable.

## A. Fichiers et dossiers égarés ou obsolètes

| # | Constat | Preuve | G | E | R | Lot |
|---|---|---|---|---|---|---|
| A1 | `AOCEDA/_backup_presync/` : 5 copies d'anciens fichiers (2026-07) | `git grep -F _backup_presync` ne trouve que `detect_dashes.py` | moyenne | 5 min | nul | 1 |
| A2 | `AOCEDA/brain/<uuid>/scratch/` : 2 scripts jetables d'une session d'agent | `patch_templates`, `wrap_verbatim` : 0 référence | basse | 5 min | nul | 1 |
| A3 | `AOCEDA/scripts/` : 15 fichiers d'essais (WAV, TXT, JSON, 5 scripts) | 0 référence hors `lamia_dioula_test.py` à lui-même | moyenne | 15 min | nul | 3 |
| A4 | `AOCEDA/detect_dashes.py` (outil ponctuel de nettoyage de typographie, 2026-07-05) | seule référence : lui-même ; mémoire `aoceda-em-dash-cleanup` | basse | 5 min | nul | 3 |
| A5 | `AOCEDA/maquette/` : 13 maquettes HTML dont 2 doublons `… (1).html` | cité seulement par le mémoire et un commentaire de gabarit | moyenne | 10 min | nul | 1 |
| A6 | `AOCEDA/rapport/` : 2 HTML de 2026-07 (rapport de tests, audit technicien) | dates du dernier commit anciennes ; contenu à confronter au code | basse | 5 min | nul | 2 |
| A7 | Deux versions du mémoire (`Memoire_MD/…md`, `diagrame+memoire/…V30FB.md` + `.docx`) | tailles 145 Ko / 128 Ko ; noms avec `+` et faute (« diagrame ») | moyenne | 15 min | nul | 2 |
| A8 | `AOCEDA/image pour coxio.png` (nom avec espaces), `skills-lock.json` (verrou d'outils d'agent), `pyrefly.toml`, `pyrightconfig.json` à la racine d'`AOCEDA` | `git grep -F 'image pour coxio'` et `skills-lock` : 0 référence ; `pyrefly` référencé seulement par des commentaires | basse | 10 min | faible | 1 |
| A9 | 13 captures `UserssilveDocuments…audit_dashboard…png` à la racine, non suivies | `git status` | basse | 1 min | nul | 1 (hors Git) |
| A10 | `ESSAI_VOIX_BAOULE/` (30 Mo, non suivi), `compile_commands.json`, `logs/` à la racine | `git status`, `du` | basse | décision humaine | nul | 1 |
| A11 | **Deux environnements Python** : `AOCEDA/venv` et `AOCEDA/.venv_local` | `ls AOCEDA` ; AGENTS.md : « jamais `venv` » | moyenne | décision humaine (suppression locale) | nul pour Git | 1 |
| A12 | `AOCEDA/db.sqlite3` suivi par Git alors que c'est la donnée de la machine | AGENTS.md §3 ; `git status` la montre modifiée | **haute** | mettre fin au suivi = changement de politique | moyen | **décision humaine** (voir doc 03 §7) |
| A13 | `AOCEDA/media/avatars/…` suivi alors que `media/` est dans `.gitignore` | `git ls-files` | basse | 1 min | nul | 1 |
| A14 | Trois sauvegardes `db.sqlite3*.sauvegarde` sur disque (ignorées) | `.gitignore` : `*.sauvegarde` | basse | humain | nul | — |
| A15 | `methode_detection_onoff_zmct103c.md` (28 Ko, firmware) à la racine | `ls` | basse | 5 min | nul | 2 |
| A16 | `static/css/refonte-*.css` (7 fichiers) : surcouche de « refonte » posée sur les CSS de page | noms ; `client-shell.css` aussi | moyenne | élevé | **élevé** (cascade) | 5 (prudence) |
| A17 | `templates/_client_shell_reference.html` : gabarit « de référence » | nom ; usage à prouver (`git grep`) | basse | à prouver | faible | 5 |

## B. Doublons et violations de couches

| # | Constat | Preuve | G | E | R | Lot |
|---|---|---|---|---|---|---|
| B1 | **Aucun ordre de dépendance entre apps** : cycles `accounts↔sensors↔alerts↔analytics` | doc 01 §3.3 (comptage des `import apps.X`) | haute | élevé | élevé | 6 |
| B2 | 91 imports **différés** (indentés) `from apps.… import` hors tests/migrations/moteur | `git grep -nE '^\s{4,}(from\|import) apps\.'` → 91 lignes | haute | élevé | moyen | 6 |
| B3 | Tarification répartie : `analytics/tarifs_cie.py` (calculs), `analytics/views.py` (`facture_mois_a_ce_jour`, `cout_entre`), `alerts/utils.py` (`cout_mois_courant_fcfa`, `etat_tranche`, `check_tranche_postpaye`) | `git grep -nE 'def .*(tarif\|tranche\|facture\|cout\|montant)'` | haute | moyen | **élevé** (argent) | 6 |
| B4 | Vues géantes : `analytics/views.py` 1 612 l., `sensors/views.py` 1 430 l. mêlent HTTP, calculs et accès base | `wc -l` | haute | élevé | élevé | 6 |
| B5 | Accès base (`objects.filter/get/create/aggregate`) **dans les serializers** de `accounts`, `alerts`, `sensors` | `git grep -lE 'objects\.(filter\|get\|create\|aggregate)' -- 'apps/*/serializers.py'` | moyenne | moyen | moyen | 6 |
| B6 | `alerts/utils.py` (508 l.) est en réalité le **moteur d'alertes** ; `accounts/utils.py` (77 l.) nom fourre-tout | `ls` / `wc -l` | moyenne | moyen | moyen | 6 |
| B7 | `dashboard/` ne contient pas de modèle mais `setup_demo.py` (575 l.) : commande de données de démo à côté de pages | `wc -l` | basse | moyen | faible | 6 |
| B8 | Commandes de seed (`seed_demo`, `seed_kpi3`, `setup_nguessan`, `setup_demo`, `creer_client_anzouango`) réparties dans 3 apps | `ls management/commands` | basse | moyen | moyen (documentées, `AGENTS.md` cite `setup_demo`) | 6 |
| B9 | `accounts/urls.py` et `urls_users.py` : deux fichiers d'URL dans une app | `ls` | basse | faible | élevé (URL figées) | **ne pas toucher** |

## C. Tests

| # | Constat | Preuve | G | E | R | Lot |
|---|---|---|---|---|---|---|
| C1 | `tests.py` et `tests_<sujet>.py` plats à côté du code ; pas de dossier `tests/` par app | doc 01 §3.4 | moyenne | moyen | faible si le découvreur de tests Django trouve toujours les mêmes tests | 4 |
| C2 | Gros fichiers mêlant des sujets : `sensors/tests.py` 74 tests, `ai_assistant/tests.py` 70, `accounts/tests.py` 49 | `grep -c 'def test_'` | basse | moyen | moyen | 4 |
| C3 | `client_test.py` et `serveur_labo.py` dans `tests_chatbot/` sont des **outils**, pas des tests ; `test_email.py`, `test_deepseek.py` sont des **commandes** nommées `test_*` | lecture des noms | basse | — | — | zone protégée / hors périmètre sans validation |
| C4 | Dossier de tests du moteur (`tests_chatbot/`) en zone protégée | AGENTS.md §4 | — | — | — | non touché |

## D. Dette technique visible

| # | Constat | Preuve | G |
|---|---|---|---|
| D1 | 0 `TODO`/`FIXME` dans le code (hors générés/rapports) | `git grep -nE 'TODO\|FIXME\|XXX'` → 0 | — (bon signe) |
| D2 | 1 `print(` hors tests/commandes | `git grep` → 1 | basse |
| D3 | 11 `except …: pass` | comptage `-A1` | moyenne : à qualifier un par un, certains sont légitimes |
| D4 | Aucun chemin absolu en dur dans le code exécuté ; seules mentions : commentaires/docstrings (`settings.py:255`, `voix_gpu.py:15`, `installer.py:80`) et un test qui simule une erreur | `git grep -nE '[A-Z]:\\\\\|C:/Users\|/home/'` | conforme |
| D5 | `requirements.txt` : `reportlab>=4.0`, `gunicorn>=22`, `psycopg2-binary>=2.9`, `celery>=5.4`, `redis>=5.0`, `whitenoise>=6.6` non épinglés ; `uvicorn`, `pytest*` mêlés aux dépendances de production | lecture du fichier | moyenne : exiger l'accord avant (contrat installateur) |
| D6 | **Secrets en clair dans le firmware local non commité** (`src/main.cpp` : mots de passe Wi-Fi) | `git diff src/main.cpp` | **haute si commité** : jamais ajouté ; voir doc 03 §7 |
| D7 | Aucun workflow CI (`.github/` ne contient que `copilot-instructions.md`) | `ls .github` | moyenne : la recette finale repose sur le Gardien manuel |
| D8 | Outils d'analyse statique absents de `requirements.txt` et de l'environnement (`ruff`, `vulture`, `coverage`) | `No module named …` | moyenne |

## E. Documentation

| # | Constat | Lot |
|---|---|---|
| E1 | Pas de dossier `docs/` ; docs dispersées (racine, `AOCEDA/`, `Memoire_MD/`, `diagrame+memoire/`) | 2, 6 |
| E2 | `README.md` racine et `INSTALLATION.md` à confronter à la réalité (phase 6) | 6 |
| E3 | Aucun README par dossier important | 6 |

## F. Ce qui n'est pas encore diagnostiqué (à faire avant d'exécuter)

- Code mort dans les fichiers Python et JS/CSS (outils absents, voir plus haut).
- Liste des gabarits ↔ vues ↔ `static` (le Gardien produit la résolution automatique).
- Références invisibles à `apps.<app>` dans `settings`, Celery (`celery.py`, `beat`), `routing.py`.
- Base visuelle Playwright (pages à 390 et 1280 px) : à capturer.
- Résultats chiffrés des deux suites de référence : en cours d'exécution (voir journal).
