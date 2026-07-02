from rest_framework import serializers
from .models import RegleDetection, Alerte

class RegleDetectionSerializer(serializers.ModelSerializer):
    capteur_nom = serializers.ReadOnlyField(source='capteur.nom')

    class Meta:
        model = RegleDetection
        fields = ['id', 'capteur', 'capteur_nom', 'puissanceMax_W', 'surveilleNuit', 'heureDébutNuit', 'heureFinNuit']
        read_only_fields = ['id']

    def validate_capteur(self, value):
        """Empêche de créer/modifier une règle sur le capteur d'un autre client (IDOR)."""
        request = self.context.get('request')
        if request and hasattr(request.user, 'client') and value.client_id != request.user.client.id:
            raise serializers.ValidationError("Ce capteur ne vous appartient pas.")
        return value

class AlerteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alerte
        fields = ['id', 'type', 'message', 'lue', 'createdAt', 'emailEnvoyé', 'sévérité']
        read_only_fields = ['id', 'createdAt', 'emailEnvoyé']
