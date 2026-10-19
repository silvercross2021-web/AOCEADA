# Conventions

- **Langue** : le projet est en français (commentaires, textes affichés, messages d'erreur, commits, documentation). Pour les
  noms dans le code, suivre le fichier modifié (le moteur de l'assistant est entièrement en français ; Django garde ses
  noms anglais : `models`, `views`, `urls`).
- **Python du projet** : `AOCEDA/.venv_local`, jamais `venv`. Toutes les commandes se lancent depuis `AOCEDA/`.
- **Commits** : `type(portée): résumé` avec `feat`, `fix`, `chore`, `docs`, `test`, en français, avec le pourquoi dans le corps.
  Ajouter les fichiers **un par un** (`git add <fichier>`), relire `git status`, jamais `git add -A` ni `git add .`.
- **Jamais dans un commit** : `.env`, `AOCEDA/db.sqlite3`, `*.sauvegarde`, `donnees_ia/`, `.venv_local/`, `staticfiles/`,
  fichiers de modèles, clés d'API. `AOCEDA/db.sqlite3` est encore suivi par Git : ses modifications locales sont vos données.
- **Aucun chemin absolu** dans le code : passer par `settings.BASE_DIR` et `settings.CHATBOT_DOSSIER_IA`.
- **Jamais de fausses données** présentées comme réelles : état vide honnête (« aucune donnée »).
- **Fichiers statiques** : après modification d'un CSS ou JS (hors page de l'assistant, qui calcule ses `?v=` seule),
  augmenter à la main le `?v=` du gabarit qui le charge.
- **Zones protégées** : voir [AGENTS.md](../../AGENTS.md) §4 (moteur de l'assistant, migrations existantes, tests,
  `personnage.js` généré, installateur…).
- **Nommage des nouveaux dossiers et documents** : minuscules, sans accent, sans espace, nom qui dit le rôle. Éviter
  `utils`, `helpers`, `misc`, `new`, `old`, `v2`, `tmp`.
