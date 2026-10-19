# Vue d'ensemble de l'architecture

Ce document est le résumé ; la carte détaillée (arborescence complète, pages, flux, tests, où mettre quoi) est dans [ARCHITECTURE.md](../../ARCHITECTURE.md).

## Les ensembles du dépôt

```
┌────────────┐   POST /api/sensors/zmct/    ┌────────────────────────── AOCEDA/ (Django 6, Daphne ASGI) ──────────────────────────┐
│ ESP32      │ ───────────────────────────► │  apps/sensors   mesures, dispositifs, interventions                                  │
│ + ZMCT103C │   (Wi-Fi, clé du dispositif) │  apps/accounts  utilisateurs, clients, techniciens, droits, JWT                      │
└────────────┘                              │  apps/analytics tarifs CIE, historique, facture, prévisions, météo                    │
┌────────────┐   pont série (X-Bridge-Token)│  apps/alerts    règles et moteur d'alertes, e-mails                                  │
│ Arduino    │ ───────────────────────────► │  apps/dashboard pages HTML (gabarits + un JS/CSS par page)                           │
└────────────┘                              │  apps/ai_assistant  assistant IA : chat, voix, appel Live (WebSocket)                │
                                            └───────────────┬──────────────────────────────────────────┬────────────────────────┘
        navigateur / application Android ◄── pages /dashboard/, /historique/…  API /api/…  WebSocket /api/assistant/live
```

| Ensemble | Chemin | Rôle |
|---|---|---|
| Micrologiciel | `src/`, `include/`, `lib/`, `platformio.ini` | lit deux capteurs de courant, envoie les mesures, met en tampon hors ligne |
| Serveur | `AOCEDA/aoceda/` + `AOCEDA/apps/` | configuration du projet + 6 applications |
| Front | `AOCEDA/static/`, `AOCEDA/templates/` | une page = un gabarit `aoceda-<page>.html` + `static/js/<page>.js` + `static/css/<page>.css` |
| Mobile | `AOCEDA/mobile_app/` | Capacitor : affiche le site distant |
| Outillage | `AOCEDA/outils/`, `installer.*`, `lancer_aoceda.bat` | installation, lancement, scripts manuels |

## Les applications Django et leurs modèles

| App (`app_label`) | Modèles principaux | Remarque |
|---|---|---|
| `accounts` | `Utilisateur`, `Client`, `Technicien`, `Administrateur`, `AuditLog`, `NoteClient` | identité et droits ; jeton JWT |
| `sensors` | `Dispositif`, `Capteur`, `PresenceCapteur`, `MesureEnergie`, `Intervention`, `RapportIntervention` | reçoit les mesures de l'ESP32 |
| `analytics` | `Prevision`, `RechargeCredit`, `MeteoJour` | `tarifs_cie.py` : barème CIE (voir [tarification](tarification-cie.md)) |
| `alerts` | `RegleDetection`, `Alerte` | `utils.py` contient le moteur d'alertes |
| `dashboard` | aucun | pages HTML seulement |
| `ai_assistant` | `Conversation`, `QuotaIA` | moteur dans `chatbot/` ; mémoire de dialogue dans `donnees_ia/` |

**Les noms de ces apps sont des contrats** : ils servent de `app_label`, de noms de tables et de références dans les
migrations. On ne les renomme pas.

## Dépendances entre applications (état réel mesuré le 2026-10-19)

```
accounts   -> alerts, analytics, sensors
sensors    -> accounts, alerts, analytics
alerts     -> accounts, analytics, sensors
analytics  -> accounts, alerts, sensors
dashboard  -> accounts, ai_assistant, alerts, analytics, sensors   (hors tests ; analytics n'importe ai_assistant que dans un test)
ai_assistant -> accounts, alerts, analytics, sensors
```

Les applications s'importent presque toutes entre elles (des dizaines d'imports faits à l'intérieur de fonctions masquent les cycles). Un ordre cible existe
(`accounts` < `sensors` < `analytics` < `alerts` < `dashboard`/`ai_assistant`) mais il n'est **pas** appliqué : le faire
casserait des tests protégés qui visent des chemins précis (voir [décision 0003](decisions/0003-refonte-sans-deplacer-le-code-python.md)).

## Flux de données

1. **Mesures** : l'ESP32 envoie `{capteur_index, etat, courant, puissance, timestamp_unix}` à `POST /api/sensors/zmct/`,
   avec la clé de son dispositif. La vue crée une `MesureEnergie` rattachée au client propriétaire du capteur.
2. **Affichage** : chaque page appelle l'API (`/api/mesures/`, `/api/mesures/serie/`, `/api/analytics/…`) avec le jeton JWT
   gardé dans `localStorage` (`aoceda_access_token`).
3. **Alertes** : une tâche Celery `apps.alerts.tasks.detecter_anomalies` tourne toutes les 5 minutes et applique les
   `RegleDetection` ; elle crée des `Alerte` (et envoie des e-mails).
4. **Prévisions et météo** : `apps.analytics.tasks.enregistrer_previsions` (toutes les heures) et `rafraichir_meteo`
   (toutes les 6 heures) ; `purger_alertes_lues` nettoie une fois par jour.
5. **Assistant IA** : le navigateur ouvre `/ia/` (gabarit AOCEDA) qui contient un cadre `/ia/assistant/`. Les questions
   passent par `/api/assistant/message` (flux SSE) ; le moteur appelle DeepSeek avec dix outils qui lisent **uniquement
   les données du client connecté** ; la voix passe par Whisper, Omnilingual (dioula), omniASR (baoulé) et des voix de
   synthèse ; l'appel en direct utilise le WebSocket `/api/assistant/live`.

## Règles qui structurent le code

- Jamais de fausses données : quand une donnée manque, un état vide honnête (voir [décisions](decisions/)).
- Zones protégées et contrats figés : voir [AGENTS.md](../../AGENTS.md) et [la décision 0002](decisions/0002-contrats-figes-et-zones-protegees.md).
- Daphne (ASGI) reste le serveur : HTTP et WebSocket sur le même port.
