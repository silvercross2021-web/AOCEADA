"""API de l'assistant IA d'AOCEDA (chatbot) : la page aoceda-ia.html <-> le moteur (apps/ai_assistant/chatbot).

Mêmes routes et mêmes formats que le serveur du laboratoire où l'assistant a été construit et validé, sous
/api/assistant/ ; ces vues ne contiennent pas de logique métier : elles vérifient la demande (compte, formats,
limites, droits) et transmettent au moteur (service_chat, voix...).

  POST /api/assistant/message            {session, texte, langue, genre...} -> flux d'événements (text/event-stream)
  POST /api/assistant/transcrire         audio WAV (≤ 60 s) + session + langue -> {texte, langue, ...}
  POST /api/assistant/transcrire/morceau morceau d'un vocal dioula / baoulé, écouté pendant l'enregistrement
  POST /api/assistant/voix/morceaux      {session, texte}                  -> {morceaux: [...]}
  POST /api/assistant/voix               {session, texte, langue, genre}   -> audio (SEULEMENT un texte du chatbot)
  POST /api/assistant/nouvelle           {session}                         -> mémoire de la conversation effacée
  GET  /api/assistant/config                                              -> langues, moteurs, état du démarrage
  GET  /api/assistant/tests                                               -> résultats du laboratoire (« Tests »)
  GET  /api/assistant/live/etat                                           -> modèles Live x comptes
  GET  /api/assistant/gpu/credit                                          -> crédit Cerebrium (voix baoulé)
  POST /api/assistant/baoule/reveil      ; GET /api/assistant/baoule/exemples (+ /valider, /rejeter : administrateur)
  GET/POST /api/assistant/conversations/ ; GET/PUT/DELETE /api/assistant/conversations/<id>/  (historique affiché)
  WS   /api/assistant/live?token=<JWT>   -> appel Live (apps/ai_assistant/live.py)

Compte : chaque demande est faite par un CLIENT connecté (jeton JWT), qui ne touche qu'à SES conversations ; ses
données (consommation, facture...) sont lues pour lui seul (chatbot/donnees_client.py).
"""
import asyncio
import json
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections
from django.http import FileResponse, Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, permissions, status
from rest_framework.exceptions import APIException, AuthenticationFailed
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import TokenAuthentication

from .chatbot import (baoule_demandes, baoule_ecoute, baoule_lexique, baoule_memoire, conversation, dioula_relais,
                      erreurs, fournisseurs, langues, live_agent, securite, service_chat, voix, voix_baoule, voix_gpu)
from .chatbot.config import AUDIOS_TESTS, CAPTURES, CONFIG, DOCUMENTATION, RESULTATS
from .chatbot.demarrage import PRET, prechauffer
from .chatbot.donnees_client import DONNEES, DonneesClient
from .chatbot.journal import journaliser
from .models import Conversation, QuotaIA
from .serializers import ConversationListSerializer, ConversationSerializer

SESSION_OK = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
RESERVE_ADMIN = "Réservé à l'administrateur d'AOCEDA."
ERREUR_INTERNE = "Erreur interne du serveur : réessayez."
# une réponse qui s'écrit occupe un fil pendant sa durée (comme au laboratoire : 100 réponses en même temps au plus)
FILS_REPONSES = ThreadPoolExecutor(max_workers=100, thread_name_prefix="assistant-reponse")


# ── Compte, conversation, limites ──────────────────────────────────────────────
class Refus(Exception):
    def __init__(self, message, code=400, entetes=None):
        super().__init__(message)
        self.code, self.entetes = code, entetes or {}


def client_de(user):
    client = getattr(user, "client", None) if user and user.is_authenticated else None
    if client is None:
        raise Refus("L'assistant AOCEDA est réservé aux comptes clients.", 403)
    return client


def ident_conversation(session):
    """Identifiant de la conversation en base : la page envoie un UUID ; un autre identifiant (8 à 64 caractères sûrs,
    comme au laboratoire) est converti en UUID stable."""
    try:
        return uuid.UUID(session)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"aoceda-assistant:{session}")


