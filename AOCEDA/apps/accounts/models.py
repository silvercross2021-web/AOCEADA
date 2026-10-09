import uuid
from django.db import models  # pyrefly: ignore [untyped-import]
from django.contrib.auth.models import AbstractUser, BaseUserManager  # pyrefly: ignore [untyped-import]

class CustomUserManager(BaseUserManager):
    def create_user(self, email, nom, password=None, **extra_fields):
        if not email:
            raise ValueError("L'adresse email doit être renseignée.")
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, nom=nom, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, nom, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, nom, password, **extra_fields)

class Utilisateur(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None  # pyrefly: ignore
    email = models.EmailField(unique=True, verbose_name="Adresse email")
    nom = models.CharField(max_length=255)
    
    ROLE_CHOICES = [
        ('client', 'Client'),
        ('technicien', 'Technicien'),
        ('admin', 'Administrateur'),
    ]
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='client')
    estActif = models.BooleanField(default=True)
    telephone = models.CharField(max_length=30, blank=True, null=True, verbose_name="Téléphone")
    # Photo de profil (avatar). Facultative : sans photo, l'UI retombe sur les initiales.
    photo = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name="Photo de profil")
    # Notifications e-mail (préférence respectée par le moteur d'alertes)
    notifEmail = models.BooleanField(default=True, verbose_name="Notifications par e-mail")
    token_reset = models.UUIDField(null=True, blank=True)
    date_expiration_token = models.DateTimeField(null=True, blank=True)
    
    # Authentification à deux facteurs (A2F par email)
    is_2fa_enabled = models.BooleanField(default=False, verbose_name="A2F activée")
    two_factor_code = models.CharField(max_length=6, blank=True, null=True)
    two_factor_expiration = models.DateTimeField(null=True, blank=True)

    # Révocation des jetons JWT : tout jeton émis (claim `iat`) avant cette date
    # est rejeté, même non expiré — voir apps.accounts.authentication.
    # TokenAuthentication. Mis à jour à chaque changement/réinitialisation de
    # mot de passe (apps.accounts.utils.revoke_all_tokens).
    password_changed_at = models.DateTimeField(null=True, blank=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nom']

    def __str__(self):
        return f"{self.nom} ({self.email})"

class Client(Utilisateur):
    LOGEMENT_CHOICES = [
        ('Appartement', 'Appartement'),
        ('Villa', 'Villa'),
        ('Maison', 'Maison'),
    ]
    AMPERAGE_CHOICES = [
        (5, '5A (1,1 kW)'),
        (10, '10A (2,2 kW)'),
        (15, '15A (3,3 kW)'),
    ]
    TARIF_CHOICES = [
        ('social', 'Domestique Social (5A uniquement)'),
        ('general', 'Domestique Général'),
    ]
    COMPTEUR_CHOICES = [
        ('postpaye', 'Intelligent postpayé (facture mensuelle)'),
        ('prepaye', 'Prépayé (recharges)'),
    ]

    typeLogement = models.CharField(max_length=50, choices=LOGEMENT_CHOICES, default='Appartement')
    # Conservé pour compatibilité/affichage ; le calcul officiel utilise la
    # grille CIE complète (apps.analytics.tarifs_cie), pas ce prix moyen.
    tarifkWh_FCFA = models.DecimalField(max_digits=10, decimal_places=2, default=87.00)
    adresse = models.TextField(blank=True, null=True)
    numeroCIE = models.CharField(max_length=100, blank=True, null=True)
    # Attributs du FOYER (réels, utiles au service énergie : conso par personne,
    # repère kWh/m²). Facultatifs : jamais de valeur inventée si non renseignés.
    nbPersonnesFoyer = models.PositiveSmallIntegerField(
        blank=True, null=True, verbose_name="Nombre de personnes au foyer")
    superficie_m2 = models.PositiveIntegerField(
        blank=True, null=True, verbose_name="Superficie du logement (m²)")

    # Paramètres tarifaires CIE (voir EXPLICATION_TARIFAIRE.md)
    amperage = models.IntegerField(choices=AMPERAGE_CHOICES, default=10, verbose_name="Ampérage souscrit")
    typeTarif = models.CharField(max_length=20, choices=TARIF_CHOICES, default='general', verbose_name="Type de tarif CIE")
    typeCompteur = models.CharField(max_length=20, choices=COMPTEUR_CHOICES, default='postpaye', verbose_name="Type de compteur")
    # Cumul des recharges (compteurs prépayés), sert au crédit restant et à
    # l'alerte « Crédit bas ». Ignoré pour les postpayés. Défaut 0 : un compteur
    # jamais rechargé n'affiche AUCUN crédit (jamais de solde fabriqué).
    creditPrepaye_FCFA = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                             verbose_name="Crédit prépayé rechargé (FCFA)")
    seuilCreditBas_FCFA = models.DecimalField(max_digits=12, decimal_places=2, default=10000.00,
                                              verbose_name="Seuil alerte crédit bas (FCFA)")

    # Mode absence/vacances : suspend la règle de surveillance nocturne (bruit de
    # fond différent quand le foyer est vide, ex. frigo/lumière de sécurité laissés
    # allumés) SANS désactiver le dépassement de seuil ni le crédit bas, qui restent
    # pertinents (voire plus utiles) en l'absence du client.
    modeAbsenceActif = models.BooleanField(default=False, verbose_name="Mode absence actif")
    absenceJusquau = models.DateField(blank=True, null=True, verbose_name="Absence jusqu'au (optionnel)")

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"

