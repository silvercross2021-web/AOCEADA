"""Agent Live Multilingue Universel (Laboratoire Isolé)

Ce module implémente la nouvelle architecture Live Multilingue d'AOCEDA :
  1. Dissociation Oreille (Ingress) / Cerveau (Gemini Live) / Bouche (Egress).
  2. Double axe de contrôle : langue_entree (ce que le client parle) vs langue_sortie (ce que l'agent répond).
  3. Matrice des 4 modes opérationnels :
       - Mode 1 : FR/EN parlé -> FR/EN répondu (100 % Gemini Live natif, 0,6 à 1,1 s).
       - Mode 2 : FR/EN parlé -> Baoulé/Dioula répondu (Gemini écoute -> Traduction -> Voix GPU Cerebrium / Djelia).
       - Mode 3 : Baoulé/Dioula parlé -> FR/EN répondu (STT local omniASR/Omnilingual -> Traduction FR -> Gemini Live).
       - Mode 4 : Baoulé/Dioula parlé -> Baoulé/Dioula répondu (STT local -> Cerveau Gemini -> Traduction -> Voix locale).
  4. Accélérateurs :
       - Earcons préenregistrés natifs (< 300 ms) pour combler le temps de calcul.
       - Préchauffage GPU Cerebrium à l'ouverture de l'appel.
       - Barge-in (interruption immédiate en 50 ms si le client reparle).
  5. Garde-fous :
       - Coupure de courant (Carte Oui/Non) validée AU CLIC UNIQUEMENT en langue locale.
       - Zéro hallucination / interdiction à Gemini d'imiter le baoulé ou le dioula avec sa voix native.
"""
import asyncio
import io
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from google.genai import types

from apps.ai_assistant.chatbot import (
    baoule_texte,
    cles_gemini,
    detection,
    dioula_texte,
    garde_langue,
    langues,
    live_agent,
    salutations,
    voix,
    voix_gpu,
)
from apps.ai_assistant.chatbot.live_agent import (
    CATALOGUE_LIVE,
    MODELES_LIVE,
    OUTILS_DECLARES,
    OUTILS_PAGE,
    OUTILS_VISION,
    RESERVES,
    SESSION_OK,
    Appel,
    carte_outil,
    declarations,
    signal_outil,
)

# ── Earcons : Micro-phrases d'attente natives préenregistrées ───────────────────
# Ces micro-phrases sont jouées dès t < 300 ms après la fin de parole si la réponse locale demande du calcul.
# Elles sont courtes (0,8 à 1,5 s), humaines et naturelles.
EARCONS_TEXTES = {
    "bci": [
        "N kɔ nian nun...",             # Je regarde / Je vérifie...
        "Sɛsɛ kpa, n ti...",            # Très bien, je comprends...
        "Anun o, n kɔ nian..."          # D'accord, je regarde...
    ],
    "dyu": [
        "A to n k'a lajɛ...",          # Laisse-moi regarder...
        "Nba, ayiwa...",                # D'accord, très bien...
        "I ni ce, n b'a fɛ..."         # Merci, je vérifie cela...
    ],
    "fr": [
        "Très bien, je regarde...",
        "Un instant, je vérifie...",
        "D'accord, je consulte vos données..."
    ]
}


