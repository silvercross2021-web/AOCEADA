# AOCEDA : suivre et prévoir sa consommation électrique

AOCEDA est une plateforme qui mesure la consommation électrique d'un foyer, la montre au client (tableau de bord,
historique, facture estimée, alertes, prévisions) et la commente grâce à un assistant IA qui parle français, dioula et
baoulé. Projet IIT 2025-2026 (Côte d'Ivoire).

```
Capteurs ZMCT103C ──► ESP32 ──Wi-Fi──► Serveur Django ──► base de données ──► pages web / application Android
                                              │
                                              └──► assistant IA (écrit, voix, appel en direct)
```

## Démarrage en 5 minutes

Prérequis : Python 3.12 ou 3.13 (ni 3.11, ni 3.14) et environ 4 Go libres.

```bat
cd AOCEDA
installer.bat                :: Windows (Linux / Mac : python3 installer.py)
lancer_aoceda.bat            :: démarre le serveur sur http://127.0.0.1:8003
```

Pour essayer sans matériel : `.venv_local\Scripts\python.exe manage.py setup_demo` crée des comptes de démonstration
(mot de passe `Password123!`) et des mesures simulées. Le détail (clés d'API, modèles de l'assistant de 2,1 Go, dépannage)
est dans [AOCEDA/INSTALLATION.md](AOCEDA/INSTALLATION.md).

## Carte du dépôt

| Dossier | Contenu | Pour en savoir plus |
|---|---|---|
| [AOCEDA/](AOCEDA/) | serveur Django : espace client, technicien, administration, API, assistant IA | [AOCEDA/README.md](AOCEDA/README.md) |
| [AOCEDA/apps/](AOCEDA/apps/) | les 6 applications Django (comptes, capteurs, analyses, alertes, tableau de bord, assistant IA) | [AOCEDA/apps/README.md](AOCEDA/apps/README.md) |
| [AOCEDA/outils/](AOCEDA/outils/) | scripts d'outillage lancés à la main (pont série, détecteur de tirets…) | [AOCEDA/outils/README.md](AOCEDA/outils/README.md) |
| [AOCEDA/mobile_app/](AOCEDA/mobile_app/) | application Android (Capacitor) qui affiche le site | |
| [src/](src/), [include/](include/), [lib/](lib/), [test/](test/), [platformio.ini](platformio.ini) | micrologiciel de l'ESP32 (PlatformIO) | [docs/firmware/](docs/firmware/) |
| [docs/](docs/) | toute la documentation | [docs/README.md](docs/README.md) |
| [_a_supprimer/](_a_supprimer/) | quarantaine de la refonte : éléments sans usage, en attente de suppression | [LISEZ-MOI](_a_supprimer/LISEZ-MOI.md) |

Fichiers à la racine : [AGENTS.md](AGENTS.md) (règles pour les agents IA, **à lire avant de modifier le dépôt**),
`CLAUDE.md`, `GEMINI.md` et `.github/copilot-instructions.md` (renvoient vers AGENTS.md), `lancer_ngrok.bat` (tunnel public
vers le serveur local).

## Documentation

- [Vue d'ensemble de l'architecture](docs/architecture/vue-ensemble.md)
- [Développement : conventions, ajouter une page ou un test, lancer les tests](docs/developpement/)
- [API : liste des endpoints](docs/api/endpoints.md)
- [Exploitation : déploiement, variables `.env`, dépannage](docs/exploitation/)
- [Firmware : test complet de bout en bout](docs/firmware/guide-test-bout-en-bout.md)
- [Historique de la refonte du dépôt](docs/refonte/)
