"""
ASGI config for aoceda project : HTTP (Django) + WebSocket (Channels).

Le WebSocket sert l'appel Live de l'assistant IA (apps/ai_assistant/routing.py).
En développement, `manage.py runserver` sert cette application (daphne dans INSTALLED_APPS).
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aoceda.settings")
django_asgi_app = get_asgi_application()   # charge Django AVANT tout import qui touche aux modèles

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.ai_assistant.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns)),
})
