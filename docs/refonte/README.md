# refonte/ : historique de la refonte du dépôt (octobre 2026)

| Page | Contenu |
|---|---|
| [00-journal.md](00-journal.md) | journal des étapes : date, lot, commit, verdict du Gardien, chiffres de référence |
| [01-inventaire.md](01-inventaire.md) | inventaire du dépôt avant refonte (photo à la date du 2026-10-19) |
| [02-diagnostic.md](02-diagnostic.md) | constats prouvés, classés par risque |
| [03-architecture-cible.md](03-architecture-cible.md) | architecture proposée, tableau « ancien → nouveau chemin », état d'avancement |
| [CHANGELOG.md](CHANGELOG.md) | ce qui a changé, lot par lot, avec l'ancien et le nouveau chemin |
| [gardien/](gardien/) | `controle.py` (20 contrôles de non-régression), `smoke_pages.py` (smoke visuel Playwright), `verifier_liens.py` (liens Markdown), `checklist.md` |

Les documents 01 à 03 décrivent l'état **avant** la refonte : leurs chemins sont ceux d'avant. Pour retrouver un fichier
déplacé, voir le [CHANGELOG](CHANGELOG.md).

Rejouer les contrôles (depuis la racine du dépôt) :

```bat
AOCEDA\.venv_local\Scripts\python.exe docs\refonte\gardien\controle.py --tag avant-refonte
python docs\refonte\gardien\verifier_liens.py
```
