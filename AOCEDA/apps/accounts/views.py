import uuid
import logging
from datetime import timedelta
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from django.conf import settings  # pyrefly: ignore [untyped-import]
from django.core.mail import send_mail  # pyrefly: ignore [untyped-import]
from rest_framework import generics, permissions, status
from .utils import send_mail_async
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Utilisateur, Client, NoteClient, Administrateur
from .serializers import (
    ClientSerializer, UtilisateurSerializer, TechnicienSerializer,
    AdminUserSerializer, AdminCreateUserSerializer, TechnicienCreateClientSerializer,
    AbonnementSerializer, ClientListSerializer, NoteClientSerializer,
    ChangePasswordSerializer, PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
)
from .permissions import IsAdministrateur, IsTechnicienOrAdministrateur
import random
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger(__name__)


def _profile_serializer_for(user, *args, **kwargs):
    """Choisit le serializer de profil selon le rôle effectif de l'utilisateur."""
    if hasattr(user, 'client'):
        return ClientSerializer(user.client, *args, **kwargs)
    if hasattr(user, 'technicien'):
        return TechnicienSerializer(user.technicien, *args, **kwargs)
    return UtilisateurSerializer(user, *args, **kwargs)


class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = _profile_serializer_for(request.user)
        return Response(serializer.data)

    def put(self, request):
        serializer = _profile_serializer_for(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        """Suppression définitive du compte de l'utilisateur connecté.
        Requiert le mot de passe actuel pour confirmation."""
        password = request.data.get('password', '')
        if not request.user.check_password(password):
            return Response(
                {"detail": "Mot de passe incorrect. Suppression annulée."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = request.user
        user.delete()
        return Response({"detail": "Compte supprimé définitivement."}, status=status.HTTP_200_OK)


class UserPhotoView(APIView):
    """Photo de profil de l'utilisateur connecté : upload (multipart) + suppression.

    POST  (champ 'photo', multipart)  → enregistre l'image, renvoie {photo: <url>}.
    DELETE                            → supprime la photo, renvoie {photo: null}.
    Validation : type image (Pillow via ImageField), taille ≤ 5 Mo."""
    permission_classes = [permissions.IsAuthenticated]
    MAX_BYTES = 5 * 1024 * 1024

    def post(self, request):
        f = request.FILES.get('photo')
        if not f:
            return Response({"detail": "Aucun fichier reçu (champ « photo » attendu)."},
                            status=status.HTTP_400_BAD_REQUEST)
        if f.size > self.MAX_BYTES:
            return Response({"detail": "Image trop lourde (maximum 5 Mo)."},
                            status=status.HTTP_400_BAD_REQUEST)
        ctype = getattr(f, 'content_type', '') or ''
        if not ctype.startswith('image/'):
            return Response({"detail": "Le fichier doit être une image."},
                            status=status.HTTP_400_BAD_REQUEST)
        user = request.user
        # Remplace l'ancienne photo (ne laisse pas de fichier orphelin sur le disque).
        if user.photo:
            user.photo.delete(save=False)
        user.photo = f
        try:
            user.save(update_fields=['photo'])
        except Exception:
            user.save()
        return Response({"photo": user.photo.url if user.photo else None})

    def delete(self, request):
        user = request.user
        if user.photo:
            user.photo.delete(save=False)
            user.photo = None
            try:
                user.save(update_fields=['photo'])
            except Exception:
                user.save()
        return Response({"photo": None})


class ChangePasswordView(APIView):
    """Changement du mot de passe par l'utilisateur connecté."""
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({"detail": "Mot de passe mis à jour avec succès."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetRequestView(APIView):
    """Mot de passe oublié : génère un token et envoie le lien par e-mail.

    Réponse générique (ne révèle pas si le compte existe). En développement
    (DEBUG=True), le token est renvoyé dans la réponse pour permettre le test
    du flux complet sans serveur SMTP.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        user = Utilisateur.objects.filter(email__iexact=email).first()
        if not user:
            return Response(
                {"detail": "Aucun compte n'est associé à cette adresse e-mail."},
                status=status.HTTP_404_NOT_FOUND
            )
        if not user.is_active:
            return Response(
                {"detail": "Ce compte est désactivé. Veuillez contacter l'administrateur."},
                status=status.HTTP_400_BAD_REQUEST
            )

        token = uuid.uuid4()
        user.token_reset = token
        user.date_expiration_token = timezone.now() + timedelta(hours=1)
        user.save(update_fields=['token_reset', 'date_expiration_token'])

        # Lien ABSOLU (via FRONTEND_URL) → cliquable dans un vrai e-mail, pas un chemin relatif.
        reset_link = f"{settings.FRONTEND_URL}/auth/?reset_token={token}&email={email}"
        
        html_reset = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background-color: #f4f5f7; margin: 0; padding: 40px 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); overflow: hidden; }}
        .header {{ background-color: #0f172a; padding: 24px; text-align: center; color: white; }}
        .header h1 {{ margin: 0; font-size: 24px; font-weight: 600; letter-spacing: 1px; }}
        .content {{ padding: 40px; color: #334155; line-height: 1.6; font-size: 16px; }}
        .btn-box {{ text-align: center; margin: 35px 0; }}
        .btn {{ background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 16px; display: inline-block; }}
        .footer {{ text-align: center; padding: 24px; font-size: 13px; color: #94a3b8; border-top: 1px solid #f1f5f9; }}
        .alert {{ color: #ef4444; font-size: 14px; margin-top: 20px; }}
        .link-alt {{ font-size: 12px; color: #64748b; word-break: break-all; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>AOCEDA</h1>
        </div>
        <div class="content">
            <p>Bonjour <strong>{user.nom}</strong>,</p>
            <p>Nous avons reçu une demande de réinitialisation du mot de passe associé à votre compte AOCEDA.</p>
            <p>Pour définir un nouveau mot de passe, veuillez cliquer sur le bouton sécurisé ci-dessous :</p>
            
            <div class="btn-box">
                <a href="{reset_link}" class="btn">Réinitialiser mon mot de passe</a>
            </div>
            
            <p>Ce lien expirera dans <strong>1 heure</strong>.</p>
            <p class="alert">Si vous n'êtes pas à l'origine de cette demande, vous pouvez ignorer cet e-mail en toute sécurité. Votre mot de passe actuel ne sera pas modifié.</p>
            
            <div class="link-alt">
                <p>Si le bouton ne fonctionne pas, copiez-collez le lien suivant dans votre navigateur :<br>
                <a href="{reset_link}" style="color: #2563eb;">{reset_link}</a></p>
            </div>
            
            <p style="margin-top: 40px;">Cordialement,<br><strong>L'équipe de Sécurité AOCEDA</strong></p>
        </div>
        <div class="footer">
            <p>© {timezone.now().year} AOCEDA - Systèmes Intelligents de Mesure. Tous droits réservés.</p>
        </div>
    </div>
</body>
</html>
"""
        plain_text = (f"Bonjour {user.nom},\n\n"
                      f"Vous avez demandé la réinitialisation de votre mot de passe.\n"
                      f"Ce lien est valable 1 heure :\n{reset_link}\n\n"
                      f"Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.\n\n"
                      f"L'équipe AOCEDA")
        
        send_mail_async(
            "Réinitialisation de votre mot de passe AOCEDA",
            plain_text,
            getattr(settings, 'DEFAULT_FROM_EMAIL', 'alertes@aoceda.ci'),
            [user.email],
            fail_silently=False,
            html_message=html_reset
        )

        response_data = {"detail": "Un e-mail de réinitialisation a été envoyé avec succès."}
        if settings.DEBUG:
            response_data["dev_token"] = str(token)
        return Response(response_data)


class PasswordResetConfirmView(APIView):
    """Applique le nouveau mot de passe à partir du token de réinitialisation."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        token = serializer.validated_data['token']
        user = Utilisateur.objects.filter(email__iexact=email, token_reset=token).first()
        if not user or not user.date_expiration_token or user.date_expiration_token < timezone.now():
            return Response({"detail": "Lien de réinitialisation invalide ou expiré."},
                            status=status.HTTP_400_BAD_REQUEST)

        user.set_password(serializer.validated_data['new_password'])
        user.token_reset = None
        user.date_expiration_token = None
        user.save(update_fields=['password', 'token_reset', 'date_expiration_token'])
        # Même garantie que le changement de mot de passe connecté : toute
        # session ouverte avec l'ancien mot de passe est immédiatement coupée.
        from .utils import revoke_all_tokens
        revoke_all_tokens(user)
        return Response({"detail": "Mot de passe réinitialisé avec succès. Vous pouvez vous connecter."})


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        if getattr(user, 'is_2fa_enabled', False):
            code = f"{random.randint(0, 999999):06d}"
            user.two_factor_code = code
            user.two_factor_expiration = timezone.now() + timedelta(minutes=10)
            user.save(update_fields=['two_factor_code', 'two_factor_expiration'])
            try:
                html_2fa = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background-color: #f4f5f7; margin: 0; padding: 40px 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); overflow: hidden; }}
        .header {{ background-color: #0f172a; padding: 24px; text-align: center; color: white; }}
        .header h1 {{ margin: 0; font-size: 24px; font-weight: 600; letter-spacing: 1px; }}
        .content {{ padding: 40px; color: #334155; line-height: 1.6; font-size: 16px; }}
        .code-box {{ background-color: #f8fafc; border: 2px dashed #cbd5e1; border-radius: 8px; padding: 24px; text-align: center; margin: 30px 0; }}
        .code {{ font-family: monospace; font-size: 38px; font-weight: 700; color: #2563eb; letter-spacing: 8px; margin: 0; }}
        .footer {{ text-align: center; padding: 24px; font-size: 13px; color: #94a3b8; border-top: 1px solid #f1f5f9; }}
        .alert {{ color: #ef4444; font-size: 14px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>AOCEDA</h1>
        </div>
        <div class="content">
            <p>Bonjour <strong>{user.nom}</strong>,</p>
            <p>Une tentative de connexion a été détectée sur votre compte. Veuillez utiliser le code de sécurité ci-dessous pour valider votre accès :</p>
            
            <div class="code-box">
                <p class="code">{code}</p>
            </div>
            
            <p>Ce code est valable pendant <strong>10 minutes</strong>. Ne le partagez avec personne.</p>
            <p class="alert">Si vous n'avez pas tenté de vous connecter, veuillez ignorer cet e-mail et vérifier la sécurité de votre compte.</p>
            
            <p style="margin-top: 40px;">Cordialement,<br><strong>L'équipe de Sécurité AOCEDA</strong></p>
        </div>
        <div class="footer">
            <p>© {timezone.now().year} AOCEDA - Systèmes Intelligents de Mesure. Tous droits réservés.</p>
        </div>
    </div>
</body>
</html>
"""
                send_mail_async(
                    "Votre code d'authentification AOCEDA",
                    f"Bonjour {user.nom},\n\nVoici votre code d'accès : {code}\nCe code expire dans 10 minutes.",
                    getattr(settings, 'DEFAULT_FROM_EMAIL', 'alertes@aoceda.ci'),
                    [user.email],
                    fail_silently=False,
                    html_message=html_2fa
                )
            except Exception:
                logger.exception("Échec d'envoi de l'e-mail de double facteur (A2F)")
            return {"require_2fa": True, "email": user.email}
        # Connexion effective (pas de relai A2F) : les jetons sont émis ici.
        from .audit import log_action
        log_action(user, 'CONNEXION', f"Utilisateur {user.email} connecté avec succès.")
        return data

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class Verify2FAView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        email = request.data.get('email')
        code = request.data.get('code')
        if not email or not code:
            return Response({"detail": "Email et code requis."}, status=400)
        
        user = Utilisateur.objects.filter(email__iexact=email).first()
        if not user or not getattr(user, 'is_2fa_enabled', False):
            return Response({"detail": "A2F non activée ou utilisateur introuvable."}, status=400)
            
        if user.two_factor_code != str(code):
            return Response({"detail": "Code invalide."}, status=400)
            
        if not user.two_factor_expiration or user.two_factor_expiration < timezone.now():
            return Response({"detail": "Code expiré."}, status=400)
            
        user.two_factor_code = None
        user.two_factor_expiration = None
        user.save(update_fields=['two_factor_code', 'two_factor_expiration'])

        from .audit import log_action
        log_action(user, 'CONNEXION', f"Utilisateur {user.email} connecté avec succès (A2F).")

        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        })


class LogoutView(APIView):
    """Déconnexion : l'API étant sans état (JWT), il n'y a rien à invalider côté
    serveur — cet endpoint sert uniquement à journaliser l'événement avant que le
    front ne supprime ses jetons localement."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .audit import log_action
        log_action(request.user, 'DÉCONNEXION', f"Utilisateur {request.user.email} déconnecté.")
        return Response(status=status.HTTP_204_NO_CONTENT)

class Toggle2FAView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        user = request.user
        enable = request.data.get('enable', False)
        user.is_2fa_enabled = bool(enable)
        user.save(update_fields=['is_2fa_enabled'])
        return Response({"is_2fa_enabled": user.is_2fa_enabled})


# ---------------------------------------------------------------------------
# Espace Administrateur (cas d'utilisation : gérer les utilisateurs,
# activer/désactiver un compte, supprimer un compte, créer compte technicien)
# ---------------------------------------------------------------------------

class AdminUserListCreateView(generics.ListCreateAPIView):
    """Liste de tous les comptes + création de comptes (techniciens, admins)."""
    permission_classes = [permissions.IsAuthenticated, IsAdministrateur]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AdminCreateUserSerializer
        return AdminUserSerializer

    def get_queryset(self):
        queryset = Utilisateur.objects.all().order_by('-date_joined')
        role = self.request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)
        search = self.request.query_params.get('search')
        if search:
            from django.db.models import Q  # pyrefly: ignore [untyped-import]
            queryset = queryset.filter(Q(nom__icontains=search) | Q(email__icontains=search))
        return queryset


class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Activer / désactiver / supprimer un compte utilisateur."""
    serializer_class = AdminUserSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdministrateur]
    queryset = Utilisateur.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.id == request.user.id:
            return Response({"detail": "Impossible de supprimer son propre compte."},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# Espace Technicien (cas d'utilisation : référencer l'abonnement et le type
# de compteur, prépayé / postpayé, d'un client lors de l'installation)
# ---------------------------------------------------------------------------

class TechnicienClientListView(generics.ListAPIView):
    """Liste des clients (sélection + abonnement) pour le technicien/admin."""
    serializer_class = ClientListSerializer
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]

    def get_queryset(self):
        queryset = Client.objects.all().order_by('nom')
        search = self.request.query_params.get('search')
        if search:
            from django.db.models import Q  # pyrefly: ignore [untyped-import]
            queryset = queryset.filter(
                Q(nom__icontains=search) | Q(email__icontains=search) | Q(numeroCIE__icontains=search))
        return queryset


class TechnicienCreateClientView(generics.CreateAPIView):
    """Création d'un compte client par un technicien lors d'une installation."""
    serializer_class = TechnicienCreateClientSerializer
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client = serializer.save()
        from .audit import log_action
        log_action(
            request.user, 'CREATION_CLIENT',
            f"Création du compte client {client.nom} ({client.email}).",
            cible_id=client.id, client=client,
        )
        return Response(serializer.to_representation(client), status=status.HTTP_201_CREATED)


class TechnicienClientDetailView(generics.RetrieveUpdateAPIView):
    """Lecture et mise à jour partielle d'un client par le technicien.

    Champs modifiables : nom, telephone.
    Les champs financiers (amperage, tarif, compteur) passent par
    /api/users/clients/<pk>/abonnement/  (AbonnementSerializer).
    """
    serializer_class = ClientListSerializer
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]
    queryset = Client.objects.all()

    def update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        avant = serializer.instance
        ancien_nom, ancien_tel = avant.nom, avant.telephone
        client = serializer.save()
        changements = []
        if client.nom != ancien_nom:
            changements.append(f"nom \"{ancien_nom}\" → \"{client.nom}\"")
        if client.telephone != ancien_tel:
            changements.append(f"téléphone \"{ancien_tel or '—'}\" → \"{client.telephone or '—'}\"")
        if changements:
            from .audit import log_action
            log_action(
                self.request.user, 'EDITION_CLIENT',
                f"Modification du client {client.nom} : " + ", ".join(changements) + ".",
                cible_id=client.id, client=client,
            )


class ClientAbonnementView(generics.RetrieveUpdateAPIView):
    """Consulter / référencer l'abonnement d'un client (ampérage, tarif,
    type de compteur prépayé/postpayé, n° CIE). Réservé technicien/admin."""
    serializer_class = AbonnementSerializer
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]
    queryset = Client.objects.all()

    def perform_update(self, serializer):
        avant = serializer.instance
        champs = ['amperage', 'typeTarif', 'typeCompteur', 'numeroCIE']
        anciennes_valeurs = {f: getattr(avant, f) for f in champs}
        client = serializer.save()
        changements = [
            f"{f} \"{anciennes_valeurs[f]}\" → \"{getattr(client, f)}\""
            for f in champs if getattr(client, f) != anciennes_valeurs[f]
        ]
        if changements:
            from .audit import log_action
            log_action(
                self.request.user, 'EDITION_ABONNEMENT',
                f"Modification de l'abonnement de {client.nom} : " + ", ".join(changements) + ".",
                cible_id=client.id, client=client,
            )