class Technicien(Utilisateur):
    matricule = models.CharField(max_length=100, unique=True)
    specialite = models.CharField(max_length=150, blank=True, null=True)

    class Meta:
        verbose_name = "Technicien"
        verbose_name_plural = "Techniciens"

class Administrateur(Utilisateur):
    NIVEAU_CHOICES = [
        ('standard', 'Standard'),
        ('super', 'Super administrateur'),
    ]
    niveauAcces = models.CharField(max_length=50, choices=NIVEAU_CHOICES, default='standard')

    class Meta:
        verbose_name = "Administrateur"
        verbose_name_plural = "Administrateurs"


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    role = models.CharField(max_length=50, blank=True, null=True)
    action = models.CharField(max_length=150, db_index=True)
    description = models.TextField()
    cible_id = models.CharField(max_length=100, null=True, blank=True)
    # FK structurée en plus de cible_id (texte libre) : permet de filtrer le journal
    # « qui a fait quoi sur quel client » sans avoir à deviner ce que référence cible_id.
    client = models.ForeignKey('Client', on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs_client")

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Journal d'audit"
        verbose_name_plural = "Journaux d'audit"

    def __str__(self):
        user_str = self.utilisateur.nom if self.utilisateur else "Système"
        return f"{self.timestamp.strftime('%d/%m/%Y %H:%M:%S')} - {user_str} ({self.role or 'N/A'}) : {self.action}"


class NoteClient(models.Model):
    """Note interne libre qu'un technicien laisse sur un client (ex. « accès
    difficile, prévenir 10 min avant »). Jamais visible du client — usage
    équipe uniquement. Plusieurs notes par client, jamais écrasées : chacune
    garde son auteur et sa date, à l'inverse d'un simple champ modifiable."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="notes_internes")
    technicien = models.ForeignKey(Technicien, on_delete=models.SET_NULL, null=True, blank=True, related_name="notes_redigees")
    contenu = models.TextField()
    dateCreation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-dateCreation']
        verbose_name = "Note interne client"
        verbose_name_plural = "Notes internes client"

    def __str__(self):
        auteur = self.technicien.nom if self.technicien else "Technicien"
        return f"Note de {auteur} sur {self.client.nom} ({self.dateCreation:%d/%m/%Y})"

