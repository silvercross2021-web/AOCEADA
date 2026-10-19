# outils/ : scripts d'outillage maintenus

Ces scripts ne font pas partie du serveur. Ils se lancent à la main, **depuis le dossier `AOCEDA/`**, avec le Python du
projet (`.venv_local`).

| Script | Rôle | Exemple |
|---|---|---|
| `serial_bridge.py` | Pont série Arduino → API AOCEDA (mesures ZMCT103C en temps réel). Jeton `X-Bridge-Token` dans `.env` | `.venv_local\Scripts\python.exe outils\serial_bridge.py COM3 9600` |
| `detect_dashes.py` | Repère les tirets longs et signes typographiques « de style IA » dans tout le projet | `.venv_local\Scripts\python.exe outils\detect_dashes.py --prose` |
| `seed_kpi3_ai_conversations.py` | Crée des conversations de l'assistant pour l'évaluation KPI3 du mémoire (écrit dans la base) | idem, à lancer sur une base de démonstration |
| `make_kpi3_pdf.py` | Produit le PDF d'évaluation KPI3 (écrit dans `Memoire_IIT_BROU_KABLAN/`, dossier personnel non suivi) | idem |

Règles : un script ici doit être documenté dans ce tableau et ne contient aucun chemin absolu. Les scripts qui
écrivent en base ou dans un dossier perso (`seed_kpi3_ai_conversations.py`, `make_kpi3_pdf.py`) lancent `django.setup()`
dès leur chargement : ne les importez jamais, exécutez-les seulement. Les essais jetables ne se committent pas.
