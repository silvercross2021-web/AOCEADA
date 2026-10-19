# AOCEDA/ : le serveur Django

Serveur Django 6 (Daphne) : espace client, espace technicien, administration, API et assistant IA. Installation et
lancement : [INSTALLATION.md](INSTALLATION.md) (`installer.bat`, `lancer_aoceda.bat`).

| Élément | Rôle |
|---|---|
| `manage.py`, `pytest.ini`, `requirements.txt`, `Procfile`, `.env.example` | point d'entrée et configuration de base |
| `lancer_ngrok.bat` | tunnel public ngrok vers le serveur local (port 8003) |
| `installer.py`, `installer.bat`, `lancer_aoceda.bat` | parcours de tous les collaborateurs (**ne pas modifier sans refaire une installation complète**) |
| `aoceda/` | projet Django : `settings.py`, `urls.py`, `asgi.py`, `wsgi.py`, `celery.py` |
| [`apps/`](apps/README.md) | les 6 applications |
| `static/`, `templates/` | front : un JS, un CSS et un gabarit par page ([static](../docs/developpement/front-statique.md), [templates](templates/README.md)) |
| [`outils/`](outils/README.md) | scripts lancés à la main |
| `deploiement/` | service de voix sur GPU (Cerebrium) : **ne pas toucher** |
| `mobile_app/` | application Android (Capacitor) |
| `db.sqlite3` | base locale, encore suivie par Git : ne jamais la committer |
| `donnees_ia/`, `staticfiles/`, `.venv_local/`, `.env` | locaux, jamais dans Git |

Documentation générale : [../docs/](../docs/README.md). Règles pour les agents IA : [../AGENTS.md](../AGENTS.md).
