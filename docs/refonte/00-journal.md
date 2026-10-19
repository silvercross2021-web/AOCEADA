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

## Base visuelle (2026-10-19, avant le lot 1)

Smoke Playwright (`gardien/smoke_pages.py`) sur une **copie** de la base avec les comptes de démonstration, serveur isolé
sur le port 8011 : 22 mesures (8 pages client + technicien + vitrine + connexion, à 390 et 1280 px). Statut 200 partout,
**0 erreur console, 0 débordement horizontal**, titres présents. Captures dans le dossier temporaire de la session.

## Étapes

| Date | Lot | Commit | Verdict du Gardien |
|---|---|---|---|
| 2026-10-19 | 0-3 : inventaire, diagnostic, cible, base de référence | `dd1f268` | contrôles de référence : 20 contrôles, 0 échec |
| 2026-10-19 | 1 : hygiène Git | `2f1603a` | VALIDÉ (avis préalable go ; 1 remarque prise en compte : `compile_commands.json` suivi) |
| 2026-10-19 | 2 : documentation vers `docs/` | `3e27c45` | VALIDÉ (40 renommages R100, 4 commentaires modifiés) |
| 2026-10-19 | 3 : outillage vers `AOCEDA/outils/` | `18f047e` | VALIDÉ (`detect_dashes.py` : sortie identique, 288 fichiers) |
| 2026-10-19 | 5' : quarantaine `_a_supprimer/` | `b1cc433` | VALIDÉ (24 renommages R100, 0 référence) |
| 2026-10-19 | 6 : documentation complète | voir `git log` | voir ci-dessous |

## Décisions prises par l'architecte sur délégation de l'humain

- `src/main.cpp` (mots de passe Wi-Fi) et `db.sqlite3` : jamais commités, laissés tels quels.
- Pas de dossier `firmware/` : PlatformIO attend le code à la racine.
- Archivage plutôt que suppression ; `venv` (deuxième environnement Python) laissé sur le disque.
- **Lots 4, 5, 6 et 7 non faits** : des tests protégés patchent des chemins précis (`mock.patch('apps.alerts.utils…')`),
  voir [décision 0003](../architecture/decisions/0003-refonte-sans-deplacer-le-code-python.md).
- `AGENTS.md` était stocké avec un encodage corrompu (accents illisibles) : réparé sans changer son sens.

## À signaler à l'humain (hors périmètre de la refonte)

- `AOCEDA/outils/serial_bridge.py` contient un **jeton d'authentification codé en dur** (déjà présent dans l'historique Git).
  Si c'est celui de la production, il faut le changer dans `.env` (`ARDUINO_BRIDGE_TOKEN`) et faire lire le script depuis
  l'environnement. Ne pas réécrire l'historique.
- Les scripts `seed_kpi3_ai_conversations.py` et `make_kpi3_pdf.py` lancent `django.setup()` à l'import (ne jamais les importer).

## Recette finale (2026-10-19, commit `6d30800`)

Clone neuf de la branche, `installer.py --sans-modeles` (code 0, 1 min 55) :
- `manage.py check` : aucun problème ; `makemigrations --check --dry-run` : aucun changement.
- `pytest` : **685 passés, 3 mis de côté** (= 688 ; les 3 sont les tests « modèle absent », modèles non téléchargés), 2 min 44.
- `manage.py test` : **458 OK**, 21 min 30. Même nombre qu'avant la refonte.
- Smoke Playwright (22 mesures, 390 et 1280 px) : résultats **identiques** à la base de départ, 0 erreur console, 0 débordement.
- Gardien : `controle.py` 20 contrôles, 0 échec.

Non vérifié : firmware sur carte réelle, application Android sur téléphone, envoi d'e-mail réel, Daphne + WebSocket Live en
fonctionnement (route présente, non exercée), modèles de l'assistant (non téléchargés), page `/admin/`.
