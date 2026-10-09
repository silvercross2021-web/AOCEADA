# Installer AOCEDA sur un PC (après un `git clone`)

Une seule commande installe tout : bibliothèques Python, réglages (`.env`), base de données et modèles de
l'assistant IA (~2,1 Go, téléchargés depuis leurs sources officielles puis vérifiés).

## 1. Prérequis

- **Python 3.11, 3.12 ou 3.13** ([python.org](https://www.python.org/downloads/), cocher « Add Python to PATH »).
- **~4 Go libres** sur le disque du projet (bibliothèques ~1,5 Go + modèles ~2,1 Go).
  Si ce disque manque de place, les modèles peuvent aller sur un autre disque (voir l'étape 2).

## 2. Installer

Dans le dossier `AOCEDA` :

```bat
installer.bat
```

ou, sur n'importe quel système : `python installer.py`

| Étape | Ce qui se passe |
|---|---|
| 1 | crée le Python du projet (`.venv_local`) |
| 2 | installe les bibliothèques (`requirements.txt`) |
| 3 | crée le `.env` depuis `.env.example` (clé secrète générée, base SQLite) |
| 4 | prépare la base de données (migrations) |
| 5 | installe les modèles de l'assistant et vérifie leurs empreintes |
| 6 | affiche les clés d'API qui restent à mettre dans `.env` |

On peut relancer sans risque : ce qui est déjà fait est sauté.

Options :

- `python installer.py --sans-modeles` : sauter les modèles (connexion lente) ; plus tard :
  `.venv_local\Scripts\python.exe manage.py installer_modeles_ia`
- `python installer.py --dossier-ia <dossier>` : modèles et données de l'assistant dans un autre dossier
  (autre disque). Ce chemin est écrit dans **votre** `.env`, jamais envoyé sur GitHub.

## 3. Les clés d'API (fichier `.env`)

Le lien pour obtenir chaque clé est écrit au-dessus d'elle dans `.env`.

| Clé | Sert à | |
|---|---|---|
| `DEEPSEEK_API_KEY` | chat écrit et vocal de l'assistant | indispensable pour l'assistant |
| `GEMINI_API_KEY` (+ `_2`, `_3`…) | appel Live (voix en direct) | conseillée |
| `CEREBRIUM_API_KEY`, `CEREBRIUM_PROJECT` | voix baoulé sur carte graphique | facultative |
| `OPENROUTER_KEY_AGENT` | secours de l'agent Live | facultative |

Sans clé, l'assistant le dit honnêtement ; le reste d'AOCEDA (tableau de bord, historique, alertes…) marche.
Le `.env` contient des secrets : il n'est **jamais** envoyé sur GitHub (`.gitignore`).

## 4. Lancer

```bat
lancer_aoceda.bat
```

puis http://127.0.0.1:8003. Premier compte administrateur :
`.venv_local\Scripts\python.exe manage.py createsuperuser`

## 5. Vérifier

```bat
.venv_local\Scripts\python.exe manage.py installer_modeles_ia --verifier   :: modèles présents et intacts
.venv_local\Scripts\python.exe -m pytest                                  :: tests de l'assistant (sans Internet)
.venv_local\Scripts\python.exe manage.py test                             :: tests du reste d'AOCEDA
```

## Où est quoi (assistant IA)

| Dossier | Contenu |
|---|---|
| `apps/ai_assistant/chatbot/` | le moteur de l'assistant (langues, dioula, baoulé, voix, appel Live…) |
| `apps/ai_assistant/views.py`, `live.py` | l'API `/api/assistant/…` et l'appel Live (WebSocket) |
| `templates/assistant.html`, `static/js/assistant.js`, `static/css/assistant.css` | la page de l'assistant |
| `apps/ai_assistant/personnage/` | sources du personnage animé (`node construire_personnage.js`) |
| `apps/ai_assistant/rapports/` | résultats des essais (menu « Tests et rapports ») |
| `deploiement/cerebrium_voix/` | service de la voix baoulé sur GPU (Cerebrium) |
| `donnees_ia/` | modèles, cache et journaux de l'assistant (créé par l'installation, jamais sur GitHub) |
