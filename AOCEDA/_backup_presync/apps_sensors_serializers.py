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
        fields = ['id', 'client', 'client_nom', 'client_email', 'numeroSerie', 'apiKeyDevice',
                  'firmwareVersion', 'estConnecté', 'adresseIP']
        read_only_fields = ['id', 'apiKeyDevice']
        extra_kwargs = {'client': {'required': False, 'allow_null': True}}


class CapteurSerializer(serializers.ModelSerializer):
    class Meta:
        model = Capteur
        fields = ['id', 'nom', 'type', 'valeurMax', 'actif', 'coeffCalibration', 'derniereLecture']
        read_only_fields = ['id', 'derniereLecture']


class CapteurTechnicienSerializer(serializers.ModelSerializer):
    """Vue technicien : inclut le client et le dispositif pour l'installation/calibration."""
    client_nom = serializers.SerializerMethodField()
    dispositif_id = serializers.ReadOnlyField(source='dispositif.id')

    def get_client_nom(self, obj):
        return obj.client.nom if obj.client else None

    class Meta:
        model = Capteur
        fields = ['id', 'client', 'client_nom', 'dispositif', 'dispositif_id', 'nom', 'type',
                  'valeurMax', 'actif', 'coeffCalibration', 'derniereLecture']
        read_only_fields = ['id', 'derniereLecture']
        extra_kwargs = {'client': {'required': False, 'allow_null': True}}


class ZMCTMesureSerializer(serializers.Serializer):
    """Format d'une mesure envoyée par l'ESP32 depuis le capteur ZMCT103C."""
    capteur_index = serializers.IntegerField(min_value=1, max_value=8)
    courant = serializers.DecimalField(max_digits=10, decimal_places=3)
    puissance = serializers.DecimalField(max_digits=10, decimal_places=2)
    etat = serializers.ChoiceField(choices=['ON', 'OFF'], required=False, default='ON')
    amplitude = serializers.IntegerField(required=False, allow_null=True)
    centre = serializers.IntegerField(required=False, allow_null=True)


class RapportInterventionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RapportIntervention
        fields = ['id', 'intervention', 'contenu', 'conclusion', 'dateGénération', 'estValidé']
        read_only_fields = ['id', 'dateGénération']


class InterventionSerializer(serializers.ModelSerializer):
    technicien_nom = serializers.ReadOnlyField(source='technicien.nom')
    client_nom = serializers.ReadOnlyField(source='client.nom')
    capteur_nom = serializers.ReadOnlyField(source='capteur.nom')
    rapport = RapportInterventionSerializer(read_only=True)
    # Optionnel en création : perform_create l'injecte pour le technicien connecté.
    # Un admin doit le fournir explicitement ; un technicien ne peut pas le modifier.
    technicien = serializers.PrimaryKeyRelatedField(
        queryset=Technicien.objects.all(),
        required=False, allow_null=False
    )

    class Meta:
        model = Intervention
        fields = ['id', 'technicien', 'technicien_nom', 'client', 'client_nom', 'dispositif',
                  'capteur', 'capteur_nom', 'typeIntervention', 'description', 'dateIntervention',
                  'statut', 'résultat', 'rapport']
        read_only_fields = ['id', 'rapport']


class MesureEnergieSerializer(serializers.ModelSerializer):
    capteur_nom = serializers.ReadOnlyField(source='capteur.nom')

    class Meta:
        model = MesureEnergie
        fields = ['id', 'capteur', 'capteur_nom', 'puissance', 'courant', 'energie', 'tension_V', 'facteur_puissance', 'timestamp']
        read_only_fields = ['id']
