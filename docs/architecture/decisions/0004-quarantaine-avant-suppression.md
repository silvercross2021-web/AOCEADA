# 0004 · Quarantaine avant suppression

**Contexte.** Un fichier « sans référence » peut être appelé par une chaîne, un script ou une personne qui l'utilise à la main.

**Choix.** Rien n'est supprimé directement. Les candidats vont dans `_a_supprimer/` (hors du chemin d'import), avec
`LISEZ-MOI.md` qui donne la preuve d'inutilité de chacun. La suppression définitive est un commit séparé, après validation de
l'humain, et reste récupérable dans l'historique Git.

**Application (2026-10-19).** La quarantaine a été supprimée sur instruction de l'humain, avec l'ancien rapport de tests de 2026-07, le mémoire V30 (remplacé par le V41) et `skills-lock.json`. La liste et les preuves restent lisibles dans l'historique : `git show b1cc433:_a_supprimer/LISEZ-MOI.md`.
