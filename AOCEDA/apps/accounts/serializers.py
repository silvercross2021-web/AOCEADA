from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from .models import Utilisateur, Client, Technicien, Administrateur

def _photo_url(obj):
    """URL de la photo de profil (relative /media/…) ou None si absente.
    L'upload se fait via l'endpoint dédié /api/users/me/photo/ (multipart)."""
    f = getattr(obj, 'photo', None)
    try:
        return f.url if f else None
    except ValueError:
        return None


class UtilisateurSerializer(serializers.ModelSerializer):
    photo = serializers.SerializerMethodField()

    class Meta:
        model = Utilisateur
        fields = ['id', 'email', 'nom', 'role', 'estActif', 'telephone', 'notifEmail', 'photo', 'is_2fa_enabled']
        read_only_fields = ['id', 'role', 'estActif']

    def get_photo(self, obj):
        return _photo_url(obj)


class TechnicienSerializer(serializers.ModelSerializer):
    """Profil technicien (vue/édition par le technicien lui-même), inclut le
    matricule et la spécialité, indispensables à l'espace technicien."""
    photo = serializers.SerializerMethodField()

    class Meta:
        model = Technicien
        fields = ['id', 'email', 'nom', 'role', 'estActif', 'telephone',
                  'notifEmail', 'matricule', 'specialite', 'photo', 'is_2fa_enabled']
        read_only_fields = ['id', 'role', 'estActif', 'matricule']

    def get_photo(self, obj):
        return _photo_url(obj)

class ClientSerializer(serializers.ModelSerializer):
    """Profil client (vue/édition par le client lui-même).

    L'abonnement officiel CIE, ampérage, type de tarif, TYPE DE COMPTEUR
    (prépayé / postpayé) et NUMÉRO D'ABONNÉ CIE, est référencé par le TECHNICIEN
    à l'installation : ces champs sont donc en lecture seule ici (cf.
    AbonnementSerializer). Le client édite son logement, son adresse et son profil.
    (Le n° CIE est un identifiant officiel de facturation : le laisser modifiable
    par le client risquerait de casser la corrélation avec la CIE.)
    """
    photo = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = ['id', 'email', 'nom', 'role', 'estActif', 'telephone', 'notifEmail', 'photo', 'is_2fa_enabled',
                  'typeLogement', 'adresse', 'numeroCIE', 'amperage', 'typeTarif', 'typeCompteur',
                  'seuilCreditBas_FCFA', 'nbPersonnesFoyer', 'superficie_m2']
        read_only_fields = ['id', 'role', 'estActif', 'amperage', 'typeTarif', 'typeCompteur', 'numeroCIE']

    def get_photo(self, obj):
        return _photo_url(obj)


def _valider_abonnement(attrs, instance=None):
    """Cohérence CIE : le 5A relève du tarif social ; le social exige le 5A."""
    amperage = attrs.get('amperage', getattr(instance, 'amperage', 10))
    type_tarif = attrs.get('typeTarif', getattr(instance, 'typeTarif', 'general'))
    if amperage == 5:
        # Le 5A domestique = Tarif Social (le 5A « général » n'existe pas à la CIE)
        attrs['typeTarif'] = 'social'
    elif type_tarif == 'social':
        raise serializers.ValidationError(
            {"typeTarif": "Le tarif social n'est disponible que pour les abonnements 5A."})
    return attrs


class TechnicienCreateClientSerializer(serializers.Serializer):
    """Création d'un compte client par un technicien lors de l'installation."""
    email = serializers.EmailField()
    nom = serializers.CharField(max_length=255)
    password = serializers.CharField(write_only=True, min_length=8)
    typeLogement = serializers.ChoiceField(choices=Client.LOGEMENT_CHOICES, required=False, default='Appartement')
    adresse = serializers.CharField(required=False, allow_blank=True, default='')
    numeroCIE = serializers.CharField(required=False, allow_blank=True, default='')
    amperage = serializers.ChoiceField(choices=[(5, '5A'), (10, '10A'), (15, '15A')], required=False, default=10)
    typeCompteur = serializers.ChoiceField(choices=[('postpaye', 'Postpayé'), ('prepaye', 'Prépayé')], required=False, default='postpaye')
    telephone = serializers.CharField(required=False, allow_blank=True, default='')
    # Capteurs disponibles (non assignés) à lier directement à ce client
    capteurs_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        write_only=True,
    )

    def validate_email(self, value):
        if Utilisateur.objects.filter(email=value).exists():
            raise serializers.ValidationError("Un compte existe déjà avec cette adresse email.")
        return value

    def create(self, validated_data):
        from apps.sensors.models import Capteur  # import local pour éviter la circularité
        password = validated_data.pop('password')
        capteurs_ids = validated_data.pop('capteurs_ids', [])
        amperage = int(validated_data.get('amperage', 10))
        type_tarif = 'social' if amperage == 5 else 'general'
        client = Client(
            email=validated_data['email'],
            nom=validated_data['nom'],
            role='client',
            typeLogement=validated_data.get('typeLogement', 'Appartement'),
            adresse=validated_data.get('adresse', ''),
            numeroCIE=validated_data.get('numeroCIE', ''),
            telephone=validated_data.get('telephone', ''),
            amperage=amperage,
            typeCompteur=validated_data.get('typeCompteur', 'postpaye'),
            typeTarif=type_tarif,
        )
        client.set_password(password)
        client.save()
        # Assigne les capteurs disponibles sélectionnés par le technicien
        if capteurs_ids:
            Capteur.objects.filter(id__in=capteurs_ids, client__isnull=True).update(client=client)
        return client

    def to_representation(self, instance):
        from apps.sensors.models import Capteur  # import local pour éviter la circularité
        capteurs = list(Capteur.objects.filter(client=instance).values('id', 'nom'))
        return {
            'id': str(instance.id),
            'email': instance.email,
            'nom': instance.nom,
            'role': instance.role,
            'amperage': instance.amperage,
            'typeCompteur': instance.typeCompteur,
            'typeTarif': instance.typeTarif,
            'capteurs_assignes': [{'id': str(c['id']), 'nom': c['nom']} for c in capteurs],
        }


