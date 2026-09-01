from django.urls import path  # pyrefly: ignore [untyped-import]
from .views import (
    CapteurListView, CapteurRenommerView,
    DispositifListCreateView, DispositifDetailView, DispositifRegenererCleView,
    DispositifReassignerView, DispositifQRConfigView,
    CapteurTechnicienListCreateView, CapteurTechnicienDetailView,
    CapteurDisponiblesView, CapteurAssignerView, CapteurCalibrerView,
    InterventionListCreateView, InterventionDetailView, InterventionFeedbackView, RapportInterventionView,
    RapportInterventionPDFView, InterventionExportCSVView, JournalListView,
    ZMCTIngestionView,
    ArduinoIngestionView, MesureStreamView,
)

urlpatterns = [
    # Espace client : ses propres capteurs
    path('', CapteurListView.as_view(), name='capteur_list'),
    # Espace client : renommer UN de ses capteurs (PATCH {nom}), scopé au client
    path('mes-capteurs/<uuid:pk>/', CapteurRenommerView.as_view(), name='capteur_renommer'),

    # Espace technicien : enregistrement ESP32 + génération API Key
    path('dispositifs/', DispositifListCreateView.as_view(), name='dispositif_list'),
    path('dispositifs/<uuid:pk>/', DispositifDetailView.as_view(), name='dispositif_detail'),
    path('dispositifs/<uuid:pk>/regenerer-cle/', DispositifRegenererCleView.as_view(), name='dispositif_regenerer_cle'),
    path('dispositifs/<uuid:pk>/reassigner/', DispositifReassignerView.as_view(), name='dispositif_reassigner'),
    path('dispositifs/<uuid:pk>/qr-config/', DispositifQRConfigView.as_view(), name='dispositif_qr_config'),

    # Pool de capteurs ZMCT disponibles (non assignés)
    path('capteurs/disponibles/', CapteurDisponiblesView.as_view(), name='capteur_disponibles'),

    # Installation et calibration des capteurs
    path('capteurs/', CapteurTechnicienListCreateView.as_view(), name='capteur_tech_list'),
    path('capteurs/<uuid:pk>/', CapteurTechnicienDetailView.as_view(), name='capteur_tech_detail'),
    path('capteurs/<uuid:pk>/calibrer/', CapteurCalibrerView.as_view(), name='capteur_calibrer'),
    path('capteurs/<uuid:pk>/assigner/', CapteurAssignerView.as_view(), name='capteur_assigner'),

    # Ingestion données ZMCT depuis ESP32 (auth via X-Device-Key / Device <key>)
    path('zmct/', ZMCTIngestionView.as_view(), name='zmct_ingestion'),

    # Ingestion depuis le pont série Arduino (serial_bridge.py, auth X-Bridge-Token)
    path('arduino/', ArduinoIngestionView.as_view(), name='arduino_ingestion'),

    # Flux SSE temps réel pour le dashboard client (?token=<JWT>)
    path('stream/', MesureStreamView.as_view(), name='mesure_stream'),

    # Pannes et interventions
    path('interventions/export/csv/', InterventionExportCSVView.as_view(), name='intervention_export_csv'),
    path('interventions/', InterventionListCreateView.as_view(), name='intervention_list'),
    path('interventions/<uuid:pk>/', InterventionDetailView.as_view(), name='intervention_detail'),
    path('interventions/<uuid:pk>/retour/', InterventionFeedbackView.as_view(), name='intervention_feedback'),
    path('interventions/<uuid:pk>/rapport/', RapportInterventionView.as_view(), name='intervention_rapport'),
    path('interventions/<uuid:pk>/rapport/pdf/', RapportInterventionPDFView.as_view(), name='intervention_rapport_pdf'),

    # Journal d'audit (traçabilité des actions hors cycle Intervention)
    path('journal/', JournalListView.as_view(), name='journal_list'),
]
