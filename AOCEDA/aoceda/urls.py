"""
URL configuration for aoceda project.

Architecture conforme au mémoire (Tableau 4.1) :
  accounts      -> /api/auth/, /api/users/
  sensors       -> /api/sensors/, /api/mesures/
  analytics     -> /api/analytics/, /api/previsions/
  alerts        -> /api/alertes/, /api/regles/
  dashboard     -> /, /tableau-de-bord/ (vues HTML)
  ai_assistant  -> /api/assistant/
"""

from django.contrib import admin  # pyrefly: ignore [untyped-import]
from django.urls import path, include  # pyrefly: ignore [untyped-import]
from apps.sensors.views import MesureEnergieView
from apps.alerts.views import RegleDetectionListCreateView, RegleDetectionDetailView
from apps.analytics.views import PrevisionListView

# Branding de l'interface d'administration
admin.site.site_header = "AOCEDA — Administration"
admin.site.site_title = "AOCEDA Admin"
admin.site.index_title = "Supervision de la plateforme"

urlpatterns = [
    # Admin Interface
    path("admin/", admin.site.urls),

    # Web Platform UI Views
    path("", include("apps.dashboard.urls")),

    # REST API Routes
    path("api/auth/", include("apps.accounts.urls")),
    path("api/users/", include("apps.accounts.urls_users")),
    path("api/sensors/", include("apps.sensors.urls")),
    path("api/mesures/", MesureEnergieView.as_view(), name="mesures"),
    path("api/alertes/", include("apps.alerts.urls")),
    path("api/regles/", RegleDetectionListCreateView.as_view(), name="regles-list"),
    path("api/regles/<uuid:pk>/", RegleDetectionDetailView.as_view(), name="regle-detail"),
    path("api/analytics/", include("apps.analytics.urls")),
    path("api/previsions/", PrevisionListView.as_view(), name="previsions-list"),
    path("api/assistant/", include("apps.ai_assistant.urls")),
]
