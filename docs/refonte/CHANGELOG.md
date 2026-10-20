# CHANGELOG de la refonte

Branche `refactor/architecture-propre` (tag `avant-refonte` = état de départ). Aucune modification de comportement : mêmes
URL, mêmes écrans, mêmes données, mêmes tests.

## Lot 1 · Hygiène Git (`2f1603a`)
- `compile_commands.json` : sorti du suivi (généré par PlatformIO, 102 chemins absolus), gardé sur disque.
- `AOCEDA/media/avatars/brou_photo.png` : sortie du suivi (donnée personnelle, `media/` était déjà ignoré), gardée sur disque.
- `.gitignore` : ajout de `ESSAI_VOIX_BAOULE/`, `compile_commands.json`, `Users*playwright*.png`.

## Lot 2 · Documentation regroupée dans `docs/` (`3e27c45`)
| Ancien | Nouveau |
|---|---|
| `README.md` (guide firmware) | `docs/firmware/guide-test-bout-en-bout.md` (nouveau `README.md` racine écrit au lot 6) |
| `methode_detection_onoff_zmct103c.md` | `docs/firmware/detection-onoff-zmct103c.md` |
| `AOCEDA/EXPLICATION_TARIFAIRE.md` | `docs/architecture/tarification-cie.md` (4 commentaires Python mis à jour) |
| `AOCEDA/Memoire_MD/` | `docs/memoire/` |
| `AOCEDA/diagrame+memoire/` | `docs/memoire/versions-et-diagrammes/` |
| `AOCEDA/maquette/` | `docs/maquettes/` (`index (1).html` renommé `index.html`) |
| `AOCEDA/rapport/` | `docs/archives/rapports-2026-07/` |

## Lot 3 · Outillage dans `AOCEDA/outils/` (`18f047e`)
| Ancien | Nouveau |
|---|---|
| `AOCEDA/serial_bridge.py` | `AOCEDA/outils/serial_bridge.py` (mode d'emploi : `python outils/serial_bridge.py COM3`) |
| `AOCEDA/detect_dashes.py` | `AOCEDA/outils/detect_dashes.py` (racine de scan inchangée : 288 fichiers, sortie identique) |
| `AOCEDA/scripts/make_kpi3_pdf.py`, `seed_kpi3_ai_conversations.py` | `AOCEDA/outils/` |

## Lot 5' · Quarantaine `_a_supprimer/` (`b1cc433`)
`AOCEDA/_backup_presync/`, `AOCEDA/brain/`, `AOCEDA/scripts/` (essais dioula), `AOCEDA/image pour coxio.png`, deux maquettes
en double : déplacés, rien supprimé. Preuves dans `_a_supprimer/LISEZ-MOI.md` (supprimé depuis, voir plus bas).

## Lot 6 · Documentation
README racine, `docs/` (architecture, développement, API, exploitation), README par dossier, décisions d'architecture,
mise à jour d'`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`.

## Nettoyage final (suivi par Git)
- `_a_supprimer/` supprimé (24 fichiers : copies `_backup_presync`, scripts jetables, essais dioula, maquettes en double, image
  sans usage). Récupérable : `git show b1cc433:_a_supprimer/LISEZ-MOI.md` donne la liste et les preuves.
- Supprimés car périmés ou interdits : `docs/archives/` (rapport de tests et audit de 2026-07), le mémoire V30 en Markdown (le
  V41 `.docx` reste), `AOCEDA/skills-lock.json` (verrou d'outil d'agent, interdit dans le dépôt par AGENTS.md).
- `lancer_ngrok.bat` : racine → `AOCEDA/lancer_ngrok.bat`, à côté de `lancer_aoceda.bat`.

## Non fait, volontairement
Rangement des tests, découpage des vues, réduction des cycles d'import, changements de `settings`/`urls`/Celery/ASGI :
voir la [décision 0003](../architecture/decisions/0003-refonte-sans-deplacer-le-code-python.md).

## Revue de tous les fichiers (relecture contre le code)
- Nouveau **`ARCHITECTURE.md`** à la racine : carte complète (arborescence, serveur, apps, assistant, front, firmware, flux, tests, contrats, où mettre quoi).
- Firmware : `docs/firmware/guide-test-bout-en-bout.md` **réécrit** (il décrivait un seul Wi-Fi ; le firmware gère plusieurs réseaux, des relais, l'OTA,
  une détection par fréquences) ; nouveau `docs/firmware/firmware-esp32.md` ; `detection-onoff-zmct103c.md` marqué « historique ».
- `AGENTS.md` : modules `facture.py`, `conversation.py`, `baoule_direct.py` ajoutés, chemin de `installer_modeles_ia.py` précisé. `INSTALLATION.md` : Python 3.14
  exclu, liens ajoutés. `tarification-cie.md` : exact (les 8 totaux d'exemple recalculés avec le moteur, identiques).
- Supprimés (sans aucune référence, vérifié) : 10 images de `static/` (`favicon.svg`, `logo-clair/sombre.png`, `auth-login-portrait.jpg`, `aoceda-full(-dark).png`,
  `logo_AOCEDA.png`, `stat-down/leaf/up.svg`) et le gabarit `templates/aoceda-composants.html` (non routé, copie dans `docs/maquettes/`).
- Déplacé : `templates/_client_shell_reference.html` (ne se compilait pas) → `docs/developpement/gabarit-page-client-reference.html`.
- Code : 6 imports inutilisés retirés (`analytics/views.py`, `accounts/urls.py`, `accounts/views.py`, `alerts/utils.py`, `ai_assistant/outils.py`), signalés par `ruff` ;
  `vulture` : aucune fonction réellement morte dans les apps Django (160 candidats, tous des hooks de framework).


## 20/10/2026 · Tests et rapports
- Ajout de l'essai de clonage de voix baoulé et d'un sommaire par thème dans la page (voir `00-journal.md`) ; 4 tests ajoutés.
