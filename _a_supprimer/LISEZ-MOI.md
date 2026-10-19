# _a_supprimer/ : quarantaine de la refonte (2026-10-19)

Ces éléments ont été sortis de l'arborescence de travail parce que **rien ne les référence**. Ils sont gardés ici,
dans l'historique Git, le temps de la validation ; rien n'est supprimé définitivement. Dossier hors du chemin
d'import Python (ni `AOCEDA/apps`, ni `PYTHONPATH`, ni `pytest.ini`). Pour restaurer : `git mv` vers l'ancien chemin.

| Élément | Ancien chemin | Preuve d'inutilité |
|---|---|---|
| `_backup_presync/` (5 copies d'anciens fichiers de 2026-07) | `AOCEDA/_backup_presync/` | `git grep -F _backup_presync` : seule occurrence dans `detect_dashes.py` (liste d'exclusion de scan) |
| `brain/…/scratch/` (`patch_templates.py`, `wrap_verbatim.py`) | `AOCEDA/brain/` | `git grep patch_templates` et `wrap_verbatim` : 0 résultat ; scripts jetables d'une session d'agent |
| `scripts_essais_dioula/` (LAMIA, Colab, WAV, JSON de questions) | `AOCEDA/scripts/` | seule référence : le mode d'emploi du script `lamia_dioula_test.py` à lui-même ; l'écoute dioula utilise désormais Omnilingual (AGENTS.md §5) |
| `maquettes_doublons/` (`aoceda-auth (1).html`, `aoceda-previsions (1).html`) | `docs/maquettes/` | octet pour octet identiques à `aoceda-auth.html` et `aoceda-previsions.html` (`diff -q`) |
| `image-pour-coxio.png` | `AOCEDA/image pour coxio.png` | `git grep -F 'image pour coxio'` : 0 résultat ; nom avec espaces |

Remarque : `docs/maquettes/index (1).html` a été **renommé** `index.html` (et non mis en quarantaine) car les maquettes
le citent sous ce nom (deux liens étaient cassés).

À la validation de l'humain : supprimer le dossier entier dans un commit séparé (`git rm -r _a_supprimer`).
