"""Ce que les tests du laboratoire lisaient dans son serveur FastAPI (chatbot/serveur.py), dans AOCEDA. Le serveur, ici,
c'est Django (apps/ai_assistant/views.py) : `app` n'est qu'un repère pour TestClient (client_test.py)."""
from apps.ai_assistant.chatbot import langues  # noqa: F401  (serveur.langues)
from apps.ai_assistant.chatbot.journal import JOURNAL  # noqa: F401

app = None