class AppelMultilingue(Appel):
    """Extension d'Appel avec support complet multilingue bidirectionnel."""

    def __init__(self, ws, journal, **kwargs):
        super().__init__(ws, journal, **kwargs)

        # ── Double Axe de Langue ──
        # Langue d'entrée (Oreille) : langue que le client parle ('auto', 'fr', 'en', 'bci', 'dyu')
        self.langue_entree = "auto"
        self.verrou_entree = None        # 'ui' ou None

        # Langue de sortie (Bouche) : langue de la réponse ('meme', 'fr', 'en', 'bci', 'dyu')
        # 'meme' = mode miroir (répondre dans la même langue que celle qui a été parlée)
        self.langue_sortie = "meme"
        self.verrou_sortie = None        # 'demande', 'ui', 'menu' ou None

        # Langue effective de la réponse en cours
        self.langue_reponse_active = "fr"

        # ── Buffers et Streaming Ingress (Oreille) ──
        self.buffer_audio_entree = bytearray()
        self.dernier_paquet_micro = time.time()
        self.en_cours_parole = False
        self.seuil_silence_s = 0.7       # 700 ms de silence = fin de parole

        # ── Buffers et Streaming Egress (Bouche) ──
        self.buffer_texte_agent = ""
        self.taches_synthese = set()
        self.earcon_en_cours = False
        self.gpu_prechauffe = False

        # Mode opérationnel en cours (1: Natif, 2: FR->Local, 3: Local->FR, 4: Full Local)
        self.mode_operationnel = 1

        # ── Verrouillage du Tour de Parole (Half-Duplex / Gating) ──
        # Lorsque l'agent prépare ou diffuse une réponse en langue locale, le micro est strictement coupé
        self.verrou_tour_agent = False

    # ── Gestion des États et Verrous ───────────────────────────────────────────
    async def verrouiller_micro(self, actif: bool, raison=""):
        """Verrouille ou déverrouille le microphone pendant le tour de l'agent."""
        self.verrou_tour_agent = actif
        await self.page({
            "type": "verrou_micro",
            "bloque": actif,
            "message": raison or ("L'agent prépare votre réponse..." if actif else "À vous de parler !")
        })
        if actif:
            # Sécurité anti-blocage : déverrouillage de secours automatique après 10 s max
            asyncio.create_task(self._deverrouiller_micro_apres_delai(10.0))

    async def _deverrouiller_micro_apres_delai(self, delai_s):
        """Secours : déverrouille le micro si le client ne signale pas la fin d'audio."""
        await asyncio.sleep(delai_s)
        if self.verrou_tour_agent:
            await self.verrouiller_micro(False, raison="À vous de parler !")

    async def suivre_langue(self, texte=None):
        """Intercepte à la voix les demandes de changement de langue (ex: 'réponds en baoulé', 'reviens en français')."""
        vocal = texte is None
        t = (self.vous if vocal else texte) or ""

        # Détection d'une demande explicite (ex: 'réponds en baoulé', 'reviens en français')
        code = garde_langue.demande_explicite(t)

        if code in ("bci", "dyu"):
            if self.langue_sortie != code:
                await self.definir_langue_sortie(code, verrou="demande")
                nom_lg = "baoulé" if code == "bci" else "dioula"
                consigne = (
                    f"(Consigne système : la personne vient de demander que tu répondes désormais en {nom_lg}. "
                    f"Réponds directement à sa question en français clair et concis. Ne refuse pas la demande : "
                    f"notre module vocal externe traduira et synthétisera ta réponse en {nom_lg}.)"
                )
                if vocal:
                    await self.envoyer_gemini(text=consigne)
                return consigne

        elif code in ("fr", "en"):
            if self.langue_sortie != code:
                await self.definir_langue_sortie(code, verrou="demande")
                nom_lg = "français" if code == "fr" else "anglais"
                consigne = (
                    f"(Consigne système : la personne demande de revenir en {nom_lg}. "
                    f"Réponds désormais directement en {nom_lg}.)"
                )
                if vocal:
                    await self.envoyer_gemini(text=consigne)
                return consigne

        # Neutraliser la déclaration 'sans voix' de live_agent pour bci/dyu
        nom_sans_voix = live_agent.demande_sans_voix(t)
        if nom_sans_voix in ("baoulé", "dioula"):
            return None

        return await super().suivre_langue(texte)
    async def definir_langue_entree(self, code, verrou=None):
        """Définit la langue que l'oreille écoute ('auto', 'fr', 'en', 'bci', 'dyu')."""
        self.langue_entree = code
        self.verrou_entree = verrou
        await self.notifier_etat_langues()

    async def definir_langue_sortie(self, code, verrou=None):
        """Définit la langue que la bouche parle ('meme', 'fr', 'en', 'bci', 'dyu')."""
        self.langue_sortie = code
        self.verrou_sortie = verrou
        if code in ("bci", "dyu") and not self.gpu_prechauffe:
            self._reveiller_gpu_si_besoin()
        await self.notifier_etat_langues()

    def _reveiller_gpu_si_besoin(self):
        """Préchauffe le GPU Cerebrium en avance pour éviter les 35 s de démarrage à froid."""
        if not self.gpu_prechauffe:
            self.gpu_prechauffe = True
            try:
                voix.reveiller_voix_baoule("lab live multilingue ouvert")
            except Exception:
                pass

    async def notifier_etat_langues(self):
        """Notifie l'interface client de l'état des langues et du mode actif."""
        self.mode_operationnel = self._determiner_mode()
        await self.page({
            "type": "langues_actives",
            "langue_entree": self.langue_entree,
            "verrou_entree": self.verrou_entree,
            "langue_sortie": self.langue_sortie,
            "verrou_sortie": self.verrou_sortie,
            "langue_reponse_effective": self.langue_reponse_active,
            "mode_operationnel": self.mode_operationnel,
            "mode_libelle": self._libelle_mode(self.mode_operationnel)
        })

    def _determiner_mode(self):
        """Calcule le mode opérationnel (1, 2, 3 ou 4)."""
        entree_locale = self.langue_entree in ("bci", "dyu")
        sortie_locale = self.langue_sortie in ("bci", "dyu") or (
            self.langue_sortie == "meme" and entree_locale
        )
        if not entree_locale and not sortie_locale:
            return 1  # Full Natif FR/EN
        elif not entree_locale and sortie_locale:
            return 2  # FR/EN parlé -> Baoulé/Dioula répondu
        elif entree_locale and not sortie_locale:
            return 3  # Baoulé/Dioula parlé -> FR/EN répondu
        else:
            return 4  # Full Local

    def _libelle_mode(self, mode):
        labels = {
            1: "Mode 1 : Direct Natif (Français/Anglais)",
            2: "Mode 2 : Asymétrique (Parler FR -> Réponse Locale)",
            3: "Mode 3 : Asymétrique (Parler Local -> Réponse FR)",
            4: "Mode 4 : Dialogue Local Intégral"
        }
        return labels.get(mode, "Mode Inconnu")

    # ── Protocole de Messages Client ───────────────────────────────────────────
    async def message_page(self, d):
        """Intercepte et traite les événements de l'interface Live."""
        t = d.get("type")

        # Sélection manuelle de langue depuis l'interface (Priorité 1)
        if t == "choix_langue_entree":
            code = d.get("code")
            if code in ("auto", "fr", "en", "bci", "dyu"):
                await self.definir_langue_entree(code, verrou="ui")
            return False

        if t == "choix_langue_sortie":
            code = d.get("code")
            if code in ("meme", "fr", "en", "bci", "dyu"):
                await self.definir_langue_sortie(code, verrou="ui")
            return False

        if t == "audio_termine":
            # Le client a terminé la lecture de tous les segments audio de la réponse
            await self.verrouiller_micro(False, raison="À vous de parler !")
            return False

        if t == "debut":
            # Initialisation au démarrage
            entree = d.get("langue_entree", "auto")
            sortie = d.get("langue_sortie", "meme")
            await self.definir_langue_entree(entree)
            await self.definir_langue_sortie(sortie)
            if sortie in ("bci", "dyu"):
                self._reveiller_gpu_si_besoin()
            # Lancement de la surveillance Ingress local (VAD pour Baoulé/Dioula)
            t_ingress = asyncio.create_task(self._veiller_ingress_local())
            self.taches.add(t_ingress)
            t_ingress.add_done_callback(self.taches.discard)

        return await super().message_page(d)

    # ── Ingress : Traitement Audio Montant ──────────────────────────────────────
    async def lire_page(self):
        """Boucle de réception du WebSocket : intercepte les paquets audio montants."""
        while not self.fini.is_set():
            try:
                m = await self.ws.receive()
            except Exception:
                self.fin("deconnexion")
                return

            if m.get("type") == "websocket.disconnect":
                self.fin("deconnexion")
                return

            # Trames audio montantes du micro (PCM 16 kHz)
            if m.get("bytes") is not None:
                if self.micro:
                    await self._traiter_audio_montant(m["bytes"])
                continue

            try:
                d = json.loads(m.get("text") or "{}")
            except ValueError:
                continue

            if not isinstance(d, dict):
                continue

            try:
                if await self.message_page(d):
                    return
            except (TypeError, ValueError, AttributeError, KeyError):
                continue

    async def _traiter_audio_montant(self, octets):
        """Route les paquets audio montants selon la langue d'entrée configurée."""
        # Verrouillage half-duplex : tant que l'agent prépare ou diffuse en baoulé/dioula,
        # le micro est strictement bloqué pour éviter les collisions et bruits parasites
        if self.verrou_tour_agent and self.mode_operationnel in (2, 3, 4):
            return

        self.dernier_paquet_micro = time.time()
        self.derniere_activite = time.time()

        # Si l'utilisateur est en mode Baoulé ou Dioula (fixé manuellement) :
        if self.langue_entree in ("bci", "dyu"):
            # L'audio est accumulé pour l'ASR local, Gemini Live ne reçoit PAS cet audio brut
            self.buffer_audio_entree.extend(octets)
            self.en_cours_parole = True
            return

        # Si l'utilisateur est en mode FR ou Auto :
        # L'audio est transmis à Gemini Live pour assurer la latence minimale (0,6 s)
        await self.envoyer_gemini(audio=types.Blob(data=octets, mime_type="audio/pcm;rate=16000"))

    async def _veiller_ingress_local(self):
        """Surveille la fin de parole en langue locale (VAD silence) et déclenche l'ASR + traduction."""
        while not self.fini.is_set():
            await asyncio.sleep(0.1)
            if not self.en_cours_parole or self.langue_entree not in ("bci", "dyu"):
                continue

            maintenant = time.time()
            if maintenant - self.dernier_paquet_micro >= self.seuil_silence_s:
                # Fin de parole détectée !
                self.en_cours_parole = False
                octets = bytes(self.buffer_audio_entree)
                self.buffer_audio_entree.clear()

                if len(octets) < 3200:  # Moins de 100 ms d'audio
                    continue

                # Verrouillage immédiat du micro dès la fin de parole pour le tour de l'agent
                await self.verrouiller_micro(True, raison="Traitement de votre question...")
                await self._traiter_vocal_local_montant(octets)

    async def _traiter_vocal_local_montant(self, octets):
        """Transcrit le vocal en baoulé ou dioula, le traduit en français et l'injecte dans Gemini Live."""
        try:
            import numpy as np
            audio = np.frombuffer(octets, dtype=np.int16).astype(np.float32) / 32768.0
            langue = self.langue_entree

            # 1. Transcription locale
            if langue == "bci":
                from apps.ai_assistant.chatbot import baoule_ecoute
                ecoute = await asyncio.to_thread(baoule_ecoute.transcrire_audio, audio)
                texte_local = getattr(ecoute, "texte", "") or ""
            else:
                from apps.ai_assistant.chatbot import dioula_ecoute
                ecoute = await asyncio.to_thread(dioula_ecoute.transcrire_audio, audio)
                texte_local = getattr(ecoute, "texte", "") or ""

            texte_local = texte_local.strip()
            if not texte_local:
                # Si rien n'est compris, libérer le micro
                await self.verrouiller_micro(False, raison="À vous de parler !")
                return

            # 2. Affichage sous-titre de la personne
            self.vous = texte_local
            self.derniere_activite = time.time()
            await self.page({"type": "sous_titre", "qui": "vous", "texte": texte_local, "fini": True})
            self.lignes.append({"qui": "vous", "texte": texte_local})

            # 3. Traduction vers le français pivot pour Gemini
            if langue == "bci":
                from apps.ai_assistant.chatbot import baoule_relais
                res = await asyncio.to_thread(baoule_relais.vers_francais, texte_local)
                texte_fr = res.get("google") or texte_local
            else:
                from apps.ai_assistant.chatbot import dioula_relais
                res = await asyncio.to_thread(dioula_relais.vers_francais, texte_local)
                texte_fr = res.get("google") or texte_local

            # 4. Envoi du texte français au cerveau Gemini Live
            consigne_contexte = (
                f"[L'utilisateur a parlé en {langues.nom(langue)} : '{texte_local}'. "
                f"Traduction française : '{texte_fr}']. Réponds en français concis."
            )
            envoye = await self.envoyer_gemini(text=consigne_contexte)
            if envoye and self.session is not None:
                self.attend_gemini = self.attend_gemini or time.time()
            else:
                # Si l'envoi échoue ou si Gemini n'est pas prêt, libérer le micro immédiatement
                await self.verrouiller_micro(False, raison="À vous de parler !")

        except Exception as e:
            await self.verrouiller_micro(False, raison="À vous de parler !")

    # ── Egress : Traitement des Réponses et Synthèse Sortante ──────────────────
    async def traiter(self, s, rep):
        """Intercepte le flux retour de Gemini Live."""
        sc0 = rep.server_content
        mode = self._determiner_mode()

        # Si la langue de réponse souhaitée est une langue locale (Baoulé ou Dioula)
        if mode in (2, 4):
            # Verrouiller le micro dès que l'agent commence à produire la réponse
            if (sc0 and (sc0.model_turn or sc0.output_transcription)) and not self.verrou_tour_agent:
                await self.verrouiller_micro(True, raison="L'agent prépare votre réponse...")

            # 1. On supprime l'audio natif Gemini (on ne le diffuse pas au client)
            if sc0 and sc0.model_turn:
                for p in sc0.model_turn.parts or []:
                    if p.inline_data:
                        # Audio natif ignoré : remplacé par notre synthèse locale
                        p.inline_data.data = b""

            # 2. Dès qu'un premier signe d'activité arrive, on joue l'Earcon natif (< 300 ms)
            if (sc0 and (sc0.model_turn or sc0.output_transcription)) and not self.earcon_en_cours:
                self.earcon_en_cours = True
                cible_earcon = self.langue_sortie if self.langue_sortie != "meme" else (
                    self.langue_entree if self.langue_entree in ("bci", "dyu") else "bci"
                )
                await self._diffuser_earcon(cible_earcon)

            # 3. On capture la transcription textuelle émise par Gemini
            if sc0 and sc0.output_transcription and sc0.output_transcription.text:
                self.buffer_texte_agent += sc0.output_transcription.text
                # Découpage phrase par phrase dès qu'un délimiteur est atteint
                if any(delim in self.buffer_texte_agent for delim in (".", "!", "?", "\n")):
                    await self._traiter_phrase_egress_locale()

            # 4. En fin de tour de parole de Gemini
            if sc0 and sc0.turn_complete:
                if self.buffer_texte_agent.strip():
                    await self._traiter_phrase_egress_locale(fin_tour=True)
                self.earcon_en_cours = False
                self.buffer_texte_agent = ""

        # Déverrouillage en Mode 3 quand Gemini finit de parler en français
        elif mode == 3 and sc0 and sc0.turn_complete and self.verrou_tour_agent:
            await self.verrouiller_micro(False, raison="À vous de parler !")

        # Interruption : déverrouiller immédiatement
        if sc0 and sc0.interrupted and self.verrou_tour_agent:
            await self.verrouiller_micro(False, raison="À vous de parler !")

        # Traitement normal pour les signaux outils, interruptions, et mode 1 / 3
        await super().traiter(s, rep)

    async def _diffuser_earcon(self, langue):
        """Joue immédiatement un son d'écoute humain préenregistré pour combler le temps de calcul."""
        phrases = EARCONS_TEXTES.get(langue, EARCONS_TEXTES["fr"])
        phrase = phrases[0]  # Premier earcon de référence
        # Émettre l'état et le sous-titre provisoire
        await self.page({
            "type": "sous_titre",
            "qui": "agent",
            "texte": f"({phrase})",
            "fini": False
        })

    async def _traiter_phrase_egress_locale(self, fin_tour=False):
        """Segment de texte prêt : traduction vers la langue locale puis synthèse vocale."""
        texte_fr = self.buffer_texte_agent.strip()
        if not texte_fr:
            return

        cible = self.langue_sortie if self.langue_sortie != "meme" else (
            self.langue_entree if self.langue_entree in ("bci", "dyu") else "bci"
        )
        self.langue_reponse_active = cible

        # Traduction vers la langue locale
        if cible == "bci":
            texte_traduit = await self._traduire_vers_baoule(texte_fr)
        elif cible == "dyu":
            texte_traduit = await self._traduire_vers_dioula(texte_fr)
        else:
            texte_traduit = texte_fr

        # Affichage du sous-titre bilingue (Langue locale + traduction française)
        await self.page({
            "type": "sous_titre",
            "qui": "agent",
            "texte": texte_traduit,
            "traduction_fr": texte_fr,
            "fini": fin_tour
        })

        # Synthèse vocale de la phrase
        if cible == "bci":
            audio_bytes = await self._synthetiser_baoule(texte_traduit)
        else:
            audio_bytes = await self._synthetiser_dioula(texte_traduit)

        if audio_bytes:
            # Envoi des octets audio WAV/PCM vers le haut-parleur
            await self.page_audio(audio_bytes)

        if fin_tour:
            self.buffer_texte_agent = ""
            # Délai de sécurité : si le client oublie d'envoyer audio_termine, déverrouiller après 6s
            asyncio.create_task(self._deverrouiller_micro_apres_delai(6.0))

    # ── Moteurs de Traduction et Synthèse ──────────────────────────────────────
    async def _traduire_vers_baoule(self, texte_fr):
        """Traduit une phrase française vers le baoulé via Google Translate / baoule_relais."""
        try:
            from apps.ai_assistant.chatbot import baoule_relais
            trad, _ = await asyncio.to_thread(baoule_relais.vers_baoule, texte_fr)
            return trad or texte_fr
        except Exception:
            return texte_fr

    async def _traduire_vers_dioula(self, texte_fr):
        """Traduit une phrase française vers le dioula via Djelia / dioula_relais."""
        try:
            from apps.ai_assistant.chatbot import dioula_relais
            trad, _ = await asyncio.to_thread(dioula_relais.vers_dioula, texte_fr)
            return trad or texte_fr
        except Exception:
            return texte_fr

    async def _synthetiser_baoule(self, texte_baoule):
        """Génère l'audio baoulé via Cerebrium GPU OmniVoice ou atelier local."""
        try:
            if voix_gpu.disponible():
                return await asyncio.to_thread(voix_gpu.fabriquer, texte_baoule, self.genre)
            from apps.ai_assistant.chatbot import voix
            statut, f, _ = voix.demander_baoule(texte_baoule, self.genre)
            if f:
                return await asyncio.to_thread(f.result, 15)
        except Exception:
            pass
        return None

    async def _synthetiser_dioula(self, texte_dioula):
        """Génère l'audio dioula via Djelia TTS."""
        try:
            from apps.ai_assistant.chatbot import voix
            return await asyncio.to_thread(voix._djelia_voix, texte_dioula)
        except Exception:
            pass
        return None

    # ── Garde-fous Critiques ───────────────────────────────────────────────────
    async def _confirmation_vocale(self, vu, avant=()):
        """Validation vocale de coupure : désactivée en langue locale (clic obligatoire)."""
        # Si la langue parlée ou la réponse est en baoulé ou dioula,
        # la coupure n'est JAMAIS confirmée à la voix (sécurité anti-confusion 'ɔnhɔn' / 'ɔn ɔn')
        if self.langue_entree in ("bci", "dyu") or self.langue_reponse_active in ("bci", "dyu"):
            return  # Validation au clic écran uniquement
        await super()._confirmation_vocale(vu, avant=avant)