def verifier_session(client, session, creer=True):
    """La conversation `session` (identifiant choisi par la page) appartient-elle à ce client ? Créée pour lui à son 1er
    message. Jamais celle d'un autre client."""
    if not isinstance(session, str) or not SESSION_OK.match(session):
        raise Refus("identifiant de session invalide", 422)
    ident = ident_conversation(session)
    conv = Conversation.objects.filter(id=ident).only("client_id").first()
    if conv is None:
        if creer:
            Conversation.objects.get_or_create(id=ident, defaults={"client": client})
        return session
    if conv.client_id != client.pk:
        raise Refus("Cette conversation n'est pas la vôtre.", 403)
    return session


def session_permise(client, session):
    """Pour l'appel Live : True si la conversation est à ce client (créée sinon), False sinon. Jamais d'exception."""
    close_old_connections()
    try:
        verifier_session(client, session)
        return True
    except Refus:
        return False
    finally:
        close_old_connections()


def limiter(action, request, *cles):
    """Limites de débit du laboratoire (securite.py), par conversation, par compte ET par adresse."""
    try:
        securite.verifier(action, *cles, f"compte:{request.user.pk}", _ip(request))
    except securite.TropDeDemandes as e:
        raise Refus(str(e), 429, {"Retry-After": str(e.attente_s)})


def _ip(request):
    return securite.adresse_client(request.META.get("REMOTE_ADDR"), {k.lower(): v for k, v in request.headers.items()})


def quota_du_jour(client):
    """Limite quotidienne de questions par client (AI_DAILY_LIMIT du .env ; 0 = illimité). Compte la question."""
    limite = settings.AI_DAILY_LIMIT
    quota, _ = QuotaIA.objects.get_or_create(client=client)
    if quota.derniere_maj.date() < timezone.now().date():
        quota.nb_requetes_aujourd_hui = 0
    if limite > 0 and quota.nb_requetes_aujourd_hui >= limite:
        raise Refus(f"Limite quotidienne atteinte : {limite} questions par jour pour l'assistant IA.", 429)
    quota.nb_requetes_aujourd_hui += 1
    quota.save()


def _json(request):
    try:
        d = json.loads(request.body or b"{}")
    except ValueError:
        raise Refus("Demande illisible (JSON attendu).", 400)
    if not isinstance(d, dict):
        raise Refus("Demande illisible (objet JSON attendu).", 400)
    return d


def _genre(v):
    return "homme" if v == "homme" else "femme"


def _langue_ok(v):
    return v if (v in langues.LANGUES or langues.est_relais(v)) else None


def _texte(d, cle="texte", maximum=4000):
    t = d.get(cle)
    if not isinstance(t, str):
        raise Refus(f"« {cle} » manquant.", 422)
    if len(t) > maximum:
        raise Refus(f"« {cle} » trop long (au plus {maximum} caractères).", 422)
    return t


class VueAssistant(APIView):
    """Vue de l'API : client connecté (JWT), erreurs propres (Refus -> message, jamais de détail technique)."""
    permission_classes = [permissions.IsAuthenticated]

    def handle_exception(self, exc):
        if isinstance(exc, Refus):
            return Response({"erreur": str(exc)}, status=exc.code, headers=exc.entetes)
        if isinstance(exc, (voix.ErreurVoix,)):
            return Response({"erreur": str(exc)}, status=400)
        if isinstance(exc, (APIException, Http404, PermissionDenied)):
            return super().handle_exception(exc)         # connexion, droits, formats : réponses habituelles de l'API
        # erreur imprévue : un message propre (jamais le détail technique), le détail dans journaux/erreurs.log
        erreurs.noter(f"{self.request.method} {self.request.path}", exc)
        return Response({"erreur": ERREUR_INTERNE}, status=500)


# ── Réponse en flux (SSE) ──────────────────────────────────────────────────────
_FIN = object()


def _evenement(d):
    return f"data: {json.dumps(d, ensure_ascii=False)}\n\n"


