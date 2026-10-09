# Installer AOCEDA sur un PC (après un `git clone`)

Une seule commande installe tout : bibliothèques Python, réglages (`.env`), base de données et modèles de
l'assistant IA (~2,1 Go, téléchargés depuis leurs sources officielles puis vérifiés).

## 0. Récupérer le projet

- **Pas encore de copie :** `git clone -b feature/chatbot-ia-update https://github.com/silvercross2021-web/AOCEADA.git`
- **Une copie existe déjà, sur une autre branche :** sauvegardez d'abord votre base, puis changez de branche :

  ```bash
  cp AOCEDA/db.sqlite3 AOCEDA/db.sqlite3.sauvegarde
  git restore AOCEDA/db.sqlite3
  git fetch origin
  git switch feature/chatbot-ia-update
  ```

  Pour retrouver vos comptes et vos mesures ensuite : `cp AOCEDA/db.sqlite3.sauvegarde AOCEDA/db.sqlite3`. Votre
  `.env` est gardé (l'installateur y ajoute seulement les réglages qui lui manquent). Détails et cas particuliers :
  [AGENTS.md](../AGENTS.md), section 1.

Puis installez (étape 2), même si vous aviez déjà installé une ancienne version.

## 1. Prérequis

- **Python 3.12 ou 3.13** (pas 3.11 : Django 6 ne l'accepte pas) ([python.org](https://www.python.org/downloads/), cocher « Add Python to PATH »).
- **~4 Go libres** sur le disque du projet (bibliothèques ~1,5 Go + modèles ~2,1 Go).
  Si ce disque manque de place, les modèles peuvent aller sur un autre disque (voir l'étape 2).

## 2. Installer

Dans le dossier `AOCEDA` :

```bat
installer.bat
```

ou, sur n'importe quel système : `python installer.py` (Linux / Mac : `python3 installer.py`)

| Étape | Ce qui se passe |
|---|---|
| 1 | crée le Python du projet (`.venv_local`) |
| 2 | installe les bibliothèques (`requirements.txt`) |
| 3 | crée le `.env` depuis `.env.example` (clé secrète générée, base SQLite), ou complète celui qui existe déjà |
| 4 | prépare la base de données (migrations) |
| 5 | installe les modèles de l'assistant et vérifie leurs empreintes |
| 6 | affiche les clés d'API qui restent à mettre dans `.env` |

On peut relancer sans risque : ce qui est déjà fait est sauté.

L'**écoute du baoulé** (327 Mo) n'a plus de source officielle : son auteur (Tree-AI) l'a retirée de Hugging Face.
La version compressée au laboratoire est publiée dans la Release
[modeles-ia-v1](https://github.com/silvercross2021-web/AOCEADA/releases/tag/modeles-ia-v1) du dépôt, avec sa
licence (Apache 2.0) et l'origine du modèle : l'installation la télécharge toute seule, comme les autres.

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
| `OPENROUTER_MANAGEMENT_KEY` | lire le crédit OpenRouter (Options > Crédits des services) | facultative |
| `CEREBRIUM_SERVICE_ACCOUNT_TOKEN` | lire le crédit Cerebrium (sinon : `cerebrium login` sur ce PC) | facultative |
| `GEMINI_MODEL`, `OPENROUTER_API_KEY`, `_2`, `OPENROUTER_KEY_GEMINI` / `_CLAUDE` / `_DEEPSEEK` | essais et comparatifs du laboratoire | facultatives |

Le solde DeepSeek, le crédit OpenRouter et le crédit Cerebrium s'affichent dans l'assistant :
**Options > Crédits des services** (lus par le serveur, aucune clé n'est envoyée à la page).

Sans clé, l'assistant le dit honnêtement ; le reste d'AOCEDA (tableau de bord, historique, alertes…) marche.
Le `.env` contient des secrets : il n'est **jamais** envoyé sur GitHub (`.gitignore`).

**Recevoir les clés d'un membre de l'équipe.** Il les envoie en privé, jamais sur GitHub ni dans un groupe. Le plus
propre : recopier seulement les lignes des clés d'API dans **votre** `.env` (celui créé par l'installateur, qui a
sa propre clé secrète Django). Si vous remplacez tout le fichier par le sien, relancez `installer.py` : il remet par
défaut `CHATBOT_DOSSIER_IA` si ce réglage vise un disque absent de votre PC (par exemple `D:\…`). Les clés
partagées consomment les crédits de leur propriétaire (Options > Crédits des services).

## 4. Lancer

```bat
lancer_aoceda.bat
```

(Linux / Mac : `.venv_local/bin/python manage.py runserver 0.0.0.0:8003`), puis http://127.0.0.1:8003.
Le lanceur affiche aussi l'adresse à utiliser depuis un téléphone ou l'ESP32 branchés sur le même Wi-Fi.

### Comptes

Il n'y a pas d'inscription publique : les comptes sont créés par l'administrateur.

- Premier compte administrateur : `.venv_local\Scripts\python.exe manage.py createsuperuser`, puis
  http://127.0.0.1:8003/admin/ pour créer les clients, leurs compteurs et leurs capteurs.
- Pour essayer tout de suite : `.venv_local\Scripts\python.exe manage.py setup_demo` crée des comptes de
  démonstration (3 clients, 1 technicien, 1 administrateur ; mot de passe `Password123!`, liste affichée à la fin)
  avec des mesures simulées. Ce sont des données d'essai : jamais sur un vrai serveur.

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
