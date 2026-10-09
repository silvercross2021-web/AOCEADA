import json
import logging
from django.conf import settings  # pyrefly: ignore [untyped-import]
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework import status, permissions, generics
from .models import QuotaIA, Conversation
from .serializers import ConversationSerializer, ConversationListSerializer
from .outils import OUTILS_SPEC, executer_outil, label_outil
from .fournisseurs_llm import (
    AdaptateurOpenAICompatible, ErreurAppelLLM, NOMS_AFFICHABLES,
    construire_adaptateur, detecter_fournisseur,
)
from apps.analytics.tarifs_cie import prix_kwh_tout_compris

logger = logging.getLogger(__name__)

# Bornes de l'historique reçu du client pour construire le contexte d'UN appel LLM
# (le fil complet est désormais persisté via Conversation/ConversationDetailView,
# synchronisé entre appareils — voir static/js/ia.js).
MAX_HISTORIQUE_ENVOI = 20
MAX_LONGUEUR_MESSAGE = 2000
# Un message d'historique n'est PAS re-borné à 2000 (une réponse d'assistant peut être
# plus longue), mais il est tronqué au-delà de cette taille : sans borne, 20 messages
# arbitraires feraient exploser le coût en tokens de chaque appel.
MAX_LONGUEUR_MESSAGE_HISTORIQUE = 4000
# Boucle « function calling » : nombre max d'appels LLM par question (le dernier tour
# force une réponse texte), et nombre max d'outils exécutés par tour.
MAX_ITERATIONS_OUTILS = 4
MAX_APPELS_OUTILS_PAR_TOUR = 5
# Labels neutres UNIQUEMENT — jamais le nom réel du fournisseur (DeepSeek/xAI/...), et jamais
# un faux nom de produit concurrent présenté comme le vrai système utilisé.
MODELES = {
    "standard": "Assistant standard",
    "personnel": "Assistant personnel",
}

JOURS_FR = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

# Filet de sécurité pour la langue forcée (voir _corriger_langue_si_besoin) : mots-outils
# très fréquents et quasi exclusifs à chaque langue, utilisés pour un diagnostic
# GROSSIER après coup — jamais une vraie détection de langue (inutile ici : on ne
# distingue que français/anglais, et seulement pour repérer un décalage flagrant).
_MARQUEURS_FR = (' le ', ' la ', ' les ', ' des ', ' du ', ' vous ', ' votre ', ' est ',
                  ' une ', ' pour ', ' avec ', ' que ', ' dans ', ' sur ', ' cette ', ' ce ')
_MARQUEURS_EN = (' the ', ' is ', ' are ', ' your ', ' you ', ' this ', ' for ', ' with ',
                  ' that ', ' have ', ' has ', ' and ', ' of ', ' to ', ' in ', ' on ')


def _langue_detectee(texte):
    """Heuristique légère (comptage de mots-outils) pour repérer un décalage GROSSIER
    de langue dans une réponse — pas une vraie détection linguistique, juste un signal
    suffisant pour savoir s'il faut déclencher une correction (voir
    _corriger_langue_si_besoin). Renvoie 'fr', 'en', ou None si le signal est trop
    faible pour trancher (réponse très courte, surtout numérique, etc. — dans le
    doute, ne JAMAIS déclencher de correction inutile)."""
    t = f' {texte.lower()} '
    fr = sum(t.count(m) for m in _MARQUEURS_FR)
    en = sum(t.count(m) for m in _MARQUEURS_EN)
    if fr == 0 and en == 0:
        return None
    return 'fr' if fr >= en else 'en'


