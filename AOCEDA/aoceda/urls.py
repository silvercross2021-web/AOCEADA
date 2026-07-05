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

from django.conf import settings  # pyrefly: ignore [untyped-import]
from django.conf.urls.static import static  # pyrefly: ignore [untyped-import]
from django.contrib import admin  # pyrefly: ignore [untyped-import]
from django.urls import path, include  # pyrefly: ignore [untyped-import]
from django.views.generic import RedirectView  # pyrefly: ignore [untyped-import]
from django.templatetags.static import static as static_url  # pyrefly: ignore [untyped-import]
from apps.sensors.views import MesureEnergieView, MesureSerieView
from apps.alerts.views import RegleDetectionListCreateView, RegleDetectionDetailView
from apps.analytics.views import PrevisionListView

# Branding de l'interface d'administration
admin.site.site_header = "AOCEDA, Administration"
admin.site.site_title = "AOCEDA Admin"
admin.site.index_title = "Supervision de la plateforme"

urlpatterns = [
    # Favicon : les navigateurs demandent /favicon.ico d'office → redirige vers le
    # logo AOCEDA (icône PNG) statique (supprime le 404 console présent sur toutes les pages).
    path("favicon.ico", RedirectView.as_view(url=static_url("img/logo/aoceda-icon.png"), permanent=False)),

    # Admin Interface
    path("admin/", admin.site.urls),

    # Web Platform UI Views
    path("", include("apps.dashboard.urls")),

    # REST API Routes
    path("api/auth/", include("apps.accounts.urls")),
    path("api/users/", include("apps.accounts.urls_users")),
    path("api/sensors/", include("apps.sensors.urls")),
    path("api/mesures/", MesureEnergieView.as_view(), name="mesures"),
    path("api/mesures/serie/", MesureSerieView.as_view(), name="mesures-serie"),
    path("api/alertes/", include("apps.alerts.urls")),
    path("api/regles/", RegleDetectionListCreateView.as_view(), name="regles-list"),
    path("api/regles/<uuid:pk>/", RegleDetectionDetailView.as_view(), name="regle-detail"),
    path("api/analytics/", include("apps.analytics.urls")),
    path("api/previsions/", PrevisionListView.as_view(), name="previsions-list"),
    path("api/assistant/", include("apps.ai_assistant.urls")),
]

# Sert les fichiers média (photos de profil) en développement (DEBUG).
# En production, ces fichiers sont servis par le serveur web / stockage objet.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
