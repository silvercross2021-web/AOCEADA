from django.urls import path  # pyrefly: ignore [untyped-import]
from .views import AlerteListView, AlerteMarkReadView, AlerteMarkAllReadView

urlpatterns = [
    path('', AlerteListView.as_view(), name='alerte_list'),
    path('tout-lire/', AlerteMarkAllReadView.as_view(), name='alerte_tout_lire'),
    path('<uuid:pk>/lire/', AlerteMarkReadView.as_view(), name='alerte_lire'),
]
