from django.urls import path  # pyrefly: ignore [untyped-import]
from .views import (AlerteListView, AlerteMarkReadView, AlerteMarkAllReadView, TrancheEtatView,
                    CompteurAlertesView, EmailTestView)

urlpatterns = [
    path('', AlerteListView.as_view(), name='alerte_list'),
    path('tranche/', TrancheEtatView.as_view(), name='alerte_tranche'),
    path('compteur/', CompteurAlertesView.as_view(), name='alerte_compteur'),
    path('test-email/', EmailTestView.as_view(), name='alerte_test_email'),
    path('tout-lire/', AlerteMarkAllReadView.as_view(), name='alerte_tout_lire'),
    path('<uuid:pk>/lire/', AlerteMarkReadView.as_view(), name='alerte_lire'),
]
