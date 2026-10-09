"""Routes WebSocket de l'assistant IA (servies par Channels, voir aoceda/asgi.py)."""
from django.urls import path

from .live import application as appel_live

websocket_urlpatterns = [
    path("api/assistant/live", appel_live),            # appel Live avec l'agent (voix en direct)
]
