import logging
import requests
from django.conf import settings  # pyrefly: ignore [untyped-import]
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from decouple import config
from .models import ConversationIA
from apps.analytics.tarifs_cie import prix_kwh_tout_compris

logger = logging.getLogger(__name__)

# Bornes de l'historique : envoyé au modèle / conservé en base.
MAX_HISTORIQUE_ENVOI = 20
MAX_HISTORIQUE_STOCKE = 40
LIMITE_QUOTIDIENNE = 10
MAX_LONGUEUR_MESSAGE = 2000


class AIChatView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_conversation(self, client):
        """Récupère la conversation du client et remet le quota à zéro si le jour a changé."""
        conversation, _created = ConversationIA.objects.get_or_create(client=client)
        if conversation.timestamp.date() < timezone.now().date():
            conversation.nb_requetes_aujourd_hui = 0
            conversation.save()
        return conversation

    def get(self, request):
        """Historique + quota du jour, SANS consommer de requête (chargement de la page)."""
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent clavarder avec l'assistant IA."}, status=status.HTTP_403_FORBIDDEN)
        conversation = self._get_conversation(user.client)
        return Response({
            "historique_messages": conversation.historique_messages,
            "nb_requetes_aujourd_hui": conversation.nb_requetes_aujourd_hui,
            "limite_quotidienne": LIMITE_QUOTIDIENNE,
        })

    def post(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent clavarder avec l'assistant IA."}, status=status.HTTP_403_FORBIDDEN)

        client = user.client
        user_message = (request.data.get('message') or '').strip()

        if not user_message:
            return Response({"detail": "Le message ne peut pas être vide."}, status=status.HTTP_400_BAD_REQUEST)
        if len(user_message) > MAX_LONGUEUR_MESSAGE:
            return Response({"detail": f"Message trop long (maximum {MAX_LONGUEUR_MESSAGE} caractères)."},
                            status=status.HTTP_400_BAD_REQUEST)

        # 1. Fetch or create conversation history (avec remise à zéro quotidienne)
        conversation = self._get_conversation(client)

        # 2. Check rate limit
        if conversation.nb_requetes_aujourd_hui >= LIMITE_QUOTIDIENNE:
            return Response({
                "detail": f"Limite quotidienne atteinte. Vous avez droit à {LIMITE_QUOTIDIENNE} requêtes par jour pour l'assistant IA."
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        # Tarif tout compris réel du client (cohérent avec ses factures CIE)
        prix_kwh = prix_kwh_tout_compris(client)
        # Contexte RÉEL du client (consommation, puissance, facture) — jamais inventé.
        ctx = self._contexte_client(client, prix_kwh)

        # 3. Append user message to history
        history = conversation.historique_messages
        history.append({"role": "user", "content": user_message})

        # 4. Attempt calling Grok / xAI API or fallback to localized energy saving response
        grok_key = config('GROK_API_KEY', default='').strip()
        grok_model = config('GROK_MODEL', default='grok-2-latest')  # grok-beta a été retiré par xAI
        response_text = ""
        mode = "fallback"  # 'ia' seulement si un vrai LLM a répondu

        if grok_key and not grok_key.startswith('your-xai'):
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {grok_key}"
                }

                # Instructions + DONNÉES RÉELLES du client (l'assistant « lit vos données »)
                system_instruction = (
                    "Tu es AOCEDA-GPT, un assistant IA expert en efficacité énergétique domestique en Côte d'Ivoire. "
                    "Aide l'utilisateur à réduire sa consommation d'énergie. "
                    "Données RÉELLES de ce client (utilise-les, ne les invente jamais) : "
                    f"consommation aujourd'hui {ctx['kwh_jour']} kWh ; "
                    f"puissance instantanée {ctx['puissance_w']} W ; "
                    f"facture mensuelle estimée {ctx['facture_fcfa']} FCFA ; "
                    f"{ctx['nb_capteurs']} capteur(s) installé(s) ; "
                    f"prix marginal du kWh (tranche 1 + taxes, TVA incluse) ≈ {prix_kwh} FCFA/kWh. "
                    "Donne des conseils précis sur les climatiseurs, réfrigérateurs, lampes LED, et l'usage nocturne. "
                    "Réponds en français, de manière concise et polie."
                )

                # On ne transmet que les derniers messages pour borner le coût/latence
                messages = [{"role": "system", "content": system_instruction}] + history[-MAX_HISTORIQUE_ENVOI:]

                payload = {"model": grok_model, "messages": messages, "temperature": 0.7}

                api_response = requests.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=10
                )

                if api_response.status_code == 200:
                    response_json = api_response.json()
                    response_text = response_json['choices'][0]['message']['content']
                    mode = "ia"
                else:
                    logger.warning("Grok API a renvoyé le statut %s", api_response.status_code)
                    response_text = self.get_fallback_response(user_message, prix_kwh, ctx)
            except Exception:
                logger.exception("Échec de l'appel à l'API Grok — repli sur l'assistant local")
                response_text = self.get_fallback_response(user_message, prix_kwh, ctx)
        else:
            # Pas de clé LLM configurée → conseils locaux (mode dégradé transparent).
            response_text = self.get_fallback_response(user_message, prix_kwh, ctx)

        # 5. Save history (borné) and increment count
        history.append({"role": "assistant", "content": response_text})
        conversation.historique_messages = history[-MAX_HISTORIQUE_STOCKE:]
        conversation.nb_requetes_aujourd_hui += 1
        conversation.save()

        return Response({
            "response": response_text,
            "mode": mode,  # 'ia' (vrai LLM) ou 'fallback' (conseils locaux) → l'UI le signale
            "nb_requetes_aujourd_hui": conversation.nb_requetes_aujourd_hui,
            "limite_quotidienne": LIMITE_QUOTIDIENNE
        })

    def _contexte_client(self, client, prix_kwh):
        """Contexte RÉEL du client (consommation/puissance/facture). Jamais fabriqué."""
        from datetime import timedelta
        from apps.sensors.models import Capteur, MesureEnergie
        from apps.analytics.views import _kwh_consommes, facture_mois_a_ce_jour
        now = timezone.now()
        debut_jour = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            kwh_jour = float(_kwh_consommes(client, debut_jour, now))
        except Exception:
            kwh_jour = 0.0
        frais = now - timedelta(seconds=60)
        puissance = 0.0
        for cap in Capteur.objects.filter(client=client, actif=True):
            m = (MesureEnergie.objects.filter(capteur=cap, timestamp__gte=frais)
                 .order_by('-timestamp').first())
            if m:
                puissance += float(m.puissance)
        try:
            facture = float(facture_mois_a_ce_jour(client)["detail"]["total_fcfa"])
        except Exception:
            facture = 0.0
        return {
            "kwh_jour": round(kwh_jour, 2),
            "puissance_w": int(puissance),
            "facture_fcfa": int(facture),
            "nb_capteurs": Capteur.objects.filter(client=client).count(),
            "prix_kwh": float(prix_kwh),
        }

    def get_fallback_response(self, user_message, prix_kwh=None, ctx=None):
        """
        Conseils locaux (mode dégradé, sans LLM) pour la Côte d'Ivoire.
        `prix_kwh` : prix marginal réel du client ; `ctx` : ses données réelles.
        Le champ `mode='fallback'` de la réponse permet à l'UI de signaler ce mode.
        """
        prix_txt = f"{prix_kwh} FCFA/kWh" if prix_kwh is not None else "le tarif CIE en vigueur"
        msg = user_message.lower()
        # Questions sur SA consommation → on répond avec ses VRAIES données (jamais inventées).
        conso_mots = ("consommation", "consomme", "combien", "aujourd", "facture",
                      "puissance", "ma conso", "je consomme", "depense", "dépense")
        if ctx and any(w in msg for w in conso_mots):
            return (
                "D'après vos capteurs AOCEDA :\n"
                f"• Consommation aujourd'hui : **{ctx['kwh_jour']} kWh**\n"
                f"• Puissance instantanée : **{ctx['puissance_w']} W**\n"
                f"• Facture mensuelle estimée : **{ctx['facture_fcfa']} FCFA** (grille CIE, TVA incluse)\n\n"
                "Pour réduire ce montant, ciblez d'abord vos plus gros postes (climatiseur, chauffe-eau) "
                "et surveillez la consommation nocturne. Demandez-moi des conseils précis sur un appareil."
            )
        if "tarif" in msg or "cie" in msg or "prix" in msg or "kwh" in msg:
            return (
                "En Côte d'Ivoire, votre facture suit la grille domestique de la Compagnie d'Électricité (CIE), "
                "découpée en tranches. Le prix de votre première tranche, **taxes et TVA 18 % incluses "
                "(hors prime fixe mensuelle)**, est d'environ "
                f"**{prix_txt}**. "
                "Surveiller votre puissance en temps réel permet de ne pas basculer dans la tranche supérieure, plus chère."
            )
        elif "climat" in msg or "clim" in msg or "temperature" in msg:
            return (
                "Le climatiseur est souvent le plus grand consommateur d'énergie en Côte d'Ivoire. Voici mes conseils :\n"
                "1. Réglez la température à **24°C** ou **25°C** ; descendre en dessous consomme 7% de plus par degré.\n"
                "2. Assurez-vous que les fenêtres et portes sont hermétiquement fermées.\n"
                "3. Nettoyez les filtres à air toutes les deux semaines pour maintenir l'efficacité de l'échangeur thermique."
            )
        elif "ampoule" in msg or "led" in msg or "eclairage" in msg or "lampe" in msg:
            return (
                "Remplacer vos anciennes ampoules incandescents ou fluorescentes par des **ampoules LED** permet d'économiser "
                "jusqu'à 85% d'électricité sur l'éclairage. Par exemple, une ampoule LED de 9W éclaire autant qu'une ampoule de 60W traditionnelle."
            )
        elif "nuit" in msg or "fantome" in msg or "veille" in msg:
            return (
                "La consommation nocturne fantôme correspond aux appareils laissés en veille (téléviseurs, décodeurs, multiprises, chargeurs). "
                "Pour les réduire :\n"
                "1. Utilisez des multiprises à interrupteur pour couper complètement l'alimentation des appareils la nuit.\n"
                "2. Configurez des alertes nocturnes sur AOCEDA pour être averti si une veille dépasse 50W entre minuit et 5h du matin."
            )
        else:
            return (
                "Bonjour ! Je suis AOCEDA-GPT, votre assistant d'économie d'énergie.\n\n"
                "Je peux vous aider à comprendre votre consommation, optimiser vos réglages et réduire vos factures "
                f"(votre prix tout compris est d'environ **{prix_txt}** selon la grille CIE).\n\n"
                "Posez-moi des questions sur vos climatiseurs, sur la veille nocturne, ou comment optimiser vos éclairages LED !"
            )
