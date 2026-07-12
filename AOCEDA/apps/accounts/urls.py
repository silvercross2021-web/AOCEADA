from django.urls import path  # pyrefly: ignore [untyped-import]
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import PasswordResetRequestView, PasswordResetConfirmView, CustomTokenObtainPairView, Verify2FAView

# Endpoints d'authentification : /api/auth/...
# NB : pas d'auto-inscription publique. Conformément aux diagrammes (cas
# d'utilisation), c'est le Technicien/Administrateur qui crée le compte client
# (voir /api/users/clients/creer/). Le Visiteur ne peut que se connecter et
# réinitialiser son mot de passe.
urlpatterns = [
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('login/2fa/', Verify2FAView.as_view(), name='verify_2fa'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('password/reset/', PasswordResetRequestView.as_view(), name='password_reset_request'),
    path('password/reset/confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
]
