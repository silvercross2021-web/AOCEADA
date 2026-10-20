# Lancer les tests

Depuis `AOCEDA/`, **une seule suite à la fois**, serveur de développement arrêté :

```bat
.venv_local\Scripts\python.exe -m pytest          :: moteur de l'assistant : 751 tests
.venv_local\Scripts\python.exe manage.py test     :: reste d'AOCEDA : 458 tests
```

Durées mesurées le 2026-10-19 sur le PC du propriétaire : `pytest` **2 min 45**, `manage.py test` **23 min 12**. Les
mots de passe sont chiffrés volontairement lentement dans les tests de comptes : ne pas interrompre.

- Sans les modèles locaux, 3 tests se mettent de côté (« modèle absent ») : normal.
- Les tests passent sans aucune clé d'API.
- Sur un PC très chargé, un test qui mesure des délais peut échouer une fois : relancer avant de conclure.
- Contrôle rapide sans les suites (environ 2 minutes) : `docs/refonte/gardien/controle.py` (voir [refonte](../refonte/README.md)).
- Smoke visuel des pages : `docs/refonte/gardien/smoke_pages.py` (à lancer sur une **copie** de la base avec les comptes
  de démonstration).
