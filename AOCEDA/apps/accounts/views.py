import uuid
import logging
from datetime import timedelta
from django.utils import timezone  # pyrefly: ignore [untyped-import]
from django.conf import settings  # pyrefly: ignore [untyped-import]
from django.core.mail import send_mail  # pyrefly: ignore [untyped-import]
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Utilisateur, Client
from .serializers import (
    RegisterSerializer, ClientSerializer, UtilisateurSerializer, TechnicienSerializer,
    AdminUserSerializer, AdminCreateUserSerializer, TechnicienCreateClientSerializer,
    AbonnementSerializer, ClientListSerializer,
    ChangePasswordSerializer, PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
)
from .permissions import IsAdministrateur, IsTechnicienOrAdministrateur

logger = logging.getLogger(__name__)


def _profile_serializer_for(user, *args, **kwargs):
    """Choisit le serializer de profil selon le rôle effectif de l'utilisateur."""
    if hasattr(user, 'client'):
        return ClientSerializer(user.client, *args, **kwargs)
    if hasattr(user, 'technicien'):
        return TechnicienSerializer(user.technicien, *args, **kwargs)
    return UtilisateurSerializer(user, *args, **kwargs)

class RegisterView(generics.CreateAPIView):
    queryset = Client.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

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
        generic = {"detail": "Si un compte existe pour cette adresse, un lien de réinitialisation vient d'être envoyé."}
        user = Utilisateur.objects.filter(email__iexact=email).first()
        if not user:
            return Response(generic)

        token = uuid.uuid4()
        user.token_reset = token
        user.date_expiration_token = timezone.now() + timedelta(hours=1)
        user.save(update_fields=['token_reset', 'date_expiration_token'])

        reset_link = f"/auth/?reset_token={token}&email={email}"
        try:
            send_mail(
                "Réinitialisation de votre mot de passe AOCEDA",
                (f"Bonjour {user.nom},\n\n"
                 f"Vous avez demandé la réinitialisation de votre mot de passe.\n"
                 f"Ce lien est valable 1 heure :\n{reset_link}\n\n"
                 f"Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.\n\n"
                 f"L'équipe AOCEDA"),
                getattr(settings, 'DEFAULT_FROM_EMAIL', 'alertes@aoceda.ci'),
                [user.email],
                fail_silently=True,
            )
        except Exception:
            logger.exception("Échec d'envoi de l'e-mail de réinitialisation")

        if settings.DEBUG:
            # Confort de démonstration : permet d'enchaîner le flux sans SMTP.
            return Response({**generic, "dev_token": str(token)})
        return Response(generic)


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
        return Response({"detail": "Mot de passe réinitialisé avec succès. Vous pouvez vous connecter."})


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
# de compteur — prépayé / postpayé — d'un client lors de l'installation)
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
        return Response(serializer.to_representation(client), status=status.HTTP_201_CREATED)


class ClientAbonnementView(generics.RetrieveUpdateAPIView):
    """Consulter / référencer l'abonnement d'un client (ampérage, tarif,
    type de compteur prépayé/postpayé, n° CIE). Réservé technicien/admin."""
    serializer_class = AbonnementSerializer
    permission_classes = [permissions.IsAuthenticated, IsTechnicienOrAdministrateur]
    queryset = Client.objects.all()
