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

## Correctifs de l'appel Live, suite à des retours (après la refonte)

1. **Boutons de l'appel commandés par la voix** : outil `commande_appel` (micro, caméra, écran, écrire). Voir le commit `4242a23`.
2. **Texte qui se superposait** (« AOCEDA vous répond » sur les sous-titres) : la zone centrale de l'appel débordait dès que la hauteur
   disponible tombait sous ~650 px (zoom du navigateur, petite fenêtre, téléphone). Correctif CSS : le personnage et la carte se règlent
   sur la hauteur disponible (`container-type: size`, unités `cqh`), la carte défile au lieu de déborder, et sous 560 px de haut les
   sous-titres sont plus courts. Mesuré dans Chromium (avec le champ « Écrire » ouvert) : avant, chevauchement à 650, 560 et 480 px de
   haut et sur téléphone 390 x 700 ; après, **aucun chevauchement** sur 12 combinaisons (390 à 1617 px de large, 450 à 777 px de haut, avec et sans carte).
3. **Carte de données qui ne revenait plus** après une interruption : la page la réaffiche bien (testé avec 4 délais), mais une carte
   n'arrive que lorsque l'agent appelle un outil de données ; après une interruption il disait « je vous affiche » sans rien appeler.
   Nouvel outil `remontrer_carte` (rejoue la dernière carte, sans recalcul ; la demande de coupure Oui / Non ne se rejoue jamais) et
   consigne : ne jamais dire « je vous l'affiche » sans appeler un outil.

Tests : 699 au total côté moteur (692 + 5 `test_remontrer_carte.py` + 2 `test_live_mise_en_page.py`), 698 verts. Le test
`test_baoule.py::test_baoule_du_menu_ecoute_par_l_oreille_baoule` a échoué avec `mkl_malloc: failed to allocate memory` : il ne restait que
2,3 Go de RAM libre sur 15,7 Go, car le serveur AOCEDA de l'utilisateur (port 8003, 1,9 Go) tournait pendant la suite. Sans lien avec ces
changements ; à relancer serveur arrêté. 73 tests Django (assistant + tableau de bord) verts.

## Correctifs de l'appel Live : carte de coupure absente, confirmation à la voix, bouton rouge

Signalés après un appel réel (« éteindre la prise »).

1. **« Appuyez sur Oui ou Non » sans aucune carte** : à « éteindre la prise », l'agent avait appelé `etat_capteurs` (journal : `outils: [etat_capteurs]`),
   jamais `preparer_coupure`, puis annoncé une carte qui n'existait pas. Correctifs : la consigne dit d'appeler `preparer_coupure` AVANT de parler
   et de ne jamais parler d'un bouton sans l'avoir appelé ; **filet serveur** : si l'agent invite à toucher Oui / Non alors qu'aucune carte n'est
   à l'écran, le son est coupé et il doit appeler l'outil (compteur `cartes_fantomes_bloquees` dans le journal).
2. **« Oui » / « non » dits à la voix** (demande du client) : le serveur décide d'après la voix transcrite, jamais l'agent ; seulement un
   oui ou non court et net, carte non expirée, une seule fois ; l'écho de la phrase de l'agent et les phrases ambiguës sont ignorés. La page
   exécute alors le même chemin que le clic (mêmes droits, carte « Envoi de l'ordre… »). Décision à connaître : AGENTS.md disait « seul le clic » ; cette règle
   est assouplie pour l'appel Live seulement, avec ces garde-fous.
3. **Bouton rouge pendant que l'agent parle** : la page laissait l'agent finir sa phrase (jusqu'à 8 s de voix déjà reçue) même quand c'était la personne
   qui raccrochait. Maintenant la voix s'arrête tout de suite et l'appel se ferme (6 ms mesurées) ; le « au revoir » de l'agent reste attendu jusqu'au bout.

Vérifié dans Chromium (oui, non, carte expirée, sans carte, raccrochage, au revoir de l'agent).

**Revue de sécurité par le Gardien (avant commit) : 2 failles hautes, 1 moyenne corrigées**, plus les points bas.
- F1 : « ok », « d'accord », « c'est bon », « merci », « allez » valaient « oui » (on les dit pour acquiescer ou clore). Retirés : il reste « oui », « ouais »,
  « je confirme », « confirme », « fais-le », « vas-y » ; « non », « annule », « laisse tomber »... pour refuser.
- F2 : le « oui » n'était pas lié à la question (un « oui » dit 100 s plus tard à une autre question aurait coupé). Maintenant : fenêtre vocale de 30 s, qui se ferme dès que la
  personne parle d'autre chose (plus de 2 mots) ; le clic sur la carte la ferme aussi.
- F3 : écho du haut-parleur : une réponse qui est la FIN de la dernière phrase de l'agent est ignorée ; l'agent ne dit jamais « oui » / « d'accord » seul pendant une carte.
  Risque restant : un bruit tiers (télévision, autre personne) qui dit « oui » nettement dans les 30 s ; la coupure d'une lampe ou d'une prise se rétablit d'un geste.
- F4 : raccrocher pendant le « au revoir » de l'agent laissait l'appel coincé (impossible d'en relancer un sans recharger) : corrigé, mesuré.
- F5 : seule la partie dite APRÈS la carte compte ; F6 : compteur renommé (`oui_non_entendus`), pas de carte redemandée juste après un oui entendu ;
  F7 : l'agent ne peut plus cliquer Oui / Non sur une carte de coupure du chat écrit (`AGENT.REFUS`).

48 tests dans `test_confirmation_vocale.py` ; 747 tests du moteur verts, 73 tests Django de l'assistant et du tableau de bord verts.

Deuxième relecture du Gardien : « acceptable pour commit », aucune faille ne permet plus de couper sans un « oui » net ; les défauts restants échouent du côté sûr (il faut alors cliquer).
Corrigé dans la foulée : la phrase de l'agent finit désormais par « je vous écoute » (sinon un vrai « non » ressemblait à l'écho de sa propre phrase « …oui ou non » et était refusé), et « oui merci » vaut de nouveau « oui ».
Résiduel connu : un bruit tiers (télévision, autre personne) qui dit « oui » nettement dans les 30 s suivant la carte ; une coupure de lampe ou de prise se rétablit d'un geste.