def _suivant(gen, arret, donnees):
    """Prochain morceau du flux (dans un fil de calcul), avec le signal d'arrêt de la page (fournisseurs.ARRET) et les
    données du client (donnees_client.DONNEES) visibles du moteur."""
    jeton_a, jeton_d = fournisseurs.ARRET.set(arret), DONNEES.set(donnees)
    try:
        return next(gen, _FIN)
    except fournisseurs.Abandon:
        return _FIN
    finally:
        DONNEES.reset(jeton_d)
        fournisseurs.ARRET.reset(jeton_a)
        close_old_connections()


def _fermer(gen):
    """Ferme le générateur de la réponse : ses blocs « finally » retirent la question sans réponse et arrêtent DeepSeek."""
    try:
        gen.close()
    except ValueError:                    # encore en cours dans un fil : fermé dès qu'il rend la main
        def plus_tard():
            for _ in range(600):
                try:
                    gen.close()
                    return
                except ValueError:
                    threading.Event().wait(0.1)
        threading.Thread(target=plus_tard, daemon=True).start()
    except Exception as e:
        erreurs.noter("fermeture d'une réponse", e)


async def _en_flux(gen, arret, donnees):
    """La réponse envoyée morceau par morceau, et TOUJOURS fermée à la fin, même coupée (bouton Stop, onglet fermé :
    Django annule alors cette boucle). Audit du laboratoire (09/10/2026) : sinon DeepSeek continuait d'écrire (payé) et la
    question restait dans la conversation."""
    boucle = asyncio.get_running_loop()
    try:
        while True:
            ev = await boucle.run_in_executor(FILS_REPONSES, _suivant, gen, arret, donnees)
            if ev is _FIN:
                return
            yield ev
    finally:
        arret.set()                       # la page a coupé : DeepSeek s'arrête sans attendre son prochain mot
        _fermer(gen)


def _authentifier(request):
    """Client connecté (jeton JWT de l'en-tête Authorization), pour la vue asynchrone du flux."""
    try:
        r = TokenAuthentication().authenticate(request)
    except AuthenticationFailed as e:
        raise Refus(str(e.detail), 401)
    if r is None:
        raise Refus("Connexion requise.", 401)
    request.user = r[0]
    return r[0]


def _preparer_message(request):
    """Partie synchrone (base de données) de /message : compte, demande, conversation, limites, quota."""
    close_old_connections()
    try:
        user = _authentifier(request)
        client = client_de(user)
        d = _json(request)
        session = verifier_session(client, d.get("session"))
        limiter("message", request, session)
        try:
            texte = conversation.nettoyer_message(_texte(d))
        except conversation.MessageInvalide as e:
            raise Refus(str(e), 400)
        quota_du_jour(client)
        langue = d.get("langue") if langues.valide(d.get("langue")) else "auto"
        indice = d.get("indice_langue") if (d.get("indice_langue") in langues.LANGUES
                                             or langues.est_relais(d.get("indice_langue"))) else None
        return {"client": client, "session": session, "texte": texte, "langue": langue, "indice": indice,
                "origine": "vocal" if d.get("origine") == "vocal" else "ecrit", "genre": _genre(d.get("genre")),
                "action": _action(d.get("action")), "voix_auto": d.get("voix_auto", True) is not False}
    finally:
        close_old_connections()


def _action(v):
    """Bouton cliqué sous une réponse baoulé : seulement les 3 boutons connus ; un choix doit désigner une demande de la
    liste fermée (texte exact : audit du laboratoire, une liste à la place du nom faisait planter le serveur)."""
    if not isinstance(v, dict):
        return None
    t, demande = v.get("type"), v.get("demande")
    if t in ("oui", "non"):
        return {"type": t}
    if t == "choix" and isinstance(demande, str) and demande in baoule_demandes.CATALOGUE:
        return {"type": "choix", "demande": demande}
    return None


