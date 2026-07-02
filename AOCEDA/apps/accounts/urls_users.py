from django.urls import path  # pyrefly: ignore [untyped-import]
from .views import (
    UserProfileView, ChangePasswordView, AdminUserListCreateView, AdminUserDetailView,
    TechnicienClientListView, ClientAbonnementView, TechnicienCreateClientView,
)

# Endpoints de gestion des utilisateurs : /api/users/...
urlpatterns = [
    # Profil de l'utilisateur connecté
    path('me/', UserProfileView.as_view(), name='user_profile'),
    path('me/password/', ChangePasswordView.as_view(), name='user_change_password'),

    # Espace technicien : liste des clients + création + référencement de l'abonnement/compteur
    path('clients/', TechnicienClientListView.as_view(), name='technicien_client_list'),
    path('clients/creer/', TechnicienCreateClientView.as_view(), name='technicien_creer_client'),
    path('clients/<uuid:pk>/abonnement/', ClientAbonnementView.as_view(), name='client_abonnement'),

    # Gestion des comptes (administrateur uniquement)
    path('', AdminUserListCreateView.as_view(), name='admin_user_list'),
    path('<uuid:pk>/', AdminUserDetailView.as_view(), name='admin_user_detail'),
]
