# Laboratoire Isolé : Mode Live Multilingue Universel

**Dossier :** `AOCEDA/lab_live/`  
**Objectif :** Développer, tester et valider la nouvelle architecture Live Multilingue (Français, Anglais, Baoulé, Dioula, et futurs Wolof/Yoruba) dans un environnement 100 % autonome et isolé du code de production.

---

## 1. Pourquoi ce laboratoire isolé ?

1. **Zéro régression sur la production** : Le code de l'assistant de production (`apps/ai_assistant/chatbot/live_agent.py`) n'est pas modifié. Les 1 209 tests existants restent 100 % verts.
2. **Même structure de code** : `live_agent_multilingue.py` reprend la structure exacte, les signatures et les conventions de `live_agent.py`. Le jour où le Lab est validé, l'intégration dans le projet réel se fait par un simple remplacement transparent.
3. **Serveur de test indépendant** : Le lab possède son propre serveur web & WebSocket (`serveur_lab.py`) sur le port **8775**. Il peut tourner en même temps que le serveur Django normal (port 8003).

---

## 2. Structure des fichiers

* [live_agent_multilingue.py](file:///c:/Users/silve/Documents/PlatformIO/Projects/Test_ZMCT/AOCEDA/lab_live/live_agent_multilingue.py) : Le moteur Live complet avec dissociation Oreille (Ingress), Cerveau (Gemini Live), Bouche (Egress), machine à états double verrou, streaming de synthèse, earcons d'attente et garde-fous.
* [serveur_lab.py](file:///c:/Users/silve/Documents/PlatformIO/Projects/Test_ZMCT/AOCEDA/lab_live/serveur_lab.py) : Serveur ASGI / aiohttp autonome sur le port 8775.
* `static/index.html` : Interface web de test dédiée pour tester l'appel Live au micro avec sélecteurs de langue, onde sonore, sous-titres bilingues et cartes.
* [tests_lab.py](file:///c:/Users/silve/Documents/PlatformIO/Projects/Test_ZMCT/AOCEDA/lab_live/tests_lab.py) : Suite de tests automatisés validant les 4 modes opérationnels, les bascules à la volée et les garde-fous.

---

## 3. Comment lancer le laboratoire

Depuis le dossier `AOCEDA/` :

```bat
:: Lancer les tests automatisés du Lab :
.venv_local\Scripts\python.exe lab_live\tests_lab.py

:: Lancer le serveur web autonome du Lab :
.venv_local\Scripts\python.exe lab_live\serveur_lab.py
```

Puis ouvrir dans votre navigateur :  
👉 **http://127.0.0.1:8775**
