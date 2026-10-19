# API : liste des endpoints

Liste **générée à partir du routeur Django** (2026-10-19, 90 routes sous `api/`). Elle décrit le contrat : ces chemins et
formats sont **figés** (ESP32, application mobile, WebSocket Live). Pour un exemple de réponse, lancer le serveur, se
connecter, puis ouvrir le chemin dans le navigateur ou lire la vue indiquée.

- **Droits** : `IsAuthenticated` est le défaut du projet (jeton JWT `Authorization: Bearer ...`). « (défaut du projet) » = ce défaut ;
  « (voir la vue) » = vue-fonction ou ensemble de vues, droits dans le décorateur.
- L'ESP32 envoie ses mesures sur `api/sensors/zmct/` avec la clé de son dispositif (pas de JWT).
- Corps de l'ESP32 : `{capteur_index, etat, courant, puissance, timestamp_unix, coupe}` ; `capteur_index` est **inversé** par rapport aux noms du firmware (voir [firmware-esp32.md](../firmware/firmware-esp32.md) §4) ; réponse `{created, coupe_1, coupe_2}`.
- Le pont série Arduino utilise l'en-tête `X-Bridge-Token` (voir [outils](../../AOCEDA/outils/README.md)).
- Le WebSocket de l'appel Live n'est pas listé ici (ASGI) : `/api/assistant/live?token=<JWT>`.

## `/api/alertes/`

| Chemin | Méthodes | Droits | Vue |
|---|---|---|---|
| `/api/alertes/` | GET | IsAuthenticated | `apps.alerts.views.AlerteListView` |
| `/api/alertes/<uuid:pk>/lire/` | PATCH | IsAuthenticated | `apps.alerts.views.AlerteMarkReadView` |
| `/api/alertes/compteur/` | GET | IsAuthenticated | `apps.alerts.views.CompteurAlertesView` |
| `/api/alertes/test-email/` | POST | IsAuthenticated | `apps.alerts.views.EmailTestView` |
| `/api/alertes/tout-lire/` | POST | IsAuthenticated | `apps.alerts.views.AlerteMarkAllReadView` |
| `/api/alertes/tranche/` | GET | IsAuthenticated | `apps.alerts.views.TrancheEtatView` |

## `/api/analytics/`

| Chemin | Méthodes | Droits | Vue |
|---|---|---|---|
| `/api/analytics/admin/stats/` | GET | IsAuthenticated | `apps.analytics.views.AdminStatsView` |
| `/api/analytics/conseils/` | GET | IsAuthenticated | `apps.analytics.views.ConseilsView` |
| `/api/analytics/credit/releve/` | POST | IsAuthenticated | `apps.analytics.views.ReleveCompteurView` |
| `/api/analytics/export/` | GET | IsAuthenticated | `apps.analytics.views.ExportCSVView` |
| `/api/analytics/export/journalier/` | GET | IsAuthenticated | `apps.analytics.views.ExportJournalierCSVView` |
| `/api/analytics/export/pdf/` | GET | IsAuthenticated | `apps.analytics.views.HistoriquePDFView` |
| `/api/analytics/export/rapport-mensuel/` | GET | IsAuthenticated | `apps.analytics.views.RapportMensuelPDFView` |
| `/api/analytics/facture/` | GET | IsAuthenticated | `apps.analytics.views.FactureDetailView` |
| `/api/analytics/heatmap/` | GET | IsAuthenticated | `apps.analytics.views.HeatmapView` |
| `/api/analytics/historique-mensuel/` | GET | IsAuthenticated | `apps.analytics.views.HistoriqueMensuelView` |
| `/api/analytics/historique/` | GET | IsAuthenticated | `apps.analytics.views.HistoriqueJournalierView` |
| `/api/analytics/prevision/` | GET | IsAuthenticated | `apps.analytics.views.PrevisionView` |
| `/api/analytics/repartition/` | GET | IsAuthenticated | `apps.analytics.views.RepartitionCapteursView` |
| `/api/analytics/summary/` | GET | IsAuthenticated | `apps.analytics.views.AnalyticsSummaryView` |
| `/api/analytics/tarif/` | GET | IsAuthenticated | `apps.analytics.views.TarifView` |

## `/api/assistant/`

