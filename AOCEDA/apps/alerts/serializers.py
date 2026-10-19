from rest_framework import serializers
from .models import RegleDetection, Alerte

MAX_REGLES = 30

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
        # 5 W : assez bas pour surveiller une lampe ou un chargeur. 100 000 W : valeur UNIQUE envoyée par la page quand
        # l'alerte de puissance est désactivée (avant le 19/10/2026, 50 000 W était accepté sans rien surveiller).
        if value != 100000 and (value < 5 or value > 5000):
            raise serializers.ValidationError("Le seuil de puissance doit être compris entre 5 W et 5 000 W.")
        return value

    def validate(self, data):
        inst = self.instance
        puissance = data.get('puissanceMax_W', inst.puissanceMax_W if inst else None)
        nuit = data.get('surveilleNuit', inst.surveilleNuit if inst else False)
        debut = data.get('heureDébutNuit', inst.heureDébutNuit if inst else None)
        fin = data.get('heureFinNuit', inst.heureFinNuit if inst else None)
        if puissance is not None and puissance >= 100000 and not nuit:
            raise serializers.ValidationError(
                "Activez au moins une surveillance : le seuil de puissance ou la surveillance nocturne.")
        if nuit and debut is not None and fin is not None and debut == fin:
            raise serializers.ValidationError("La plage nocturne doit commencer et finir à deux heures différentes.")
        request = self.context.get('request')
        if (not inst and request and hasattr(request.user, 'client')
                and RegleDetection.objects.filter(client=request.user.client).count() >= MAX_REGLES):
            raise serializers.ValidationError(f"Limite de {MAX_REGLES} configurations atteinte : supprimez-en une.")
        return data

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
    # Règle à l'origine (None : crédit, tranche, ancienne alerte) : permet « Modifier la règle » depuis l'alerte
    regle_id = serializers.PrimaryKeyRelatedField(source='regle', read_only=True)
    regle_nom = serializers.SerializerMethodField()
    capteur_id = serializers.SerializerMethodField()
    intervention_id = serializers.PrimaryKeyRelatedField(source='intervention', read_only=True)

    class Meta:
        model = Alerte
        fields = ['id', 'type', 'type_display', 'message', 'lue', 'createdAt', 'emailEnvoyé', 'sévérité', 'capteur_nom',
                  'capteur_id', 'regle_id', 'regle_nom', 'intervention_id']
        read_only_fields = ['id', 'createdAt', 'emailEnvoyé']

    def get_capteur_nom(self, obj):
        if obj.mesure and obj.mesure.capteur:
            return obj.mesure.capteur.nom
        return None

    def get_capteur_id(self, obj):
        return str(obj.mesure.capteur_id) if obj.mesure and obj.mesure.capteur_id else None

    def get_regle_nom(self, obj):
        return obj.regle.nom if obj.regle_id else None