class AbonnementSerializer(serializers.ModelSerializer):
    """Référencement de l'abonnement/compteur d'un client par le TECHNICIEN.

    Écrivables : ampérage, type de tarif, type de compteur (prépayé/postpayé),
    n° d'abonné CIE. Le reste est en lecture seule (repère pour le technicien).
    """
    class Meta:
        model = Client
        fields = ['id', 'nom', 'email', 'adresse', 'typeLogement',
                  'amperage', 'typeTarif', 'typeCompteur', 'numeroCIE']
        read_only_fields = ['id', 'nom', 'email', 'adresse', 'typeLogement']

    def validate(self, attrs):
        return _valider_abonnement(attrs, self.instance)


class ClientListSerializer(serializers.ModelSerializer):
    """Liste des clients pour l'espace technicien (sélection + abonnement)."""
    class Meta:
        model = Client
        fields = ['id', 'nom', 'email', 'adresse', 'amperage', 'typeTarif',
                  'typeCompteur', 'numeroCIE']
        read_only_fields = fields


class AdminUserSerializer(serializers.ModelSerializer):
    """Vue administrateur : liste et gestion des comptes (activer / désactiver)."""
    date_inscription = serializers.DateTimeField(source='date_joined', read_only=True)

    class Meta:
        model = Utilisateur
        fields = ['id', 'email', 'nom', 'role', 'estActif', 'is_active', 'date_inscription', 'last_login', 'is_2fa_enabled']
        read_only_fields = ['id', 'email', 'role', 'date_inscription', 'last_login']

    def update(self, instance, validated_data):
        # estActif et is_active restent synchronisés (blocage de connexion effectif)
        est_actif = validated_data.get('estActif', validated_data.get('is_active'))
        if est_actif is not None:
            instance.estActif = est_actif
            instance.is_active = est_actif
        if 'nom' in validated_data:
            instance.nom = validated_data['nom']
        instance.save()
        return instance


class AdminCreateUserSerializer(serializers.Serializer):
    """Création de comptes par l'administrateur (notamment les comptes techniciens)."""
    email = serializers.EmailField()
    nom = serializers.CharField(max_length=255)
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(choices=['client', 'technicien', 'admin'], default='technicien')
    matricule = serializers.CharField(max_length=100, required=False, allow_blank=True)
    specialite = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_email(self, value):
        if Utilisateur.objects.filter(email=value).exists():
            raise serializers.ValidationError("Un compte existe déjà avec cette adresse email.")
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        role = validated_data.pop('role')
        if role == 'technicien':
            matricule = validated_data.pop('matricule', '') or f"TECH-{Technicien.objects.count() + 1:04d}"
            user = Technicien(
                email=validated_data['email'], nom=validated_data['nom'], role='technicien',
                matricule=matricule, specialite=validated_data.pop('specialite', ''),
            )
        elif role == 'admin':
            user = Administrateur(
                email=validated_data['email'], nom=validated_data['nom'], role='admin', is_staff=True,
            )
        else:
            user = Client(email=validated_data['email'], nom=validated_data['nom'], role='client')
        user.set_password(password)
        user.save()
        return user

    def to_representation(self, instance):
        return AdminUserSerializer(instance).data


# ---------------------------------------------------------------------------
# Mot de passe : changement (connecté) et réinitialisation (oubli)
# ---------------------------------------------------------------------------
class ChangePasswordSerializer(serializers.Serializer):
    """Changement du mot de passe par l'utilisateur connecté."""
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value

    def validate_new_password(self, value):
        user = self.context['request'].user
        try:
            validate_password(value, user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    """Demande de lien de réinitialisation (mot de passe oublié)."""
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Confirmation : applique le nouveau mot de passe via le token reçu."""
    email = serializers.EmailField()
    token = serializers.UUIDField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value
