"""Tests Automatisés du Laboratoire Isolé Live Multilingue

Vérifie l'intégrité de la nouvelle architecture :
  - Détermination et transition des 4 modes opérationnels.
  - Double verrouillage (langue d'entrée vs langue de sortie).
  - Suppression de l'audio natif Gemini quand la sortie est locale.
  - Déclenchement des Earcons d'attente.
  - Garde-fou de coupure électrique (validation au clic obligatoire en baoulé/dioula).
"""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aoceda.settings")
import django
django.setup()

from lab_live.live_agent_multilingue import EARCONS_TEXTES, AppelMultilingue


class FakeWebSocket:
    def __init__(self):
        self.sent_texts = []
        self.sent_bytes = []
        self.closed = False

    async def send_text(self, t):
        self.sent_texts.append(t)

    async def send_bytes(self, b):
        self.sent_bytes.append(b)

    async def close(self, code=1000):
        self.closed = True


class TestLiveMultilingue(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.ws = FakeWebSocket()
        self.journaliser = MagicMock()
        self.agent = AppelMultilingue(self.ws, self.journaliser)

    async def test_initialisation_double_verrou(self):
        """Au démarrage, langue d'entrée est 'auto' et langue de sortie est 'meme' (Mode 1)."""
        self.assertEqual(self.agent.langue_entree, "auto")
        self.assertEqual(self.agent.langue_sortie, "meme")
        self.assertIsNone(self.agent.verrou_entree)
        self.assertIsNone(self.agent.verrou_sortie)
        self.assertEqual(self.agent._determiner_mode(), 1)

    async def test_matrice_des_4_modes_operationnels(self):
        """Vérifie le calcul rigoureux des 4 modes opérationnels."""
        # Mode 1 : FR parlé -> FR répondu
        self.agent.langue_entree = "fr"
        self.agent.langue_sortie = "fr"
        self.assertEqual(self.agent._determiner_mode(), 1)

        # Mode 2 : FR parlé -> Baoulé répondu
        self.agent.langue_entree = "fr"
        self.agent.langue_sortie = "bci"
        self.assertEqual(self.agent._determiner_mode(), 2)

        # Mode 2 : Anglais parlé -> Dioula répondu
        self.agent.langue_entree = "en"
        self.agent.langue_sortie = "dyu"
        self.assertEqual(self.agent._determiner_mode(), 2)

        # Mode 3 : Baoulé parlé -> Français répondu
        self.agent.langue_entree = "bci"
        self.agent.langue_sortie = "fr"
        self.assertEqual(self.agent._determiner_mode(), 3)

        # Mode 4 : Baoulé parlé -> Baoulé répondu
        self.agent.langue_entree = "bci"
        self.agent.langue_sortie = "bci"
        self.assertEqual(self.agent._determiner_mode(), 4)

        # Mode 4 : Dioula parlé -> Mode miroir (répondre dans la même langue)
        self.agent.langue_entree = "dyu"
        self.agent.langue_sortie = "meme"
        self.assertEqual(self.agent._determiner_mode(), 4)

    async def test_changement_langue_ui_declenche_prechauffage_gpu(self):
        """Sélectionner le Baoulé en sortie déclenche le réveil anticipé du GPU Cerebrium."""
        with patch("apps.ai_assistant.chatbot.voix.reveiller_voix_baoule") as mock_gpu:
            await self.agent.definir_langue_sortie("bci", verrou="ui")
            self.assertEqual(self.agent.langue_sortie, "bci")
            self.assertEqual(self.agent.verrou_sortie, "ui")
            self.assertTrue(self.agent.gpu_prechauffe)
            mock_gpu.assert_called_once()

    async def test_garde_fou_coupure_desactive_en_langue_locale(self):
        """En baoulé ou dioula, la confirmation vocale de coupure est formellement bloquée."""
        from apps.ai_assistant.chatbot.live_agent import Appel
        with patch.object(Appel, "_confirmation_vocale") as mock_super:
            # En Baoulé
            self.agent.langue_entree = "bci"
            await self.agent._confirmation_vocale("oui", avant=())
            # La confirmation de base ne doit PAS être appelée
            mock_super.assert_not_called()

    async def test_presence_earcons_natifs(self):
        """Les earcons de chaque langue locale sont disponibles et non vides."""
        self.assertIn("bci", EARCONS_TEXTES)
        self.assertIn("dyu", EARCONS_TEXTES)
        self.assertIn("fr", EARCONS_TEXTES)
        self.assertTrue(len(EARCONS_TEXTES["bci"]) >= 2)
        self.assertTrue(len(EARCONS_TEXTES["dyu"]) >= 2)
        # Vérifie que les phrases baoulé contiennent du vrai baoulé
        self.assertTrue(any("nian" in e for e in EARCONS_TEXTES["bci"]))

    async def test_suppression_audio_natif_en_mode_local(self):
        """En mode 2 (sortie locale), les paquets audio de Gemini sont neutralisés."""
        self.agent.langue_sortie = "bci"
        self.assertEqual(self.agent._determiner_mode(), 2)

        # Simuler une réponse de Gemini contenant de l'audio natif
        partie_audio = MagicMock()
        partie_audio.inline_data.data = b"FAUX_AUDIO_GEMINI_A_IGNORER"
        rep = MagicMock()
        rep.usage_metadata = None
        rep.tool_call = None
        rep.session_resumption_update = None
        rep.go_away = None
        rep.server_content.model_turn.parts = [partie_audio]
        rep.server_content.output_transcription.text = "Votre consommation est de 45 kWh."
        rep.server_content.input_transcription = None
        rep.server_content.interrupted = None
        rep.server_content.turn_complete = False

        with patch.object(self.agent, "_diffuser_earcon", new_callable=AsyncMock) as mock_earcon, \
             patch.object(self.agent, "_traduire_vers_baoule", new_callable=AsyncMock, return_value="O kɔnɔman...") as mock_trad, \
             patch.object(self.agent, "_synthetiser_baoule", new_callable=AsyncMock, return_value=b"FAUX_AUDIO_BAOULE") as mock_synth:
            # On lance traiter
            await self.agent.traiter(None, rep)
            # L'audio natif Gemini doit avoir été vidé
            self.assertEqual(partie_audio.inline_data.data, b"")
            # L'earcon doit avoir été déclenché
            mock_earcon.assert_called_once()

    async def test_ingress_local_vad_et_transcription(self):
        """En entrée locale (Mode 3/4), l'audio montant est transcrit localement puis traduit en français pour Gemini."""
        self.agent.langue_entree = "bci"
        # 1. Simuler l'arrivée de trames audio micro (3200 octets = 100 ms)
        trame = b"\x00\x01" * 1600
        await self.agent._traiter_audio_montant(trame)
        self.assertEqual(len(self.agent.buffer_audio_entree), 3200)
        self.assertTrue(self.agent.en_cours_parole)

        # 2. Simuler le traitement du vocal montant
        mock_ecoute = MagicMock()
        mock_ecoute.texte = "N kulo kpa"

        with patch("apps.ai_assistant.chatbot.baoule_ecoute.transcrire_audio", return_value=mock_ecoute), \
             patch("apps.ai_assistant.chatbot.baoule_relais.vers_francais", return_value={"google": "Je veux savoir"}), \
             patch.object(self.agent, "envoyer_gemini", new_callable=AsyncMock, return_value=True) as mock_gemini:

            await self.agent._traiter_vocal_local_montant(trame)

            # Le sous-titre de la personne doit afficher le texte baoulé
            self.assertEqual(self.agent.vous, "N kulo kpa")
            # Gemini Live doit avoir reçu la traduction française
            mock_gemini.assert_called_once()
            consigne_envoyee = mock_gemini.call_args.kwargs["text"]
            self.assertIn("Je veux savoir", consigne_envoyee)
            self.assertIn("N kulo kpa", consigne_envoyee)

    async def test_verrouillage_micro_half_duplex(self):
        """Vérifie le verrouillage du micro pendant le tour de l'agent et sa libération à fin audio."""
        self.agent.mode_operationnel = 2
        # 1. Verrouiller le micro
        await self.agent.verrouiller_micro(True, raison="L'agent prépare votre réponse...")
        self.assertTrue(self.agent.verrou_tour_agent)

        # 2. Vérifier que tout audio montant est rejeté
        audio_test = b"\x00\x01" * 100
        taille_avant = len(self.agent.buffer_audio_entree)
        await self.agent._traiter_audio_montant(audio_test)
        self.assertEqual(len(self.agent.buffer_audio_entree), taille_avant)

        # 3. Réception de 'audio_termine' depuis le client déverrouille le micro
        await self.agent.message_page({"type": "audio_termine"})
        self.assertFalse(self.agent.verrou_tour_agent)

    async def test_changement_langue_sortie_vocale_et_ui(self):
        """Vérifie la bascule dynamique de la langue de sortie à la voix et au clic bouton."""
        # 1. Changement par intention vocale (« réponds-moi en baoulé »)
        self.agent.vous = "donne ma consommation et réponds-moi en baoulé"
        await self.agent.suivre_langue()
        self.assertEqual(self.agent.langue_sortie, "bci")
        self.assertEqual(self.agent.verrou_sortie, "demande")

        # 2. Changement par bouton UI rapide (Dioula)
        await self.agent.message_page({"type": "choix_langue_sortie", "code": "dyu"})
        self.assertEqual(self.agent.langue_sortie, "dyu")
        self.assertEqual(self.agent.verrou_sortie, "ui")


if __name__ == "__main__":
    unittest.main()