class NoteClientListCreateView(generics.ListCreateAPIView):
    """Notes internes libres d'un technicien sur un client (jamais visibles du
    client). Plusieurs notes par client, jamais écrasées."""
    serializer_class = NoteClientSerializer
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]

    def get_queryset(self):
        queryset = NoteClient.objects.select_related('technicien', 'client').all()
        client_id = self.request.query_params.get('client')
        if client_id:
            queryset = queryset.filter(client_id=client_id)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        note = serializer.save(technicien=getattr(user, 'technicien', None))
        from .audit import log_action
        log_action(
            user, 'NOTE_CLIENT', f"Note interne ajoutée sur {note.client.nom}.",
            cible_id=note.id, client=note.client,
        )


class DemanderDesactivationView(APIView):
    """Un technicien demande la désactivation de son propre compte : notifie les
    administrateurs actifs par e-mail et journalise la demande (auparavant un
    bouton factice sans aucun effet)."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not hasattr(user, 'technicien'):
            return Response({"detail": "Réservé aux techniciens."}, status=status.HTTP_403_FORBIDDEN)

        from .audit import log_action
        log_action(
            user, 'DEMANDE_DESACTIVATION',
            f"Le technicien {user.nom} ({user.email}) a demandé la désactivation de son compte.",
            cible_id=user.id,
        )

        destinataires = list(
            Administrateur.objects.filter(estActif=True).exclude(email='').values_list('email', flat=True)
        )
        if destinataires:
            send_mail_async(
                "AOCEDA — Demande de désactivation de compte technicien",
                f"Le technicien {user.nom} ({user.email}, matricule {getattr(user.technicien, 'matricule', '—')}) "
                f"a demandé la désactivation de son compte. Merci de traiter cette demande depuis l'administration.",
                getattr(settings, 'DEFAULT_FROM_EMAIL', 'alertes@aoceda.ci'),
                destinataires,
                fail_silently=True,
            )

        return Response({"detail": "Votre demande a été transmise aux administrateurs."}, status=status.HTTP_200_OK)
