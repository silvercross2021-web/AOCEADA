from rest_framework import serializers
from .models import Prevision

class PrevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prevision
        fields = ['id', 'moisConcerné', 'annee_mois', 'consomméeEstimée_kWh', 'montantEstimé_FCFA', 'écartSurMoisPrécédent']
        read_only_fields = ['id']
