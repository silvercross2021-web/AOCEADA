# Check-list de non-regression du Gardien (refonte refactor/architecture-propre)

Base de comparaison : tag `avant-refonte` (références dans `docs/refonte/gardien/reference/`). Python : `AOCEDA/.venv_local/Scripts/python.exe`.

## A. Automatique (rapide, ~2 min sur PC charge, sans suite de tests ni serveur)

Depuis la racine du depot :

    AOCEDA/.venv_local/Scripts/python.exe docs/refonte/gardien/controle.py
    # autorisations explicites de zones protegees pour une etape :
    AOCEDA/.venv_local/Scripts/python.exe docs/refonte/gardien/controle.py --autoriser "AOCEDA/aoceda/settings.py"
    # un seul controle : --seulement urls,celery,tests    (liste : --liste)
    # re-enregistrer la reference (UNIQUEMENT apres validation d'un ecart voulu) : --enregistrer-reference

Code de sortie 0 = aucun ECHEC ; ATTENTION = a lire, non bloquant.

| Id | Controle | Regle |
|---|---|---|
| a `check` | `manage.py check` | code 0, aucun message nouveau |
| b `migrations_a_jour` | `makemigrations --check --dry-run` | "No changes detected" |
| c `showmigrations` | `showmigrations --list` (app.migration) | identique a la reference (83) |
| d `urls` | `get_resolver()` : motif + nom (244 routes) | identique ; vues cibles changees = ATTENTION |
| e `celery` | taches enregistrees + beat_schedule | identique, chaque tache du beat enregistree |
| f `gabarits` | `extends`/`include` (compilation), `{% static %}`, `{% url %}`, `<script src>`/`<link href>` locaux, `reverse()` et `.html` cites en Python, URL `/api/...` du JS/gabarits | aucun nouveau probleme |
| f2 `statiques` | inventaire `static/` | aucun fichier disparu |
| g `compilation` | `compile()` de chaque .py suivi (apps, aoceda) | 0 erreur de syntaxe |
| g2 `imports` | import reel de chaque module (hors tests, scripts) | aucun nouvel echec |
| g3 `imports_internes` | `from apps.x import y`, relatifs, chaines `'apps.x.y'` (settings, Celery, `mock.patch`), tests inclus, resolus statiquement | aucune nouvelle reference cassee |
| h `lint` | ruff/pyflakes/flake8 si installes | pas d'erreur F nouvelle (ATTENTION : outil absent) |
| i `chemins_absolus` | `C:\Users`, `D:\`, `/home/` dans le code suivi | aucun nouveau fichier fautif |
| j `zones_protegees` | `git diff --diff-filter=MD avant-refonte` sur AGENTS.md sect. 4 | vide, sauf `--autoriser` |
| k `fichiers_interdits` | index, diff, ajouts : .env, db.sqlite3*, *.sauvegarde, donnees_ia/, venv, staticfiles, modeles, cles d'API (sk-, AIza, ghp_...) | rien |
| l `tests` | `def test*` par nom (Classe.methode) | aucun test perdu (deplacement OK) |
| m `asgi` | `asgi.py`, `routing.py`, `application_mapping`, daphne en tete | route WS `api/assistant/live` presente |
| n `reglages` | noms de settings (sans perte) + valeurs structurantes | identiques |
| o `modeles_commandes` | modeles (champs) + commandes `manage.py` | identiques |
| p `references_externes` | chemins cites par Procfile, .bat, installer.py, pytest.ini | aucune nouvelle reference cassee |
| q `mobile` | config Capacitor + sources JS/HTML mobile | identiques |

## B. Manuel (a chaque etape qui touche code ou gabarits, et obligatoirement a la fin)

Depuis `AOCEDA/` (jamais en parallele d'autres suites ; ne pas interrompre, voir AGENTS.md sect. 7) :

1. pytest, meme nombre qu'avant (688 passes + 3 ecartes tolerés si modeles absents) :
   `.venv_local\Scripts\python.exe -m pytest`
2. Django, meme nombre (458) :
   `.venv_local\Scripts\python.exe manage.py test`
   Un echec de delai sous charge : relancer une fois avant de conclure.
3. Daphne demarre (HTTP + WebSocket) : `.venv_local\Scripts\python.exe manage.py runserver 127.0.0.1:8003 --noreload`
   puis `curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8003/` (200), `/ia/assistant/` (200 ou 302 login), `/api/assistant/config`
   (401 sans jeton = protection intacte), `/admin/login/` (200). Le journal de demarrage doit afficher "Daphne" et aucun traceback.
   Arret propre ensuite. (Apres un runserver --noreload : bumper les `?v=` des CSS/JS modifies.)
4. Smoke Playwright (Python ou MCP) a 390 px et 1280 px, theme clair puis sombre, console sans erreur JS ni 404 reseau :
   pages `/` (vitrine), `/login`-auth, tableau de bord, historique, alertes, interventions, facturation (previsions),
   parametres, technicien, `/ia/` (+ cadre `/ia/assistant/`), `/admin/`. Pour chaque page : titre/KPI non vides, barre du bas
   mobile presente a 390 px, aucune requete `static` en 404 (`browser_network_requests` filtre sur 404/500).
5. Appel Live : ouvrir la page IA, verifier que la connexion WebSocket `/api/assistant/live?token=...` s'etablit (101) ou ferme
   proprement sans cle (pas de 404).
6. Comptes de demonstration si base vide : `manage.py setup_demo` (sur une COPIE de la base, ne pas toucher `db.sqlite3` suivie).
7. Firmware : `pio run` (racine) si `src/`, `include/` ou `platformio.ini` sont touches ; sinon verifier `git diff avant-refonte -- src include platformio.ini` (`src/main.cpp` est deja modifie hors refonte).
8. Installateur : si `installer.py/.bat` ou `lancer_aoceda.bat` changent (zone protegee), refaire une installation complete dans un clone neuf (`--sans-modeles`).
9. Relecture finale : `git status` (aucun fichier interdit), `git diff --stat avant-refonte`, relancer A, puis comparer le nombre de tests de B1/B2.
