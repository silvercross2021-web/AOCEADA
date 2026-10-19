# Comment ajouter…

## …une page web
1. Gabarit `AOCEDA/templates/aoceda-<page>.html` : partir de [gabarit-page-client-reference.html](gabarit-page-client-reference.html) (remplacer `PAGE`, ajouter `{% load static %}`) ou d'une page existante comme `aoceda-alertes.html`.
2. `AOCEDA/static/js/<page>.js` et `AOCEDA/static/css/<page>.css`, chargés avec un `?v=` à augmenter à chaque modification.
3. Une vue dans `AOCEDA/apps/dashboard/views.py` et une route dans `AOCEDA/apps/dashboard/urls.py` (voir `alertes_view`).
4. Les données viennent de l'API (`/api/...`) avec le jeton `aoceda_access_token` du `localStorage`.
5. Un test dans `apps/dashboard/tests.py`, puis les deux suites.

## …une application Django
Préférer **ne pas** en créer : 6 apps existent déjà ([vue d'ensemble](../architecture/vue-ensemble.md)).
Si c'est vraiment nécessaire : `manage.py startapp`, la déclarer dans `INSTALLED_APPS` (`aoceda/settings.py`), choisir un nom
durable (il devient l'`app_label`, voir [décision 0001](../architecture/decisions/0001-garder-les-noms-d-apps-django.md)).

## …un réglage
1. `aoceda/settings.py` : `NOM = config('NOM', default=...)`.
2. `AOCEDA/.env.example` : la ligne `NOM=` (vide si secret) avec un commentaire.
3. Pour l'assistant : le lire dans `chatbot/config.py` depuis `settings`, jamais directement dans le `.env`.

## …un test
- Reste d'AOCEDA : dans `apps/<app>/tests.py` ou un fichier `tests_<sujet>.py` voisin (découverte par `manage.py test`).
- Moteur de l'assistant : `apps/ai_assistant/tests_chatbot/test_<sujet>.py` (découverte par `pytest`).
- Les tests n'appellent ni Internet ni service payant ; ils écrivent dans un dossier temporaire, jamais dans `donnees_ia/`.
- Ne jamais supprimer ni affaiblir un test pour le faire passer : corriger le code.

## …une migration
`manage.py makemigrations` pour une nouvelle ; ne jamais modifier ni supprimer une migration existante.

## …une commande de gestion
`apps/<app>/management/commands/<nom>.py`. Éviter le préfixe `test_` (réservé aux tests).
