# outils/ : scripts d'outillage maintenus

Ces scripts ne font pas partie du serveur. Ils se lancent à la main, **depuis le dossier `AOCEDA/`**, avec le Python du
projet (`.venv_local`).

| Script | Rôle | Exemple |
|---|---|---|
| `serial_bridge.py` | Pont série Arduino → API AOCEDA (mesures ZMCT103C en temps réel). Jeton `X-Bridge-Token` dans `.env` | `.venv_local\Scripts\python.exe outils\serial_bridge.py COM3 9600` |
| `pont_usb_esp32.py` | **Canal de secours du Wi-Fi** : quand l'ESP32 ne joint ni le Wi-Fi ni le serveur, il envoie ses mesures par le câble USB ; ce pont les transmet à Django et renvoie les ordres de coupure des relais. Détecte seul le port de l'ESP32, lit la clé du boîtier dans `include/secrets.h`. Envoie aussi l'heure du PC à la carte (`@HEURE`) : sans Wi-Fi, c'est ce qui permet de dater le relevé de température. Fermer le moniteur série de PlatformIO avant (un seul programme sur le port). Sans effet quand le Wi-Fi marche (pas de doublon) | **`lancer_tout.bat`** (Django + pont, un clic ; `etat`, `arreter`, `tout`, `navigateur`), `lancer_pont_usb.bat` (pont seul), ou `.venv_local\Scripts\python.exe outils\pont_usb_esp32.py` |
| `detect_dashes.py` | Repère les tirets longs et signes typographiques « de style IA » dans tout le projet | `.venv_local\Scripts\python.exe outils\detect_dashes.py --prose` |
| `seed_kpi3_ai_conversations.py` | Crée des conversations de l'assistant pour l'évaluation KPI3 du mémoire (écrit dans la base) | idem, à lancer sur une base de démonstration |
| `make_kpi3_pdf.py` | Produit le PDF d'évaluation KPI3 (écrit dans `Memoire_IIT_BROU_KABLAN/`, dossier personnel non suivi) | idem |
| `construire_rapport_voix_baoule.py` | Construit `rapports/resultats/voix_baoule.json` et les MP3 de l'essai de clonage de voix baoulé (page Tests et rapports) | `.venv_local\Scripts\python.exe outils\construire_rapport_voix_baoule.py <dossier ESSAI> --sens <sens_fr_auto.json>` |
| `construire_detecteur_langue.py` | Construit `apps/ai_assistant/chatbot/donnees/langue_ngrammes.json` (modèle de langue par suites de lettres : fr, en, dioula, baoulé, wolof, autre) à partir de corpus étiquetés ; affiche à la fin le résultat sur les messages jamais appris | `.venv_local\Scripts\python.exe outils\construire_detecteur_langue.py <corpus.json>` |
| `construire_catalogue_rapports.py` | Construit `rapports/resultats/catalogue.json` (sommaire par thème) et `rapports/README.md` ; vérifie que chaque fichier de `rapports/` est cité | `.venv_local\Scripts\python.exe outils\construire_catalogue_rapports.py` |

Règles : un script ici doit être documenté dans ce tableau et ne contient aucun chemin absolu. Les scripts qui
écrivent en base ou dans un dossier perso (`seed_kpi3_ai_conversations.py`, `make_kpi3_pdf.py`) lancent `django.setup()`
dès leur chargement : ne les importez jamais, exécutez-les seulement. Les essais jetables ne se committent pas.
