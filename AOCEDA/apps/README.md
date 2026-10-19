# apps/ : les 6 applications Django

| Dossier | Rôle | Fichiers clés |
|---|---|---|
| `accounts/` | utilisateurs, clients, techniciens, droits, JWT, paramètres du compte | `models.py`, `views.py`, `authentication.py`, `permissions.py` |
| `sensors/` | dispositifs, capteurs, mesures (réception ESP32), interventions | `models.py`, `views.py` (réception des mesures, technicien) |
| `analytics/` | tarifs CIE, historique, facture, prévisions, météo, exports PDF | `tarifs_cie.py`, `views.py`, `prevision_ia.py`, `pdf.py` |
| `alerts/` | règles et moteur d'alertes, e-mails | `utils.py` (moteur), `tasks.py` |
| `dashboard/` | pages HTML (aucun modèle) et données de démonstration | `views.py`, `urls.py`, `setup_demo` |
| `ai_assistant/` | assistant IA (chat, voix, appel en direct) | `chatbot/` (**moteur protégé**), `views.py`, `live.py`, `tests_chatbot/` |

À savoir :
- Le nom d'une app est son `app_label` : on ne le change pas ([décision 0001](../../docs/architecture/decisions/0001-garder-les-noms-d-apps-django.md)).
- Les apps s'importent presque toutes entre elles ; ne pas supposer d'ordre ([vue d'ensemble](../../docs/architecture/vue-ensemble.md)).
- Les tests sont à côté du code (`tests.py`, `tests_<sujet>.py`) et patchent des chemins précis : ne pas déplacer le code
  qu'ils visent ([décision 0003](../../docs/architecture/decisions/0003-refonte-sans-deplacer-le-code-python.md)).
- Zones protégées de cette arborescence : voir [AGENTS.md](../../AGENTS.md) §4.
