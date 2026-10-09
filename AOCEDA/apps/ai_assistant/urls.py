"""Routes HTTP de l'assistant IA (/api/assistant/...), voir views.py ; l'appel Live (WebSocket) est dans routing.py."""
from django.urls import path, re_path

from . import views

urlpatterns = [
    path("message", views.message, name="assistant_message"),
    path("transcrire", views.Transcrire.as_view(), name="assistant_transcrire"),
    path("transcrire/morceau", views.TranscrireMorceau.as_view(), name="assistant_transcrire_morceau"),
    path("voix", views.Voix.as_view(), name="assistant_voix"),
    path("voix/morceaux", views.VoixMorceaux.as_view(), name="assistant_voix_morceaux"),
    path("nouvelle", views.Nouvelle.as_view(), name="assistant_nouvelle"),
    path("config", views.Config.as_view(), name="assistant_config"),
    path("tests", views.Tests.as_view(), name="assistant_tests"),
    path("live/etat", views.LiveEtat.as_view(), name="assistant_live_etat"),
    path("gpu/credit", views.GpuCredit.as_view(), name="assistant_gpu_credit"),
    path("baoule/reveil", views.BaouleReveil.as_view(), name="assistant_baoule_reveil"),
    path("baoule/exemples", views.BaouleExemples.as_view(), name="assistant_baoule_exemples"),
    path("baoule/exemples/valider", views.BaouleValider.as_view(), name="assistant_baoule_valider"),
    path("baoule/exemples/rejeter", views.BaouleRejeter.as_view(), name="assistant_baoule_rejeter"),
    re_path(r"^rapports/(?P<dossier>audios|captures)/(?P<chemin>[A-Za-z0-9_./ -]+)$", views.fichier_rapport,
            name="assistant_rapport"),
    path("conversations/", views.ConversationListCreateView.as_view(), name="ai_conversations"),
    path("conversations/<uuid:id>/", views.ConversationDetailView.as_view(), name="ai_conversation_detail"),
]