class AIChatView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_quota(self, client):
        """Quota/tokens PAR CLIENT. Remet le quota à zéro si le jour a changé."""
        quota, _created = QuotaIA.objects.get_or_create(client=client)
        if quota.derniere_maj.date() < timezone.now().date():
            quota.nb_requetes_aujourd_hui = 0
            quota.save()
        return quota

    def get(self, request):
        """Quota du jour + modèles disponibles, SANS consommer de requête (chargement de
        la page). Le contenu des conversations est servi séparément par
        ConversationListCreateView/ConversationDetailView (synchronisé entre appareils)."""
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent clavarder avec l'assistant IA."}, status=status.HTTP_403_FORBIDDEN)
        client = user.client
        quota = self._get_quota(client)

        cle_perso = (getattr(client, 'cle_api_ia_personnelle', '') or '').strip()
        url_perso = (getattr(client, 'url_api_ia_personnelle', '') or '').strip()
        fournisseur_perso = detecter_fournisseur(cle_perso, url_perso) if cle_perso else None
        return Response({
            "nb_requetes_aujourd_hui": quota.nb_requetes_aujourd_hui,
            # None = illimité (settings.AI_DAILY_LIMIT <= 0) ; le frontend distingue
            # ce cas de "limite = 0" pour ne pas afficher un quota déjà épuisé.
            "limite_quotidienne": settings.AI_DAILY_LIMIT if settings.AI_DAILY_LIMIT > 0 else None,
            # Jours de rétention avant purge (indicatif — aucune purge automatique
            # côté serveur pour l'instant ; les fils persistent tant qu'ils ne sont
            # pas supprimés explicitement via ConversationDetailView).
            "retention_jours": getattr(settings, 'AI_HISTORIQUE_RETENTION_JOURS', 7),
            "modeles": [
                {"id": "standard", "nom": MODELES["standard"], "disponible": True},
                {"id": "personnel", "nom": MODELES["personnel"], "disponible": bool(fournisseur_perso)},
            ],
            # Informatif UNIQUEMENT pour la clé PERSO du client (jamais pour 'standard' —
            # voir RÈGLE D'IDENTITÉ dans _construire_system_instruction) : lui permet de
            # confirmer que sa propre clé a bien été reconnue, sans deviner en silence.
            "fournisseur_personnel": NOMS_AFFICHABLES.get(fournisseur_perso) if fournisseur_perso else None,
        })

    def post(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent clavarder avec l'assistant IA."}, status=status.HTTP_403_FORBIDDEN)

        client = user.client
        user_message = (request.data.get('message') or '').strip()
        # Seul signal de langue disponible pour le mode dégradé SANS LLM (le vrai LLM détecte
        # la langue directement dans le message, voir _construire_system_instruction).
        lang = (request.data.get('lang') or '').strip().lower()
        if lang not in ('fr', 'en'):
            lang = 'fr'
        # Langue de RÉPONSE choisie explicitement par le client (bouton dédié « langue de
        # réponse », indépendant de la langue de saisie/dictée — voir static/js/ia.js) :
        # force la langue réelle de la réponse du LLM, prioritaire sur sa détection
        # automatique. None si absent/invalide → comportement d'origine (détection seule).
        lang_sortie = (request.data.get('lang_sortie') or '').strip().lower()
        if lang_sortie not in ('fr', 'en', 'dioula'):
            lang_sortie = None
        # Historique du fil ACTIF (fourni par le client, lu depuis Conversation via
        # ConversationDetailView côté frontend) — VALIDÉ avant d'entrer dans le contexte
        # LLM : rôles user/assistant seulement (jamais 'system' → pas d'injection de
        # consignes), contenus bornés (pas d'explosion de tokens).
        history = self._valider_history(request.data.get('history'))
        provider = (request.data.get('provider') or 'standard').strip().lower()
        if provider not in MODELES:
            provider = 'standard'

        if not user_message:
            return Response({"detail": "Le message ne peut pas être vide."}, status=status.HTTP_400_BAD_REQUEST)
        if len(user_message) > MAX_LONGUEUR_MESSAGE:
            return Response({"detail": f"Message trop long (maximum {MAX_LONGUEUR_MESSAGE} caractères)."},
                            status=status.HTTP_400_BAD_REQUEST)

        # 1. Quota (remis à zéro si le jour a changé)
        quota = self._get_quota(client)

        # 2. Check rate limit — seulement si une limite est activée (voir settings.AI_DAILY_LIMIT).
        limite = settings.AI_DAILY_LIMIT
        if limite > 0 and quota.nb_requetes_aujourd_hui >= limite:
            return Response({
                "detail": f"Limite quotidienne atteinte. Vous avez droit à {limite} requêtes par jour pour l'assistant IA."
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        # Tarif tout compris réel du client (cohérent avec ses factures CIE)
        prix_kwh = prix_kwh_tout_compris(client)
        # Résumé LÉGER du jour (jamais inventé) : l'essentiel pour les questions simples ;
        # tout le reste est lu À LA DEMANDE par le LLM via les outils (outils.py).
        ctx = self._snapshot_client(client, prix_kwh)

        # 3. Boucle LLM + outils (fournisseur choisi par le client via sa clé perso,
        #    ou fournisseur partagé du projet), ou repli local honnête.
        adaptateur, fournisseur = self._resoudre_adaptateur(client, provider)
        response_text = ""
        mode = "fallback"  # 'ia' seulement si un vrai LLM a répondu
        outils_utilises = []
        tokens_in = tokens_out = 0

        if adaptateur is not None:
            try:
                system_instruction = self._construire_system_instruction(ctx, prix_kwh, lang_sortie)
                # Historique validé + le nouveau message (system passé séparément —
                # voir _boucle_llm). Rappel de langue collé au message lui-même (voir
                # _rappel_langue_reponse) : la règle du system prompt seule ne suffit
                # pas à contrer un historique déjà écrit dans une autre langue.
                messages = history + [{"role": "user", "content": user_message + self._rappel_langue_reponse(lang_sortie)}]
                response_text, outils_utilises, tokens_in, tokens_out = self._boucle_llm(
                    client, adaptateur, system_instruction, messages)
                if response_text:
                    mode = "ia"
                    # Filet de sécurité (voir _corriger_langue_si_besoin) : seulement si
                    # une langue fr/en est explicitement forcée (jamais pour 'dioula',
                    # dont la vérification post-hoc n'a pas de sens ici, ni pour l'auto-
                    # détection, où il n'y a par définition pas de langue "attendue").
                    if lang_sortie in ('fr', 'en'):
                        response_text, t_in_corr, t_out_corr = self._corriger_langue_si_besoin(
                            adaptateur, response_text, lang_sortie)
                        tokens_in += t_in_corr
                        tokens_out += t_out_corr
                else:
                    response_text = self.get_fallback_response(user_message, prix_kwh, ctx, lang)
            except Exception:
                logger.exception("Échec de l'appel au LLM, repli sur l'assistant local")
                outils_utilises = []
                response_text = self.get_fallback_response(user_message, prix_kwh, ctx, lang)
        else:
            # Pas de clé LLM configurée → conseils locaux (mode dégradé transparent).
            response_text = self.get_fallback_response(user_message, prix_kwh, ctx, lang)

        # 4. Quota : consommé UNIQUEMENT quand un vrai LLM a répondu — le repli local ne
        #    coûte rien et ne doit pas décompter une question du client. (Le frontend
        #    persiste l'échange lui-même juste après, via ConversationListCreateView/
        #    ConversationDetailView.)
        if mode == "ia":
            quota.nb_requetes_aujourd_hui += 1
            if tokens_in or tokens_out:
                # Trace de l'usage réel pour repérer un éventuel gaspillage.
                logger.info(
                    "Assistant IA (%s, fournisseur=%s, client=%s) : %d tokens entrée / %d tokens sortie, outils : %s",
                    adaptateur.modele, fournisseur, client.pk, tokens_in, tokens_out, outils_utilises or "aucun",
                )
                quota.tokens_entree_total += tokens_in
                quota.tokens_sortie_total += tokens_out
            quota.save()

        return Response({
            "response": response_text,
            "mode": mode,  # 'ia' (vrai LLM) ou 'fallback' (conseils locaux) → l'UI le signale
            "provider_utilise": provider,
            # Labels FR (dédupliqués, ordre d'appel) des données réellement consultées via
            # les outils — l'UI les affiche en note discrète sous la réponse.
            "outils_utilises": [label_outil(n) for n in dict.fromkeys(outils_utilises)],
            "nb_requetes_aujourd_hui": quota.nb_requetes_aujourd_hui,
            "limite_quotidienne": limite if limite > 0 else None,
        })

    @staticmethod
    def _valider_history(brut):
        """Assainit l'historique fourni par le client avant de le rejouer au LLM :
        seuls des tours {role: user|assistant, content: str} bien formés passent
        (jamais de rôle 'system' injecté ni de champs annexes), contenu tronqué à
        MAX_LONGUEUR_MESSAGE_HISTORIQUE, MAX_HISTORIQUE_ENVOI messages max."""
        if not isinstance(brut, list):
            return []
        propre = []
        for m in brut:
            if not isinstance(m, dict):
                continue
            role = m.get('role')
            content = m.get('content')
            if role not in ('user', 'assistant') or not isinstance(content, str) or not content.strip():
                continue
            propre.append({"role": role, "content": content[:MAX_LONGUEUR_MESSAGE_HISTORIQUE]})
        return propre[-MAX_HISTORIQUE_ENVOI:]

    def _resoudre_adaptateur(self, client, provider='standard'):
        """Résout l'adaptateur LLM à utiliser pour CE client, selon le choix explicite
        `provider` ('standard' = clé partagée du projet, 'personnel' = clé perso du
        client). Le FOURNISSEUR de la clé perso (OpenAI, Gemini, Anthropic, DeepSeek,
        xAI...) est déduit automatiquement de son format — voir fournisseurs_llm —
        jamais fixé par settings.AI_PROVIDER, qui ne concerne QUE la clé partagée.
        Repli silencieux sur 'standard' si 'personnel' est demandé mais qu'aucune clé
        perso n'est réglée. Renvoie (adaptateur, fournisseur_id) ; adaptateur=None si
        aucune clé exploitable (→ l'appelant replie sur l'assistant local)."""
        if provider == 'personnel':
            cle_perso = (getattr(client, 'cle_api_ia_personnelle', '') or '').strip()
            if cle_perso:
                url_perso = (getattr(client, 'url_api_ia_personnelle', '') or '').strip()
                modele_perso = (getattr(client, 'modele_api_ia_personnelle', '') or '').strip()
                fournisseur = detecter_fournisseur(cle_perso, url_perso)
                if fournisseur is None:
                    return None, None
                return construire_adaptateur(fournisseur, cle_perso, url_perso, modele_perso, settings), fournisseur
            provider = 'standard'  # comportement inchangé : repli silencieux, jamais d'erreur

        if settings.AI_PROVIDER == 'grok':
            cle = (settings.GROK_API_KEY or '').strip()
            adaptateur = AdaptateurOpenAICompatible(
                cle, settings.GROK_API_URL, settings.GROK_MODEL,
                settings.GROK_TIMEOUT, settings.GROK_MAX_TOKENS, settings.GROK_TEMPERATURE)
        else:
            cle = (settings.DEEPSEEK_API_KEY or '').strip()
            adaptateur = AdaptateurOpenAICompatible(
                cle, settings.DEEPSEEK_API_URL, settings.DEEPSEEK_MODEL,
                settings.DEEPSEEK_TIMEOUT, settings.DEEPSEEK_MAX_TOKENS, settings.DEEPSEEK_TEMPERATURE,
                desactiver_thinking=True)
        if not cle or cle.startswith('your-'):
            return None, settings.AI_PROVIDER
        return adaptateur, settings.AI_PROVIDER

    def _boucle_llm(self, client, adaptateur, system_instruction, messages):
        """Boucle « function calling », générique quel que soit le fournisseur (voir
        fournisseurs_llm) : le LLM peut demander des outils (outils.py), le serveur
        les exécute (bornés à CE client) et lui renvoie les résultats, jusqu'à la
        réponse finale. Le dernier tour force une conclusion en texte au lieu de
        boucler. Renvoie (texte, outils_utilises, tokens_in, tokens_out) — texte
        vide = échec, l'appelant replie en local. `messages` : historique canonique
        SANS le message system (passé séparément à l'adaptateur — certains
        fournisseurs, ex. Anthropic/Gemini, l'attendent hors de la liste des tours)."""
        outils_utilises = []
        tokens_in = tokens_out = 0
        messages = list(messages)
        for iteration in range(MAX_ITERATIONS_OUTILS):
            dernier_tour = (iteration == MAX_ITERATIONS_OUTILS - 1)
            try:
                texte, tool_calls, t_in, t_out = adaptateur.appeler(
                    system_instruction, messages, OUTILS_SPEC, dernier_tour)
            except ErreurAppelLLM as e:
                # Corps tronqué dans le message → diagnostique un mauvais model id (404),
                # une clé invalide (401/403) ou un quota (429) sans casser l'expérience.
                logger.warning(str(e))
                return "", outils_utilises, tokens_in, tokens_out
            tokens_in += t_in
            tokens_out += t_out

            if tool_calls and not dernier_tour:
                messages.append({"role": "assistant", "content": texte, "tool_calls": tool_calls})
                for tc in tool_calls[:MAX_APPELS_OUTILS_PAR_TOUR]:
                    resultat = executer_outil(client, tc['name'], tc['arguments'])
                    outils_utilises.append(tc['name'])
                    messages.append({
                        "role": "tool", "tool_call_id": tc['id'], "name": tc['name'],
                        # default=str : Decimal/datetime résiduels sérialisés sans casser
                        "content": json.dumps(resultat, ensure_ascii=False, default=str),
                    })
                continue

            if not texte:
                logger.warning("%s : réponse 200 mais contenu vide", adaptateur.modele)
            return texte, outils_utilises, tokens_in, tokens_out
        return "", outils_utilises, tokens_in, tokens_out

    def _snapshot_client(self, client, prix_kwh):
        """Résumé LÉGER, RÉEL et sans PII du client pour le prompt système (et le repli
        local) : l'essentiel « aujourd'hui » seulement. Tout le reste (autres périodes,
        historique mensuel, prévision, crédit, alertes, interventions, capteurs) est lu
        À LA DEMANDE par le LLM via les outils — au lieu d'être précalculé et payé en
        tokens à chaque message comme avant. Chaque champ réutilise une fonction déjà
        éprouvée ailleurs (mêmes chiffres que le dashboard), rien n'est réinventé."""
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
        # Noms d'appareils choisis par le client (« Clim salon »…) : pas de PII, et
        # indispensables au LLM pour nommer correctement les capteurs dans ses réponses.
        noms_appareils = list(Capteur.objects.filter(client=client).values_list('nom', flat=True))

        return {
            "kwh_jour": round(kwh_jour, 2),
            "puissance_w": int(puissance),
            "facture_fcfa": int(facture),
            "nb_capteurs": len(noms_appareils),
            "noms_appareils": noms_appareils,
            "prix_kwh": float(prix_kwh),
            "type_compteur": getattr(client, 'typeCompteur', 'postpaye'),
            "type_tarif": getattr(client, 'typeTarif', 'general'),
            "amperage": getattr(client, 'amperage', 10),
            "mode_absence": bool(getattr(client, 'modeAbsenceActif', False)),
        }

    @staticmethod
    def _rappel_langue_reponse(lang_sortie):
        """Rappel de langue ajouté à la FIN du dernier message utilisateur envoyé au LLM
        (en plus de la RÈGLE DE LANGUE du system prompt, voir _construire_system_instruction)
        — jamais affiché ni persisté, purement interne à CET appel LLM. Bug corrigé,
        constaté en test réel : dans une conversation de plusieurs tours déjà écrite dans
        une langue (ex. anglais forcé sur les 2 premiers tours), changer lang_sortie sur
        FR au 3e tour gardait la réponse en anglais malgré une RÈGLE DE LANGUE système sans
        ambiguïté — l'historique de conversation (des centaines de tokens en anglais, tout
        proches du point de génération) l'emportait sur une consigne système plus éloignée.
        Répéter la consigne collée au message à traiter (juste avant que le LLM génère sa
        réponse) est nettement plus fiable. Renvoie '' si lang_sortie n'est pas fr/en/dioula
        (comportement inchangé, auto-détection seule)."""
        if lang_sortie not in ('fr', 'en', 'dioula'):
            return ''
        langue_txt = 'français' if lang_sortie in ('fr', 'dioula') else 'anglais'
        return (
            f"\n\n[Consigne de langue : réponds à CE message en {langue_txt}, quelle que "
            f"soit la langue des échanges précédents de cette conversation.]"
        )

    @staticmethod
    def _corriger_langue_si_besoin(adaptateur, texte, langue_attendue):
        """Filet de sécurité : même avec le rappel de langue collé au message (voir
        _rappel_langue_reponse), un LLM généraliste peut occasionnellement répondre
        dans la mauvaise langue malgré une consigne sans ambiguïté — constaté en test
        réel, de façon NON déterministe (parfois respecté, parfois non, sur des
        appels par ailleurs identiques). Détecte ce cas via _langue_detectee (mots-
        outils, pas une vraie détection) et, seulement si un décalage clair est
        repéré, redemande une traduction STRICTE au LLM — appel léger, SANS outils
        (`outils_spec=[]`), qui ne refait jamais les lectures de données déjà faites,
        juste une reformulation dans la bonne langue. `langue_attendue` : 'fr' ou 'en'
        uniquement (jamais appelé pour 'dioula' — traduit de toute façon ensuite par
        LAMIA, qui a son propre repli si le texte source est mauvais).
        Renvoie (texte_final, tokens_in_suppl, tokens_out_suppl) — texte_final =
        `texte` inchangé si la langue détectée correspond déjà, ou si la correction
        échoue (jamais pire qu'avant : au pire on garde la réponse originale)."""
        detectee = _langue_detectee(texte)
        # None = signal insuffisant (texte trop court/numérique) → jamais de correction
        # sur un simple doute, seulement sur un décalage CLAIREMENT identifié.
        if not texte or detectee is None or detectee == langue_attendue:
            return texte, 0, 0
        langue_txt = 'français' if langue_attendue == 'fr' else 'anglais'
        try:
            texte_corrige, _tool_calls, t_in, t_out = adaptateur.appeler(
                f"Tu es un traducteur strict. Traduis le texte suivant en {langue_txt} SANS "
                f"changer un seul chiffre ni une seule donnée, sans rien ajouter ni retirer, "
                f"en conservant EXACTEMENT la mise en forme Markdown (titres, gras, listes, "
                f"tableaux). Réponds UNIQUEMENT avec la traduction, rien d'autre.",
                [{"role": "user", "content": texte}],
                [], True,
            )
            return (texte_corrige or texte), t_in, t_out
        except Exception:
            logger.exception("Échec de la correction de langue de secours")
            return texte, 0, 0

    def _construire_system_instruction(self, ctx, prix_kwh, lang_sortie=None):
        """Construit le prompt système : identité/isolation/bilingue (règles absolues),
        date-heure courante (les « hier »/« ce mois-ci » deviennent calculables), résumé
        réel du jour, et la consigne d'appeler les outils pour toute autre donnée chiffrée.
        Méthode séparée exprès pour être testable sans mocker l'appel réseau (voir
        tests.py, test de non-fuite de PII).

        `lang_sortie` ('fr'/'en'/'dioula'/None) : langue de RÉPONSE choisie explicitement
        par le client (bouton dédié, indépendant de la langue de saisie/dictée — voir
        static/js/ia.js). None = comportement d'origine, détection automatique de la
        langue de LA QUESTION (compat arrière, ex. vieux client qui n'enverrait pas ce
        champ). 'dioula' force le français en interne : LAMIA ne traduit fiablement QUE
        français -> dioula (voir dioula.py), donc même si la question était en anglais,
        la réponse générée ici doit être en français avant la traduction dioula faite
        ensuite par l'appelant (AIChatView.post / AIChatAudioView.post)."""
        now = timezone.localtime()
        from apps.analytics.views import MOIS_FR
        date_txt = (f"{JOURS_FR[now.weekday()]} {now.day} {MOIS_FR[now.month - 1].lower()} "
                    f"{now.year}, {now.strftime('%H:%M')}")

        # UNE SEULE règle de langue à la fois, JAMAIS deux — bug corrigé, constaté en
        # test réel : avec l'ancienne version (règle de détection auto TOUJOURS présente
        # + règle de forçage ajoutée « par-dessus » en la qualifiant de « prioritaire »
        # en prose), le LLM continuait à répondre dans la langue de la QUESTION malgré
        # lang_sortie='en' explicitement envoyé — deux règles qualifiées d'« absolues »
        # qui se contredisent ne se résolvent pas de façon fiable par un LLM généraliste,
        # même avec un mot « prioritaire ». La seule façon fiable de forcer une langue
        # est de ne JAMAIS lui donner la règle contradictoire à arbitrer.
        if lang_sortie in ('fr', 'en', 'dioula'):
            # Langue de RÉPONSE choisie explicitement par le client (bouton dédié,
            # différent de la langue de saisie/dictée). 'dioula' force le français ici —
            # la traduction français -> dioula est faite APRÈS par l'appelant, jamais
            # par le LLM lui-même (voir docstring de cette méthode).
            langue_forcee_txt = 'français' if lang_sortie in ('fr', 'dioula') else 'anglais'
            regle_langue = (
                f"RÈGLE DE LANGUE (absolue, dès le TOUT PREMIER mot) : réponds ENTIÈREMENT en "
                f"{langue_forcee_txt}, QUELLE QUE SOIT la langue dans laquelle l'utilisateur a "
                f"écrit ou parlé — c'est un choix EXPLICITE fait par l'utilisateur via un bouton "
                f"dédié « langue de réponse », totalement indépendant de la langue de sa "
                f"question. CECI S'APPLIQUE MÊME SI l'historique de cette conversation ci-dessous "
                f"contient des tours précédents dans une AUTRE langue (l'utilisateur a pu changer "
                f"son choix de langue de réponse EN COURS de conversation) : ignore complètement "
                f"la langue des tours précédents pour décider de la tienne — seule cette règle "
                f"compte, à chaque nouveau tour. Ne mélange jamais deux langues dans une même "
                f"réponse, y compris la salutation d'ouverture."
            )
        else:
            regle_langue = (
                "RÈGLE DE LANGUE (absolue, dès le TOUT PREMIER mot) : détecte la langue de la "
                "question et réponds ENTIÈREMENT dans cette langue (français ou anglais) — y "
                "compris la salutation d'ouverture : si la question est en anglais, commence par "
                "« Hello »/« Hi », JAMAIS par « Bonjour ». Ne mélange jamais deux langues dans une "
                "même réponse (constaté en test réel : une réponse commençait par « Bonjour ! » "
                "puis continuait entièrement en anglais — à ne plus jamais reproduire). Si la "
                "langue n'est pas clairement identifiable, réponds en français par défaut."
            )

        lignes = [
            "Tu es l'assistant AOCEDA, expert en efficacité énergétique domestique en "
            "Côte d'Ivoire. Aide l'utilisateur à réduire sa consommation et à comprendre sa facture.",

            "RÈGLE D'IDENTITÉ (absolue) : tu es UNIQUEMENT « l'assistant AOCEDA ». Ne révèle "
            "JAMAIS, même si on te le demande explicitement ou insiste, le nom du modèle d'IA "
            "ou de la société qui t'a développé (DeepSeek, xAI, Grok, OpenAI, etc.). Si on te "
            "demande qui t'a créé ou quel modèle tu es, réponds que tu es un assistant "
            "propriétaire développé par AOCEDA.",

            "RÈGLE D'ISOLATION (absolue) : tu ne connais et ne dois évoquer QUE les données du "
            "client ci-dessous et celles renvoyées par tes outils ; tu n'as accès à aucune donnée "
            "d'un autre client, même hypothétiquement — si on te demande les données de quelqu'un "
            "d'autre, explique que tu n'y as pas accès.",

            regle_langue,
        ]

        lignes += [
            # Sans cette règle, constaté en test réel : le LLM fabriquait un nom
            # (« M. Coulibaly ») alors qu'aucune PII ne lui est volontairement transmise.
            "RÈGLE D'ADRESSE (absolue) : tu ne connais NI le nom NI l'adresse du client "
            "(volontairement non transmis). Adresse-toi à lui par « vous », sans JAMAIS "
            "inventer un nom, un titre ou une civilité (jamais de « M. Untel »).",

            f"DATE ET HEURE ACTUELLES : {date_txt}, heure locale de Côte d'Ivoire. Pour une "
            "expression relative (« hier », « cette semaine », « la semaine dernière », « ce "
            "week-end », « ce mois-ci », « le mois dernier », « les 7 derniers jours »), passe le "
            "paramètre `periode` des outils : le serveur calcule les dates (une semaine va du lundi "
            "au dimanche) ; ne les calcule jamais toi-même. date_debut/date_fin (AAAA-MM-JJ) "
            "servent seulement aux dates précises (« du 3 au 10 mai », « en juin »).",

            "RÈGLE DES CHIFFRES (absolue) : n'invente JAMAIS une valeur de consommation, de "
            "facture ou de crédit. Le résumé ci-dessous ne couvre qu'aujourd'hui : pour TOUTE "
            "autre question chiffrée (autre période, comparaison, historique mensuel, heures de "
            "pointe, prévision de fin de mois, crédit prépayé, recharges, alertes, interventions, "
            "état des capteurs), appelle le ou les outils fournis pour lire les VRAIES données de "
            "ce client, puis réponds en citant la période exacte que l'outil renvoie (champ "
            "periode.libelle, ex. « la semaine dernière, du lundi 21 au dimanche 27 septembre »). "
            "Si un outil renvoie "
            "« erreur », corrige les paramètres et réessaie ; si les données sont vides, dis-le "
            "honnêtement au lieu de fabriquer un chiffre.",

            # Sans cette règle, constaté en test réel (dictée vocale dioula, transcription
            # imparfaite) : la réponse commençait par « Votre message reste difficile à
            # comprendre. Le mot X pourrait faire référence à... » — une réponse honnête sur
            # le fond, mais qui expose inutilement la mécanique interne (transcription
            # ratée) et met l'utilisateur en position d'échec au lieu de l'aider.
            "RÈGLE DE TON FACE À L'INCERTITUDE (absolue) : si une question est floue, "
            "incomplète, ou mal transcrite (dictée vocale imparfaite, formulation ambiguë…), "
            "n'écris AUCUNE phrase, même indirecte ou polie, qui évoque une difficulté à "
            "comprendre/identifier/interpréter la demande — interdits notamment : « je n'ai pas "
            "compris », « je n'arrive pas à identifier votre demande », « votre message est "
            "difficile à comprendre », « la langue/formulation pose problème », citer un mot "
            "précis mal transcrit. Commence DIRECTEMENT par une phrase d'accueil chaleureuse SANS "
            "aucun lien avec un problème de compréhension (ex. « Je suis là pour vous aider avec "
            "votre électricité ! »), puis enchaîne tout de suite sur des questions concrètes qui "
            "aident l'utilisateur à préciser sa demande (sa consommation d'hier, sa facture du "
            "mois, l'appareil qui consomme le plus, ses alertes…) — comme si poser ces questions "
            "était ton comportement normal d'ouverture, jamais la conséquence d'un échec. Cela ne "
            "t'autorise jamais à inventer un chiffre pour autant (voir RÈGLE DES CHIFFRES) : "
            "propose de vérifier une fois que tu sais quoi chercher.",

            "Résumé RÉEL d'aujourd'hui (déjà à jour — pas besoin d'outil pour ces chiffres) :",
            f"- Consommation aujourd'hui : {ctx['kwh_jour']} kWh ; puissance instantanée : "
            f"{ctx['puissance_w']} W ; facture du mois à ce jour : {ctx['facture_fcfa']} FCFA.",
            f"- {ctx['nb_capteurs']} capteur(s)/appareil(s) suivi(s) : "
            f"{', '.join(ctx['noms_appareils']) if ctx['noms_appareils'] else 'aucun'}. "
            f"Compteur {ctx['type_compteur']}, tarif CIE {ctx['type_tarif']}, "
            f"{ctx['amperage']}A souscrits ; prix marginal du kWh (tranche 1 + taxes, TVA "
            f"incluse) ≈ {prix_kwh} FCFA/kWh.",
        ]

        if ctx.get('mode_absence'):
            lignes.append("- Mode absence actif : le client n'est pas chez lui actuellement.")

        lignes.append(
            "Donne des conseils précis et actionnables (climatiseurs, réfrigérateurs, lampes "
            "LED, usage nocturne, crédit prépayé si applicable). Sois concis et poli."
        )
        lignes.append(
            "RÈGLE DE FORME : mise en page sobre en Markdown simple — gras pour les chiffres "
            "clés, listes à puces, intertitre court (###) seulement si la réponse a plusieurs "
            "parties, petit tableau seulement quand il aide vraiment à comparer des chiffres. "
            "N'insère PAS de ligne de séparation « --- » entre les sections."
        )
        return "\n".join(lignes)

    def get_fallback_response(self, user_message, prix_kwh=None, ctx=None, lang='fr'):
        """
        Conseils locaux (mode dégradé, sans LLM) pour la Côte d'Ivoire, en français ou en
        anglais selon `lang` — seul signal disponible ici (pas de LLM pour détecter la
        langue du message ; le chemin LLM réel s'en charge nativement, voir
        _construire_system_instruction). `prix_kwh` : prix marginal réel du client ;
        `ctx` : ses données réelles. Le champ `mode='fallback'` de la réponse permet à
        l'UI de signaler ce mode.
        """
        en = (lang == 'en')
        prix_txt = (f"{prix_kwh} FCFA/kWh" if prix_kwh is not None
                    else ("the current CIE tariff" if en else "le tarif CIE en vigueur"))
        msg = user_message.lower()
        # Questions sur SA consommation → on répond avec ses VRAIES données (jamais inventées).
        conso_mots = ("consommation", "consomme", "combien", "aujourd", "facture",
                      "puissance", "ma conso", "je consomme", "depense", "dépense",
                      "how much", "consumption", "bill", "power", "spend")
        if ctx and any(w in msg for w in conso_mots):
            if en:
                return (
                    "According to your AOCEDA sensors:\n"
                    f"- Consumption today: **{ctx['kwh_jour']} kWh**\n"
                    f"- Instantaneous power: **{ctx['puissance_w']} W**\n"
                    f"- Estimated monthly bill so far: **{ctx['facture_fcfa']} FCFA** (CIE tariff, VAT included)\n\n"
                    "To lower this amount, target your biggest loads first (AC, water heater) "
                    "and watch your nighttime consumption. Ask me for tips on a specific device."
                )
            return (
                "D'après vos capteurs AOCEDA :\n"
                f"• Consommation aujourd'hui : **{ctx['kwh_jour']} kWh**\n"
                f"• Puissance instantanée : **{ctx['puissance_w']} W**\n"
                f"• Facture mensuelle estimée : **{ctx['facture_fcfa']} FCFA** (grille CIE, TVA incluse)\n\n"
                "Pour réduire ce montant, ciblez d'abord vos plus gros postes (climatiseur, chauffe-eau) "
                "et surveillez la consommation nocturne. Demandez-moi des conseils précis sur un appareil."
            )
        if any(w in msg for w in ("tarif", "cie", "prix", "kwh", "tariff", "price", "rate")):
            if en:
                return (
                    "In Côte d'Ivoire, your bill follows the CIE (Compagnie d'Électricité) "
                    "residential tiered grid. Your first-tier price, **taxes and 18% VAT "
                    f"included (excluding the monthly fixed fee)**, is about **{prix_txt}**. "
                    "Monitoring your real-time power helps you avoid moving into the more "
                    "expensive tier."
                )
            return (
                "En Côte d'Ivoire, votre facture suit la grille domestique de la Compagnie d'Électricité (CIE), "
                "découpée en tranches. Le prix de votre première tranche, **taxes et TVA 18 % incluses "
                "(hors prime fixe mensuelle)**, est d'environ "
                f"**{prix_txt}**. "
                "Surveiller votre puissance en temps réel permet de ne pas basculer dans la tranche supérieure, plus chère."
            )
        elif any(w in msg for w in ("climat", "clim", "temperature", "ac ", "air condition", "aircon")):
            if en:
                return (
                    "Air conditioning is often the biggest energy consumer in Côte d'Ivoire. My tips:\n"
                    "1. Set the temperature to **24-25°C**; each degree lower uses about 7% more energy.\n"
                    "2. Make sure windows and doors are sealed shut.\n"
                    "3. Clean the air filters every two weeks to keep the heat exchanger efficient."
                )
            return (
                "Le climatiseur est souvent le plus grand consommateur d'énergie en Côte d'Ivoire. Voici mes conseils :\n"
                "1. Réglez la température à **24°C** ou **25°C** ; descendre en dessous consomme 7% de plus par degré.\n"
                "2. Assurez-vous que les fenêtres et portes sont hermétiquement fermées.\n"
                "3. Nettoyez les filtres à air toutes les deux semaines pour maintenir l'efficacité de l'échangeur thermique."
            )
        elif any(w in msg for w in ("ampoule", "led", "eclairage", "lampe", "bulb", "light", "lighting")):
            if en:
                return (
                    "Replacing your old incandescent or fluorescent bulbs with **LED bulbs** "
                    "can save up to 85% of your lighting electricity. For example, a 9W LED "
                    "bulb gives as much light as a traditional 60W bulb."
                )
            return (
                "Remplacer vos anciennes ampoules incandescents ou fluorescentes par des **ampoules LED** permet d'économiser "
                "jusqu'à 85% d'électricité sur l'éclairage. Par exemple, une ampoule LED de 9W éclaire autant qu'une ampoule de 60W traditionnelle."
            )
        elif any(w in msg for w in ("nuit", "fantome", "veille", "night", "standby", "phantom")):
            if en:
                return (
                    "Phantom nighttime consumption comes from devices left on standby (TVs, "
                    "set-top boxes, power strips, chargers). To reduce it:\n"
                    "1. Use switched power strips to fully cut power to devices at night.\n"
                    "2. Set up nighttime alerts on AOCEDA to be warned if standby power exceeds "
                    "50W between midnight and 5am."
                )
            return (
                "La consommation nocturne fantôme correspond aux appareils laissés en veille (téléviseurs, décodeurs, multiprises, chargeurs). "
                "Pour les réduire :\n"
                "1. Utilisez des multiprises à interrupteur pour couper complètement l'alimentation des appareils la nuit.\n"
                "2. Configurez des alertes nocturnes sur AOCEDA pour être averti si une veille dépasse 50W entre minuit et 5h du matin."
            )
        else:
            if en:
                return (
                    "Hello! I'm the AOCEDA assistant, your energy-saving helper.\n\n"
                    "I can help you understand your consumption, optimize your settings, and "
                    f"lower your bills (your all-in price is about **{prix_txt}** per the CIE grid).\n\n"
                    "Ask me about your air conditioners, nighttime standby, or how to optimize "
                    "your LED lighting!"
                )
            return (
                "Bonjour ! Je suis l'assistant AOCEDA, votre assistant d'économie d'énergie.\n\n"
                "Je peux vous aider à comprendre votre consommation, optimiser vos réglages et réduire vos factures "
                f"(votre prix tout compris est d'environ **{prix_txt}** selon la grille CIE).\n\n"
                "Posez-moi des questions sur vos climatiseurs, sur la veille nocturne, ou comment optimiser vos éclairages LED !"
            )


class ConversationListCreateView(generics.ListCreateAPIView):
    """Liste des fils de discussion du client (panneau Historique) + création d'un
    nouveau fil. Synchronisé entre appareils via le compte — voir Conversation."""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not hasattr(self.request.user, 'client'):
            return Conversation.objects.none()
        return Conversation.objects.filter(client=self.request.user.client)

    def get_serializer_class(self):
        return ConversationListSerializer if self.request.method == 'GET' else ConversationSerializer

    def perform_create(self, serializer):
        serializer.save(client=self.request.user.client)


class ConversationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Détail (avec messages), mise à jour après chaque échange, suppression d'un fil."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ConversationSerializer
    lookup_field = 'id'

    def get_queryset(self):
        if not hasattr(self.request.user, 'client'):
            return Conversation.objects.none()
        return Conversation.objects.filter(client=self.request.user.client)


class AIChatAudioView(AIChatView):
    """Variante audio du chat — dioula uniquement pour l'instant : l'utilisateur
    envoie un enregistrement vocal au lieu d'un texte. Pipeline complet, validé
    empiriquement (voir mémoire) :
      audio dioula -> STT (Meta MMS auto-hébergé, apps.ai_assistant.dioula)
      -> transcription dioula (imparfaite, surtout sur noms propres/sigles)
      -> LA MÊME boucle outils que le chat FR/EN (AIChatView._boucle_llm),
         avec un system prompt augmenté qui prévient des erreurs typiques de
         la transcription -> réponse en FRANÇAIS (jamais générée directement
         en dioula — testé peu fiable : un LLM généraliste part facilement
         sur un contresens, ex. « prix de la nourriture » au lieu de
         « consommation électrique », sans ce garde-fou)
      -> traduction + voix dioula (LAMIA)
    Hérite de AIChatView pour réutiliser tel quel tout le reste (quota, config
    fournisseur, données réelles du client via les outils, repli local) —
    seule l'entrée/sortie change de langue, jamais l'exactitude des chiffres."""
    parser_classes = [MultiPartParser]

    # Socle commun (corrections de transcription connues, garde-fou anti-hors-sujet) —
    # la dernière phrase (langue de réponse imposée) varie selon `lang_sortie`, voir
    # _addendum_dioula() : c'est elle qui a besoin d'un LLM généraliste écrivant en
    # français OU en anglais, jamais en dioula directement (testé peu fiable — un LLM
    # généraliste part facilement sur un contresens sans ce garde-fou).
    ADDENDUM_DIOULA_SOCLE = (
        "\n\nCAS PARTICULIER — DICTÉE VOCALE EN DIOULA : le message utilisateur ci-dessous "
        "est une TRANSCRIPTION AUTOMATIQUE d'un message vocal en dioula (langue mandingue de "
        "Côte d'Ivoire), produite par un moteur de reconnaissance vocale imparfait. Erreurs "
        "fréquentes et connues, à corriger mentalement :\n"
        "- « kuran »/« kuranko » = électricité/courant (généralement bien reconnu)\n"
        "- « wari » = argent ; « CFA » est souvent déformé (ex: « fawari »)\n"
        "- les nombres dioula (naani=4, fila=2, saba=3, duuru=5…) sont assez bien transcrits\n"
        "- « AOCEDA » est souvent déformé (ex: « ceda », « aw ce da »)\n"
        "RÈGLE ABSOLUE : le sujet de cette application est TOUJOURS l'électricité/la "
        "consommation/la facturation — ne pars JAMAIS sur un autre sujet (nourriture, etc.) "
        "sur la base d'un seul mot mal transcrit qui y ressemble vaguement. Si le sens général "
        "reste clair malgré les erreurs, réponds normalement en utilisant tes outils comme "
        "d'habitude. Si le message reste vraiment flou malgré tout, applique la RÈGLE DE TON "
        "FACE À L'INCERTITUDE ci-dessus : ne mentionne JAMAIS la transcription ratée ni un mot "
        "précis mal reconnu, pivote directement vers des questions concrètes. "
    )

    @classmethod
    def _addendum_dioula(cls, lang_sortie):
        """Addendum complet pour la dictée dioula, langue de réponse imposée selon le
        bouton « langue de réponse » choisi par le client (indépendant de la langue de
        saisie — ici toujours dioula puisqu'on est dans AIChatAudioView) :
        - 'en' -> réponse en ANGLAIS (pas de traduction dioula ensuite, voir post()).
        - 'fr'/'dioula'/None -> réponse en FRANÇAIS (cas 'dioula' : traduite ensuite par
          LAMIA, qui ne traduit fiablement QUE depuis le français, voir dioula.py)."""
        if lang_sortie == 'en':
            regle = (
                "Réponds TOUJOURS EN ANGLAIS (jamais en français ni en dioula : c'est la "
                "langue de réponse choisie par l'utilisateur pour cet échange)."
            )
        else:
            regle = (
                "Réponds TOUJOURS EN FRANÇAIS (jamais en dioula : si une traduction dioula "
                "est nécessaire, elle est faite automatiquement ensuite, ne le fais pas "
                "toi-même)."
            )
        return cls.ADDENDUM_DIOULA_SOCLE + regle

    def post(self, request):
        user = request.user
        if not hasattr(user, 'client'):
            return Response({"detail": "Seuls les clients peuvent clavarder avec l'assistant IA."}, status=status.HTTP_403_FORBIDDEN)
        client = user.client

        from . import dioula
        if not dioula.stt_disponible():
            return Response({"detail": "La dictée vocale en dioula n'est pas disponible sur ce serveur."},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        audio_file = request.FILES.get('audio')
        if not audio_file:
            return Response({"detail": "Fichier audio manquant."}, status=status.HTTP_400_BAD_REQUEST)

        history_brut = request.data.get('history')
        try:
            history = self._valider_history(json.loads(history_brut) if isinstance(history_brut, str) else history_brut)
        except (ValueError, TypeError):
            history = []
        provider = (request.data.get('provider') or 'standard').strip().lower()
        if provider not in MODELES:
            provider = 'standard'
        # Langue de RÉPONSE choisie via le bouton dédié (indépendant du fait que la
        # SAISIE soit en dioula, forcément, ici) : 'dioula' par défaut = comportement
        # d'origine (traduction systématique ci-dessous), 'fr'/'en' = réponse affichée
        # telle quelle, sans passer par LAMIA (voir _addendum_dioula et l'étape 5).
        lang_sortie = (request.data.get('lang_sortie') or '').strip().lower()
        if lang_sortie not in ('fr', 'en', 'dioula'):
            lang_sortie = 'dioula'
        lang_reponse_llm = 'en' if lang_sortie == 'en' else 'fr'

        # 1. Quota (mêmes règles que le chat texte)
        quota = self._get_quota(client)
        limite = settings.AI_DAILY_LIMIT
        if limite > 0 and quota.nb_requetes_aujourd_hui >= limite:
            return Response({
                "detail": f"Limite quotidienne atteinte. Vous avez droit à {limite} requêtes par jour pour l'assistant IA."
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        # 2. STT : audio -> texte dioula brut
        transcription = dioula.transcrire(audio_file.read())
        if not transcription:
            return Response(
                {"detail": "Impossible de comprendre l'enregistrement audio. Réessayez dans un environnement plus calme."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        # 3. LLM : MÊME pipeline outils que le chat texte (données réelles du
        # client), avec le system prompt augmenté ci-dessus — répond en français.
        prix_kwh = prix_kwh_tout_compris(client)
        ctx = self._snapshot_client(client, prix_kwh)
        adaptateur, fournisseur = self._resoudre_adaptateur(client, provider)
        response_text = ""
        mode = "fallback"
        outils_utilises = []
        tokens_in = tokens_out = 0

        if adaptateur is not None:
            try:
                system_instruction = (
                    self._construire_system_instruction(ctx, prix_kwh, lang_reponse_llm)
                    + self._addendum_dioula(lang_sortie)
                )
                # Rappel de langue collé au message (voir _rappel_langue_reponse) : même
                # motif que AIChatView.post — un historique déjà écrit dans une autre
                # langue peut l'emporter sur la seule règle du system prompt.
                messages = history + [{"role": "user", "content": transcription + self._rappel_langue_reponse(lang_reponse_llm)}]
                response_text, outils_utilises, tokens_in, tokens_out = self._boucle_llm(
                    client, adaptateur, system_instruction, messages)
                if response_text:
                    mode = "ia"
                    # Filet de sécurité (voir _corriger_langue_si_besoin) — même motif que
                    # AIChatView.post. lang_reponse_llm est toujours 'fr' ou 'en' ici.
                    response_text, t_in_corr, t_out_corr = self._corriger_langue_si_besoin(
                        adaptateur, response_text, lang_reponse_llm)
                    tokens_in += t_in_corr
                    tokens_out += t_out_corr
                else:
                    response_text = self.get_fallback_response(transcription, prix_kwh, ctx, lang_reponse_llm)
            except Exception:
                logger.exception("Échec de l'appel au LLM (chat audio dioula), repli sur l'assistant local")
                response_text = self.get_fallback_response(transcription, prix_kwh, ctx, lang_reponse_llm)
        else:
            response_text = self.get_fallback_response(transcription, prix_kwh, ctx, lang_reponse_llm)

        # 4. Quota consommé UNIQUEMENT si un vrai LLM a répondu (même règle que le texte)
        if mode == "ia":
            quota.nb_requetes_aujourd_hui += 1
            if tokens_in or tokens_out:
                quota.tokens_entree_total += tokens_in
                quota.tokens_sortie_total += tokens_out
            quota.save()

        # 5. Traduction + voix dioula de la réponse, PHRASE PAR PHRASE (voir
        # dioula.traduire_par_phrases) : alimente le lecteur bilingue synchronisé du
        # front (dioula à gauche / français à droite, surlignage qui avance phrase par
        # phrase) — demandé après retour de vrais locuteurs dioula : la synthèse est un
        # dioula authentique mais pas toujours facile à suivre, d'où l'intérêt
        # d'afficher le français en vis-à-vis. UNIQUEMENT si le client a choisi Dioula
        # comme langue de RÉPONSE (bouton dédié) — sinon (fr/en) response_text est déjà
        # dans la bonne langue (voir lang_reponse_llm ci-dessus), pas de traduction.
        # Jamais bloquant : si LAMIA échoue sur une phrase, les autres s'affichent quand
        # même (voir dioula._traduire_une_phrase).
        if lang_sortie == 'dioula':
            segments = dioula.traduire_par_phrases(response_text)
            texte_dioula = " ".join(s["dioula"] for s in segments if s.get("dioula"))
        else:
            segments = []
            texte_dioula = ""

        return Response({
            "transcription_dioula": transcription,
            "response": response_text,  # langue = lang_reponse_llm, cohérent avec l'historique
            "response_dioula": texte_dioula or None,
            "dioula_segments": segments,  # [{fr, dioula, audio_base64}, ...] — voir ia.js
            "mode": mode,
            "provider_utilise": provider,
            "outils_utilises": [label_outil(n) for n in dict.fromkeys(outils_utilises)],
            "nb_requetes_aujourd_hui": quota.nb_requetes_aujourd_hui,
            "limite_quotidienne": limite if limite > 0 else None,
        })


class TranslateDioulaView(APIView):
    """Traduit un texte déjà généré (une réponse du chat TEXTE classique) vers le
    dioula — utilisé quand l'utilisateur tape du texte (au lieu de parler) alors
    que le dioula est sélectionné comme langue de la voix : la réponse doit sortir
    en dioula dans ce cas aussi, pas seulement pour la dictée vocale (voir
    AIChatAudioView, qui fait la même traduction mais après son propre appel LLM).
    Aucun appel LLM ici (le texte est déjà généré) : PAS de coût de quota, juste
    une traduction — voir apps.ai_assistant.dioula.traduire_par_phrases."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not hasattr(request.user, 'client'):
            return Response({"detail": "Seuls les clients peuvent utiliser l'assistant IA."}, status=status.HTTP_403_FORBIDDEN)
        texte = (request.data.get('text') or '').strip()
        if not texte:
            return Response({"detail": "Texte vide."}, status=status.HTTP_400_BAD_REQUEST)

        from . import dioula
        segments = dioula.traduire_par_phrases(texte[:MAX_LONGUEUR_MESSAGE_HISTORIQUE])
        texte_dioula = " ".join(s["dioula"] for s in segments if s.get("dioula"))
        return Response({
            "response_dioula": texte_dioula or None,
            "dioula_segments": segments,
        })
