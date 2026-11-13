"""Serveur Autonome du Laboratoire Live Multilingue (Port 8775).

Ce serveur fait tourner le banc d'essai isolé pour le mode Live multilingue (Baoulé, Dioula, Français, Anglais).
Il ne modifie aucun fichier de production d'AOCEDA et fonctionne en parallèle sur son propre port.

Usage :
    cd AOCEDA
    .venv_local\\Scripts\\python.exe lab_live\\serveur_lab.py
    (ou python lab_live/serveur_lab.py)

Accès :
    http://127.0.0.1:8775/
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# ── 1. Initialisation Django pour le Laboratoire ──────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aoceda.settings")

import django
django.setup()

from aiohttp import web, WSMsgType
from django.db import close_old_connections

from apps.accounts.models import Client
from apps.ai_assistant.chatbot.donnees_client import DonneesClient
from apps.ai_assistant.chatbot.journal import journaliser
from lab_live.live_agent_multilingue import AppelMultilingue

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("lab_live")

DOSSIER_STATIC = Path(__file__).resolve().parent / "static"


# ── 2. Adaptateur WebSocket aiohttp -> Interface Starlette / Channels ─────────
class AdaptateurWsAiohttp:
    """Adapte le WebSocket d'aiohttp pour fournir l'API attendue par AppelMultilingue."""

    def __init__(self, ws: web.WebSocketResponse, request: web.Request):
        self._ws = ws
        self.request = request
        self.headers = dict(request.headers)
        self.client = type("ClientAddr", (), {"host": request.remote or "127.0.0.1"})()

    async def accept(self):
        """Déjà accepté lors du ws.prepare(request)."""
        pass

    async def send_text(self, data: str):
        if not self._ws.closed:
            await self._ws.send_str(data)

    async def send_bytes(self, data: bytes):
        if not self._ws.closed:
            await self._ws.send_bytes(data)

    async def close(self, code: int = 1000):
        if not self._ws.closed:
            await self._ws.close(code=code)

    async def receive_text(self) -> str:
        msg = await self._ws.receive()
        if msg.type == WSMsgType.TEXT:
            return msg.data
        elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
            raise ConnectionResetError("WebSocket fermé par le client")
        elif msg.type == WSMsgType.ERROR:
            raise ConnectionError(str(self._ws.exception()))
        return ""

    async def receive(self) -> dict:
        msg = await self._ws.receive()
        if msg.type == WSMsgType.TEXT:
            return {"type": "websocket.receive", "text": msg.data, "bytes": None}
        elif msg.type == WSMsgType.BINARY:
            return {"type": "websocket.receive", "bytes": msg.data, "text": None}
        elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
            return {"type": "websocket.disconnect", "code": msg.data}
        elif msg.type == WSMsgType.ERROR:
            return {"type": "websocket.disconnect", "code": 1006}
        return {"type": "websocket.receive", "text": None, "bytes": None}


# ── 3. Gestionnaires HTTP et WebSocket ─────────────────────────────────────────
async def handle_index(request: web.Request) -> web.Response:
    """Sert l'interface de test du laboratoire."""
    index_file = DOSSIER_STATIC / "index.html"
    if not index_file.exists():
        return web.Response(text="Erreur : index.html introuvable dans lab_live/static", status=404)
    return web.FileResponse(index_file)


async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    """Gère la connexion WebSocket de l'appel Live."""
    ws = web.WebSocketResponse(heartbeat=15.0)
    await ws.prepare(request)
    logger.info(f"Nouvelle connexion Live depuis {request.remote}")

    # Récupération d'un client pour brancher les vrais outils de lecture de données
    await asyncio.to_thread(close_old_connections)
    client = await asyncio.to_thread(lambda: Client.objects.first())
    pont = DonneesClient(client) if client else None

    adaptateur = AdaptateurWsAiohttp(ws, request)
    adresse_session = f"{request.remote or '127.0.0.1'}_{id(ws)}"
    appel = AppelMultilingue(
        ws=adaptateur,
        journal=journaliser,
        pont=pont,
        version=None,  # Pas de vérification d'empreinte en lab
        adresse=adresse_session
    )

    try:
        await appel.servir()
    except Exception as e:
        logger.error(f"Erreur pendant l'appel Live : {e}", exc_info=True)
    finally:
        logger.info(f"Fin de session Live pour {request.remote}")
        if not ws.closed:
            await ws.close()

    return ws


# ── 4. Démarrage de l'Application ─────────────────────────────────────────────
def creer_application() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/ws", handle_ws)
    app.router.add_static("/static/", DOSSIER_STATIC, name="static")
    return app


def main():
    port = 8775
    app = creer_application()
    print("=" * 72)
    print("   AOCEDA · Laboratoire Live Multilingue Universel")
    print("   Architecture : Oreille (Ingress) / Cerveau (Gemini) / Bouche (Egress)")
    print("-" * 72)
    print(f"   Serveur démarré sur : http://127.0.0.1:{port}/")
    print("   Matrice des modes testables :")
    print("     - Mode 1 : FR / EN direct natif (Gemini Live)")
    print("     - Mode 2 : Parler FR -> Réponse Baoulé / Dioula (Traduction + Voix GPU)")
    print("     - Mode 3 : Parler Baoulé / Dioula -> Réponse FR (ASR local + Traduction)")
    print("     - Mode 4 : Dialogue Baoulé / Dioula intégral")
    print("=" * 72)
    web.run_app(app, host="127.0.0.1", port=port, print=None)


if __name__ == "__main__":
    main()