| Chemin | Méthodes | Droits | Vue |
|---|---|---|---|
| `/api/assistant/^rapports/(?P<dossier>audios|captures)/(?P<chemin>[A-Za-z0-9_./ -]+)$` | ? | (voir la vue) | `apps.ai_assistant.views.fichier_rapport` |
| `/api/assistant/baoule/exemples` | GET | IsAuthenticated | `apps.ai_assistant.views.BaouleExemples` |
| `/api/assistant/baoule/exemples/rejeter` | POST | IsAuthenticated | `apps.ai_assistant.views.BaouleRejeter` |
| `/api/assistant/baoule/exemples/valider` | POST | IsAuthenticated | `apps.ai_assistant.views.BaouleValider` |
| `/api/assistant/baoule/reveil` | POST | IsAuthenticated | `apps.ai_assistant.views.BaouleReveil` |
| `/api/assistant/config` | GET | IsAuthenticated | `apps.ai_assistant.views.Config` |
| `/api/assistant/conversations/` | GET,POST,DELETE | IsAuthenticated | `apps.ai_assistant.views.ConversationListCreateView` |
| `/api/assistant/conversations/<uuid:id>/` | GET,PUT,PATCH,DELETE | IsAuthenticated | `apps.ai_assistant.views.ConversationDetailView` |
| `/api/assistant/credits` | GET | IsAuthenticated | `apps.ai_assistant.views.Credits` |
| `/api/assistant/document` | POST | IsAuthenticated | `apps.ai_assistant.views.Document` |
| `/api/assistant/gpu/credit` | GET | IsAuthenticated | `apps.ai_assistant.views.GpuCredit` |
| `/api/assistant/live/etat` | GET | IsAuthenticated | `apps.ai_assistant.views.LiveEtat` |
| `/api/assistant/message` | ? | (voir la vue) | `apps.ai_assistant.views.message` |
| `/api/assistant/nouvelle` | POST | IsAuthenticated | `apps.ai_assistant.views.Nouvelle` |
| `/api/assistant/tests` | GET | IsAuthenticated | `apps.ai_assistant.views.Tests` |
| `/api/assistant/transcrire` | POST | IsAuthenticated | `apps.ai_assistant.views.Transcrire` |
| `/api/assistant/transcrire/morceau` | POST | IsAuthenticated | `apps.ai_assistant.views.TranscrireMorceau` |
| `/api/assistant/voix` | POST | IsAuthenticated | `apps.ai_assistant.views.Voix` |
| `/api/assistant/voix/morceaux` | POST | IsAuthenticated | `apps.ai_assistant.views.VoixMorceaux` |

## `/api/auth/`

| Chemin | Méthodes | Droits | Vue |
|---|---|---|---|
| `/api/auth/login/` | POST | (défaut du projet) | `apps.accounts.views.CustomTokenObtainPairView` |
| `/api/auth/login/2fa/` | POST | AllowAny | `apps.accounts.views.Verify2FAView` |
| `/api/auth/logout/` | POST | IsAuthenticated | `apps.accounts.views.LogoutView` |
| `/api/auth/password/reset/` | POST | AllowAny | `apps.accounts.views.PasswordResetRequestView` |
| `/api/auth/password/reset/confirm/` | POST | AllowAny | `apps.accounts.views.PasswordResetConfirmView` |
| `/api/auth/refresh/` | POST | (défaut du projet) | `rest_framework_simplejwt.views.TokenRefreshView` |

## `/api/mesures/`

| Chemin | Méthodes | Droits | Vue |
|---|---|---|---|
| `/api/mesures/` | GET,POST | IsAuthenticated | `apps.sensors.views.MesureEnergieView` |
| `/api/mesures/serie/` | GET | IsAuthenticated | `apps.sensors.views.MesureSerieView` |

## `/api/previsions/`

| Chemin | Méthodes | Droits | Vue |
|---|---|---|---|
| `/api/previsions/` | GET | IsAuthenticated | `apps.analytics.views.PrevisionListView` |

## `/api/regles/`

| Chemin | Méthodes | Droits | Vue |
|---|---|---|---|
| `/api/regles/` | GET,POST | IsAuthenticated | `apps.alerts.views.RegleDetectionListCreateView` |
| `/api/regles/<uuid:pk>/` | GET,PUT,PATCH,DELETE | IsAuthenticated | `apps.alerts.views.RegleDetectionDetailView` |

## `/api/sensors/`

