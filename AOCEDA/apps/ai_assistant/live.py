"""Appel Live (WebSocket /api/assistant/live?token=<JWT>) : le client connecté parle à l'agent en direct.

La passerelle du laboratoire (chatbot/live_agent.py) est reprise telle quelle : elle parle à la page par l'objet
WebSocket de Starlette, créé ici sur la connexion que Channels a reçue (aoceda/asgi.py -> routing.py). Le client est
authentifié par son jeton (le navigateur ne peut pas mettre d'en-tête Authorization sur un WebSocket) ; l'agent ne lit
que SES données et ne reprend que SES conversations.
"""
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections
from starlette.websockets import WebSocket

from .chatbot import live_agent, securite
from .chatbot.donnees_client import DonneesClient
from .chatbot.journal import journaliser


def _client_du_jeton(jeton):
    """Client du jeton JWT (même contrôle que l'API : jeton valide, compte actif, mot de passe pas changé depuis)."""
    from rest_framework.exceptions import AuthenticationFailed

    from apps.accounts.authentication import TokenAuthentication
    close_old_connections()
    try:
        auth = TokenAuthentication()
        user = auth.get_user(auth.get_validated_token(jeton))
        return getattr(user, "client", None) if user and user.is_active else None
    except (AuthenticationFailed, Exception):
        return None
    finally:
        close_old_connections()


def _hote_permis(hote):
    """Noms d'hôte du serveur AOCEDA en ligne (ALLOWED_HOSTS précis), en plus des adresses IP et de « localhost »."""
    nom = securite.nom_hote(hote)
    return bool(nom) and any(h != "*" and (nom == h.lower() or (h.startswith(".") and nom.endswith(h.lower())))
                             for h in settings.ALLOWED_HOSTS)


async def application(scope, receive, send):
    ws = WebSocket(scope, receive, send)
    jeton = (parse_qs(scope.get("query_string", b"").decode("latin-1")).get("token") or [""])[0]
    client = await sync_to_async(_client_du_jeton, thread_sensitive=False)(jeton) if jeton else None
    if client is None:
        await ws.close(code=4401)                      # pas de compte client : refus (la page invite à se reconnecter)
        return

    def session_permise(session):
        from .views import session_permise as permise
        return permise(client, session)

    await live_agent.servir(ws, journaliser, pont=DonneesClient(client), session_permise=session_permise,
                            hote_permis=_hote_permis)