@csrf_exempt                                       # API à jeton (pas de cookie de session) : pas de CSRF
async def message(request):
    if request.method != "POST":
        return JsonResponse({"erreur": "Méthode non autorisée."}, status=405)
    boucle = asyncio.get_running_loop()
    try:
        m = await boucle.run_in_executor(FILS_REPONSES, _preparer_message, request)
    except Refus as e:
        r = JsonResponse({"erreur": str(e)}, status=e.code)
        for k, v in e.entetes.items():
            r[k] = v
        return r
    except Exception as e:                # imprévu : message propre, détail dans journaux/erreurs.log
        erreurs.noter("POST /api/assistant/message", e)
        return JsonResponse({"erreur": ERREUR_INTERNE}, status=500)

    def flux():
        # protection : une erreur imprévue n'est JAMAIS une coupure muette ; la page reçoit un vrai message (bouton
        # Réessayer) et le détail va dans journaux/erreurs.log
        try:
            yield from _flux()
        except Exception as e:
            erreurs.noter("/api/assistant/message", e, m["texte"])
            journaliser({"type": "message", "origine": m["origine"], "langue": m["langue"], "question": m["texte"][:300],
                         "statut": "erreur", "erreur": f"{type(e).__name__} : {e}"[:300]})
            yield _evenement({"type": "erreur", "texte": "L'assistant a eu un problème technique. Réessayez.", "essais": []})

    def _flux():
        for ev in service_chat.repondre(m["session"], m["texte"], m["langue"], m["indice"], m["genre"],
                                        origine=m["origine"], action=m["action"], voix_auto=m["voix_auto"]):
            if ev["type"] == "bilan":
                fin = ev["fin"] or {}
                extra = {k: ev[k] for k in ("intention", "certitude", "traduction_aller_s", "dossier", "chaine") if k in ev}
                if fin.get("premiere_phrase_s") is not None:
                    extra.update({"premiere_phrase_s": fin.get("premiere_phrase_s"), "francais": fin.get("francais", "")[:600],
                                  "non_traduit": fin.get("non_traduit")})
                try:                                # la réponse est déjà partie : le journal ne doit jamais la gâcher
                    journaliser({"type": "message", "origine": m["origine"], "langue": m["langue"], **extra,
                                 "langue_reponse": ev["langue_reponse"], "source_langue": ev["source_langue"],
                                 "refaites": ev["refaites"], "question": m["texte"][:300], "reponse": fin.get("texte", "")[:600],
                                 "statut": fin.get("type"), "modele": fin.get("modele"),
                                 "premier_mot_s": fin.get("premier_mot_s"), "total_s": fin.get("total_s"),
                                 "essais": fin.get("essais")})
                except Exception as e:
                    erreurs.noter("journal", e, m["texte"])
                continue
            yield _evenement(ev)

    arret = threading.Event()
    return StreamingHttpResponse(_en_flux(flux(), arret, DonneesClient(m["client"])), content_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Micro ──────────────────────────────────────────────────────────────────────
class Transcrire(VueAssistant):
    """Langue imposée par le menu (dioula compris), ou détection automatique (« auto ») : Whisper ou Omnilingual."""
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        client = client_de(request.user)
        session = verifier_session(client, request.data.get("session"))
        limiter("transcription", request, session)
        audio = request.FILES.get("audio")
        if audio is None:
            raise Refus("audio manquant", 422)
        octets = audio.read(voix.AUDIO_MAX_OCTETS + 1)       # on ne lit jamais plus que la limite
        langue = request.data.get("langue") or "auto"
        try:
            deja = int(request.data.get("deja") or 0)
        except ValueError:
            deja = 0
        try:
            r = voix.transcrire(octets, _langue_ok(langue), None, conversation.langue(session), session,
                                max(0, min(deja, voix.MORCEAUX_MAX)))
        except voix.ServeurOccupe as e:
            journaliser({"type": "transcription", "erreur": str(e)})
            return Response({"erreur": str(e)}, status=503, headers={"Retry-After": "5"})
        except voix.ErreurVoix as e:
            journaliser({"type": "transcription", "erreur": str(e)})
            return Response({"erreur": str(e)}, status=400 if "Transcription impossible" not in str(e) else 503)
        journaliser({"type": "transcription", "langue_menu": langue,
                     **{k: r.get(k) for k in ("texte", "langue", "certitude_langue", "parole", "prise_en_charge", "modele",
                                              "duree_audio_s", "duree_s", "routage", "temps", "dioula") if k in r}})
        return Response(r)


class TranscrireMorceau(VueAssistant):
    """Dioula ou baoulé : un morceau du vocal, envoyé à une pause PENDANT l'enregistrement ; écouté tout de suite."""
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        client = client_de(request.user)
        session = verifier_session(client, request.data.get("session"))
        limiter("morceau", request, session)
        audio = request.FILES.get("audio")
        try:
            rang = int(request.data.get("rang"))
        except (TypeError, ValueError):
            raise Refus("rang manquant", 422)
        if audio is None:
            raise Refus("audio manquant", 422)
        octets = audio.read(voix.AUDIO_MAX_OCTETS + 1)
        langue = request.data.get("langue") or "dyu"
        if langue == "bci" and not baoule_ecoute.disponible():
            langue = "dyu"
        return Response(voix.ecouter_morceau(octets, session, rang, "bci" if langue == "bci" else "dyu"))


# ── Voix ───────────────────────────────────────────────────────────────────────
class VoixMorceaux(VueAssistant):
    def post(self, request):
        d = _json(request)
        session = verifier_session(client_de(request.user), d.get("session"), creer=False)
        limiter("decoupage", request, session)
        texte = _texte(d)
        if d.get("langue") == "bci":      # baoulé : UN seul audio continu pour toute la réponse
            return Response({"morceaux": [voix.texte_pour_voix(texte)]})
        return Response({"morceaux": voix.decouper(texte)})


class Voix(VueAssistant):
    def post(self, request):
        d = _json(request)
        session = verifier_session(client_de(request.user), d.get("session"), creer=False)
        limiter("voix", request, session)
        texte = _texte(d)
        morceau = voix.texte_pour_voix(texte)
        if not conversation.voix_autorisee(session, morceau):   # seulement les textes écrits par le chatbot
            journaliser({"type": "voix", "refus": morceau[:160], "langue": d.get("langue")})
            return Response({"erreur": "Ce texte ne fait pas partie d'une réponse de cette conversation."}, status=403)
        lg = _langue_ok(d.get("langue"))
        if lg == "bci":                   # baoulé : GPU ~2 s, ou plusieurs minutes sur le PC -> jamais d'attente ici
            if not voix_baoule.disponible():
                return Response({"erreur": "Voix baoulé indisponible sur ce serveur."}, status=503)
            etat, tache, rang, (faites, total) = voix.demander_baoule_reponse(texte)
            if etat == "echec":
                journaliser({"type": "voix", "langue": "bci", "erreur": str(tache.exception())[:200]})
                return Response({"erreur": "Voix baoulé indisponible pour le moment (réessayez dans 2 minutes)."}, status=503)
            if etat != "prete":
                return Response({"etat": "preparation", "rang": rang, "phrases_pretes": faites, "phrases": total,
                                 "attente_s": voix_baoule.attente_estimee_s(max(rang, total - faites)),
                                 "moteur": voix_baoule.moteur()}, status=202)
            audio, infos = tache.result()
            r = HttpResponse(audio, content_type=infos["mime"])
            r["X-Moteur"], r["X-Voix"], r["X-Duree-S"] = infos["moteur"], infos["voix"], "0"
            return r
        try:
            audio, infos = voix.obtenir(texte, lg, _genre(d.get("genre")))   # déjà prêt en général
        except voix.ErreurVoix as e:
            journaliser({"type": "voix", "erreur": str(e)[:200]})
            return Response({"erreur": str(e)}, status=503)
        journaliser({"type": "voix", "caracteres": len(texte), "langue": lg, "moteur": infos["moteur"], "voix": infos["voix"],
                     "cache": infos["cache"], "duree_s": infos["duree_s"]})
        r = HttpResponse(audio, content_type=infos["mime"])
        r["X-Moteur"], r["X-Voix"], r["X-Duree-S"] = infos["moteur"], infos["voix"], str(infos["duree_s"])
        return r


class Nouvelle(VueAssistant):
    def post(self, request):
        d = _json(request)
        session = verifier_session(client_de(request.user), d.get("session"), creer=False)
        limiter("nouvelle", request, session)
        conversation.effacer(session)
        return Response({"ok": True})


# ── Baoulé ─────────────────────────────────────────────────────────────────────
class BaouleReveil(VueAssistant):
    """La page vient de passer au baoulé : le GPU de la voix démarre en arrière-plan (~35 s s'il dormait)."""
    def post(self, request):
        d = _json(request)
        session = verifier_session(client_de(request.user), d.get("session"), creer=False)
        limiter("reveil", request, session)
        return Response({"reveil": voix_gpu.reveiller("menu baoulé"), "moteur": voix_baoule.moteur(),
                         "eveille": voix_gpu.eveille()})


class BaouleExemples(VueAssistant):
    """Phrases confirmées en attente de validation, taille de la banque, mots manquants du carnet. RÉSERVÉ À
    L'ADMINISTRATEUR (audit du laboratoire) : ce sont des phrases dites par d'autres personnes, et la banque validée
    influence la compréhension du baoulé de tout le monde."""
    def get(self, request):
        limiter("lecture", request)
        if not request.user.is_staff:
            return Response({"erreur": RESERVE_ADMIN}, status=403)
        return Response({"attente": baoule_memoire.attente(), "banque": len(baoule_memoire.banque()),
                         "mots_manquants": baoule_lexique.mots_manquants(50),
                         "demandes": [{"id": d.id, "libelle": d.libelle} for d in baoule_demandes.CATALOGUE.values()]})


class BaouleValider(VueAssistant):
    def post(self, request):
        limiter("credit", request)
        if not request.user.is_staff:
            return Response({"erreur": RESERVE_ADMIN}, status=403)
        d = _json(request)
        ident, demande = str(d.get("id") or "")[:40], d.get("demande")
        if demande and demande not in baoule_demandes.CATALOGUE:
            return Response({"erreur": "demande inconnue"}, status=400)
        return Response({"ok": baoule_memoire.valider(ident, demande)})


class BaouleRejeter(VueAssistant):
    def post(self, request):
        limiter("credit", request)
        if not request.user.is_staff:
            return Response({"erreur": RESERVE_ADMIN}, status=403)
        return Response({"ok": baoule_memoire.rejeter(str(_json(request).get("id") or "")[:40])})


class GpuCredit(VueAssistant):
    """Crédit restant sur Cerebrium (Options > Voix baoulé). Jamais de clé dans la réponse. La relecture forcée est
    réservée à l'administrateur ; sinon le crédit gardé 60 s est renvoyé."""
    def get(self, request):
        limiter("credit", request)
        return Response(voix_gpu.credit(forcer=request.query_params.get("forcer") == "1" and request.user.is_staff))


# ── Configuration, Live, tests ─────────────────────────────────────────────────
class Config(VueAssistant):
    def get(self, request):
        prechauffer()                     # 1re ouverture de la page : les oreilles et Whisper se chargent (~10 s)
        return Response({
            "langues": langues.liste_pour_page(), "cerveau": f"DeepSeek ({CONFIG['DEEPSEEK_MODEL']})",
            "version_page": live_agent.version_page(),     # la page compare : nouvelle version -> elle se recharge
            "transcription": f"Whisper tiny + {CONFIG['MODELE_WHISPER']} ; dioula : Meta Omnilingual 1B ; baoulé : "
                             "Omnilingual 300M baoulé (Tree-AI) (sur le serveur)",
            "voix": "Microsoft (edge-tts), secours Kokoro ; dioula : Djelia ; baoulé : OmniVoice ("
                    + ("GPU Cerebrium ~2 s" + (", secours sur ce serveur)" if voix_baoule.atelier_installe() else ")")
                       if voix_gpu.disponible() else "sur ce serveur, lent)"),
            "audio_max_s": voix.AUDIO_MAX_S, "pret": PRET, "relais": dioula_relais.etat(),
            "baoule": {"ecoute": baoule_ecoute.disponible(), "voix": voix_baoule.disponible(),
                       "voix_moteur": voix_baoule.moteur(), "voix_attente_s": voix_baoule.attente_estimee_s(1)},
            "live": live_agent.etat(), "administrateur": bool(request.user.is_staff)})


class LiveEtat(VueAssistant):
    """Modèles Live × comptes : disponible ou limite atteinte (et retour), usage du jour. Jamais les clés."""
    def get(self, request):
        limiter("lecture", request)
        return Response(live_agent.etat())


class Tests(VueAssistant):
    """Résultats des essais du laboratoire où l'assistant a été construit (menu « Tests et rapports »)."""
    def get(self, request):
        limiter("lecture", request)

        def lire(nom):
            f = RESULTATS / nom
            if not f.exists():
                return None
            return json.loads(f.read_text(encoding="utf-8")) if nom.endswith(".json") else f.read_text(encoding="utf-8")

        def bilan(nom):
            f = DOCUMENTATION / nom
            return f.read_text(encoding="utf-8") if f.exists() else None
        return Response({
            "evaluation": lire("evaluation.json"), "tests_unitaires": lire("tests_unitaires.txt"),
            "navigateur": lire("essai_navigateur.json"), "bilan": bilan("ETAPE_1_CHATBOT.txt"),
            "voix_gratuites": lire("comparaison_voix.json"), "live": lire("essai_gemini_live.json"),
            "dioula": lire("dioula_evaluation.json"), "baoule": lire("baoule_evaluation.json"),
            "etape4": {"bilan": bilan("ETAPE_4_LIVE.txt"), "bout_en_bout": lire("essai_live_agent.json"),
                       "reserves": lire("essai_live_reserves.json"), "navigateur": lire("essai_navigateur_live.json"),
                       "periodes": lire("essai_live_periodes.json")},
            "personnage": lire("essai_personnage.json"),
            "agent_page": lire("essai_agent_page.json"),
            "agent_plan": {"plan": lire("essai_agent_plan.json"), "live": lire("essai_agent_live.json"),
                           "comparatif": lire("comparatif_agent_actions.json")},
            "langue": {"live": lire("essai_live_langue.json"), "chat": lire("essai_chat_langue.json")},
            "voix_gpu": lire("essai_voix_gpu.json"),
            "chaine_baoule": {"essai": lire("essai_chaine_baoule.json"), "reparation": lire("essai_reparation_baoule.json"),
                              "carnet": baoule_lexique.etat()}})


def fichier_rapport(request, dossier, chemin):
    """Audios et captures des essais du laboratoire (menu « Tests et rapports ») : lus par <audio> et <img>, qui
    n'envoient pas le jeton ; fichiers des essais seulement, jamais en dehors de leur dossier."""
    racine = {"audios": AUDIOS_TESTS, "captures": CAPTURES}.get(dossier)
    if racine is None:
        raise Http404
    f = (racine / chemin).resolve()
    if not f.is_file() or racine.resolve() not in f.parents:
        raise Http404
    return FileResponse(open(f, "rb"))


# ── Historique affiché (synchronisé entre les appareils du client) ─────────────
class ConversationListCreateView(generics.ListCreateAPIView):
    """Liste des conversations du client (feuille Historique) ; DELETE : toutes effacées (et leur mémoire)."""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        client = getattr(self.request.user, "client", None)
        return Conversation.objects.filter(client=client).exclude(messages=[]) if client else Conversation.objects.none()

    def get_serializer_class(self):
        return ConversationListSerializer if self.request.method == "GET" else ConversationSerializer

    def perform_create(self, serializer):
        serializer.save(client=client_de(self.request.user))

    def delete(self, request):
        convs = list(self.get_queryset().values_list("id", flat=True))
        for ident in convs:
            conversation.effacer(str(ident))
        self.get_queryset().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConversationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Une conversation (messages affichés), mise à jour après chaque échange, suppression (et sa mémoire)."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ConversationSerializer
    lookup_field = "id"

    def get_queryset(self):
        client = getattr(self.request.user, "client", None)
        return Conversation.objects.filter(client=client) if client else Conversation.objects.none()

    def perform_destroy(self, instance):
        conversation.effacer(str(instance.id))
        instance.delete()
