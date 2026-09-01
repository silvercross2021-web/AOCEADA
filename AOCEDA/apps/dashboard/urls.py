from django.urls import path  # pyrefly: ignore [untyped-import]
from . import views

app_name = 'dashboard'

urlpatterns = [
    # Site vitrine
    path('', views.index, name='index'),

    # Vidéo du site servie par plage d'octets (scrubbing du film logo au scroll)
    path('media/site-video/<str:name>', views.site_video, name='site_video'),

    # Authentification (connexion / inscription)
    path('auth/', views.auth_view, name='auth'),
    path('aoceda-auth.html', views.auth_view, name='auth_html'),

    # Espace client
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('historique/', views.historique_view, name='historique'),
    path('alertes/', views.alertes_view, name='alertes'),
    path('ia/', views.ia_view, name='ia'),
    path('previsions/', views.previsions_view, name='previsions'),
    path('parametres/', views.parametres_view, name='parametres'),
    path('interventions/', views.interventions_view, name='interventions'),

    # Espace technicien
    path('technicien/', views.technicien_view, name='technicien'),

    # Données agrégées pour le tableau de bord de l'admin Django (staff uniquement)
    path('admin-stats-data/', views.admin_stats_data, name='admin_stats_data'),

    # Anciens chemins .html conservés pour compatibilité (liens internes des pages)
    path('aoceda-dashboard.html', views.dashboard_view, name='dashboard_html'),
    path('aoceda-historique.html', views.historique_view, name='historique_html'),
    path('aoceda-ia.html', views.ia_view, name='ia_html'),
    path('aoceda-previsions.html', views.previsions_view, name='previsions_html'),
    path('aoceda-alertes.html', views.alertes_view, name='alertes_html'),
    path('aoceda-parametres.html', views.parametres_view, name='parametres_html'),
    path('aoceda-technicien.html', views.technicien_view, name='technicien_html'),
    path('aoceda-interventions.html', views.interventions_view, name='interventions_html'),
]