| Chemin | Méthodes | Droits | Vue |
|---|---|---|---|
| `/api/sensors/` | GET | IsAuthenticated | `apps.sensors.views.CapteurListView` |
| `/api/sensors/arduino/` | POST | (défaut du projet) | `apps.sensors.views.ArduinoIngestionView` |
| `/api/sensors/capteurs/` | GET,POST | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.sensors.views.CapteurTechnicienListCreateView` |
| `/api/sensors/capteurs/<uuid:pk>/` | GET,PUT,PATCH,DELETE | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.sensors.views.CapteurTechnicienDetailView` |
| `/api/sensors/capteurs/<uuid:pk>/assigner/` | POST | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.sensors.views.CapteurAssignerView` |
| `/api/sensors/capteurs/<uuid:pk>/calibrer/` | POST | IsAuthenticated | `apps.sensors.views.CapteurCalibrerView` |
| `/api/sensors/capteurs/disponibles/` | GET | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.sensors.views.CapteurDisponiblesView` |
| `/api/sensors/dispositifs/` | GET,POST | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.sensors.views.DispositifListCreateView` |
| `/api/sensors/dispositifs/<uuid:pk>/` | GET,PUT,PATCH,DELETE | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.sensors.views.DispositifDetailView` |
| `/api/sensors/dispositifs/<uuid:pk>/qr-config/` | GET | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.sensors.views.DispositifQRConfigView` |
| `/api/sensors/dispositifs/<uuid:pk>/reassigner/` | POST | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.sensors.views.DispositifReassignerView` |
| `/api/sensors/dispositifs/<uuid:pk>/regenerer-cle/` | POST | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.sensors.views.DispositifRegenererCleView` |
| `/api/sensors/interventions/` | GET,POST | IsAuthenticated | `apps.sensors.views.InterventionListCreateView` |
| `/api/sensors/interventions/<uuid:pk>/` | GET,PUT,PATCH,DELETE | IsAuthenticated, IsOwnerOrTechnicienOrAdmin | `apps.sensors.views.InterventionDetailView` |
| `/api/sensors/interventions/<uuid:pk>/annuler/` | POST | IsAuthenticated | `apps.sensors.views.InterventionAnnulerView` |
| `/api/sensors/interventions/<uuid:pk>/rapport/` | POST | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.sensors.views.RapportInterventionView` |
| `/api/sensors/interventions/<uuid:pk>/rapport/pdf/` | GET | IsAuthenticated | `apps.sensors.views.RapportInterventionPDFView` |
| `/api/sensors/interventions/<uuid:pk>/retour/` | PUT,PATCH | IsAuthenticated | `apps.sensors.views.InterventionFeedbackView` |
| `/api/sensors/interventions/export/csv/` | GET | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.sensors.views.InterventionExportCSVView` |
| `/api/sensors/journal/` | GET | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.sensors.views.JournalListView` |
| `/api/sensors/mes-capteurs/<uuid:pk>/` | GET,PUT,PATCH | IsAuthenticated | `apps.sensors.views.CapteurRenommerView` |
| `/api/sensors/mes-capteurs/<uuid:pk>/coupure/` | POST | IsAuthenticated | `apps.sensors.views.CapteurCoupureView` |
| `/api/sensors/stream/` | GET | (défaut du projet) | `apps.sensors.views.MesureStreamView` |
| `/api/sensors/zmct/` | POST | IsAuthenticated | `apps.sensors.views.ZMCTIngestionView` |

## `/api/users/`

| Chemin | Méthodes | Droits | Vue |
|---|---|---|---|
| `/api/users/` | GET,POST | IsAuthenticated, IsAdministrateur | `apps.accounts.views.AdminUserListCreateView` |
| `/api/users/<uuid:pk>/` | GET,PUT,PATCH,DELETE | IsAuthenticated, IsAdministrateur | `apps.accounts.views.AdminUserDetailView` |
| `/api/users/clients/` | GET | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.accounts.views.TechnicienClientListView` |
| `/api/users/clients/<uuid:pk>/` | GET,PUT,PATCH | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.accounts.views.TechnicienClientDetailView` |
| `/api/users/clients/<uuid:pk>/abonnement/` | GET,PUT,PATCH | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.accounts.views.ClientAbonnementView` |
| `/api/users/clients/creer/` | POST | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.accounts.views.TechnicienCreateClientView` |
| `/api/users/clients/notes/` | GET,POST | IsAuthenticated, IsTechnicienOrAdministrateur | `apps.accounts.views.NoteClientListCreateView` |
| `/api/users/me/` | GET,PUT,DELETE | IsAuthenticated | `apps.accounts.views.UserProfileView` |
| `/api/users/me/2fa/` | POST | IsAuthenticated | `apps.accounts.views.Toggle2FAView` |
| `/api/users/me/connexions/` | GET | IsAuthenticated | `apps.accounts.views.UserConnexionsView` |
| `/api/users/me/deconnexion-partout/` | POST | IsAuthenticated | `apps.accounts.views.DeconnexionGlobaleView` |
| `/api/users/me/demander-desactivation/` | POST | IsAuthenticated | `apps.accounts.views.DemanderDesactivationView` |
| `/api/users/me/export/` | GET | IsAuthenticated | `apps.accounts.views.UserExportView` |
| `/api/users/me/password/` | PUT | IsAuthenticated | `apps.accounts.views.ChangePasswordView` |
| `/api/users/me/photo/` | POST,DELETE | IsAuthenticated | `apps.accounts.views.UserPhotoView` |

