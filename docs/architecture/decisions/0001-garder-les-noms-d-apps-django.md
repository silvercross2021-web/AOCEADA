# 0001 · Garder les noms d'applications Django

**Contexte.** Les apps s'appellent `accounts`, `sensors`, `analytics`, `alerts`, `dashboard`, `ai_assistant` (mélange
d'anglais et de français dans le reste du code). Leur nom sert d'`app_label` : il figure dans les noms de tables, les
migrations, les permissions et les `ContentType` de la base `db.sqlite3` des collaborateurs.

**Choix.** On ne renomme aucune application et on ne déplace aucun dossier `apps/<app>/`.

**Alternatives écartées.** Renommer en français (`comptes`, `capteurs`…) : exigerait de réécrire des migrations déjà
appliquées sur des bases réelles et de migrer les `ContentType`. Le gain de lisibilité ne vaut pas le risque de base cassée.
