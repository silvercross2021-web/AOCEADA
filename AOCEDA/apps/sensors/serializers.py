from rest_framework import serializers
from .models import Dispositif, Capteur, MesureEnergie, Intervention, RapportIntervention
from apps.accounts.models import Technicien


class DispositifSerializer(serializers.ModelSerializer):
    client_nom = serializers.SerializerMethodField()
    client_email = serializers.SerializerMethodField()

    def get_client_nom(self, obj):
        return obj.client.nom if obj.client else None

    def get_client_email(self, obj):
        return obj.client.email if obj.client else None

    class Meta:
        model = Dispositif
        fields = ['id', 'client', 'client_nom', 'client_email', 'nom', 'adresse', 'numeroSerie', 'apiKeyDevice',
                  'firmwareVersion', 'estConnecté', 'adresseIP']
        read_only_fields = ['id', 'apiKeyDevice']
        extra_kwargs = {'client': {'required': False, 'allow_null': True}}


class CapteurSerializer(serializers.ModelSerializer):
    class Meta:
        model = Capteur
        fields = ['id', 'nom', 'type', 'valeurMax', 'actif', 'coeffCalibration', 'derniereLecture', 'etatCourant']
        read_only_fields = ['id', 'derniereLecture', 'etatCourant']


class CapteurRenommerSerializer(serializers.ModelSerializer):
    """Renommage par le CLIENT de son propre capteur. Seul `nom` est modifiable :
    la calibration, le type, le seuil, l'état… restent hors de portée du client
    (réservés au technicien). Le nom est nettoyé et ne peut pas être vide."""
    class Meta:
        model = Capteur
        fields = ['id', 'nom']
        read_only_fields = ['id']

    def validate_nom(self, value):
        nom = (value or '').strip()
        if not nom:
            raise serializers.ValidationError("Le nom ne peut pas être vide.")
        if len(nom) > 150:
            raise serializers.ValidationError("Le nom ne peut pas dépasser 150 caractères.")
        return nom


class CapteurTechnicienSerializer(serializers.ModelSerializer):
    """Vue technicien : inclut le client et le dispositif pour l'installation/calibration."""
    client_nom = serializers.SerializerMethodField()
    dispositif_id = serializers.ReadOnlyField(source='dispositif.id')

    def get_client_nom(self, obj):
        return obj.client.nom if obj.client else None

    class Meta:
        model = Capteur
        fields = ['id', 'client', 'client_nom', 'dispositif', 'dispositif_id', 'nom', 'type',
                  'valeurMax', 'actif', 'coeffCalibration', 'derniereLecture', 'derniereCalibration']
        # derniereCalibration : jamais modifiable directement via l'API — seule la
        # logique serveur des vues de calibration (auto/manuelle) la met à jour,
        # sinon un technicien pourrait la falsifier comme une simple donnée de formulaire.
        read_only_fields = ['id', 'derniereLecture', 'derniereCalibration']
        extra_kwargs = {'client': {'required': False, 'allow_null': True}}


class ZMCTMesureSerializer(serializers.Serializer):
    """Format d'une mesure envoyée par l'ESP32 depuis le capteur ZMCT103C."""
    capteur_index = serializers.IntegerField(min_value=1, max_value=8)
    courant = serializers.DecimalField(max_digits=10, decimal_places=3)
    puissance = serializers.DecimalField(max_digits=10, decimal_places=2)
    etat = serializers.ChoiceField(choices=['ON', 'OFF'], required=False, default='ON')
    amplitude = serializers.IntegerField(required=False, allow_null=True)
    centre = serializers.IntegerField(required=False, allow_null=True)
    # Horodatage RÉEL de l'acquisition (epoch UTC, secondes), fourni par le firmware
    # pour une mesure mise en tampon hors-ligne (coupure WiFi/serveur) et rejouée
    # après reconnexion — voir Test_ZMCT/src/main.cpp. Sans ce champ, toute une
    # coupure serait horodatée au moment du REJEU (mesures tassées sur quelques
    # secondes au lieu d'être réparties sur la vraie durée de la coupure). Absent/
    # invalide → heure de réception du serveur (comportement historique, streaming
    # live), voir apps.sensors.views._horodatage_mesure.
    timestamp_unix = serializers.IntegerField(required=False, allow_null=True)


class RapportInterventionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RapportIntervention
        fields = ['id', 'intervention', 'contenu', 'conclusion', 'dateGénération', 'estValidé']
        read_only_fields = ['id', 'dateGénération']


class InterventionSerializer(serializers.ModelSerializer):
    technicien_nom = serializers.ReadOnlyField(source='technicien.nom')
    technicien_telephone = serializers.ReadOnlyField(source='technicien.telephone')
    client_nom = serializers.ReadOnlyField(source='client.nom')
    capteur_nom = serializers.ReadOnlyField(source='capteur.nom')
    rapport = RapportInterventionSerializer(read_only=True)
    # Optionnel en création : perform_create l'injecte pour le technicien connecté.
    # Un admin doit le fournir explicitement ; un technicien ne peut pas le modifier.
    technicien = serializers.PrimaryKeyRelatedField(
        queryset=Technicien.objects.all(),
        required=False, allow_null=False
    )
    # Optionnel en création : un client ne connaît/ne maîtrise pas cette date, le
    # serveur l'impose (voir InterventionListCreateView.perform_create) — sans ça,
    # DRF rejetait systématiquement la création côté client (champ requis manquant).
    dateIntervention = serializers.DateTimeField(required=False)

    class Meta:
        model = Intervention
        fields = ['id', 'technicien', 'technicien_nom', 'technicien_telephone', 'client', 'client_nom',
                  'dispositif', 'capteur', 'capteur_nom', 'typeIntervention', 'description', 'dateIntervention',
                  'statut', 'résultat', 'rapport', 'dateProgrammee', 'satisfactionClient', 'commentaireClient',
                  'dateRetourClient', 'interventionOrigine']
        # satisfactionClient/commentaireClient/dateRetourClient : en LECTURE SEULE ici,
        # écrits uniquement via l'endpoint dédié InterventionFeedbackView (serializer à
        # portée volontairement réduite, même principe que CapteurRenommerSerializer).
        read_only_fields = ['id', 'rapport', 'dateRetourClient', 'satisfactionClient', 'commentaireClient']

    def validate(self, attrs):
        origine = attrs.get('interventionOrigine')
        request = self.context.get('request')
        if origine is not None and request is not None and hasattr(request.user, 'client'):
            if origine.client_id != request.user.client.id:
                raise serializers.ValidationError(
                    {"interventionOrigine": "Cette intervention ne vous appartient pas."})
            if origine.statut != 'TERMINEE':
                raise serializers.ValidationError(
                    {"interventionOrigine": "Seule une intervention terminée peut faire l'objet d'un signalement de persistance."})
        return attrs


class InterventionFeedbackSerializer(serializers.ModelSerializer):
    """Retour client après une intervention TERMINEE : n'expose QUE la note de
    satisfaction et le commentaire en écriture (portée réduite, même principe que
    CapteurRenommerSerializer — jamais statut/résultat/dates via ce canal)."""

    class Meta:
        model = Intervention
        fields = ['id', 'satisfactionClient', 'commentaireClient', 'dateRetourClient']
        read_only_fields = ['id', 'dateRetourClient']

    def validate_satisfactionClient(self, value):
        if value is not None and not (1 <= value <= 5):
            raise serializers.ValidationError("La note de satisfaction doit être comprise entre 1 et 5.")
        return value


class MesureEnergieSerializer(serializers.ModelSerializer):
    capteur_nom = serializers.ReadOnlyField(source='capteur.nom')

    class Meta:
        model = MesureEnergie
        fields = ['id', 'capteur', 'capteur_nom', 'puissance', 'courant', 'energie', 'tension_V', 'facteur_puissance', 'timestamp']
        read_only_fields = ['id']


