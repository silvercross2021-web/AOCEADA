# Consignes pour GitHub Copilot

Toutes les consignes de ce dépôt sont dans [AGENTS.md](../AGENTS.md), à la racine : lis-le en entier avant toute
action (branche `feature/chatbot-ia-update`, arrivée sur la branche depuis une autre copie, installation, zones
protégées, interdits, tests).

L'essentiel :

- Python du projet : `AOCEDA/.venv_local` (créé par `AOCEDA/installer.bat` ou `python3 AOCEDA/installer.py`).
- Ne jamais committer `.env`, `AOCEDA/db.sqlite3`, `donnees_ia/` ni un modèle ; ajouter les fichiers un par un.
- Aucune commande Git destructrice (`-f`, `reset --hard`, `clean`, `push --force`).
- Ne pas modifier les zones protégées d'AGENTS.md (moteur de l'assistant, données, migrations existantes, tests,
  empreintes des modèles) sans demande explicite.
- Projet en français : commentaires, textes affichés, commits.
