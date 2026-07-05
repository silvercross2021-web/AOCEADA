from django.urls import path  # pyrefly: ignore [untyped-import]
from .views import (
    CapteurListView,
    DispositifListCreateView, DispositifDetailView, DispositifRegenererCleView,
    CapteurTechnicienListCreateView, CapteurTechnicienDetailView,
    CapteurDisponiblesView, CapteurAssignerView, CapteurCalibrerView,
    InterventionListCreateView, InterventionDetailView, RapportInterventionView,
    RapportInterventionPDFView,
    ZMCTIngestionView,
    ArduinoIngestionView, MesureStreamView,
)

urlpatterns = [
    # Espace client : ses propres capteurs
    path('', CapteurListView.as_view(), name='capteur_list'),

    # Espace technicien : enregistrement ESP32 + génération API Key
    path('dispositifs/', DispositifListCreateView.as_view(), name='dispositif_list'),
    path('dispositifs/<uuid:pk>/', DispositifDetailView.as_view(), name='dispositif_detail'),
    path('dispositifs/<uuid:pk>/regenerer-cle/', DispositifRegenererCleView.as_view(), name='dispositif_regenerer_cle'),

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
    path('interventions/', InterventionListCreateView.as_view(), name='intervention_list'),
    path('interventions/<uuid:pk>/', InterventionDetailView.as_view(), name='intervention_detail'),
    path('interventions/<uuid:pk>/rapport/', RapportInterventionView.as_view(), name='intervention_rapport'),
    path('interventions/<uuid:pk>/rapport/pdf/', RapportInterventionPDFView.as_view(), name='intervention_rapport_pdf'),
]
