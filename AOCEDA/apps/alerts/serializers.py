from rest_framework import serializers
from .models import RegleDetection, Alerte

class RegleDetectionSerializer(serializers.ModelSerializer):
    capteur_nom = serializers.ReadOnlyField(source='capteur.nom')

    class Meta:
        model = RegleDetection
        fields = ['id', 'nom', 'capteur', 'capteur_nom', 'puissanceMax_W', 'surveilleNuit', 'heureDébutNuit',
                  'heureFinNuit', 'seuilNuit_W', 'seuilNuitEffectif_W']
        read_only_fields = ['id']

    # Seuil de nuit réellement appliqué (celui du client, sinon l'automatique)
    seuilNuitEffectif_W = serializers.SerializerMethodField()

    def get_seuilNuitEffectif_W(self, obj):
        from .utils import seuil_nuit
        return float(seuil_nuit(obj))

    def validate_puissanceMax_W(self, value):
        # 5 W : assez bas pour surveiller une lampe ou un chargeur. 100 000 W : valeur
        # envoyée par la page quand l'alerte de puissance est désactivée.
        if value < 5 or value > 100000:
            raise serializers.ValidationError("Le seuil de puissance doit être compris entre 5 W et 5 000 W.")
        return value

    def validate_seuilNuit_W(self, value):
        if value is not None and (value < 1 or value > 100000):
            raise serializers.ValidationError("Le seuil de nuit doit être d'au moins 1 W.")
        return value

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
