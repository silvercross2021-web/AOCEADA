from rest_framework import serializers
from .models import RegleDetection, Alerte

class RegleDetectionSerializer(serializers.ModelSerializer):
    capteur_nom = serializers.ReadOnlyField(source='capteur.nom')

    class Meta:
        model = RegleDetection
        fields = ['id', 'nom', 'capteur', 'capteur_nom', 'puissanceMax_W', 'surveilleNuit', 'heureDébutNuit', 'heureFinNuit']
        read_only_fields = ['id']

    def validate_capteur(self, value):
        """Empêche de créer/modifier une règle sur le capteur d'un autre client (IDOR)."""
        request = self.context.get('request')
        if request and hasattr(request.user, 'client') and value.client_id != request.user.client.id:
            raise serializers.ValidationError("Ce capteur ne vous appartient pas.")
        return value

class AlerteSerializer(serializers.ModelSerializer):
    # Libellé humain du type (« Dépassement de seuil » au lieu de DEPASSEMENT_SEUIL)
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    # Capteur à l'origine de l'alerte (via la mesure déclencheuse), null si l'alerte
    # n'est pas liée à un capteur (ex. crédit bas, qui concerne le compte).
    capteur_nom = serializers.SerializerMethodField()

    class Meta:
        model = Alerte
        fields = ['id', 'type', 'type_display', 'message', 'lue', 'createdAt', 'emailEnvoyé', 'sévérité', 'capteur_nom']
        read_only_fields = ['id', 'createdAt', 'emailEnvoyé']

    def get_capteur_nom(self, obj):
        if obj.mesure and obj.mesure.capteur:
            return obj.mesure.capteur.nom
        return None
