# Journal de la refonte

## Phase 0 : base de référence (2026-10-19)

- Branche `refactor/architecture-propre` (depuis `feature/chatbot-ia-update`), tag local `avant-refonte`.
- Base sauvegardée hors dépôt : `C:\Users\silve\Documents\AOCEDA_sauvegardes_refonte\db.sqlite3.2026-10-19`.
- Modifications locales laissées telles quelles, jamais commitées : `AOCEDA/db.sqlite3`, `src/main.cpp`
  (mots de passe Wi-Fi en clair), `ESSAI_VOIX_BAOULE/`, 13 captures Playwright à la racine.
- `manage.py check` : aucun problème. `makemigrations --check --dry-run` : aucun changement. 83 migrations.
- `pytest` : **688 passés**, 2 min 45. `manage.py test` : **458 passés**, 23 min 12 (serveur arrêté pendant les suites).
- Gardien : 20 contrôles automatiques (`docs/refonte/gardien/controle.py`), 0 échec, 1 attention (aucun linter installé).
  Références : 244 routes, 221 noms d'URL, 4 tâches Celery, 26 modèles, 42 commandes.
- Écarts déjà présents avant la refonte : `templates/_client_shell_reference.html` ne se compile pas (pas de
  `{% load static %}`, jamais rendu) ; `chatbot/omnivoice_atelier.py` exige `OMNIVOICE_HF_HOME` à l'import.
- **Pas encore fait** : capture visuelle Playwright (390/1280 px), à faire avant le lot 1.
